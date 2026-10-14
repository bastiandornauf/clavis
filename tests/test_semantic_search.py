from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse

from apps.library.models import Book, Section
from apps.search.embeddings import (
    HashingEmbedder,
    rebuild_embeddings_for_books,
    semantic_search_available,
)
from apps.search.models import SectionEmbedding
from apps.search.semantic import (
    _semantic_snippet,
    search_sections_hybrid,
    search_sections_semantic,
)
from apps.search.services import search_sections
from apps.sources.models import SourceSnapshot
from apps.sources.services import import_sources


@pytest.mark.django_db
def test_hashing_embeddings_rebuild_and_semantic_hit(tmp_path: Path):
    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="embed",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    book = Book.objects.create(
        snapshot=snap,
        slug="embed-book",
        title="Embed Book",
        relative_path="reviewed/embed.md",
        review_status=Book.ReviewStatus.REVIEWED,
    )
    fire = Section.objects.create(
        book=book,
        level=2,
        title="Pilum of Fire",
        slug="pilum-of-fire",
        path="spells/pilum",
        body_markdown="A spear of flame streaks from your hand toward a target.",
        content_hash="fire",
        stable_id="embed-fire",
        position=0,
    )
    Section.objects.create(
        book=book,
        level=2,
        title="Quiet Study",
        slug="quiet-study",
        path="lab/quiet",
        body_markdown="The magus copies a summa in candlelight without interruption.",
        content_hash="quiet",
        stable_id="embed-quiet",
        position=1,
    )

    updated = rebuild_embeddings_for_books([book.id], embedder=HashingEmbedder())
    assert updated == 2
    assert SectionEmbedding.objects.filter(book=book).count() == 2

    hits = search_sections_semantic("spear of flame", limit=5)
    assert hits
    assert any(hit.section.id == fire.id for hit in hits)
    assert hits[0].section.id == fire.id


@pytest.mark.django_db
def test_hybrid_search_combines_modes(fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    book_ids = list(Book.objects.values_list("id", flat=True))
    rebuild_embeddings_for_books(book_ids)
    keyword = search_sections("Pilum", limit=10)
    hybrid = search_sections_hybrid("Pilum", limit=10)
    assert keyword
    assert hybrid
    assert any(hit.section.display_title == "Pilum of Fire" for hit in hybrid)


@pytest.mark.django_db
def test_search_page_hides_mode_selector_without_index(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    response = client.get(reverse("search:index"), {"q": "Pilum", "mode": "hybrid"})
    assert response.status_code == 200
    body = response.content.decode()
    assert "Pilum of Fire" in body
    assert 'name="mode"' not in body


@pytest.mark.django_db
def test_hashing_index_alone_does_not_enable_modes(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    rebuild_embeddings_for_books(list(Book.objects.values_list("id", flat=True)))
    assert not semantic_search_available()


@pytest.mark.django_db
def test_search_page_offers_modes_when_index_exists(
    client, settings, fixture_markdown_dir: Path
):
    settings.CLAVIS_SEARCH_MODES_ENABLED = "1"
    import_sources(sync=False, local_path=fixture_markdown_dir)
    rebuild_embeddings_for_books(list(Book.objects.values_list("id", flat=True)))
    response = client.get(reverse("search:index"), {"q": "Pilum", "mode": "semantic"})
    body = response.content.decode()
    assert 'name="mode"' in body
    assert '<option value="semantic" selected>' in body
    assert "Pilum of Fire" in body


@pytest.mark.django_db
def test_reimport_reuses_unchanged_vectors(settings, fixture_markdown_dir: Path, monkeypatch):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    rebuild_embeddings_for_books(list(Book.objects.values_list("id", flat=True)))
    count = SectionEmbedding.objects.count()
    assert count

    embedded: list[int] = []
    original = HashingEmbedder.embed_documents

    def counting(self, texts):
        embedded.append(len(texts))
        return original(self, texts)

    monkeypatch.setattr(HashingEmbedder, "embed_documents", counting)
    settings.CLAVIS_SEARCH_MODES_ENABLED = "1"
    import_sources(sync=False, local_path=fixture_markdown_dir)

    assert SectionEmbedding.objects.count() == count
    assert sum(embedded) == 0
    assert semantic_search_available()


def test_semantic_snippet_is_escaped():
    section = Section(title="X", body_markdown="<script>alert(1)</script> fire spear")
    assert "<script>" not in _semantic_snippet(section, "fire")
