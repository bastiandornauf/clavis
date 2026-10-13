from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse

from apps.annotations.services import toggle_bookmark, upsert_note
from apps.campaigns.models import Campaign
from apps.campaigns.services import add_excerpt_item, refresh_excerpt_flags
from apps.library.models import Book, Section
from apps.search.services import search_sections
from apps.sources.services import import_sources


@pytest.mark.django_db
def test_import_fixture_books_and_search(fixture_markdown_dir: Path):
    snapshot = import_sources(sync=False, local_path=fixture_markdown_dir)
    assert snapshot.status == "ready"
    assert Book.objects.count() == 3

    hits = search_sections("Pilum")
    assert hits
    assert any("Pilum" in hit.section.title for hit in hits)


def test_reviewed_core_rules_preferred_over_wip_alias(tmp_path: Path):
    from apps.library.services import list_source_markdown_files

    reviewed = tmp_path / "reviewed"
    wip = tmp_path / "wip"
    reviewed.mkdir()
    wip.mkdir()
    (reviewed / "Ars Magica - Definitive Edition (Core Rules).md").write_text(
        "# Definitive\n\n## A\n\nBody.\n",
        encoding="utf-8",
    )
    (wip / "Ars Magica 5e - Core Rules.md").write_text(
        "# Core\n\n## B\n\nOlder body.\n",
        encoding="utf-8",
    )
    (wip / "Ars Magica 5e - Magi of Hermes.md").write_text(
        "# Magi\n\n## C\n\nOnly in wip.\n",
        encoding="utf-8",
    )

    files = list_source_markdown_files(tmp_path)
    titles = {f.title for f in files}
    assert "Definitive Edition (Core Rules)" in titles
    assert "Core Rules" not in titles
    assert "Magi of Hermes" in titles
    core = next(f for f in files if "Definitive" in f.title)
    assert core.review_status == Book.ReviewStatus.REVIEWED


@pytest.mark.django_db
def test_annotations_and_excerpts_survive_reimport(fixture_markdown_dir: Path, tmp_path: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    section = Section.objects.get(title="Pilum of Fire")
    toggle_bookmark(section)
    upsert_note(section, "Use in the first combat.")

    campaign = Campaign.objects.create(name="Next Session")
    add_excerpt_item(campaign, section, "A javelin of fire flies from your hand")

    # Re-import identical fixtures: overlays remain by stable_id.
    import_sources(sync=False, local_path=fixture_markdown_dir)
    new_section = Section.objects.get(title="Pilum of Fire")
    assert new_section.stable_id == section.stable_id

    from apps.annotations.models import Bookmark, Note

    assert Bookmark.objects.filter(section_stable_id=section.stable_id).exists()
    assert Note.objects.get(section_stable_id=section.stable_id).body.startswith("Use in")

    # Broken excerpt when source text no longer contains the selection.
    altered = tmp_path / "reviewed"
    altered.mkdir()
    altered_md = (
        "# Definitive Edition Sample\n\n"
        "## Spells\n\n### LEVEL 20\n\n#### Pilum of Fire\n\n"
        "Changed text only.\n"
    )
    (altered / "Ars Magica 5e - Definitive Edition (Core Rules).md").write_text(
        altered_md,
        encoding="utf-8",
    )
    import_sources(sync=False, local_path=tmp_path)
    refresh_excerpt_flags()
    item = campaign.items.get()
    assert item.source_changed is True


@pytest.mark.django_db
def test_library_and_reader_pages(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    book = Book.objects.get(title__icontains="Definitive Edition")

    library = client.get(reverse("library:index"))
    assert library.status_code == 200
    assert b"Definitive Edition" in library.content
    assert b"books" in library.content
    assert b'href="/notice/"' in library.content or b"/notice/" in library.content

    notice = client.get(reverse("notice"))
    assert notice.status_code == 200
    assert b"MIT License" in notice.content or b"MIT" in notice.content
    assert b"CC BY-SA" in notice.content or b"Attribution-ShareAlike" in notice.content

    reader = client.get(reverse("reader:book", args=[book.slug]))
    assert reader.status_code == 200

    search = client.get(reverse("search:index"), {"q": "Durenmar"})
    assert search.status_code == 200
    assert b"Durenmar" in search.content
