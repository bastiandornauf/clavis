"""ClavisGen reads the Lexicon; it does not extract or copy book text."""

from __future__ import annotations

from django.db.models import Count

from apps.catalog.models import CatalogEntry
from apps.chargen.core_tables import CORE_BOOK_SLUG
from apps.library.models import Book
from apps.sources.models import SourceSnapshot


def core_book() -> Book | None:
    current = SourceSnapshot.current()
    if current is None:
        return None
    return Book.objects.filter(snapshot=current, slug=CORE_BOOK_SLUG).first()


def core_entries(entry_type: str):
    book = core_book()
    if book is None:
        return CatalogEntry.objects.none()
    return CatalogEntry.objects.filter(
        book=book,
        kind=CatalogEntry.Kind.DEFINITION,
        entry_type=entry_type,
    ).order_by("name")


def core_catalog_counts() -> dict[str, int]:
    book = core_book()
    if book is None:
        return {}
    rows = (
        CatalogEntry.objects.filter(book=book, kind=CatalogEntry.Kind.DEFINITION)
        .values("entry_type")
        .annotate(total=Count("id"))
    )
    return {row["entry_type"]: row["total"] for row in rows}
