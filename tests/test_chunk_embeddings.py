from __future__ import annotations

from pathlib import Path

import pytest

from apps.library.models import Book, Section
from apps.search.embeddings import (
    CHUNK_CHARS,
    CHUNK_FIRST_START,
    HashingEmbedder,
    rebuild_embeddings_for_books,
    section_chunks,
)
from apps.search.models import SectionChunkEmbedding
from apps.search.semantic import search_sections_semantic
from apps.sources.models import SourceSnapshot

FILLER = "The covenant keeps its grain stores dry through the long winter. " * 60
TAIL = (
    "Deep in the archive a basilisk sleeps beneath the library, its gaze turning "
    "careless librarians to stone."
)


@pytest.fixture
def book(tmp_path: Path) -> Book:
    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="chunks",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    return Book.objects.create(
        snapshot=snap, slug="chunk-book", title="Chunk Book", relative_path="reviewed/c.md"
    )


def _section(book: Book, title: str, body: str, position: int = 0) -> Section:
    return Section.objects.create(
        book=book,
        level=2,
        title=title,
        slug=title.lower().replace(" ", "-"),
        path=title.lower().replace(" ", "-"),
        body_markdown=body,
        content_hash=f"{title}-{len(body)}",
        stable_id=f"chunk-{title}",
        position=position,
    )


def test_short_sections_have_no_chunks():
    assert section_chunks(Section(title="Short", body_markdown="x " * 500)) == []


def test_chunks_cover_the_tail_without_cutting_words():
    body = FILLER + FILLER + TAIL
    chunks = section_chunks(Section(title="Long", body_markdown=body))
    assert chunks
    assert chunks[0][0] >= CHUNK_FIRST_START
    assert chunks[-1][1] == len(body)
    for start, end, text in chunks:
        assert end - start <= CHUNK_CHARS
        assert body[start - 1].isspace()
        assert text.startswith("Long\n")


@pytest.mark.django_db
def test_search_finds_text_only_in_long_section_tail(book: Book):
    long = _section(book, "Covenant Stores", FILLER + FILLER + TAIL)
    _section(book, "Stone Gaze", "A short note on petrifying glances in old tales.", 1)

    rebuild_embeddings_for_books([book.id], embedder=HashingEmbedder())
    assert SectionChunkEmbedding.objects.filter(section=long).exists()

    hits = search_sections_semantic(
        "basilisk sleeps beneath the library turning librarians to stone", limit=5
    )
    assert hits[0].section.id == long.id
    assert "basilisk" in hits[0].snippet


@pytest.mark.django_db
def test_unchanged_long_sections_are_not_re_embedded(book: Book, monkeypatch):
    _section(book, "Covenant Stores", FILLER + FILLER + TAIL)
    rebuild_embeddings_for_books([book.id], embedder=HashingEmbedder())
    count = SectionChunkEmbedding.objects.count()

    calls: list[int] = []
    original = HashingEmbedder.embed_documents

    def counting(self, texts):
        calls.append(len(texts))
        return original(self, texts)

    monkeypatch.setattr(HashingEmbedder, "embed_documents", counting)
    rebuild_embeddings_for_books([book.id], embedder=HashingEmbedder())
    assert sum(calls) == 0
    assert SectionChunkEmbedding.objects.count() == count


@pytest.mark.django_db
def test_shortened_section_drops_its_chunks(book: Book):
    section = _section(book, "Covenant Stores", FILLER + FILLER + TAIL)
    rebuild_embeddings_for_books([book.id], embedder=HashingEmbedder())
    section.body_markdown = "Now brief."
    section.content_hash = "brief"
    section.save()
    rebuild_embeddings_for_books([book.id], embedder=HashingEmbedder())
    assert not SectionChunkEmbedding.objects.filter(section=section).exists()
