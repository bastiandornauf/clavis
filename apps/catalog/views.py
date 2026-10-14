"""Lexicon browse views."""

from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from apps.catalog.extractors import NON_HERMETIC
from apps.catalog.models import CatalogEntry
from apps.catalog.services import (
    FORMS,
    TECHNIQUES,
    coverage_by_book,
    coverage_counts,
    current_entries,
    entry_has_mentions,
    resolve_section_for_entry,
    workshop_cell,
    workshop_grid,
)
from apps.catalog.similarity import (
    candidate_types,
    entries_by_description,
    missed_entry_candidates,
    similar_entries,
)
from apps.library.models import Book
from apps.library.preferences import apply_reviewed_only, get_reviewed_only
from apps.search.embeddings import semantic_search_available
from apps.search.semantic import related_sections
from apps.search.services import sections_mentioning
from apps.sources.models import SourceSnapshot


def catalog_index(request: HttpRequest) -> HttpResponse:
    only = get_reviewed_only(request)
    counts = coverage_counts(reviewed_only=only)
    return render(
        request,
        "catalog/index.html",
        {
            "counts": counts,
            "page_title": "Lexicon",
            "current_snapshot": SourceSnapshot.current(),
        },
    )


def catalog_coverage(request: HttpRequest) -> HttpResponse:
    only = get_reviewed_only(request)
    return render(
        request,
        "catalog/coverage.html",
        {
            "coverage_rows": coverage_by_book(reviewed_only=only),
            "meaning_available": semantic_search_available(),
            "counts": coverage_counts(reviewed_only=only),
            "page_title": "Lexicon coverage",
            "breadcrumbs": [
                {"label": "Lexicon", "url": reverse("catalog:index")},
                {"label": "Coverage", "url": None},
            ],
        },
    )


def catalog_candidates(request: HttpRequest) -> HttpResponse:
    types = candidate_types()
    entry_type = request.GET.get("type", "").strip()
    if entry_type not in dict(types):
        entry_type = types[0][0] if types else ""
    available = semantic_search_available()
    candidates = missed_entry_candidates(entry_type) if available and entry_type else []
    if get_reviewed_only(request):
        candidates = [
            c for c in candidates if c.section.book.review_status == Book.ReviewStatus.REVIEWED
        ]
    return render(
        request,
        "catalog/candidates.html",
        {
            "types": types,
            "entry_type": entry_type,
            "entry_type_label": dict(types).get(entry_type, ""),
            "candidates": candidates,
            "meaning_available": available,
            "page_title": "Possibly missed entries",
            "breadcrumbs": [
                {"label": "Lexicon", "url": reverse("catalog:index")},
                {"label": "Coverage", "url": reverse("catalog:coverage")},
                {"label": "Possibly missed", "url": None},
            ],
        },
    )


def spell_workshop(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "catalog/workshop.html",
        {
            "grid": workshop_grid(reviewed_only=get_reviewed_only(request)),
            "forms": FORMS,
            "page_title": "Spell workshop",
            "breadcrumbs": [
                {"label": "Lexicon", "url": reverse("catalog:index")},
                {"label": "Spell workshop", "url": None},
            ],
        },
    )


def spell_workshop_cell(request: HttpRequest, technique: str, form: str) -> HttpResponse:
    technique, form = technique.title(), form.title()
    if technique not in TECHNIQUES or form not in FORMS:
        raise Http404("Unknown Technique or Form.")
    guidelines, spells = workshop_cell(
        technique, form, reviewed_only=get_reviewed_only(request)
    )
    title = f"{technique} {form}"
    return render(
        request,
        "catalog/workshop_cell.html",
        {
            "technique": technique,
            "form": form,
            "guidelines": guidelines,
            "spells": spells,
            "page_title": title,
            "breadcrumbs": [
                {"label": "Lexicon", "url": reverse("catalog:index")},
                {"label": "Spell workshop", "url": reverse("catalog:workshop")},
                {"label": title, "url": None},
            ],
        },
    )


def catalog_list(request: HttpRequest, entry_type: str) -> HttpResponse:
    if entry_type not in CatalogEntry.EntryType.values:
        entry_type = CatalogEntry.EntryType.SPELL

    only = get_reviewed_only(request)
    entries = current_entries(reviewed_only=only).filter(
        entry_type=entry_type,
        kind=CatalogEntry.Kind.DEFINITION,
    )
    q = request.GET.get("q", "").strip()
    magnitude = request.GET.get("magnitude", "").strip()
    technique = request.GET.get("technique", "").strip()
    form = request.GET.get("form", "").strip()
    category = request.GET.get("category", "").strip()
    book_slug = request.GET.get("book", "").strip()
    level_min = request.GET.get("level_min", "").strip()
    level_max = request.GET.get("level_max", "").strip()
    tradition = request.GET.get("tradition", "").strip()

    if entry_type == CatalogEntry.EntryType.SPELL:
        if tradition == "hermetic":
            entries = entries.exclude(technique="")
        elif tradition == "other":
            entries = entries.filter(category=NON_HERMETIC)
    if q:
        entries = entries.filter(name__icontains=q)
    if magnitude:
        entries = entries.filter(magnitude__iexact=magnitude)
    if technique:
        entries = entries.filter(technique__iexact=technique)
    if form:
        entries = entries.filter(form__iexact=form)
    if category:
        entries = entries.filter(category__iexact=category)
    if book_slug:
        entries = entries.filter(book__slug=book_slug)
    if level_min.isdigit():
        entries = entries.filter(level__gte=int(level_min))
    if level_max.isdigit():
        entries = entries.filter(level__lte=int(level_max))

    current = SourceSnapshot.current()
    if current:
        books = apply_reviewed_only(
            Book.objects.filter(snapshot=current).order_by("title"),
            request,
        )
    else:
        books = Book.objects.none()

    label = dict(CatalogEntry.EntryType.choices).get(entry_type, entry_type)
    breadcrumbs = [
        {"label": "Lexicon", "url": reverse("catalog:index")},
        {"label": label, "url": None},
    ]
    meaning = semantic_search_available()
    describe = request.GET.get("describe", "").strip() if meaning else ""
    display_limit = 500
    if describe:
        shown = entries_by_description(entries, describe)
        result_count = len(shown)
    else:
        result_count = entries.count()
        shown = entries[:display_limit]
    return render(
        request,
        "catalog/list.html",
        {
            "entries": shown,
            "result_count": result_count,
            "display_limit": display_limit,
            "meaning_available": meaning,
            "describe": describe,
            "entry_type": entry_type,
            "entry_type_label": label,
            "query": q,
            "selected_magnitude": magnitude,
            "selected_technique": technique,
            "selected_form": form,
            "selected_category": category,
            "selected_book": book_slug,
            "level_min": level_min,
            "level_max": level_max,
            "selected_tradition": tradition,
            "books": books,
            "breadcrumbs": breadcrumbs,
            "page_title": label,
            "counts": coverage_counts(reviewed_only=only),
        },
    )


def catalog_detail(request: HttpRequest, entry_type: str, slug: str) -> HttpResponse:
    only = get_reviewed_only(request)
    matches = current_entries(reviewed_only=only).filter(
        entry_type=entry_type,
        slug=slug,
        kind=CatalogEntry.Kind.DEFINITION,
    )
    book_slug = request.GET.get("book", "").strip()
    if book_slug:
        matches = matches.filter(book__slug=book_slug)
    entry = matches.first()
    if entry is None:
        raise Http404("No catalog entry matches.")
    section = resolve_section_for_entry(entry)
    related = list(
        current_entries(reviewed_only=only)
        .filter(entry_type=entry_type, slug=slug)
        .exclude(pk=entry.pk)[:20]
    )
    mentions = []
    if entry_has_mentions(entry):
        defined_in = {entry.primary_section_stable_id} | {
            other.primary_section_stable_id for other in related
        }
        mentions = [
            hit
            for hit in sections_mentioning(entry.name, exclude_stable_ids=defined_in)
            if not only or hit.section.book.review_status == Book.ReviewStatus.REVIEWED
        ]

    similar: list[CatalogEntry] = []
    reprints = []
    if semantic_search_available():
        similar = [
            other
            for other in similar_entries(entry)
            if not only or other.book.review_status == Book.ReviewStatus.REVIEWED
        ]
        if section is not None:
            reprints = related_sections(section).reprints

    breadcrumbs = [
        {"label": "Lexicon", "url": reverse("catalog:index")},
        {
            "label": entry.get_entry_type_display(),
            "url": reverse("catalog:list", args=[entry.entry_type]),
        },
        {"label": entry.name, "url": None},
    ]
    return render(
        request,
        "catalog/detail.html",
        {
            "entry": entry,
            "section": section,
            "related": related,
            "mentions": mentions,
            "similar_entries": similar,
            "reprints": reprints,
            "in_workshop": entry.technique in TECHNIQUES and entry.form in FORMS,
            "breadcrumbs": breadcrumbs,
            "page_title": entry.name,
        },
    )
