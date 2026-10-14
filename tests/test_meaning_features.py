from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse

from apps.catalog.models import CatalogEntry
from apps.catalog.services import rebuild_catalog_for_books
from apps.catalog.similarity import (
    entries_by_description,
    missed_entry_candidates,
    similar_entries,
)
from apps.library.models import Book, Section
from apps.search.embeddings import rebuild_embeddings_for_books
from apps.search.semantic import related_sections
from apps.search.services import rebuild_fts_for_books
from apps.sources.models import SourceSnapshot

SPELLS = {
    "Pilum of Fire": "A spear of flame streaks from the hand toward a target and burns.",
    "Ball of Abysmal Flame": "A ball of flame bursts from the hand and burns the target.",
    "Aura of Rightful Authority": "Listeners obey the commands of the caster as rightful lord.",
    "Calm the Storm": "The winds die down and the rain stops around the caster.",
}
FILLER = " The text continues with details for the storyguide." * 5


@pytest.fixture
def meaning_settings(settings):
    # Hashing vectors stand in for the real model; "1" lets them enable the UI.
    settings.CLAVIS_SEARCH_MODES_ENABLED = "1"
    return settings


def _snapshot(tmp_path: Path) -> SourceSnapshot:
    return SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="meaning",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )


def _book(snap: SourceSnapshot, slug: str) -> Book:
    return Book.objects.create(
        snapshot=snap,
        slug=slug,
        title=slug.title(),
        relative_path=f"reviewed/{slug}.md",
        review_status=Book.ReviewStatus.REVIEWED,
    )


def _section(book: Book, position: int, title: str, body: str, path: str = "") -> Section:
    path = path or f"spells/{title.lower().replace(' ', '-')}"
    return Section.objects.create(
        book=book,
        level=3,
        title=title,
        slug=path.rsplit("/", 1)[-1],
        path=path,
        body_markdown=body,
        content_hash=f"{book.slug}-{path}-{body}",
        stable_id=f"{book.slug}-{position}",
        position=position,
    )


@pytest.fixture
def library(tmp_path: Path, meaning_settings) -> Book:
    snap = _snapshot(tmp_path)
    core = _book(snap, "core")
    for position, (title, text) in enumerate(SPELLS.items()):
        _section(core, position, title, f"CrIg 20\n\nR: Voice, D: Mom, T: Ind\n\n{text}{FILLER}")
    _section(
        core,
        10,
        "Fiery Lance",
        "A lance of flame streaks from the hand toward a target and burns." + FILLER,
        path="stories/fiery-lance",
    )
    rebuild_catalog_for_books([core.id])
    rebuild_fts_for_books([core.id])
    rebuild_embeddings_for_books([core.id])
    return core


def _spells():
    return CatalogEntry.objects.filter(entry_type=CatalogEntry.EntryType.SPELL)


@pytest.mark.django_db
def test_entries_by_description_ranks_closest_first(library: Book):
    ranked = entries_by_description(_spells(), "the winds die down and the rain stops")
    assert ranked[0].name == "Calm the Storm"


@pytest.mark.django_db
def test_list_describe_field(client, library: Book):
    url = reverse("catalog:list", args=["spell"])
    body = client.get(url, {"describe": "spear of flame toward a target"}).content.decode()
    assert 'name="describe"' in body
    assert "closest match" in body
    assert body.index("Pilum of Fire") < body.index("Calm the Storm")


@pytest.mark.django_db
def test_similar_entries_same_type(library: Book):
    pilum = _spells().get(name="Pilum of Fire")
    similar = [e.name for e in similar_entries(pilum)]
    assert "Pilum of Fire" not in similar
    assert similar[0] == "Ball of Abysmal Flame"


@pytest.mark.django_db
def test_missed_candidates_finds_uncatalogued_lookalike(library: Book, settings, monkeypatch):
    monkeypatch.setattr("apps.catalog.similarity.CANDIDATE_MIN_KNOWN", 2)
    names = [c.section.title for c in missed_entry_candidates("spell")]
    assert names and names[0] == "Fiery Lance"


@pytest.mark.django_db
def test_reprint_in_other_book(tmp_path: Path, meaning_settings):
    snap = _snapshot(tmp_path)
    core, supplement = _book(snap, "core"), _book(snap, "supplement")
    text = "Leprosy slowly eats the flesh of the sufferer over many years." + FILLER
    original = _section(core, 0, "Leprosy", text, path="diseases/leprosy")
    _section(supplement, 0, "Leprosy", text, path="appendix/leprosy")
    _section(core, 1, "Quiet Study", "The magus copies a summa." + FILLER, path="lab/quiet")
    rebuild_embeddings_for_books([core.id, supplement.id])
    related = related_sections(original)
    assert [s.book.slug for s in related.reprints] == ["supplement"]
    assert all(s.book.slug != "supplement" for s in related.similar)


@pytest.mark.django_db
def test_keyword_search_falls_back_to_meaning(client, library: Book):
    response = client.get(
        reverse("search:index"), {"q": "zzqx spear flame target", "mode": "keyword"}
    )
    body = response.content.decode()
    assert "No exact matches" in body
    assert "Pilum of Fire" in body


@pytest.mark.django_db
def test_candidates_page(client, library: Book, monkeypatch):
    monkeypatch.setattr("apps.catalog.similarity.CANDIDATE_MIN_KNOWN", 2)
    body = client.get(reverse("catalog:candidates"), {"type": "spell"}).content.decode()
    assert "Possibly missed entries" in body
    assert "Fiery Lance" in body
