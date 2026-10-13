"""Full-text search views."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.http import urlencode

from apps.library.models import Book
from apps.library.services import citation_parts
from apps.search.services import search_sections
from apps.sources.models import SourceSnapshot
from clavis.citations import Citation, format_citation


def search_page(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    edition = request.GET.get("edition", "").strip()
    book_slug = request.GET.get("book", "").strip()
    status = request.GET.get("status", "").strip()

    hits = []
    if query:
        raw_hits = search_sections(
            query,
            edition=edition,
            book_slug=book_slug,
            review_status=status,
        )
        for hit in raw_hits:
            citation = Citation(**citation_parts(hit.section))
            hits.append(
                {
                    "section": hit.section,
                    "snippet": hit.snippet,
                    "citation": format_citation(citation),
                }
            )

    current = SourceSnapshot.current()
    if current:
        books = Book.objects.filter(snapshot=current).order_by("title")
    else:
        books = Book.objects.none()

    filter_params = {
        k: v
        for k, v in {
            "q": query,
            "edition": edition,
            "book": book_slug,
            "status": status,
        }.items()
        if v
    }

    return render(
        request,
        "search/index.html",
        {
            "query": query,
            "hits": hits,
            "books": books,
            "selected_edition": edition,
            "selected_book": book_slug,
            "selected_status": status,
            "edition_choices": Book.Edition.choices,
            "status_choices": Book.ReviewStatus.choices,
            "return_query": urlencode(filter_params),
            "page_title": "Search",
        },
    )
