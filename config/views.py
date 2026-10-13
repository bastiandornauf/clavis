"""Project-level pages (notices, about)."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from clavis.markdown import render_markdown


def notice(request: HttpRequest) -> HttpResponse:
    """Render the repository NOTICE.md for attribution details."""
    path = Path(settings.BASE_DIR) / "NOTICE.md"
    if not path.is_file():
        raise Http404("NOTICE.md is missing from this install.")
    text = path.read_text(encoding="utf-8")
    return render(
        request,
        "notice.html",
        {
            "page_title": "Notices",
            "body_html": render_markdown(text),
            "breadcrumbs": [
                {"label": "Notices", "url": None},
            ],
        },
    )
