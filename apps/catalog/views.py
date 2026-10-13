"""Lexicon browse views."""

from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from apps.catalog.models import CatalogEntry
from apps.catalog.services import (
    coverage_by_book,
    coverage_counts,
    current_entries,
    resolve_section_for_entry,
)
from apps.library.models import Book
from apps.library.preferences import apply_reviewed_only, get_reviewed_only
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
            "counts": coverage_counts(reviewed_only=only),
            "page_title": "Lexicon coverage",
            "breadcrumbs": [
                {"label": "Lexicon", "url": reverse("catalog:index")},
                {"label": "Coverage", "url": None},
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
    result_count = entries.count()
    display_limit = 500
    return render(
        request,
        "catalog/list.html",
        {
            "entries": entries[:display_limit],
            "result_count": result_count,
            "display_limit": display_limit,
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
    related = current_entries(reviewed_only=only).filter(
        entry_type=entry_type,
        slug=slug,
    ).exclude(pk=entry.pk)[:20]

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
            "breadcrumbs": breadcrumbs,
            "page_title": entry.name,
        },
    )
