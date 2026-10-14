"""Full-text search views."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.http import urlencode

from apps.library.models import Book
from apps.library.preferences import apply_reviewed_only, get_reviewed_only
from apps.library.services import citation_parts
from apps.search.embeddings import semantic_search_available
from apps.search.services import search_sections
from apps.sources.models import SourceSnapshot
from clavis.citations import Citation, format_citation

SEARCH_MODES = {
    "keyword": "Keyword",
    "semantic": "Meaning",
    "hybrid": "Keyword + meaning",
}


def _search_function(mode: str):
    if mode == "semantic":
        from apps.search.semantic import search_sections_semantic

        return search_sections_semantic
    if mode == "hybrid":
        from apps.search.semantic import search_sections_hybrid

        return search_sections_hybrid
    return search_sections


def search_page(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    edition = request.GET.get("edition", "").strip()
    book_slug = request.GET.get("book", "").strip()
    status = request.GET.get("status", "").strip()
    only = get_reviewed_only(request)
    effective_status = Book.ReviewStatus.REVIEWED if only else status

    modes = SEARCH_MODES if semantic_search_available() else {}
    mode = request.GET.get("mode", "").strip()
    if mode not in modes:
        mode = "hybrid" if modes else "keyword"

    hits = []
    if query:
        raw_hits = _search_function(mode)(
            query,
            edition=edition,
            book_slug=book_slug,
            review_status=effective_status,
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
        books = apply_reviewed_only(
            Book.objects.filter(snapshot=current).order_by("title"),
            request,
        )
    else:
        books = Book.objects.none()

    filter_params = {
        k: v
        for k, v in {
            "q": query,
            "edition": edition,
            "book": book_slug,
            "status": "" if only else status,
            "mode": mode if modes else "",
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
            "selected_status": effective_status if only else status,
            "search_modes": modes,
            "selected_mode": mode,
            "edition_choices": Book.Edition.choices,
            "status_choices": Book.ReviewStatus.choices,
            "return_query": urlencode(filter_params),
            "page_title": "Search",
        },
    )
