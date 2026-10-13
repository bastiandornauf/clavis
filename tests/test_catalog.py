from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse

from apps.catalog.models import CatalogEntry
from apps.sources.services import import_sources


@pytest.mark.django_db
def test_rules_extract_spells_virtues_flaws(fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)

    spells = CatalogEntry.objects.filter(entry_type="spell")
    virtues = CatalogEntry.objects.filter(entry_type="virtue")
    flaws = CatalogEntry.objects.filter(entry_type="flaw")

    assert spells.filter(name="Pilum of Fire").exists()
    pilum = spells.get(name="Pilum of Fire")
    assert pilum.level == 20
    assert pilum.range.lower().startswith("voice")

    assert virtues.filter(name="Second Sight").exists()
    assert virtues.get(name="Second Sight").magnitude == "Minor"

    assert flaws.filter(name="Necessary Condition").exists()
    assert flaws.get(name="Necessary Condition").magnitude == "Major"
    assert flaws.filter(name="Magical Air").exists()

    # Art & Academe–style: category-first italics + bold blocks under chapter headings.
    doctor = virtues.get(name="Doctor in (Faculty)")
    assert doctor.magnitude == "Major"
    assert doctor.category == "Social Status"
    assert virtues.filter(name="Baccalaureus").exists()
    assert virtues.get(name="Jurist").magnitude == "Minor"
    assert virtues.get(name="Nuntius").magnitude == "Free"
    assert virtues.filter(name="Prestigious Student").exists()
    assert flaws.get(name="Failed Student").category == "Story"
    assert flaws.filter(name="Poor Disputer").exists()

    seeds = CatalogEntry.objects.filter(entry_type="story_seed")
    assert seeds.filter(name="Blood Enemies").exists()
    assert seeds.filter(name="The Glade's Secrets").exists()
    prose = seeds.filter(name__endswith="…").first()
    assert prose is not None
    assert prose.name.startswith("A Bjornaer")
    assert len(prose.name) <= 24
    assert "scapegoat" in prose.summary.lower()

    creature = CatalogEntry.objects.get(entry_type="creature", name="Elemental of Flame")
    assert creature.level == 20
    assert creature.category == "Magic"
    assert creature.form == "Ignem"
    assert "Size" in creature.summary

    # Might line after a short prose lead still counts (CREATURE_LEAD_WINDOW).
    delayed = CatalogEntry.objects.get(entry_type="creature", name="Shade of the Old Oak")
    assert delayed.level == 15
    assert delayed.form == "Herbam"
    assert delayed.category == "Magic"

    # Blockquote callout with ``**Faerie Might:**`` (Contested Isle–style).
    donn = CatalogEntry.objects.get(entry_type="creature", name="Donn")
    assert donn.level == 50
    assert donn.category == "Faerie"
    assert donn.form == "Corpus"

    character = CatalogEntry.objects.get(entry_type="character", name__icontains="Daria La Gris")
    assert "Daria La Gris" in character.name
    assert character.category == "Tremere"
    assert "Age 67" in character.summary

    guidelines = CatalogEntry.objects.filter(entry_type="guideline")
    assert guidelines.filter(name__startswith="Creo Ignem 1:").exists()
    fire = guidelines.get(name__contains="Create a fire doing +10 damage")
    assert fire.technique == "Creo"
    assert fire.form == "Ignem"
    assert fire.level == 5

    abilities = CatalogEntry.objects.filter(entry_type="ability")
    awareness = abilities.get(name="Awareness")
    assert awareness.category == "General"
    ceremony = abilities.get(name="Ceremony*")
    assert ceremony.category == "Supernatural"
    assert "\\" not in ceremony.name


@pytest.mark.django_db
def test_character_house_from_section_title(tmp_path: Path):
    from apps.catalog.extractors import extract_characters
    from apps.library.models import Book, Section
    from apps.sources.models import SourceSnapshot

    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="test",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    book = Book.objects.create(
        snapshot=snap,
        slug="against-the-dark",
        title="Against the Dark",
        relative_path="reviewed/x.md",
    )

    def make_section(*, title: str, slug: str, stable_id: str, position: int) -> Section:
        return Section.objects.create(
            book=book,
            level=4,
            title=title,
            slug=slug,
            path=f"magi/{slug}",
            body_markdown=(
                "**Age:** 41 (apparent age: 36)\n"
                "**Personality Traits:** Ambitious +3, Restless +3, Loyal +2.\n\n"
                "A short writeup.\n"
            ),
            content_hash=stable_id,
            stable_id=stable_id,
            position=position,
        )

    adulio = extract_characters(
        make_section(
            title="Adulio of House Tremere",
            slug="adulio-of-house-tremere",
            stable_id="adulio-test",
            position=0,
        )
    )
    assert len(adulio) == 1
    assert adulio[0].name == "Adulio of House Tremere"
    assert adulio[0].category == "Tremere"

    angelus = extract_characters(
        make_section(
            title="Angelus of Ex Miscellanea",
            slug="angelus-of-ex-miscellanea",
            stable_id="angelus-test",
            position=1,
        )
    )
    assert len(angelus) == 1
    assert angelus[0].name == "Angelus of Ex Miscellanea"
    assert angelus[0].category == "Ex Miscellanea"

    valgravian = extract_characters(
        make_section(
            title="Archmage Valgravian of Jerbiton",
            slug="archmage-valgravian-of-jerbiton",
            stable_id="valgravian-test",
            position=2,
        )
    )
    assert len(valgravian) == 1
    assert valgravian[0].name == "Archmage Valgravian of Jerbiton"
    assert valgravian[0].category == "Jerbiton"


@pytest.mark.django_db
def test_contents_section_does_not_harvest_story_seed_index(tmp_path: Path):
    """TOC pages list seed titles; those must not become catalog entries."""
    from apps.catalog.extractors import extract_story_seeds
    from apps.library.models import Book, Section
    from apps.sources.models import SourceSnapshot

    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="test",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    book = Book.objects.create(
        snapshot=snap,
        slug="against-the-dark",
        title="Against the Dark",
        relative_path="reviewed/x.md",
    )
    section = Section.objects.create(
        book=book,
        level=1,
        title="Contents",
        slug="contents",
        path="contents",
        body_markdown=(
            "**Chapter 1**\n"
            "Story Seed: A Snake in the Classroom\n"
            "Story Seed: The Ice Cave\n"
        ),
        content_hash="x",
        stable_id="contents-test",
        position=0,
    )
    assert extract_story_seeds(section) == []


@pytest.mark.django_db
def test_lexicon_pages(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)

    index = client.get(reverse("catalog:index"))
    assert index.status_code == 200
    assert b"Virtues" in index.content
    assert b"Creatures" in index.content
    assert b"Characters" in index.content

    virtues = client.get(reverse("catalog:list", args=["virtue"]))
    assert virtues.status_code == 200
    assert b"Second Sight" in virtues.content

    creatures = client.get(reverse("catalog:list", args=["creature"]))
    assert creatures.status_code == 200
    assert b"Elemental of Flame" in creatures.content

    characters = client.get(reverse("catalog:list", args=["character"]))
    assert characters.status_code == 200
    assert b"Daria La Gris" in characters.content

    detail = client.get(reverse("catalog:detail", args=["spell", "pilum-of-fire"]))
    assert detail.status_code == 200
    assert b"Open in reader" in detail.content

    creature_detail = client.get(
        reverse("catalog:detail", args=["creature", "elemental-of-flame"])
    )
    assert creature_detail.status_code == 200
    assert b"Might" in creature_detail.content
    assert b"Realm" in creature_detail.content
