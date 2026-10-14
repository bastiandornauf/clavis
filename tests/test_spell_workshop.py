from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse

from apps.catalog.extractors import extract_guidelines
from apps.catalog.services import rebuild_catalog_for_books
from apps.library.models import Book, Section
from apps.search.embeddings import rebuild_embeddings_for_books
from apps.search.semantic import related_sections
from apps.search.services import rebuild_fts_for_books, sections_mentioning
from apps.sources.models import SourceSnapshot

WRAPPED_TABLE = (
    "| Level | Creo Ignem Guideline |\n"
    "| ----- | -------------------- |\n"
    "| 1 | • Create light equivalent to moonlight |\n"
    "| 2 | • Create light equivalent to candlelight  \n"
    "• Heat an object to be warm to the touch |\n"
    "| 5 | • Create a fire doing +10 damage |\n"
)


@pytest.fixture
def book(tmp_path: Path) -> Book:
    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="workshop",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    return Book.objects.create(
        snapshot=snap,
        slug="core",
        title="Core",
        relative_path="reviewed/core.md",
        review_status=Book.ReviewStatus.REVIEWED,
    )


def _section(book: Book, position: int, title: str, path: str, body: str) -> Section:
    return Section.objects.create(
        book=book,
        level=3,
        title=title,
        slug=path.rsplit("/", 1)[-1],
        path=path,
        body_markdown=body,
        content_hash=f"{path}-{len(body)}",
        stable_id=f"ws-{position}",
        position=position,
    )


@pytest.mark.django_db
def test_guideline_table_rows_wrapping_lines(book: Book):
    section = _section(
        book, 0, "Creo Ignem Guidelines", "ignem/creo-ignem-guidelines", WRAPPED_TABLE
    )
    levels = sorted((g.level, g.evidence) for g in extract_guidelines(section))
    assert levels == [
        (1, "Create light equivalent to moonlight"),
        (2, "Create light equivalent to candlelight"),
        (2, "Heat an object to be warm to the touch"),
        (5, "Create a fire doing +10 damage"),
    ]


@pytest.fixture
def workshop_book(book: Book) -> Book:
    _section(book, 0, "Creo Ignem Guidelines", "ignem/creo-ignem-guidelines", WRAPPED_TABLE)
    _section(
        book,
        1,
        "Pilum of Fire",
        "ignem/creo-ignem-spells/pilum-of-fire",
        "CrIg 20\n\nR: Voice, D: Mom, T: Ind\n\nA spear of flame streaks toward a target. "
        + "The fire burns fiercely. " * 10,
    )
    _section(
        book,
        2,
        "Flambeau",
        "houses/flambeau",
        "Many Flambeau magi learn Pilum of Fire as apprentices. " + "They love fire. " * 15,
    )
    rebuild_catalog_for_books([book.id])
    rebuild_fts_for_books([book.id])
    return book


@pytest.mark.django_db
def test_workshop_grid_and_cell(client, workshop_book: Book):
    grid = client.get(reverse("catalog:workshop")).content.decode()
    assert "Creo Ignem: 1 spells, 4 guidelines" in grid

    cell = client.get(reverse("catalog:workshop_cell", args=["creo", "ignem"])).content.decode()
    assert "Pilum of Fire" in cell
    assert "Create light equivalent to moonlight" in cell
    assert client.get(reverse("catalog:workshop_cell", args=["creo", "foo"])).status_code == 404


@pytest.mark.django_db
def test_spell_detail_links_workshop_and_mentions(client, workshop_book: Book):
    body = client.get(reverse("catalog:detail", args=["spell", "pilum-of-fire"])).content.decode()
    assert "All Creo Ignem" in body
    assert "Mentioned in" in body
    assert "Flambeau" in body


@pytest.mark.django_db
def test_sections_mentioning_excludes_definition(workshop_book: Book):
    hits = sections_mentioning("Pilum of Fire", exclude_stable_ids={"ws-1"})
    assert [hit.section.title for hit in hits] == ["Flambeau"]


@pytest.mark.django_db
def test_related_sections_uses_stored_vectors(workshop_book: Book):
    rebuild_embeddings_for_books([workshop_book.id])
    pilum = Section.objects.get(stable_id="ws-1")
    related = [other.title for other in related_sections(pilum).similar]
    assert "Pilum of Fire" not in related
    assert "Flambeau" in related


@pytest.mark.django_db
def test_sources_page_reports_meaning_index(client, workshop_book: Book):
    body = client.get(reverse("sources:status")).content.decode()
    assert "Meaning search" in body
    assert "Not built" in body
    rebuild_embeddings_for_books([workshop_book.id])
    body = client.get(reverse("sources:status")).content.decode()
    assert "Ready: 3 of 3 sections" in body
