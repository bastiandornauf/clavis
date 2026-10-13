"""Local section embeddings (stdlib hashing backend; swappable later)."""

from __future__ import annotations

import hashlib
import math
import re
import struct
from typing import Protocol

from django.conf import settings

from apps.library.models import Section
from apps.search.models import SectionEmbedding

TOKEN_RE = re.compile(r"\w+", re.UNICODE)
HASHING_MODEL = "hashing-v1"
HASHING_DIM = 256


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed(self, text: str) -> bytes: ...


class HashingEmbedder:
    """Deterministic bag-of-tokens hashing projector (offline, no ML deps)."""

    model_name = HASHING_MODEL
    dimensions = HASHING_DIM

    def embed(self, text: str) -> bytes:
        vec = [0.0] * self.dimensions
        tokens = TOKEN_RE.findall(text.lower())
        if not tokens:
            return struct.pack(f"{self.dimensions}f", *vec)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vec = [v / norm for v in vec]
        return struct.pack(f"{self.dimensions}f", *vec)


def get_embedder(name: str | None = None) -> Embedder:
    backend = (name or getattr(settings, "CLAVIS_EMBEDDINGS_BACKEND", HASHING_MODEL)).strip()
    if backend in {HASHING_MODEL, "hashing", "default"}:
        return HashingEmbedder()
    if backend in {"none", "off", "disabled"}:
        raise ValueError("Embeddings backend is disabled")
    raise ValueError(f"Unknown embeddings backend: {backend}")


def unpack_vector(blob: bytes, dimensions: int) -> list[float]:
    expected = dimensions * 4
    if len(blob) != expected:
        raise ValueError("Embedding blob size mismatch")
    return list(struct.unpack(f"{dimensions}f", blob))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))


def section_embed_text(section: Section) -> str:
    return f"{section.display_title}\n{section.body_markdown or ''}"


def rebuild_embeddings_for_books(
    book_ids: list[int],
    *,
    embedder: Embedder | None = None,
) -> int:
    if not book_ids:
        return 0
    embedder = embedder or get_embedder()
    updated = 0
    sections = Section.objects.filter(book_id__in=book_ids).only(
        "id",
        "book_id",
        "title",
        "body_markdown",
        "content_hash",
    )
    existing = {
        row.section_id: row
        for row in SectionEmbedding.objects.filter(
            book_id__in=book_ids, model_name=embedder.model_name
        )
    }
    for section in sections.iterator():
        current = existing.get(section.id)
        if (
            current
            and current.content_hash == section.content_hash
            and current.dimensions == embedder.dimensions
        ):
            continue
        vector = embedder.embed(section_embed_text(section))
        SectionEmbedding.objects.update_or_create(
            section_id=section.id,
            defaults={
                "book_id": section.book_id,
                "model_name": embedder.model_name,
                "content_hash": section.content_hash,
                "vector": vector,
                "dimensions": embedder.dimensions,
            },
        )
        updated += 1
    # Drop stale rows for these books / other models.
    SectionEmbedding.objects.filter(book_id__in=book_ids).exclude(
        model_name=embedder.model_name
    ).delete()
    return updated
