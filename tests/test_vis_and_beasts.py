from __future__ import annotations

from pathlib import Path

import pytest

from apps.catalog.extractors import extract_from_section, extract_vis_sources
from apps.catalog.saga_extractors import extract_beast
from apps.library.models import Book, Section
from apps.sources.models import SourceSnapshot


def _book(tmp_path: Path) -> Book:
    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="vis",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    return Book.objects.create(
        snapshot=snap, slug="vis-book", title="Vis Book", relative_path="v.md"
    )


def _section(book: Book, title: str, body: str = "", *, parent=None, level=4, key="s") -> Section:
    return Section.objects.create(
        book=book,
        parent=parent,
        level=level,
        title=title,
        slug=key,
        path=f"{parent.path}/{key}" if parent else key,
        body_markdown=body,
        content_hash="h",
        stable_id=key,
        position=0,
    )


@pytest.mark.django_db
def test_site_section_led_by_yearly_amount(tmp_path: Path):
    section = _section(
        _book(tmp_path),
        "The Black Grapes",
        "*6 pawns of Perdo per year in autumn*\n\nThe grapes wither on the vine.",
    )

    (source,) = extract_vis_sources(section)

    assert (source.name, source.form, source.level, source.category) == (
        "The Black Grapes",
        "Perdo",
        6,
        "Perdo",
    )


@pytest.mark.django_db
def test_vis_sources_list_skips_sites_with_own_section(tmp_path: Path):
    book = _book(tmp_path)
    resources = _section(book, "Resources", "Intro.", level=3, key="res")
    listing = _section(
        book,
        "Vis Sources",
        "**Alexander's Camp**\n\n4 Herbam per year 20 points\n\n"
        "**Spring of the Sun**\n\nEither 6 Aquam or 6 Ignem 30 points",
        parent=resources,
        key="vis",
    )
    _section(book, "Alexander's Camp", "*4 pawns of Herbam per year*", parent=resources, key="camp")

    sources = extract_vis_sources(listing)

    assert [(s.name, s.category, s.level) for s in sources] == [("Spring of the Sun", "Mixed", 6)]


@pytest.mark.django_db
def test_vis_site_title_names_the_source(tmp_path: Path):
    section = _section(
        _book(tmp_path),
        "Vis Site: The Abandoned Mine",
        "Three pawns of Terram vis gather in the deepest shaft each winter.",
    )

    (source,) = extract_vis_sources(section)

    assert (source.name, source.form, source.level) == ("The Abandoned Mine", "Terram", 3)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("title", "body"),
    [
        ("Sapphire", "A Sapphire of Virtue contains 1 pawn of Intellego vis each year."),
        ("Vis Extraction", "For each season that you spend, you get one pawn of Vim vis."),
        ("The Ritual", "The ritual leaves 12 pawns of Vim vis in the form of crystal shards."),
    ],
)
def test_one_off_vis_is_not_a_source(tmp_path: Path, title: str, body: str):
    assert extract_vis_sources(_section(_book(tmp_path), title, body)) == []


@pytest.mark.django_db
def test_bold_beast_stat_block_with_inline_size(tmp_path: Path):
    section = _section(
        _book(tmp_path),
        "Adder (Viperis)",
        "**Characteristics:** Cun –1, Per –2, Pre –6, Com –6, Str –8, Sta +2, Dex +2, Qik +3 "
        "**Size: –**4 **Confidence Score:** 0 **Virtues and Flaws:** Lightning Reflexes",
    )

    beast = extract_beast(section)

    assert beast is not None
    assert beast.summary == "Mundane beast; Size –4"


@pytest.mark.django_db
def test_virtue_kind_from_italic_line_in_mixed_chapter(tmp_path: Path):
    book = _book(tmp_path)
    chapter = _section(
        book, "New Virtues and Flaws", "Intro.", level=2, key="new-virtues-and-flaws"
    )
    section = _section(
        book,
        "Dust Devil",
        "*Minor, Supernatural Virtue*\n\nYou can call a whirlwind.",
        parent=chapter,
    )

    (entry,) = [e for e in extract_from_section(section) if e.entry_type in {"virtue", "flaw"}]

    assert (entry.entry_type, entry.name, entry.category) == (
        "virtue",
        "Dust Devil",
        "Supernatural",
    )


@pytest.mark.django_db
def test_flaw_kind_and_name_from_title_prefix(tmp_path: Path):
    section = _section(
        _book(tmp_path),
        "New Flaw: Exciting Experimentation",
        "*Minor, Hermetic*\n\nYou cannot resist experimenting.",
        key="new-flaw",
    )

    (entry,) = [e for e in extract_from_section(section) if e.entry_type in {"virtue", "flaw"}]

    assert (entry.entry_type, entry.name) == ("flaw", "Exciting Experimentation")
