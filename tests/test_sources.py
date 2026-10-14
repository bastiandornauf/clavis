from __future__ import annotations

import pytest
from django.urls import reverse

from apps.sources.models import SourceSnapshot
from apps.sources.services import UpdateCheck, check_for_updates
from apps.sources.views import RECENT_IMPORT_LIMIT


@pytest.mark.django_db
def test_sources_page_shows_recent_limit(client, monkeypatch):
    for i in range(8):
        SourceSnapshot.objects.create(
            repo_url="https://example.test/repo",
            commit_sha=f"{'a' * 40}"[:-1] + str(i),
            local_path="/tmp",
            status=SourceSnapshot.Status.READY,
            message=f"Import {i}",
            is_current=(i == 7),
        )
    monkeypatch.setattr(
        "apps.sources.views.check_for_updates",
        lambda: UpdateCheck(status="current", message="up to date"),
    )
    response = client.get(reverse("sources:status"))
    assert response.status_code == 200
    assert response.context["history_limit"] == RECENT_IMPORT_LIMIT
    assert len(response.context["history"]) == RECENT_IMPORT_LIMIT
    assert response.context["history_total"] == 8
    assert b"Download full history" in response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "headline", "button"),
    [
        ("current", "Your library is up to date", "Sync and re-import"),
        ("available", "Update available", "Import update"),
        ("missing", "Sources not downloaded yet", "Download and import"),
        ("unknown", "Couldn’t check for updates", "Sync and re-import"),
    ],
)
def test_sources_update_card(client, monkeypatch, status, headline, button):
    monkeypatch.setattr(
        "apps.sources.views.check_for_updates",
        lambda: UpdateCheck(status=status, message="msg", remote_sha="b" * 40),
    )
    body = client.get(reverse("sources:status")).content.decode()
    assert f"update-card--{status}" in body
    assert headline in body
    assert button in body


@pytest.mark.django_db
def test_import_history_download(client):
    SourceSnapshot.objects.create(
        repo_url="https://example.test/repo",
        commit_sha="abc1234deadbeef",
        local_path="/tmp",
        status=SourceSnapshot.Status.READY,
        message="Imported 3 book(s)",
        is_current=True,
    )
    response = client.get(reverse("sources:history_download"))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    assert "attachment" in response["Content-Disposition"]
    body = response.content.decode()
    assert "Clavis import history" in body
    assert "abc1234deadbeef" in body
    assert "Imported 3 book(s)" in body


@pytest.mark.django_db
def test_check_for_updates_missing_clone(tmp_path, settings):
    settings.CLAVIS_SOURCES_DIR = tmp_path
    settings.CLAVIS_SOURCE_REPO_NAME = "missing-repo"
    result = check_for_updates()
    assert result.status == "missing"
    assert result.updates_available is False
