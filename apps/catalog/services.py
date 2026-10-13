"""Build and query the rule-based catalog."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count, QuerySet

from apps.catalog.extractors import extract_from_section
from apps.catalog.models import CatalogEntry
from apps.library.models import Book, Section
from apps.sources.models import SourceSnapshot


@transaction.atomic
def rebuild_catalog_for_books(book_ids: list[int]) -> int:
    if not book_ids:
        return 0

    CatalogEntry.objects.filter(book_id__in=book_ids).delete()
    created = 0
    sections = (
        Section.objects.filter(book_id__in=book_ids)
        .select_related("book", "book__snapshot", "parent", "parent__parent")
        .order_by("book_id", "position")
    )
    batch: list[CatalogEntry] = []
    for section in sections.iterator(chunk_size=500):
        for extracted in extract_from_section(section):
            batch.append(
                CatalogEntry(
                    snapshot_id=section.book.snapshot_id,
                    book_id=section.book_id,
                    entry_type=extracted.entry_type,
                    kind=extracted.kind,
                    name=extracted.name,
                    slug=extracted.slug,
                    summary=extracted.summary,
                    primary_section_stable_id=section.stable_id,
                    section_path=section.path,
                    technique=extracted.technique,
                    form=extracted.form,
                    level=extracted.level,
                    range=extracted.range,
                    duration=extracted.duration,
                    target=extracted.target,
                    magnitude=extracted.magnitude,
                    category=extracted.category,
                    evidence=extracted.evidence,
                    extractor="rules",
                )
            )
            created += 1
            if len(batch) >= 500:
                CatalogEntry.objects.bulk_create(batch)
                batch.clear()
    if batch:
        CatalogEntry.objects.bulk_create(batch)
    return created


def current_entries(*, reviewed_only: bool = False) -> QuerySet[CatalogEntry]:
    current = SourceSnapshot.current()
    if not current:
        return CatalogEntry.objects.none()
    qs = CatalogEntry.objects.filter(snapshot=current).select_related("book")
    if reviewed_only:
        qs = qs.filter(book__review_status=Book.ReviewStatus.REVIEWED)
    return qs


def coverage_counts(*, reviewed_only: bool = False) -> dict[str, int]:
    qs = (
        current_entries(reviewed_only=reviewed_only)
        .filter(kind=CatalogEntry.Kind.DEFINITION)
        .values("entry_type")
        .annotate(total=Count("id"))
    )
    return {row["entry_type"]: row["total"] for row in qs}


def coverage_by_book(*, reviewed_only: bool = False) -> list[dict[str, object]]:
    """Per-book lexicon coverage for the current snapshot."""
    current = SourceSnapshot.current()
    if not current:
        return []

    books = Book.objects.filter(snapshot=current).order_by("title")
    if reviewed_only:
        books = books.filter(review_status=Book.ReviewStatus.REVIEWED)
    rows: list[dict[str, object]] = []
    for book in books:
        typed = {
            row["entry_type"]: row["total"]
            for row in CatalogEntry.objects.filter(
                book=book,
                kind=CatalogEntry.Kind.DEFINITION,
            )
            .values("entry_type")
            .annotate(total=Count("id"))
        }
        section_count = book.sections.count()
        catalog_total = sum(typed.values())
        rows.append(
            {
                "book": book,
                "section_count": section_count,
                "spell": typed.get("spell", 0),
                "virtue": typed.get("virtue", 0),
                "flaw": typed.get("flaw", 0),
                "story_seed": typed.get("story_seed", 0),
                "creature": typed.get("creature", 0),
                "character": typed.get("character", 0),
                "guideline": typed.get("guideline", 0),
                "ability": typed.get("ability", 0),
                "catalog_total": catalog_total,
                "density": (catalog_total / section_count) if section_count else 0.0,
            }
        )
    return rows


def resolve_section_for_entry(entry: CatalogEntry) -> Section | None:
    return (
        Section.objects.filter(
            stable_id=entry.primary_section_stable_id,
            book__snapshot=entry.snapshot,
        )
        .select_related("book")
        .first()
    )
