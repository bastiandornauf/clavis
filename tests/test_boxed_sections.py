from __future__ import annotations

from pathlib import Path

import pytest

from apps.catalog.extractors import boxed_sections, extract_from_section
from apps.library.models import Book, Section
from apps.sources.models import SourceSnapshot


@pytest.fixture
def book(tmp_path: Path) -> Book:
    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="boxes",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    return Book.objects.create(
        snapshot=snap, slug="boxes", title="Boxes", relative_path="reviewed/boxes.md"
    )


def _section(book: Book, title: str, body: str) -> Section:
    return Section.objects.create(
        book=book,
        level=3,
        title=title,
        slug=title.lower().replace(" ", "-"),
        path=f"chapter/{title.lower().replace(' ', '-')}",
        body_markdown=body,
        content_hash=title,
        stable_id=f"box-{title}",
        position=0,
    )


@pytest.mark.django_db
def test_boxes_split_on_quoted_headings_and_keep_blank_lines(book: Book):
    section = _section(
        book,
        "The Open Exhibits",
        "Visitors wander the hall.\n\n"
        "> ### Everbright Chandelier\n>\n> CrIg 24\n\n> Pen 0, constant effect\n"
        "> ### Glowing Footprints\n> Text\n\n"
        "Plain prose again.\n",
    )
    boxes = boxed_sections(section)
    assert [box.title for box in boxes] == ["Everbright Chandelier", "Glowing Footprints"]
    assert boxes[0].body_markdown.startswith("CrIg 24")
    assert "Pen 0, constant effect" in boxes[0].body_markdown
    assert not any(line.startswith(">") for line in boxes[0].body_markdown.splitlines())


@pytest.mark.django_db
def test_boxed_spell_and_item_are_extracted_against_enclosing_section(book: Book):
    section = _section(
        book,
        "Tatiana of Tremere",
        "Tatiana keeps a workshop.\n\n"
        "> #### Object of Increased Size\n>\n> MuTe 20\n>\n"
        "> R: Touch, D: Sun, T: Ind\n>\n> The target grows.\n\n"
        "> #### Everbright Chandelier\n>\n> CrIg 24\n>\n> Pen 0, constant effect\n>\n"
        "> R: Touch, D: Sun, T: Room\n>\n> This chandelier never dims.\n",
    )
    entries = extract_from_section(section)
    found = {(entry.entry_type, entry.name) for entry in entries}
    assert ("spell", "Object of Increased Size") in found
    assert ("item", "Everbright Chandelier") in found
    assert all(entry.section is section for entry in entries)


@pytest.mark.django_db
def test_new_spell_prefix_is_dropped_from_names(book: Book):
    section = _section(
        book,
        "New Spell: The Twisted Spine",
        "MuCo 20\n\nR: Touch, D: Sun, T: Ind\n\nBends the spine.",
    )
    names = [entry.name for entry in extract_from_section(section)]
    assert names == ["The Twisted Spine"]
