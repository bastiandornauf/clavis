"""Semantic and hybrid search over section embeddings."""

from __future__ import annotations

import re

from apps.library.models import Book, Section
from apps.search.embeddings import (
    cosine_similarity,
    get_embedder,
    unpack_vector,
)
from apps.search.models import SectionEmbedding
from apps.search.services import SearchHit, ensure_fts_schema, search_sections
from apps.sources.models import SourceSnapshot

_SAFE_TOKEN = re.compile(r"[^\w]+", re.UNICODE)


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
    query_vec = unpack_vector(embedder.embed(query), embedder.dimensions)
    rows = SectionEmbedding.objects.filter(
        book_id__in=book_ids,
        model_name=embedder.model_name,
    ).only("section_id", "vector", "dimensions")

    scored: list[tuple[int, float]] = []
    for row in rows.iterator():
        try:
            vec = unpack_vector(bytes(row.vector), row.dimensions)
        except ValueError:
            continue
        score = cosine_similarity(query_vec, vec)
        if score <= 0:
            continue
        scored.append((row.section_id, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    top = scored[:limit]
    if not top:
        return []

    sections = {
        section.id: section
        for section in Section.objects.filter(id__in=[sid for sid, _ in top]).select_related(
            "book", "book__snapshot", "parent"
        )
    }
    hits: list[SearchHit] = []
    for section_id, score in top:
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
    body = (section.body_markdown or "").strip()
    if not body:
        return ""
    tokens = [t for t in _SAFE_TOKEN.split(query.lower()) if t]
    lower = body.lower()
    for token in tokens:
        idx = lower.find(token)
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(body), idx + len(token) + 80)
            snippet = body[start:end].replace("\n", " ")
            prefix = "…" if start else ""
            suffix = "…" if end < len(body) else ""
            return f"{prefix}{snippet}{suffix}"
    return body[:140].replace("\n", " ") + ("…" if len(body) > 140 else "")
