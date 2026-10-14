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
                    level_general=extracted.level_general,
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
        virtue_flaw = typed.get("virtue", 0) + typed.get("flaw", 0)
        boon_hook = typed.get("boon", 0) + typed.get("hook", 0)
        accounted = (
            typed.get("spell", 0)
            + virtue_flaw
            + typed.get("creature", 0)
            + typed.get("beast", 0)
            + boon_hook
            + typed.get("organization", 0)
            + typed.get("place", 0)
            + typed.get("item", 0)
        )
        rows.append(
            {
                "book": book,
                "section_count": section_count,
                "spell": typed.get("spell", 0),
                "virtue_flaw": virtue_flaw,
                "creature": typed.get("creature", 0),
                "beast": typed.get("beast", 0),
                "boon_hook": boon_hook,
                "organization": typed.get("organization", 0),
                "place": typed.get("place", 0),
                "item": typed.get("item", 0),
                "other": max(catalog_total - accounted, 0),
                "catalog_total": catalog_total,
                "density": (catalog_total / section_count) if section_count else 0.0,
            }
        )
    return rows


TECHNIQUES = ("Creo", "Intellego", "Muto", "Perdo", "Rego")
FORMS = (
    "Animal",
    "Aquam",
    "Auram",
    "Corpus",
    "Herbam",
    "Ignem",
    "Imaginem",
    "Mentem",
    "Terram",
    "Vim",
)


def workshop_grid(*, reviewed_only: bool = False) -> list[dict[str, object]]:
    """Hermetic spells and guidelines counted per Technique × Form."""
    counts: dict[tuple[str, str, str], int] = {}
    rows = (
        current_entries(reviewed_only=reviewed_only)
        .filter(
            entry_type__in=[CatalogEntry.EntryType.SPELL, CatalogEntry.EntryType.GUIDELINE],
            kind=CatalogEntry.Kind.DEFINITION,
            technique__in=TECHNIQUES,
            form__in=FORMS,
        )
        .values("entry_type", "technique", "form")
        .annotate(total=Count("id"))
    )
    for row in rows:
        counts[(row["entry_type"], row["technique"], row["form"])] = row["total"]
    return [
        {
            "technique": technique,
            "cells": [
                {
                    "form": form,
                    "spells": counts.get(("spell", technique, form), 0),
                    "guidelines": counts.get(("guideline", technique, form), 0),
                }
                for form in FORMS
            ],
        }
        for technique in TECHNIQUES
    ]


def workshop_cell(
    technique: str, form: str, *, reviewed_only: bool = False
) -> tuple[list[CatalogEntry], list[CatalogEntry]]:
    """Guidelines and spells for one Technique + Form, lowest level first."""
    base = current_entries(reviewed_only=reviewed_only).filter(
        kind=CatalogEntry.Kind.DEFINITION, technique=technique, form=form
    )
    guidelines = list(
        base.filter(entry_type=CatalogEntry.EntryType.GUIDELINE).order_by("level", "name")
    )
    spells = list(
        base.filter(entry_type=CatalogEntry.EntryType.SPELL).order_by(
            "-level_general", "level", "name"
        )
    )
    return guidelines, spells


MENTION_MAX_WORDS = 6


def entry_has_mentions(entry: CatalogEntry) -> bool:
    """Only proper names are worth a cross-book lookup.

    Guideline and story-seed names are sentences; one-word generic names
    ("Size", "Ward") would match half the corpus.
    """
    if entry.entry_type in {CatalogEntry.EntryType.GUIDELINE, CatalogEntry.EntryType.STORY_SEED}:
        return False
    words = entry.name.split()
    if len(words) > MENTION_MAX_WORDS:
        return False
    return len(words) >= 2 or len(entry.name) >= 6


def resolve_section_for_entry(entry: CatalogEntry) -> Section | None:
    return (
        Section.objects.filter(
            stable_id=entry.primary_section_stable_id,
            book__snapshot=entry.snapshot,
        )
        .select_related("book")
        .first()
    )
