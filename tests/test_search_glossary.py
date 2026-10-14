from __future__ import annotations

from pathlib import Path

import pytest

from apps.search.glossary import expand_for_meaning, glossary_notes
from apps.search.services import _fts_query, search_sections
from apps.sources.services import import_sources


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("CrIg", '("CrIg" OR "Creo Ignem")'),
        ("creo ignem bolt", '("creo" AND "ignem" OR "CrIg") AND "bolt"*'),
        ("Pen bonus", '("Pen" OR "Penetration") AND "bonus"*'),
        ("magic resistance", '("magic" AND "resistance" OR "MR")'),
        ("Corporem", '("corpus" OR "corporem")'),
        ("pawns per year", '"pawns" AND "per" AND "year"*'),
        ("mute servant", '"mute" AND "servant"*'),
        ("MuTe", '("MuTe" OR "Muto Terram")'),
    ],
)
def test_fts_query_ors_glossary_counterparts(query: str, expected: str):
    assert _fts_query(query) == expected


def test_glossary_notes_name_the_expansion():
    assert glossary_notes("ReCo Pen") == ["ReCo ↔ Rego Corpus", "Pen ↔ Penetration"]
    assert glossary_notes("pawns per year") == []


def test_meaning_query_writes_out_short_forms():
    assert expand_for_meaning("CrIg bolt with high Pen") == (
        "Creo Ignem bolt with high Penetration"
    )
    assert expand_for_meaning("Rego Corpus") == "Rego Corpus"


@pytest.mark.django_db
def test_art_abbreviation_finds_written_out_text(fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)

    hits = search_sections("CrIg")

    assert any("Creo Ignem" in hit.section.body_markdown for hit in hits)
