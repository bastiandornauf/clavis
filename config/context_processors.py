"""Template context shared across Clavis pages."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest

from apps.library.preferences import get_reviewed_only


def clavis_globals(request: HttpRequest) -> dict[str, Any]:
    return {
        "clavis_app_name": "Clavis",
        "clavis_tagline": "Ars Magica source archive",
        "clavis_app_repo_url": settings.CLAVIS_APP_REPO_URL,
        "reviewed_only": get_reviewed_only(request),
    }
