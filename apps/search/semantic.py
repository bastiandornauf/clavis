"""Semantic and hybrid search over section embeddings."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
from django.db.models import Count, Max
from django.utils.html import escape

from apps.library.models import Book, Section
from apps.search.embeddings import active_model_name, get_embedder
from apps.search.models import SectionChunkEmbedding, SectionEmbedding
from apps.search.services import SearchHit, ensure_fts_schema, search_sections
from apps.sources.models import SourceSnapshot

_SAFE_TOKEN = re.compile(r"[^\w]+", re.UNICODE)


@dataclass(frozen=True)
class _VectorIndex:
    key: tuple
    section_ids: np.ndarray
    book_ids: np.ndarray
    matrix: np.ndarray
    positions: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class _ChunkIndex:
    key: tuple
    section_ids: np.ndarray
    book_ids: np.ndarray
    starts: np.ndarray
    ends: np.ndarray
    matrix: np.ndarray


_index_lock = threading.Lock()
_index: _VectorIndex | None = None
_chunk_index: _ChunkIndex | None = None


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
            positions={sid: i for i, sid in enumerate(section_ids)},
        )
        return _index


def _load_chunk_index(
    snapshot: SourceSnapshot, model_name: str, dimensions: int
) -> _ChunkIndex:
    """Long-section tail chunks as a matrix, cached like the section index."""
    global _chunk_index
    rows = SectionChunkEmbedding.objects.filter(
        book__snapshot=snapshot, model_name=model_name, dimensions=dimensions
    )
    stats = rows.aggregate(count=Count("pk"), latest=Max("updated_at"))
    key = (snapshot.pk, model_name, dimensions, stats["count"], stats["latest"])
    with _index_lock:
        if _chunk_index is not None and _chunk_index.key == key:
            return _chunk_index
        section_ids: list[int] = []
        book_ids: list[int] = []
        starts: list[int] = []
        ends: list[int] = []
        buffers: list[bytes] = []
        for section_id, book_id, start, end, vector in rows.values_list(
            "section_id", "book_id", "start", "end", "vector"
        ).iterator(chunk_size=2000):
            section_ids.append(section_id)
            book_ids.append(book_id)
            starts.append(start)
            ends.append(end)
            buffers.append(bytes(vector))
        matrix = (
            np.frombuffer(b"".join(buffers), dtype=np.float32).reshape(len(buffers), dimensions)
            if buffers
            else np.zeros((0, dimensions), dtype=np.float32)
        )
        _chunk_index = _ChunkIndex(
            key=key,
            section_ids=np.asarray(section_ids, dtype=np.int64),
            book_ids=np.asarray(book_ids, dtype=np.int64),
            starts=np.asarray(starts, dtype=np.int64),
            ends=np.asarray(ends, dtype=np.int64),
            matrix=matrix,
        )
        return _chunk_index


def _top(scores: np.ndarray, limit: int) -> np.ndarray:
    take = min(limit, len(scores))
    if not take:
        return np.zeros(0, dtype=np.int64)
    top = np.argpartition(-scores, take - 1)[:take]
    return top[np.argsort(-scores[top])]


def active_index() -> _VectorIndex | None:
    """Vector index of the active model for the current snapshot, if built."""
    current = SourceSnapshot.current()
    if not current:
        return None
    model_name = active_model_name()
    dimensions = (
        SectionEmbedding.objects.filter(model_name=model_name, book__snapshot=current)
        .values_list("dimensions", flat=True)
        .first()
    )
    if dimensions is None:
        return None
    return _load_index(current, model_name, dimensions)


def query_vector(text: str) -> np.ndarray:
    """Embed free text with the active model (loads it on first use)."""
    return np.frombuffer(get_embedder().embed_query(text), dtype=np.float32)


def rank_sections(
    index: _VectorIndex,
    vector: np.ndarray,
    *,
    section_ids: Iterable[int] | None = None,
    exclude: Iterable[int] = (),
    limit: int = 50,
) -> list[tuple[int, float]]:
    """Section ids closest to ``vector``, optionally restricted to ``section_ids``."""
    if section_ids is None:
        rows = np.arange(len(index.section_ids))
    else:
        rows = np.fromiter(
            (index.positions[sid] for sid in section_ids if sid in index.positions),
            dtype=np.int64,
        )
    skip = {index.positions[sid] for sid in exclude if sid in index.positions}
    if skip:
        rows = rows[~np.isin(rows, list(skip))]
    if not len(rows):
        return []
    scores = index.matrix[rows] @ vector
    take = min(limit, len(rows))
    top = np.argpartition(-scores, take - 1)[:take]
    top = top[np.argsort(-scores[top])]
    return [(int(index.section_ids[rows[i]]), float(scores[i])) for i in top]


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

    book_filter = np.asarray(book_ids, dtype=np.int64)
    # Section score = best of its head vector and any tail chunk; the winning
    # chunk's span drives the snippet.
    best: dict[int, tuple[float, tuple[int, int] | None]] = {}
    candidates = np.flatnonzero(np.isin(index.book_ids, book_filter))
    if len(candidates):
        scores = index.matrix[candidates] @ query_vec
        for i in _top(scores, limit):
            best[int(index.section_ids[candidates[i]])] = (float(scores[i]), None)

    chunks = _load_chunk_index(current, embedder.model_name, embedder.dimensions)
    chunk_rows = np.flatnonzero(np.isin(chunks.book_ids, book_filter))
    if len(chunk_rows):
        chunk_scores = chunks.matrix[chunk_rows] @ query_vec
        for i in _top(chunk_scores, limit * 3):
            row = chunk_rows[i]
            sid = int(chunks.section_ids[row])
            score = float(chunk_scores[i])
            if sid not in best or score > best[sid][0]:
                best[sid] = (score, (int(chunks.starts[row]), int(chunks.ends[row])))

    ranked = sorted(
        ((sid, score, span) for sid, (score, span) in best.items() if score > 0),
        key=lambda item: item[1],
        reverse=True,
    )[:limit]
    if not ranked:
        return []

    sections = {
        section.id: section
        for section in Section.objects.filter(
            id__in=[sid for sid, _, _ in ranked]
        ).select_related("book", "book__snapshot", "parent")
    }
    hits: list[SearchHit] = []
    for section_id, score, span in ranked:
        section = sections.get(section_id)
        if section is None:
            continue
        hits.append(
            SearchHit(
                section=section,
                snippet=_semantic_snippet(section, query, span=span),
                rank=-score,  # keep "lower is better" consistent with FTS rank
            )
        )
    return hits


RELATED_MIN_BODY_CHARS = 200
_RELATED_SKIP_TITLE_RE = re.compile(
    r"^(?:table of )?contents$|^index$|^credits$|^front matter$|^list of (?:inserts|tables)$",
    re.I,
)


# Near-identical text in another book: reprints across editions/supplements.
REPRINT_MIN_BODY_CHARS = 150
REPRINT_SCORE_SAME_TITLE = 0.95
REPRINT_SCORE_ANY_TITLE = 0.97


@dataclass
class RelatedPassages:
    reprints: list[Section] = field(default_factory=list)
    similar: list[Section] = field(default_factory=list)


def is_reprint(section: Section, other: Section, score: float) -> bool:
    if other.book_id == section.book_id:
        return False
    if min(len(section.body_markdown or ""), len(other.body_markdown or "")) < (
        REPRINT_MIN_BODY_CHARS
    ):
        return False
    if score >= REPRINT_SCORE_ANY_TITLE:
        return True
    same_title = section.display_title.casefold() == other.display_title.casefold()
    return same_title and score >= REPRINT_SCORE_SAME_TITLE


def is_listable(other: Section) -> bool:
    """Worth showing as a passage: not a heading stub, TOC, or credits page."""
    if len(other.body_markdown or "") < RELATED_MIN_BODY_CHARS:
        return False
    return not _RELATED_SKIP_TITLE_RE.match(other.display_title.strip())


def related_sections(section: Section, *, limit: int = 5) -> RelatedPassages:
    """Reprints and similar passages elsewhere, from the stored vector only.

    Skips the section's own ancestors and descendants (already on the page or one
    click away) and near-empty heading stubs.
    """
    index = active_index()
    if index is None or section.id not in index.positions:
        return RelatedPassages()
    vector = index.matrix[index.positions[section.id]]
    candidates = rank_sections(index, vector, exclude=[section.id], limit=limit * 6)
    by_id = {
        s.id: s
        for s in Section.objects.filter(id__in=[sid for sid, _ in candidates]).select_related(
            "book"
        )
    }
    related = RelatedPassages()
    for section_id, score in candidates:
        other = by_id.get(section_id)
        if other is None:
            continue
        if other.book_id == section.book_id and (
            other.path.startswith(f"{section.path}/") or section.path.startswith(f"{other.path}/")
        ):
            continue
        if is_reprint(section, other, score):
            related.reprints.append(other)
        elif is_listable(other) and len(related.similar) < limit:
            related.similar.append(other)
    return related


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


def _semantic_snippet(
    section: Section, query: str, *, span: tuple[int, int] | None = None
) -> str:
    """Plain-text excerpt; escaped because the template renders snippets as HTML.

    ``span`` limits the excerpt to the matching chunk of a long section.
    """
    body = section.body_markdown or ""
    if span:
        body = "…" + body[span[0] : span[1]]
    body = body.strip()
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
