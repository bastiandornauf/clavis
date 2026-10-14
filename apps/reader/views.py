"""Book reader views."""

from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.http import urlencode

from apps.annotations.services import (
    get_bookmarks_for_book,
    get_last_read,
    get_notes_for_book,
    set_last_read,
)
from apps.campaigns.models import Campaign
from apps.catalog.models import CatalogEntry
from apps.library.models import Book, Section
from apps.library.services import citation_parts
from apps.reader.services import (
    DEFAULT_TOC_DEPTH,
    DEFAULT_VIEW_MODE,
    branch_neighbors,
    build_toc_tree,
    parse_toc_depth,
    parse_view_mode,
    reader_query,
    section_branch,
    section_path_nodes,
)
from apps.search.embeddings import semantic_search_available
from apps.sources.models import SourceSnapshot
from clavis.citations import Citation, format_citation
from clavis.markdown import render_markdown


def _current_book(slug: str) -> Book:
    current = SourceSnapshot.current()
    if not current:
        raise Http404("No sources imported yet.")
    return get_object_or_404(Book, snapshot=current, slug=slug)


def _all_sections(book: Book) -> list[Section]:
    return list(book.sections.order_by("position"))


def _single_neighbors(section: Section) -> tuple[Section | None, Section | None]:
    qs = Section.objects.filter(book=section.book).order_by("position")
    prev_section = qs.filter(position__lt=section.position).last()
    next_section = qs.filter(position__gt=section.position).first()
    return prev_section, next_section


def read_book(request: HttpRequest, book_slug: str) -> HttpResponse:
    book = _current_book(book_slug)
    sections = _all_sections(book)
    if not sections:
        raise Http404("This book has no sections.")

    last = get_last_read(book)
    if last and last.section and last.section.book_id == book.pk:
        target = last.section
    else:
        target = sections[0]
    return read_section(request, book_slug, target.path)


def read_section(request: HttpRequest, book_slug: str, section_path: str) -> HttpResponse:
    book = _current_book(book_slug)
    section = get_object_or_404(
        Section.objects.select_related(
            "parent",
            "parent__parent",
            "parent__parent__parent",
        ),
        book=book,
        path=section_path,
    )
    set_last_read(section)

    toc_depth = parse_toc_depth(
        request.GET.get("toc"),
        request.session.get("reader_toc_depth", DEFAULT_TOC_DEPTH),
    )
    view_mode = parse_view_mode(
        request.GET.get("view"),
        request.session.get("reader_view_mode", DEFAULT_VIEW_MODE),
    )
    request.session["reader_toc_depth"] = toc_depth
    request.session["reader_view_mode"] = view_mode

    search_extras = {
        k: v
        for k, v in {
            "q": request.GET.get("q", "").strip(),
            "edition": request.GET.get("edition", "").strip(),
            "book": request.GET.get("book", "").strip(),
            "status": request.GET.get("status", "").strip(),
        }.items()
        if v
    }
    return_query = reader_query(
        toc_depth=toc_depth,
        view_mode=view_mode,
        extra=search_extras,
    )

    back_to_search_url = None
    if search_extras.get("q"):
        back_to_search_url = f"{reverse('search:index')}?{urlencode(search_extras)}"

    branch = section_branch(section)
    child_count = max(len(branch) - 1, 0)
    if view_mode == "branch":
        blocks = branch
        prev_section, next_section = branch_neighbors(section)
    else:
        blocks = [section]
        prev_section, next_section = _single_neighbors(section)

    stable_ids = [block.stable_id for block in blocks]
    catalog_by_stable: dict[str, list[CatalogEntry]] = {sid: [] for sid in stable_ids}
    for entry in CatalogEntry.objects.filter(
        primary_section_stable_id__in=stable_ids,
        kind=CatalogEntry.Kind.DEFINITION,
        book=book,
    ).order_by("entry_type", "name"):
        catalog_by_stable.setdefault(entry.primary_section_stable_id, []).append(entry)

    # Header badges only for the opened heading — not a dump of every subsection.
    # Cap the strip so TOC-like pages never drown the title in chips.
    catalog_entries = catalog_by_stable.get(section.stable_id, [])
    show_header_badges = (
        (view_mode == "single" or len(blocks) == 1) and len(catalog_entries) <= 5
    )

    rendered_blocks = [
        {
            "section": block,
            "body_html": render_markdown(block.body_markdown),
            # The opened section is the page h1; subsections nest from h2 under it.
            "heading_level": min(max(block.level - section.level + 1, 2), 6),
            "catalog_entries": catalog_by_stable.get(block.stable_id, []),
        }
        for block in blocks
    ]

    related = None
    if semantic_search_available():
        from apps.search.semantic import related_sections

        related = related_sections(section)

    bookmarks = {b.section_stable_id for b in get_bookmarks_for_book(book)}
    notes = {n.section_stable_id: n for n in get_notes_for_book(book)}
    citation = Citation(**citation_parts(section))
    toc_tree = build_toc_tree(_all_sections(book), toc_depth, section)

    breadcrumbs: list[dict[str, str | None]] = [
        {"label": "Library", "url": reverse("library:index")},
        {
            "label": book.title,
            "url": f"{reverse('reader:book', args=[book.slug])}?{return_query}",
        },
    ]
    # Omit the current section — it is already the page heading.
    for node in section_path_nodes(section)[:-1]:
        breadcrumbs.append(
            {
                "label": node.display_title,
                "url": (
                    f"{reverse('reader:section', args=[book.slug, node.path])}"
                    f"?{return_query}"
                ),
            }
        )

    return render(
        request,
        "reader/section.html",
        {
            "book": book,
            "section": section,
            "blocks": rendered_blocks,
            "toc_tree": toc_tree,
            "toc_depth": toc_depth,
            "view_mode": view_mode,
            "child_count": child_count,
            "prev_section": prev_section,
            "next_section": next_section,
            "citation_text": format_citation(citation),
            "citation": citation,
            "is_bookmarked": section.stable_id in bookmarks,
            "note": notes.get(section.stable_id),
            "campaigns": Campaign.objects.all(),
            "catalog_entries": catalog_entries,
            "show_header_badges": show_header_badges,
            "similar_sections": related.similar if related else [],
            "reprints": related.reprints if related else [],
            "back_to_search_url": back_to_search_url,
            "breadcrumbs": breadcrumbs,
            "page_title": f"{section.display_title} · {book.title}",
            "return_query": return_query,
        },
    )
