from __future__ import annotations

from pathlib import Path

import pytest

from apps.catalog.extractors import extract_from_section
from apps.catalog.models import CatalogEntry
from apps.catalog.saga_extractors import (
    extract_beast,
    extract_boons_and_hooks,
    extract_item,
    extract_organization,
    extract_place,
)
from apps.library.models import Book, Section
from apps.sources.models import SourceSnapshot


def _book(tmp_path: Path, slug: str = "saga-book") -> Book:
    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="saga",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    return Book.objects.create(
        snapshot=snap,
        slug=slug,
        title="Saga Book",
        relative_path="reviewed/saga.md",
    )


def _section(book: Book, **kwargs) -> Section:
    defaults = {
        "level": 3,
        "slug": "sec",
        "path": "sec",
        "body_markdown": "",
        "content_hash": "h",
        "stable_id": "sid",
        "position": 0,
    }
    defaults.update(kwargs)
    return Section.objects.create(book=book, **defaults)


@pytest.mark.django_db
def test_extract_mundane_beast(tmp_path: Path):
    book = _book(tmp_path)
    section = _section(
        book,
        title="Adder (Viperis)",
        path="bestiary/mundane-beasts/adder",
        body_markdown=(
            "Characteristics: Cun -1, Per -2, Pre -6, Com -6, Str -8, Sta +2, Dex +2, Qik +3\n\n"
            "Size: -4\n\n"
            "Qualities: Ambush Predator, Venomous\n\n"
            "A common venomous snake.\n"
        ),
        stable_id="adder",
    )
    beast = extract_beast(section)
    assert beast is not None
    assert beast.entry_type == "beast"
    assert beast.category == ""
    assert "Size" in beast.summary
    # Might creatures must not become beasts.
    magical = _section(
        book,
        title="Flame Spirit",
        path="spirits/flame",
        body_markdown="**Magic Might:** 10 (Ignem)\n\nCharacteristics: Int 0, Per 0\n",
        stable_id="flame",
        slug="flame",
        position=1,
    )
    assert extract_beast(magical) is None
    assert extract_from_section(magical)[0].entry_type == "creature"


@pytest.mark.django_db
def test_extract_boons_hooks_core_and_covenants_shapes(tmp_path: Path):
    book = _book(tmp_path)
    major = _section(
        book,
        title="Major Site Boons",
        path="boons/major-site",
        body_markdown=(
            "**Aura**: Limited aura boost.\n\n"
            "**Immunity:** Immune to a form of damage.\n"
        ),
        stable_id="major-site",
    )
    entries = extract_boons_and_hooks(major)
    assert {e.name for e in entries} >= {"Aura", "Immunity"}
    assert all(e.entry_type == "boon" and e.magnitude == "Major" for e in entries)
    assert entries[0].category == "Site"

    minor_hooks = _section(
        book,
        title="Minor Hooks",
        path="hooks/minor",
        body_markdown=(
            "Contested Resource: Access to a resource is contested.\n\n"
            "**Poverty:** The covenant is poor.\n"
        ),
        stable_id="minor-hooks",
        slug="minor-hooks",
        position=1,
    )
    hooks = extract_boons_and_hooks(minor_hooks)
    names = {e.name for e in hooks}
    assert "Contested Resource" in names
    assert "Poverty" in names
    assert all(e.entry_type == "hook" for e in hooks)


@pytest.mark.django_db
def test_extract_applied_aegis_boons(tmp_path: Path):
    book = _book(tmp_path)
    section = _section(
        book,
        title="Boons & Hooks",
        path="jardin/boons",
        body_markdown=(
            "**Mystical Allies (Major Surroundings Boon)**: Merfolk allies.\n\n"
            "**Criminals (Minor Residents Boon)**: Willing risk-takers.\n"
        ),
        stable_id="aegis-boons",
    )
    entries = extract_boons_and_hooks(section)
    assert len(entries) == 2
    allies = next(e for e in entries if e.name == "Mystical Allies")
    assert allies.magnitude == "Major"
    assert allies.category == "Surroundings"


@pytest.mark.django_db
def test_extract_organization_house_and_office(tmp_path: Path):
    book = _book(tmp_path)
    house = _section(
        book,
        level=3,
        title="House Bonisagus",
        path="order/houses/house-bonisagus",
        body_markdown=(
            "House Bonisagus is split into political and theoretical strands. "
            "They push Hermetic theory and keep the Order together.\n"
        ),
        stable_id="house-bonisagus",
    )
    org = extract_organization(house)
    assert org is not None
    assert org.category == ""
    assert "Bonisagus" in org.form

    office = _section(
        book,
        level=3,
        title="Colentes Arcanorum",
        path="chapter-one-house-bonisagus/house-organization-in-1220/colentes-arcanorum",
        body_markdown=(
            "The Colentes Arcanorum are five magi Bonisagi responsible for "
            "disseminating recent research of the House to other lineages.\n"
        ),
        stable_id="colentes",
        slug="colentes",
        position=1,
    )
    office_entry = extract_organization(office)
    assert office_entry is not None
    assert office_entry.form == "Bonisagus"


@pytest.mark.django_db
def test_extract_place_covenant_and_season_example(tmp_path: Path):
    book = _book(tmp_path)
    jardin = _section(
        book,
        level=1,
        title="Jardin: A Summer Covenant",
        path="jardin-a-summer-covenant",
        body_markdown=(
            "Jardin is a Summer covenant in Provençal. The Magic aura of the site is 3.\n"
        ),
        stable_id="jardin",
    )
    place = extract_place(jardin)
    assert place is not None
    assert place.category == ""

    vernus = _section(
        book,
        level=4,
        title="Vernus",
        path="chapter-6-covenants/covenant-seasons/spring/vernus",
        body_markdown="Vernus is a Spring covenant example used in the core rules.\n",
        stable_id="vernus",
        slug="vernus",
        position=1,
    )
    assert extract_place(vernus) is not None


@pytest.mark.django_db
def test_extract_enchanted_item(tmp_path: Path):
    book = _book(tmp_path)
    item = _section(
        book,
        level=5,
        title="Chest of Good Food",
        path="zenodochium/chest",
        body_markdown=(
            "This enchanted item is a large chest carved with scenes of feasting. "
            "Food made from animal or plant matter placed inside is preserved.\n"
        ),
        stable_id="chest",
    )
    entry = extract_item(item)
    assert entry is not None
    assert entry.entry_type == "item"
    assert CatalogEntry.EntryType.ITEM in CatalogEntry.EntryType.values


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("body", "use", "art"),
    [
        (
            "ReCo 30\n\nPen +12, 12/day\n\nR: Touch, D: Mom, T: Ind\n\nHurls the target.",
            "12/day",
            ("Rego", "Corpus", 30),
        ),
        (
            "**CrAu** 40  \n\n**Pen** 0, 24 uses per day  \n\n**R:** Touch, **D:** Sun, "
            "**T:** Ind\n\nKeeps the rain off.",
            "24/day",
            ("Creo", "Auram", 40),
        ),
        (
            "InVi 50  \nPenetration +32, constant effect   \nR: Touch D: Sun, T Room  \n"
            "Detects magical beings.",
            "Constant effect",
            ("Intellego", "Vim", 50),
        ),
        (
            "CrIm 28\n\nPen +0, unlimited uses/day\n\nR: Touch, D: Sun, T: Ind\n\nWakes.",
            "Unlimited uses/day",
            ("Creo", "Imaginem", 28),
        ),
    ],
)
def test_device_effect_use_line_makes_item(tmp_path: Path, body, use, art):
    section = _section(_book(tmp_path), level=4, title="Some Effect", body_markdown=body)
    entry = extract_item(section)
    assert entry is not None
    assert entry.category == use
    assert (entry.technique, entry.form, entry.level) == art


@pytest.mark.django_db
def test_device_heading_makes_item(tmp_path: Path):
    section = _section(
        _book(tmp_path),
        level=2,
        title="Talisman: Staff of Ranulf",
        body_markdown="A gnarled oak staff bound with bronze.",
    )
    entry = extract_item(section)
    assert (entry.name, entry.category) == ("Staff of Ranulf", "Talisman")


@pytest.mark.django_db
def test_theurgy_daimon_effect_is_not_an_item(tmp_path: Path):
    section = _section(
        _book(tmp_path),
        level=5,
        title="Apollo's Luminescent Blessing",
        path="azai/example-azai-effects/apollo-s-luminescent-blessing",
        body_markdown="R: Touch, D: Conc, T: Ind Ignem, Pen +4, 6 uses/day\n\nGlows.",
    )
    assert extract_item(section) is None


@pytest.mark.django_db
def test_power_cost_line_is_not_an_item(tmp_path: Path):
    section = _section(
        _book(tmp_path),
        level=4,
        title="Lesser Power",
        body_markdown="1 point, Init +2, Corpus: The demon causes pain. Pen +0 against.",
    )
    assert extract_item(section) is None
