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
from django.db import transaction

from apps.library.models import Section
from apps.search.models import SectionChunkEmbedding, SectionEmbedding
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
# Long sections: the tail past the section vector is split into overlapping
# chunks (raw-body offsets; markup makes raw text longer than the cleaned window).
CHUNK_FIRST_START = 1800
CHUNK_CHARS = 1500
CHUNK_STEP = 1300
CHUNK_MIN_CHARS = 200


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
    return SectionEmbedding.objects.filter(model_name=model_name, book__snapshot=current).exists()


def index_status() -> dict[str, object]:
    """How much of the current snapshot the active model has embedded."""
    current = SourceSnapshot.current()
    model_name = active_model_name()
    if not current:
        return {
            "model_name": model_name,
            "vectors": 0,
            "sections": 0,
            "chunks": 0,
            "complete": False,
        }
    sections = Section.objects.filter(book__snapshot=current).count()
    vectors = SectionEmbedding.objects.filter(model_name=model_name, book__snapshot=current).count()
    chunks = SectionChunkEmbedding.objects.filter(
        model_name=model_name, book__snapshot=current
    ).count()
    return {
        "model_name": model_name.removeprefix("local:"),
        "vectors": vectors,
        "sections": sections,
        "chunks": chunks,
        "complete": bool(sections) and vectors >= sections,
        "available": semantic_search_available(),
    }


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


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", _MARKUP_RE.sub(" ", text)).strip()


def section_embed_text(section: Section) -> str:
    return f"{section.display_title}\n{_plain(section.body_markdown or '')[:EMBED_TEXT_CHARS]}"


def section_chunks(section: Section) -> list[tuple[int, int, str]]:
    """``(start, end, embed_text)`` for the tail of a long section, else empty.

    Chunk edges snap to whitespace so words are not cut; the title is prefixed so
    each chunk keeps its context.
    """
    body = section.body_markdown or ""
    chunks: list[tuple[int, int, str]] = []
    start = CHUNK_FIRST_START
    while len(body) - start >= CHUNK_MIN_CHARS:
        if start and not body[start - 1].isspace():
            space = body.find(" ", start, start + 80)
            start = space + 1 if space >= 0 else start
        end = min(len(body), start + CHUNK_CHARS)
        if end < len(body):
            space = body.rfind(" ", end - 80, end)
            end = space if space > start else end
        text = _plain(body[start:end])
        if text:
            chunks.append((start, end, f"{section.display_title}\n{text}"))
        if end >= len(body):
            break
        start += CHUNK_STEP
    return chunks


def rebuild_embeddings_for_books(
    book_ids: list[int],
    *,
    embedder: Embedder | None = None,
    progress: Callable[[int, int], None] | None = None,
    chunk_progress: Callable[[int, int], None] | None = None,
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
    rebuild_chunk_embeddings_for_books(book_ids, embedder=embedder, progress=chunk_progress)
    return len(pending)


def rebuild_chunk_embeddings_for_books(
    book_ids: list[int],
    *,
    embedder: Embedder | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """Embed the tails of long sections; same reuse/resume rules as section vectors.

    Returns the number of chunks embedded (reused chunks are copied, not counted).
    """
    if not book_ids:
        return 0
    embedder = embedder or get_embedder()
    model = embedder.model_name
    sections = list(
        Section.objects.filter(book_id__in=book_ids).only(
            "id", "book_id", "title", "body_markdown", "content_hash"
        )
    )
    stored: dict[int, tuple[str, int]] = {}
    for section_id, content_hash, dimensions in SectionChunkEmbedding.objects.filter(
        book_id__in=book_ids, model_name=model
    ).values_list("section_id", "content_hash", "dimensions"):
        stored[section_id] = (content_hash, dimensions)

    def is_long(section: Section) -> bool:
        return len(section.body_markdown or "") - CHUNK_FIRST_START >= CHUNK_MIN_CHARS

    stale = {
        s.id
        for s in sections
        if s.id in stored
        and (not is_long(s) or stored[s.id] != (s.content_hash, embedder.dimensions))
    }
    SectionChunkEmbedding.objects.filter(section_id__in=stale, model_name=model).delete()
    pending = [s for s in sections if is_long(s) and (s.id not in stored or s.id in stale)]

    reusable: dict[str, list[SectionChunkEmbedding]] = {}
    hashes = {s.content_hash for s in pending}
    if hashes:
        for row in SectionChunkEmbedding.objects.filter(
            model_name=model, dimensions=embedder.dimensions, content_hash__in=hashes
        ).order_by("section_id", "chunk_index"):
            group = reusable.setdefault(row.content_hash, [])
            if not group or group[0].section_id == row.section_id:
                group.append(row)

    def save(section: Section, rows: list[tuple[int, int, bytes]]) -> list[SectionChunkEmbedding]:
        return [
            SectionChunkEmbedding(
                section_id=section.id,
                book_id=section.book_id,
                model_name=model,
                content_hash=section.content_hash,
                chunk_index=index,
                start=start,
                end=end,
                vector=vector,
                dimensions=embedder.dimensions,
            )
            for index, (start, end, vector) in enumerate(rows)
        ]

    copies: list[SectionChunkEmbedding] = []
    to_embed: list[Section] = []
    for section in pending:
        group = reusable.get(section.content_hash)
        if group:
            copies.extend(save(section, [(r.start, r.end, bytes(r.vector)) for r in group]))
        else:
            to_embed.append(section)
    SectionChunkEmbedding.objects.bulk_create(copies, batch_size=1000)

    work = [(section, section_chunks(section)) for section in to_embed]
    total = sum(len(chunks) for _, chunks in work)
    done = 0
    batch: list[tuple[Section, list[tuple[int, int, str]]]] = []
    batch_size = 0

    # Saved per group of whole sections so an interrupted run resumes cleanly.
    def flush() -> None:
        nonlocal done, batch, batch_size
        if not batch:
            return
        texts = [text for _, chunks in batch for _, _, text in chunks]
        vectors = iter(embedder.embed_documents(texts))
        rows: list[SectionChunkEmbedding] = []
        for section, chunks in batch:
            rows.extend(save(section, [(start, end, next(vectors)) for start, end, _ in chunks]))
        with transaction.atomic():
            SectionChunkEmbedding.objects.bulk_create(rows, batch_size=1000)
        done += batch_size
        batch, batch_size = [], 0
        if progress:
            progress(done, total)

    for section, chunks in work:
        if not chunks:
            continue
        batch.append((section, chunks))
        batch_size += len(chunks)
        if batch_size >= EMBED_BATCH_SIZE * 4:
            flush()
    flush()

    SectionChunkEmbedding.objects.filter(book_id__in=book_ids).exclude(model_name=model).delete()
    logger.info("Chunk embeddings %s: %s embedded, %s reused", model, total, len(copies))
    return total
