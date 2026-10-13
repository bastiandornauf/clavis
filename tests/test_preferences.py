from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse

from apps.library.models import Book
from apps.library.preferences import REVIEWED_ONLY_SESSION_KEY, get_reviewed_only
from apps.sources.services import import_sources


@pytest.mark.django_db
def test_reviewed_only_preference_filters_library(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    assert Book.objects.filter(review_status=Book.ReviewStatus.REVIEWED).exists()

    # Fixtures are all under reviewed/; add a WIP sibling for contrast.
    wip = Book.objects.filter(review_status=Book.ReviewStatus.REVIEWED).first()
    assert wip is not None
    Book.objects.create(
        snapshot=wip.snapshot,
        slug="wip-extra-book",
        title="WIP Extra Book",
        relative_path="wip/extra.md",
        edition=wip.edition,
        review_status=Book.ReviewStatus.WIP,
    )

    open_list = client.get(reverse("library:index"))
    assert open_list.status_code == 200
    assert b"WIP Extra Book" in open_list.content
    assert b"Reviewed" in open_list.content

    toggle = client.post(
        reverse("library:reviewed_only"),
        {"reviewed_only": "1", "next": reverse("library:index")},
    )
    assert toggle.status_code == 302
    assert get_reviewed_only(toggle.wsgi_request) or client.session.get(
        REVIEWED_ONLY_SESSION_KEY
    )

    filtered = client.get(reverse("library:index"))
    assert filtered.status_code == 200
    assert b"WIP Extra Book" not in filtered.content
    assert b"(reviewed only)" in filtered.content

    off = client.post(
        reverse("library:reviewed_only"),
        {"next": reverse("library:index")},
    )
    assert off.status_code == 302
    restored = client.get(reverse("library:index"))
    assert b"WIP Extra Book" in restored.content
