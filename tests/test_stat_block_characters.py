from __future__ import annotations

from pathlib import Path

import pytest

from apps.catalog.extractors import extract_from_section
from apps.library.models import Book, Section
from apps.sources.models import SourceSnapshot

ROME_TEMPLATE = """Intelligence +2 Presence +1

Perception -1 Communication +2

Strength -2 Dexterity -2

Stamina +2 Ouickness -2

AGE: 22

VIRTUES & FLAWS: Learn From Mistakes (Certámen) +1, Knack (Certámen) +2

ABILITIES: Speak Latin 5, Magic Theory 5, Parma Magica 3, Certámen 6

CONFIDENCE: 6

PERSONALITY TRAITS: Brave -1, Liar +3

TECHNIQUES & FORMS: Creo 4, Intéllego 0, Rego 7, Córporem 6, Imágonem 1

SPELLS: Pilum of Fire (Creo Ignem 20)

When your master came to the Roman Tribunal long ago, he was full of hope.
"""

CORE_TEMPLATE = """**Characteristics:** Int 0, Per 0, Pre 0, Com 0, Str +2, Sta +2, Dex +1, Qik +1

**Size:** 0

**Age:** 25 (25)

**Virtues and Flaws:** Large; Berserk

**Abilities:** Brawl 3 (fist), Great Weapon 5 (axe)
"""


def _book(tmp_path: Path) -> Book:
    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="stat",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    return Book.objects.create(
        snapshot=snap, slug="stat-book", title="Stat Book", relative_path="stat.md"
    )


def _section(book: Book, title: str, body: str, path: str = "people/sec") -> Section:
    return Section.objects.create(
        book=book,
        level=4,
        title=title,
        slug=path.rsplit("/", 1)[-1],
        path=path,
        body_markdown=body,
        content_hash="h",
        stable_id=path,
        position=0,
    )


def _characters(section: Section):
    return [entry for entry in extract_from_section(section) if entry.entry_type == "character"]


@pytest.mark.django_db
def test_uppercase_template_block_is_a_template_character(tmp_path: Path):
    section = _section(
        _book(tmp_path),
        "Independent Rebel (Tremere)",
        ROME_TEMPLATE,
        path="appendix-templates/magus-vocations/independent-rebel-tremere",
    )

    (entry,) = _characters(section)

    assert entry.name == "Independent Rebel (Tremere)"
    assert entry.category == "Template"
    assert entry.summary == "Template; Tremere; Age 22"


@pytest.mark.django_db
def test_bold_stat_block_without_personality_line(tmp_path: Path):
    section = _section(
        _book(tmp_path),
        "The Berserker",
        CORE_TEMPLATE,
        path="character-templates/grog-templates/the-berserker",
    )

    (entry,) = _characters(section)

    assert entry.name == "The Berserker"
    assert entry.category == "Template"


@pytest.mark.django_db
def test_stat_block_outside_templates_keeps_house_category(tmp_path: Path):
    section = _section(_book(tmp_path), "Petrus, Magus ex Bonisagus", CORE_TEMPLATE)

    (entry,) = _characters(section)

    assert entry.category == "Bonisagus"


@pytest.mark.django_db
def test_might_before_characteristics_is_not_a_character(tmp_path: Path):
    body = "*A quote about ravens.*\n\n**Magic Might:** 9 (Animal)\n\n" + CORE_TEMPLATE
    section = _section(_book(tmp_path), "Raven of Virtue", body)

    assert _characters(section) == []


@pytest.mark.django_db
def test_power_before_stat_block_is_not_a_character(tmp_path: Path):
    body = "Incantation/Effusion, Level 70 **R:** Eye, **D:** Forsaken, **T:** Ind\n\n"
    section = _section(_book(tmp_path), "My Symbol Shall Come Unto Me", body + CORE_TEMPLATE)

    assert _characters(section) == []


@pytest.mark.django_db
@pytest.mark.parametrize("title", ["Attunements:", "Minor Hermetic Flaw", "Human Form"])
def test_rule_titles_over_stat_blocks_are_not_characters(tmp_path: Path, title: str):
    section = _section(_book(tmp_path), title, CORE_TEMPLATE)

    assert _characters(section) == []
