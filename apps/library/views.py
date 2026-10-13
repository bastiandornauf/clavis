"""Library book listing and released-image gallery."""

from __future__ import annotations

from pathlib import Path

from django.db.models import Count, QuerySet
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.library.gallery import (
    list_gallery_albums,
    preview_png_path,
    released_images_root,
    resolve_gallery_file,
)
from apps.library.guides import load_guides_catalog
from apps.library.models import Book
from apps.library.preferences import apply_reviewed_only, get_reviewed_only, set_reviewed_only
from apps.sources.models import SourceSnapshot


def _filtered_books(request: HttpRequest) -> QuerySet[Book]:
    current = SourceSnapshot.current()
    books = Book.objects.none()
    if current:
        books = (
            Book.objects.filter(snapshot=current)
            .annotate(section_count=Count("sections"))
            .order_by("title")
        )
    edition = request.GET.get("edition", "").strip()
    status = request.GET.get("status", "").strip()
    if edition:
        books = books.filter(edition=edition)
    books = apply_reviewed_only(books, request)
    if not get_reviewed_only(request) and status:
        books = books.filter(review_status=status)
    return books


def toggle_reviewed_only(request: HttpRequest) -> HttpResponse:
    """Persist the global reviewed-only preference and return to the previous page."""
    if request.method == "POST":
        set_reviewed_only(request, request.POST.get("reviewed_only") == "1")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = "/"
    return redirect(next_url)


def library_index(request: HttpRequest) -> HttpResponse:
    books = _filtered_books(request)
    return render(
        request,
        "library/index.html",
        {
            "books": books,
            "book_count": books.count(),
            "current_snapshot": SourceSnapshot.current(),
            "selected_edition": request.GET.get("edition", ""),
            "selected_status": request.GET.get("status", ""),
            "edition_choices": Book.Edition.choices,
            "status_choices": Book.ReviewStatus.choices,
            "page_title": "Library",
        },
    )


def gallery_index(request: HttpRequest) -> HttpResponse:
    root = released_images_root()
    albums = list_gallery_albums(root)
    image_count = sum(len(album.images) for album in albums)
    return render(
        request,
        "library/gallery.html",
        {
            "albums": albums,
            "image_count": image_count,
            "has_images": bool(albums),
            "page_title": "Gallery",
        },
    )


def guides_index(request: HttpRequest) -> HttpResponse:
    catalog = load_guides_catalog()
    return render(
        request,
        "library/guides.html",
        {
            "intro": catalog.intro,
            "categories": catalog.categories,
            "page_title": "Guides",
        },
    )


def gallery_image(request: HttpRequest, relative_path: str) -> HttpResponse:
    try:
        source = resolve_gallery_file(relative_path)
        preview = preview_png_path(source, relative_path)
    except FileNotFoundError as exc:
        raise Http404("Image not found") from exc

    content_type = "image/png"
    suffix = Path(preview).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        content_type = "image/jpeg"
    elif suffix == ".webp":
        content_type = "image/webp"
    elif suffix == ".gif":
        content_type = "image/gif"

    return FileResponse(preview.open("rb"), content_type=content_type)
