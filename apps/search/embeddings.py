"""Local section embeddings for semantic search.

Default backend is a small ONNX sentence-embedding model run via fastembed
(no PyTorch, no API key). The model is downloaded once into the data dir and
then works offline. ``hashing-v1`` remains as a dependency-free test backend.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import struct
from collections.abc import Callable, Iterable
from functools import lru_cache
from typing import Protocol

from django.conf import settings

from apps.library.models import Section
from apps.search.models import SectionEmbedding
from apps.sources.models import SourceSnapshot

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_MARKUP_RE = re.compile(r"[*_`>#|]+")
HASHING_MODEL = "hashing-v1"
HASHING_DIM = 256
DEFAULT_LOCAL_MODEL = "BAAI/bge-small-en-v1.5"
# The model reads at most ~512 tokens; longer text only costs time.
EMBED_TEXT_CHARS = 2000
EMBED_BATCH_SIZE = 64


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[bytes]: ...

    def embed_query(self, text: str) -> bytes: ...


class HashingEmbedder:
    """Deterministic bag-of-tokens hashing projector (tests / no ML deps)."""

    model_name = HASHING_MODEL
    dimensions = HASHING_DIM

    def _embed(self, text: str) -> bytes:
        vec = [0.0] * self.dimensions
        for token in TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dimensions
            vec[idx] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return struct.pack(f"{self.dimensions}f", *(v / norm for v in vec))

    def embed_documents(self, texts: list[str]) -> list[bytes]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> bytes:
        return self._embed(text)


class LocalModelEmbedder:
    """Sentence-embedding model run locally through fastembed (ONNX)."""

    def __init__(self, model_id: str) -> None:
        from fastembed import TextEmbedding

        cache_dir = settings.CLAVIS_DATA_DIR / "cache" / "models"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = TextEmbedding(model_id, cache_dir=str(cache_dir))
        self.model_name = f"local:{model_id}"[:64]
        self.dimensions = int(self._model.embedding_size)

    @staticmethod
    def _pack(vectors: Iterable) -> list[bytes]:
        import numpy as np

        packed: list[bytes] = []
        for vec in vectors:
            arr = np.asarray(vec, dtype=np.float32)
            norm = float(np.linalg.norm(arr)) or 1.0
            packed.append((arr / norm).astype(np.float32).tobytes())
        return packed

    def embed_documents(self, texts: list[str]) -> list[bytes]:
        return self._pack(self._model.passage_embed(texts, batch_size=EMBED_BATCH_SIZE))

    def embed_query(self, text: str) -> bytes:
        return self._pack(self._model.query_embed([text]))[0]


def _backend_name(name: str | None = None) -> str:
    return (name or getattr(settings, "CLAVIS_EMBEDDINGS_BACKEND", "local")).strip().lower()


def active_model_name(name: str | None = None) -> str:
    """Model name rows are stored under, without loading the model."""
    backend = _backend_name(name)
    if backend in {HASHING_MODEL, "hashing"}:
        return HASHING_MODEL
    model_id = getattr(settings, "CLAVIS_EMBEDDINGS_MODEL", DEFAULT_LOCAL_MODEL)
    return f"local:{model_id}"[:64]


@lru_cache(maxsize=4)
def _cached_local_embedder(model_id: str) -> LocalModelEmbedder:
    return LocalModelEmbedder(model_id)


def get_embedder(name: str | None = None) -> Embedder:
    backend = _backend_name(name)
    if backend in {HASHING_MODEL, "hashing"}:
        return HashingEmbedder()
    if backend in {"none", "off", "disabled"}:
        raise ValueError("Embeddings backend is disabled")
    if backend in {"local", "fastembed", "default"}:
        model_id = getattr(settings, "CLAVIS_EMBEDDINGS_MODEL", DEFAULT_LOCAL_MODEL)
        return _cached_local_embedder(model_id)
    raise ValueError(f"Unknown embeddings backend: {backend}")


def semantic_search_available() -> bool:
    """True when the active model has vectors for the current snapshot."""
    mode = str(getattr(settings, "CLAVIS_SEARCH_MODES_ENABLED", "auto")).strip().lower()
    if mode in {"0", "off", "false", "no"}:
        return False
    model_name = active_model_name()
    if mode not in {"1", "on", "true", "yes"} and model_name == HASHING_MODEL:
        return False
    current = SourceSnapshot.current()
    if not current:
        return False
    return SectionEmbedding.objects.filter(
        model_name=model_name, book__snapshot=current
    ).exists()


def refresh_embeddings_after_import(book_ids: list[int]) -> int:
    """Keep an existing meaning-search index in step with a new import.

    Failures are logged, never raised: keyword search must not depend on the model.
    """
    mode = str(getattr(settings, "CLAVIS_REBUILD_EMBEDDINGS_ON_IMPORT", "auto")).lower()
    if mode in {"0", "off", "false", "no"}:
        return 0
    if mode not in {"1", "on", "true", "yes"}:
        if not SectionEmbedding.objects.filter(model_name=active_model_name()).exists():
            return 0
    try:
        return rebuild_embeddings_for_books(book_ids)
    except Exception:
        logger.exception("Embedding refresh after import failed; keyword search unaffected")
        return 0


def section_embed_text(section: Section) -> str:
    body = _MARKUP_RE.sub(" ", section.body_markdown or "")
    body = re.sub(r"\s+", " ", body).strip()
    return f"{section.display_title}\n{body[:EMBED_TEXT_CHARS]}"


def rebuild_embeddings_for_books(
    book_ids: list[int],
    *,
    embedder: Embedder | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """Embed changed sections; reuse vectors whose content hash is unchanged.

    Reuse also covers re-imports: the previous snapshot's rows still exist while
    the new snapshot is being built, so unchanged sections are copied, not
    re-embedded.
    """
    if not book_ids:
        return 0
    embedder = embedder or get_embedder()
    sections = list(
        Section.objects.filter(book_id__in=book_ids).only(
            "id", "book_id", "title", "body_markdown", "content_hash"
        )
    )
    current = {
        row.section_id: row
        for row in SectionEmbedding.objects.filter(
            book_id__in=book_ids, model_name=embedder.model_name
        ).only("section_id", "content_hash", "dimensions")
    }
    pending = [
        s
        for s in sections
        if not (
            (row := current.get(s.id))
            and row.content_hash == s.content_hash
            and row.dimensions == embedder.dimensions
        )
    ]

    reusable: dict[str, bytes] = {}
    hashes = {s.content_hash for s in pending}
    if hashes:
        for row in (
            SectionEmbedding.objects.filter(
                model_name=embedder.model_name,
                dimensions=embedder.dimensions,
                content_hash__in=hashes,
            )
            .only("content_hash", "vector")
            .iterator()
        ):
            reusable.setdefault(row.content_hash, bytes(row.vector))

    def save(batch: list[Section], vectors: list[bytes]) -> None:
        SectionEmbedding.objects.filter(section_id__in=[s.id for s in batch]).delete()
        SectionEmbedding.objects.bulk_create(
            [
                SectionEmbedding(
                    section_id=s.id,
                    book_id=s.book_id,
                    model_name=embedder.model_name,
                    content_hash=s.content_hash,
                    vector=vector,
                    dimensions=embedder.dimensions,
                )
                for s, vector in zip(batch, vectors, strict=True)
            ]
        )

    reused = [s for s in pending if s.content_hash in reusable]
    for start in range(0, len(reused), 500):
        batch = reused[start : start + 500]
        save(batch, [reusable[s.content_hash] for s in batch])

    # Saved per batch so an interrupted run resumes where it stopped.
    to_embed = [s for s in pending if s.content_hash not in reusable]
    total = len(to_embed)
    for start in range(0, total, EMBED_BATCH_SIZE * 4):
        batch = to_embed[start : start + EMBED_BATCH_SIZE * 4]
        save(batch, embedder.embed_documents([section_embed_text(s) for s in batch]))
        if progress:
            progress(start + len(batch), total)

    SectionEmbedding.objects.filter(book_id__in=book_ids).exclude(
        model_name=embedder.model_name
    ).delete()
    logger.info(
        "Embeddings %s: %s embedded, %s reused, %s unchanged",
        embedder.model_name,
        total,
        len(pending) - total,
        len(sections) - len(pending),
    )
    return len(pending)
