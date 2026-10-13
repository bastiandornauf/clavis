"""Source management views."""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from apps.sources.models import SourceSnapshot
from apps.sources.services import SourceSyncError, check_for_updates, import_sources

# Enough for “what just happened”; full history via download.
RECENT_IMPORT_LIMIT = 5


def _format_import_history_lines(snapshots: list[SourceSnapshot]) -> list[str]:
    lines = ["Clavis import history", ""]
    for snap in snapshots:
        marker = " current" if snap.is_current else ""
        lines.append(
            f"{snap.imported_at.isoformat()}  {snap.commit_sha or '-'}  "
            f"{snap.status}{marker}  {snap.message}"
        )
    return lines


@require_http_methods(["GET", "POST"])
def sources_status(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        try:
            snapshot = import_sources(sync=True)
            messages.success(
                request,
                f"Import complete: {snapshot.message} @ {snapshot.commit_sha[:7]}",
            )
        except SourceSyncError as exc:
            messages.error(request, f"Source sync failed: {exc}")
        except Exception as exc:
            messages.error(request, f"Import failed: {exc}")
        return redirect("sources:status")

    current = SourceSnapshot.current()
    history_total = SourceSnapshot.objects.count()
    history = list(SourceSnapshot.objects.all()[:RECENT_IMPORT_LIMIT])
    update_check = check_for_updates()
    return render(
        request,
        "sources/status.html",
        {
            "current": current,
            "history": history,
            "history_total": history_total,
            "history_limit": RECENT_IMPORT_LIMIT,
            "source_repo_url": settings.CLAVIS_SOURCE_REPO_URL,
            "update_check": update_check,
            "page_title": "Sources",
        },
    )


@require_GET
def import_history_download(request: HttpRequest) -> HttpResponse:
    """Download the full import history as plain text."""
    snapshots = list(SourceSnapshot.objects.all())
    body = "\n".join(_format_import_history_lines(snapshots)) + "\n"
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    response = HttpResponse(body, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="clavis-import-history-{stamp}.txt"'
    )
    return response
