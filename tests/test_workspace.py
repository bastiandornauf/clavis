from __future__ import annotations

import pytest
from django.urls import reverse

from apps.annotations.models import Bookmark
from apps.campaigns.models import Campaign


@pytest.mark.django_db
def test_workspace_tabs_and_nav_redirects(client):
    Campaign.objects.create(name="Rhine saga", description="")
    Bookmark.objects.create(
        section_stable_id="abc",
        book_slug="core",
        section_path="spells/pilum",
        title="Pilum",
    )

    page = client.get(reverse("campaigns:workspace"))
    assert page.status_code == 200
    assert b"Workspace" in page.content
    assert b"Rhine saga" in page.content

    bookmarks = client.get(reverse("campaigns:workspace"), {"tab": "bookmarks"})
    assert bookmarks.status_code == 200
    assert b"Pilum" in bookmarks.content

    redirect = client.get(reverse("annotations:bookmarks"))
    assert redirect.status_code == 302
    assert "tab=bookmarks" in redirect["Location"]

    home = client.get(reverse("library:index"))
    assert b">Search<" not in home.content
    assert b">Workspace<" in home.content
    # Gallery comes after Lexicon in the Browse group markup order.
    body = home.content.decode()
    assert body.index("Lexicon") < body.index("Gallery")
