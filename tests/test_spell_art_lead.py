from __future__ import annotations

from pathlib import Path

import pytest

from apps.catalog.extractors import NON_HERMETIC, extract_from_section, extract_spell
from apps.library.models import Book, Section
from apps.sources.models import SourceSnapshot


@pytest.fixture
def book(tmp_path: Path) -> Book:
    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="lead",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    return Book.objects.create(
        snapshot=snap, slug="moh", title="Magi of Hermes", relative_path="reviewed/moh.md"
    )


def _section(book: Book, title: str, body: str) -> Section:
    return Section.objects.create(
        book=book,
        level=4,
        title=title,
        slug=title.lower().replace(" ", "-"),
        path=f"new-spells/{title.lower().replace(' ', '-')}",
        body_markdown=body,
        content_hash=title,
        stable_id=f"lead-{title}",
        position=0,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("lead", "technique", "form", "level"),
    [
        ("CrHe 10", "Creo", "Herbam", 10),
        ("MuCo(He) 5", "Muto", "Corpus", 5),
        ("**ReHe 48**", "Rego", "Herbam", 48),
        ("Mulm 45", "Muto", "Imaginem", 45),
        ("PeVi Gen", "Perdo", "Vim", None),
        ("Re(Cr)Te(He) 20", "Rego", "Terram", 20),
        ("CrIg Level 15", "Creo", "Ignem", 15),
    ],
)
def test_abbreviated_art_lead(book: Book, lead, technique, form, level):
    section = _section(
        book,
        "Statim Sessio",
        f"{lead}\n\nR: Touch, D: Sun, T: Ind\n\nThis spell creates a comfortable chair.",
    )
    spell = extract_spell(section)
    assert spell is not None
    assert (spell.technique, spell.form, spell.level) == (technique, form, level)
    assert spell.level_general == (level is None)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("title", "body", "expected"),
    [
        (
            "Absent Mind of the Scholar",
            "**MuMe** 10\n\n**R:** Touch, **D:** Sun, **T:** Individual\n\nChanges memory.",
            ("Muto", "Mentem", 10, False, "Touch", "Individual"),
        ),
        (
            "Fingers for Eyes",
            "**InIm** 5\n\n**R:** Touch, **D:** Diameter, **T:** Room\n\nSee the Room.",
            ("Intellego", "Imaginem", 5, False, "Touch", "Room"),
        ),
        (
            "Aura of Beguiling Appearance",
            "MuIm 15 Pen 0, 12/day R: Touch, D: Sun, T: Ind\n\nA variant of the spell.",
            ("Muto", "Imaginem", 15, False, "Touch", "Ind"),
        ),
        (
            "Sense the Airy Trespass",
            "InVi 50  \nPenetration +32, constant effect   \nR: Touch D: Sun, T Room  \n"
            "This enchantment detects entities.",
            ("Intellego", "Vim", 50, False, "Touch", "Room"),
        ),
        (
            "Wrappings of Metaphysical Iron",
            "ReVi Gen R: Touch, D: Sun, T: Individual\n\nThis spell wards an object.",
            ("Rego", "Vim", None, True, "Touch", "Individual"),
        ),
    ],
)
def test_art_led_writeups_with_odd_param_lines(book: Book, title, body, expected):
    spell = extract_spell(_section(book, title, body))
    assert spell is not None
    assert (
        spell.technique,
        spell.form,
        spell.level,
        spell.level_general,
        spell.range,
        spell.target.strip(),
    ) == expected


@pytest.mark.django_db
def test_top_level_section_needs_art_lead(book: Book):
    section = _section(book, "Overview", "R: Touch, D: Sun, T: Ind\n\nNot a spell heading.")
    section.level = 1
    assert extract_spell(section) is None
    section.body_markdown = "ReVi Gen R: Touch, D: Sun, T: Individual\n\nWards an object."
    assert extract_spell(section) is not None


@pytest.mark.django_db
def test_general_level_heading(book: Book):
    band = _section(book, "GENERAL", "")
    spell = _section(book, "Aegis of the Hearth", "R: Touch, D: Year, T: Bound, Ritual\n\nWards.")
    spell.parent = band
    spell.save()
    entry = extract_spell(spell)
    assert entry.level is None and entry.level_general


@pytest.mark.django_db
def test_level_after_target(book: Book):
    section = _section(
        book,
        "(Mental Characteristic) of the Sage",
        "R: Touch, D: Mom, T: Ind, Level 35, Ritual\n\nFour variations.",
    )
    assert extract_spell(section).level == 35


@pytest.mark.django_db
def test_narrative_bold_params_without_art_lead_stay_out(book: Book):
    section = _section(
        book,
        "Magi",
        "**Henri de Tours**\n\n**R:** Eye, **D:** Sun, **T:** Individual, **Level 25**\n\nTrades.",
    )
    assert extract_spell(section) is None


@pytest.mark.django_db
def test_art_in_title_parentheses(book: Book):
    section = _section(
        book,
        "Air of Friendly Magic (MuVi 30)",
        "R: Per, D: Sun, T: Group/Room, Ritual\n\nThis spell blends traditions.",
    )
    spell = extract_spell(section)
    assert (spell.technique, spell.form, spell.level) == ("Muto", "Vim", 30)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lead", ["Level 10", "Evocation/Beguile 15", "Threads of Fate Ease Factor 30"]
)
def test_foreign_tradition_spell(book: Book, lead):
    section = _section(
        book,
        "The Blade of Menhit",
        f"{lead}\n\nR: Seen Stranger, D: Mom, T: Ind\n\nThis incantation wounds.",
    )
    spell = extract_spell(section)
    assert spell is not None
    assert spell.technique == ""
    assert spell.category == NON_HERMETIC


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lead",
    [
        "1 point, Init: Qik–1, Animal\n\nR: Per, D: Sun, T: Ind",
        "R: Per, D: Sun, T: Ind\n\nMentem, Pen +0, 1 use/day",
    ],
)
def test_powers_are_not_spells(book: Book, lead):
    section = _section(book, "Resistance to Claws", f"{lead}\n\nThe coat hardens.")
    assert extract_spell(section) is None


@pytest.mark.django_db
def test_lowercase_prose_is_not_an_art_lead(book: Book):
    section = _section(
        book,
        "Quiet Note",
        "Here 10 magi gathered.\n\nR: Touch, D: Sun, T: Ind\n\nNot a lead.",
    )
    spell = extract_spell(section)
    assert spell is None or spell.technique == ""


@pytest.mark.django_db
def test_enchanted_item_with_spell_style_effect_keeps_item(book: Book):
    section = _section(
        book,
        "Vermin Ward",
        "**ReAn** 24  \n**Pen** +0, constant effect  \n**R:** Touch, **D:** Sun, "
        "**T:** Structure\n\nThis enchanted item, a carved statue of a rat, keeps "
        "animals out.\n\n(Base 2, +1 Touch, +2 Sun, +3 Structure; +4 Constant Effect)",
    )
    entries = extract_from_section(section)
    assert sorted(entry.entry_type for entry in entries) == ["item", "spell"]
    spell = next(entry for entry in entries if entry.entry_type == "spell")
    assert spell.device_effect


@pytest.mark.django_db
def test_mixed_bold_params_after_art_lead(book: Book):
    section = _section(
        book,
        "Reparation of the Wounded Vessel",
        "**CrHe(Te)** 45\n\nR: Touch, **D:** Momentary, **T:** Structure, Ritual\n\nRepairs.",
    )
    spell = extract_spell(section)
    assert (spell.technique, spell.form, spell.level, spell.target.strip()) == (
        "Creo",
        "Herbam",
        45,
        "Structure",
    )


@pytest.mark.django_db
def test_bold_params_opening_section_with_own_level(book: Book):
    section = _section(
        book,
        "The Discerning Eye",
        "**R:** Per, **D:** Sun, **T:** Vision, **Level Gen**\n\nAn enhanced version.",
    )
    spell = extract_spell(section)
    assert spell is not None and spell.level_general


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Rego Córporem 10", "Rego Corpus 10"),
        ("Creo Imágonem, Intéllego Animál", "Creo Imaginem, Intellego Animal"),
        ("MUTO CORPOREM", "MUTO CORPUS"),
        ("Indrechtach an t-Éigse", "Indrechtach an t-Éigse"),
    ],
)
def test_art_names_are_normalized(raw, expected):
    from apps.catalog.extractors import normalize_art_names

    assert normalize_art_names(raw) == expected


@pytest.mark.django_db
def test_accented_art_parent_heading(book: Book):
    parent = _section(book, "Rego Córporem Spells", "")
    spell = _section(book, "Despair of the Quivering Manacles", "R: Touch, D: Sun, T: Ind")
    spell.parent = parent
    spell.save()
    entry = extract_spell(spell)
    assert (entry.technique, entry.form) == ("Rego", "Corpus")
