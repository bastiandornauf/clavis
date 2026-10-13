"""Session preferences that affect browsing across Clavis."""

from __future__ import annotations

from django.db.models import QuerySet
from django.http import HttpRequest

from apps.library.models import Book

REVIEWED_ONLY_SESSION_KEY = "reviewed_only"


def get_reviewed_only(request: HttpRequest) -> bool:
    return bool(request.session.get(REVIEWED_ONLY_SESSION_KEY, False))


def set_reviewed_only(request: HttpRequest, enabled: bool) -> None:
    request.session[REVIEWED_ONLY_SESSION_KEY] = bool(enabled)


def apply_reviewed_only(books: QuerySet[Book], request: HttpRequest) -> QuerySet[Book]:
    """Restrict a book queryset when the global reviewed-only preference is on."""
    if get_reviewed_only(request):
        return books.filter(review_status=Book.ReviewStatus.REVIEWED)
    return books
