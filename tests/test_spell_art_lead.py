from __future__ import annotations

from pathlib import Path

import pytest

from apps.catalog.extractors import NON_HERMETIC, extract_spell
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
