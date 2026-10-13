from __future__ import annotations

from pathlib import Path

import pytest

from apps.catalog.extractors import extract_blockquote_spells, extract_from_section
from apps.library.models import Book, Section
from apps.sources.models import SourceSnapshot


@pytest.mark.django_db
def test_blockquote_spell_my_new_best_friend(tmp_path: Path):
    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="spell",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    book = Book.objects.create(
        snapshot=snap,
        slug="rhine",
        title="Rhine",
        relative_path="reviewed/rhine.md",
    )
    section = Section.objects.create(
        book=book,
        level=3,
        title="Magi",
        slug="magi",
        path="covenant/magi",
        body_markdown=(
            "**Henri de Tours, Follower of Jerbiton**\n"
            "**Age:** 42\n"
            "**Personality Traits:** Curious +2\n\n"
            "Henri trades along the coast.\n\n"
            "> #### Creo Mentem Spell\n"
            ">**MY NEW BEST FRIEND**  \n\n"
            ">**R:** Eye, **D:** Sun, **T:** Individual, **Level 25**   \n\n"
            ">**Requisite:** Muto\n"
            ">\n"
            ">This spell causes the target to believe that the caster is an old friend.\n"
        ),
        content_hash="magi",
        stable_id="magi-spell",
        position=0,
    )
    boxed = extract_blockquote_spells(section)
    assert len(boxed) == 1
    spell = boxed[0]
    assert spell.name == "MY NEW BEST FRIEND"
    assert spell.level == 25
    assert spell.technique == "Creo"
    assert spell.form == "Mentem"
    assert spell.range.lower() == "eye"

    merged = extract_from_section(section)
    types = {e.entry_type for e in merged}
    assert "spell" in types
    assert "character" in types
    assert any(e.name == "MY NEW BEST FRIEND" for e in merged)
