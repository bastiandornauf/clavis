"""Semantic and hybrid search over section embeddings."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass

import numpy as np
from django.db.models import Count, Max
from django.utils.html import escape

from apps.library.models import Book, Section
from apps.search.embeddings import active_model_name, get_embedder
from apps.search.models import SectionEmbedding
from apps.search.services import SearchHit, ensure_fts_schema, search_sections
from apps.sources.models import SourceSnapshot

_SAFE_TOKEN = re.compile(r"[^\w]+", re.UNICODE)


@dataclass(frozen=True)
class _VectorIndex:
    key: tuple
    section_ids: np.ndarray
    book_ids: np.ndarray
    matrix: np.ndarray


_index_lock = threading.Lock()
_index: _VectorIndex | None = None


def _load_index(snapshot: SourceSnapshot, model_name: str, dimensions: int) -> _VectorIndex:
    """All vectors of one model/snapshot as a matrix, cached until rows change."""
    global _index
    rows = SectionEmbedding.objects.filter(
        book__snapshot=snapshot, model_name=model_name, dimensions=dimensions
    )
    stats = rows.aggregate(count=Count("pk"), latest=Max("updated_at"))
    key = (snapshot.pk, model_name, dimensions, stats["count"], stats["latest"])
    with _index_lock:
        if _index is not None and _index.key == key:
            return _index
        section_ids: list[int] = []
        book_ids: list[int] = []
        buffers: list[bytes] = []
        for section_id, book_id, vector in rows.values_list(
            "section_id", "book_id", "vector"
        ).iterator(chunk_size=2000):
            section_ids.append(section_id)
            book_ids.append(book_id)
            buffers.append(bytes(vector))
        if buffers:
            matrix = np.frombuffer(b"".join(buffers), dtype=np.float32).reshape(
                len(buffers), dimensions
            )
        else:
            matrix = np.zeros((0, dimensions), dtype=np.float32)
        _index = _VectorIndex(
            key=key,
            section_ids=np.asarray(section_ids, dtype=np.int64),
            book_ids=np.asarray(book_ids, dtype=np.int64),
            matrix=matrix,
        )
        return _index


def search_sections_semantic(
    query: str,
    *,
    edition: str = "",
    book_slug: str = "",
    review_status: str = "",
    limit: int = 50,
) -> list[SearchHit]:
    query = query.strip()
    if not query:
        return []

    current = SourceSnapshot.current()
    if not current:
        return []

    books = Book.objects.filter(snapshot=current)
    if edition:
        books = books.filter(edition=edition)
    if review_status:
        books = books.filter(review_status=review_status)
    if book_slug:
        books = books.filter(slug=book_slug)
    book_ids = list(books.values_list("id", flat=True))
    if not book_ids:
        return []

    embedder = get_embedder()
    index = _load_index(current, embedder.model_name, embedder.dimensions)
    if not len(index.section_ids):
        return []
    query_vec = np.frombuffer(embedder.embed_query(query), dtype=np.float32)

    mask = np.isin(index.book_ids, np.asarray(book_ids, dtype=np.int64))
    candidates = np.flatnonzero(mask)
    if not len(candidates):
        return []
    scores = index.matrix[candidates] @ query_vec
    take = min(limit, len(candidates))
    top = np.argpartition(-scores, take - 1)[:take]
    top = top[np.argsort(-scores[top])]
    ranked = [
        (int(index.section_ids[candidates[i]]), float(scores[i]))
        for i in top
        if scores[i] > 0
    ]
    if not ranked:
        return []

    sections = {
        section.id: section
        for section in Section.objects.filter(id__in=[sid for sid, _ in ranked]).select_related(
            "book", "book__snapshot", "parent"
        )
    }
    hits: list[SearchHit] = []
    for section_id, score in ranked:
        section = sections.get(section_id)
        if section is None:
            continue
        hits.append(
            SearchHit(
                section=section,
                snippet=_semantic_snippet(section, query),
                rank=-score,  # keep "lower is better" consistent with FTS rank
            )
        )
    return hits


RELATED_MIN_BODY_CHARS = 200
_RELATED_SKIP_TITLE_RE = re.compile(
    r"^(?:table of )?contents$|^index$|^credits$|^front matter$|^list of (?:inserts|tables)$",
    re.I,
)


def related_sections(section: Section, *, limit: int = 5) -> list[tuple[Section, float]]:
    """Passages elsewhere that read like this one, from the stored vector only.

    Skips the section's own ancestors and descendants (already on the page or one
    click away) and near-empty heading stubs.
    """
    current = SourceSnapshot.current()
    if not current:
        return []
    own = (
        SectionEmbedding.objects.filter(section=section, model_name=active_model_name())
        .only("vector", "dimensions", "model_name")
        .first()
    )
    if own is None:
        return []
    index = _load_index(current, own.model_name, own.dimensions)
    if len(index.section_ids) < 2:
        return []
    query_vec = np.frombuffer(bytes(own.vector), dtype=np.float32)
    scores = index.matrix @ query_vec
    take = min(len(scores), limit * 6 + 1)
    top = np.argpartition(-scores, take - 1)[:take]
    top = top[np.argsort(-scores[top])]
    candidates = [
        (int(index.section_ids[i]), float(scores[i]))
        for i in top
        if int(index.section_ids[i]) != section.id
    ]
    by_id = {
        s.id: s
        for s in Section.objects.filter(id__in=[sid for sid, _ in candidates]).select_related(
            "book"
        )
    }
    results: list[tuple[Section, float]] = []
    for section_id, score in candidates:
        other = by_id.get(section_id)
        if other is None or len(other.body_markdown or "") < RELATED_MIN_BODY_CHARS:
            continue
        if _RELATED_SKIP_TITLE_RE.match(other.display_title.strip()):
            continue
        if other.book_id == section.book_id and (
            other.path.startswith(f"{section.path}/") or section.path.startswith(f"{other.path}/")
        ):
            continue
        results.append((other, score))
        if len(results) >= limit:
            break
    return results


def search_sections_hybrid(
    query: str,
    *,
    edition: str = "",
    book_slug: str = "",
    review_status: str = "",
    limit: int = 50,
    fts_weight: float = 0.55,
    semantic_weight: float = 0.45,
) -> list[SearchHit]:
    ensure_fts_schema()
    fts_hits = search_sections(
        query,
        edition=edition,
        book_slug=book_slug,
        review_status=review_status,
        limit=limit * 2,
    )
    sem_hits = search_sections_semantic(
        query,
        edition=edition,
        book_slug=book_slug,
        review_status=review_status,
        limit=limit * 2,
    )

    fts_by_id = {hit.section.id: hit for hit in fts_hits}
    sem_by_id = {hit.section.id: hit for hit in sem_hits}
    fts_norm = _minmax({sid: -hit.rank for sid, hit in fts_by_id.items()})
    sem_norm = _minmax({sid: -hit.rank for sid, hit in sem_by_id.items()})

    combined_ids = set(fts_by_id) | set(sem_by_id)
    ranked: list[tuple[int, float, SearchHit]] = []
    for sid in combined_ids:
        score = fts_weight * fts_norm.get(sid, 0.0) + semantic_weight * sem_norm.get(sid, 0.0)
        base = fts_by_id.get(sid) or sem_by_id[sid]
        snippet = base.snippet
        if sid in fts_by_id and fts_by_id[sid].snippet:
            snippet = fts_by_id[sid].snippet
        ranked.append(
            (
                sid,
                score,
                SearchHit(section=base.section, snippet=snippet, rank=-score),
            )
        )
    ranked.sort(key=lambda item: item[1], reverse=True)
    return [hit for _, _, hit in ranked[:limit]]


def _minmax(scores: dict[int, float]) -> dict[int, float]:
    if not scores:
        return {}
    values = list(scores.values())
    low, high = min(values), max(values)
    if high <= low:
        return {key: 1.0 for key in scores}
    span = high - low
    return {key: (value - low) / span for key, value in scores.items()}


def _semantic_snippet(section: Section, query: str) -> str:
    """Plain-text excerpt; escaped because the template renders snippets as HTML."""
    body = (section.body_markdown or "").strip()
    if not body:
        return ""
    tokens = [t for t in _SAFE_TOKEN.split(query.lower()) if len(t) > 2]
    lower = body.lower()
    for token in tokens:
        idx = lower.find(token)
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(body), idx + len(token) + 120)
            snippet = body[start:end].replace("\n", " ")
            prefix = "…" if start else ""
            suffix = "…" if end < len(body) else ""
            return escape(f"{prefix}{snippet}{suffix}")
    return escape(body[:180].replace("\n", " ") + ("…" if len(body) > 180 else ""))
