"""Library book listing and released-image gallery."""

from __future__ import annotations

from pathlib import Path

from django.db.models import Count, QuerySet
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from apps.library.gallery import (
    list_gallery_albums,
    preview_png_path,
    released_images_root,
    resolve_gallery_file,
)
from apps.library.models import Book
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
    if status:
        books = books.filter(review_status=status)
    return books


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
