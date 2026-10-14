"""SQLite FTS5 index over library sections."""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db import connection

from apps.library.models import Book, Section
from apps.sources.models import SourceSnapshot

FTS_TABLE = "section_fts"

_SAFE_TOKEN = re.compile(r"[^\w]+", re.UNICODE)


@dataclass
class SearchHit:
    section: Section
    snippet: str
    rank: float


def ensure_fts_schema() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE}
            USING fts5(
                section_id UNINDEXED,
                book_id UNINDEXED,
                title,
                body,
                tokenize = 'porter unicode61'
            )
            """
        )


def rebuild_fts_for_books(book_ids: list[int]) -> None:
    if not book_ids:
        return
    ensure_fts_schema()
    with connection.cursor() as cursor:
        placeholders = ",".join(["%s"] * len(book_ids))
        cursor.execute(
            f"DELETE FROM {FTS_TABLE} WHERE book_id IN ({placeholders})",
            book_ids,
        )
        sections = Section.objects.filter(book_id__in=book_ids).only(
            "id", "book_id", "title", "body_markdown"
        )
        rows = [
            (
                section.id,
                section.book_id,
                section.display_title,
                section.body_markdown,
            )
            for section in sections.iterator()
        ]
        cursor.executemany(
            f"INSERT INTO {FTS_TABLE}(section_id, book_id, title, body) VALUES (%s, %s, %s, %s)",
            rows,
        )


def _fts_query(raw: str) -> str:
    tokens = [t for t in _SAFE_TOKEN.split(raw.strip()) if t]
    if not tokens:
        return ""
    # Prefix match on the last token helps partial typing; AND the rest.
    parts = [f'"{token}"' for token in tokens[:-1]]
    parts.append(f'"{tokens[-1]}"*')
    return " AND ".join(parts)


def sections_mentioning(
    phrase: str,
    *,
    exclude_stable_ids: set[str] = frozenset(),
    limit: int = 10,
) -> list[SearchHit]:
    """Sections whose text contains ``phrase`` as an exact word sequence."""
    ensure_fts_schema()
    tokens = [t for t in _SAFE_TOKEN.split(phrase.strip()) if t]
    current = SourceSnapshot.current()
    if not tokens or not current:
        return []
    fts_query = '"' + " ".join(tokens) + '"'
    sql = f"""
        SELECT f.section_id,
               snippet({FTS_TABLE}, 3, '<mark>', '</mark>', '…', 16) AS snip,
               f.rank
        FROM {FTS_TABLE} AS f
        JOIN {Book._meta.db_table} AS b ON b.id = f.book_id
        WHERE {FTS_TABLE} MATCH %s AND b.snapshot_id = %s
        ORDER BY f.rank
        LIMIT %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [fts_query, current.pk, limit + len(exclude_stable_ids) + 5])
        rows = cursor.fetchall()
    sections = {
        s.id: s
        for s in Section.objects.filter(id__in=[row[0] for row in rows]).select_related("book")
    }
    hits: list[SearchHit] = []
    for section_id, snippet, rank in rows:
        section = sections.get(section_id)
        if section is None or section.stable_id in exclude_stable_ids:
            continue
        hits.append(SearchHit(section=section, snippet=snippet or "", rank=float(rank)))
        if len(hits) >= limit:
            break
    return hits


def search_sections(
    query: str,
    *,
    edition: str = "",
    book_slug: str = "",
    review_status: str = "",
    limit: int = 50,
) -> list[SearchHit]:
    ensure_fts_schema()
    fts_query = _fts_query(query)
    if not fts_query:
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

    placeholders = ",".join(["%s"] * len(book_ids))
    sql = f"""
        SELECT section_id,
               snippet({FTS_TABLE}, 3, '<mark>', '</mark>', '…', 16) AS snip,
               rank
        FROM {FTS_TABLE}
        WHERE {FTS_TABLE} MATCH %s
          AND book_id IN ({placeholders})
        ORDER BY rank
        LIMIT %s
    """
    params: list[object] = [fts_query, *book_ids, limit]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    section_ids = [row[0] for row in rows]
    sections = {
        section.id: section
        for section in Section.objects.filter(id__in=section_ids).select_related(
            "book", "book__snapshot", "parent"
        )
    }
    hits: list[SearchHit] = []
    for section_id, snippet, rank in rows:
        section = sections.get(section_id)
        if section is None:
            continue
        hits.append(SearchHit(section=section, snippet=snippet or "", rank=float(rank)))
    return hits
