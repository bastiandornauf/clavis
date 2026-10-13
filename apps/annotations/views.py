"""Bookmark and note actions."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.annotations.services import toggle_bookmark, upsert_note
from apps.library.models import Section
from apps.sources.models import SourceSnapshot


def _resolve_section(stable_id: str) -> Section:
    current = SourceSnapshot.current()
    qs = Section.objects.filter(stable_id=stable_id).select_related("book")
    if current:
        section = qs.filter(book__snapshot=current).first()
        if section:
            return section
    section = qs.first()
    if not section:
        raise Section.DoesNotExist
    return section


@require_POST
def bookmark_toggle(request: HttpRequest) -> HttpResponse:
    stable_id = request.POST.get("stable_id", "")
    try:
        section = _resolve_section(stable_id)
    except Section.DoesNotExist:
        section = get_object_or_404(Section, stable_id=stable_id)
    added = toggle_bookmark(section)
    messages.success(request, "Bookmark added." if added else "Bookmark removed.")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)


@require_http_methods(["POST"])
def note_save(request: HttpRequest) -> HttpResponse:
    stable_id = request.POST.get("stable_id", "")
    section = _resolve_section(stable_id)
    upsert_note(section, request.POST.get("body", ""))
    messages.success(request, "Note saved.")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)


def bookmark_list(request: HttpRequest) -> HttpResponse:
    return redirect(f"{reverse('campaigns:workspace')}?tab=bookmarks")


def note_list(request: HttpRequest) -> HttpResponse:
    return redirect(f"{reverse('campaigns:workspace')}?tab=notes")
