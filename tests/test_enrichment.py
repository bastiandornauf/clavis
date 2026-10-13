from __future__ import annotations

from pathlib import Path

import pytest
from django.core.management import call_command

from apps.catalog.enrichment import (
    DryRunHeuristicProvider,
    accept_proposal,
    collect_proposals,
    persist_proposals,
)
from apps.catalog.models import CatalogEntry, EnrichmentProposal
from apps.library.models import Book, Section
from apps.sources.models import SourceSnapshot
from apps.sources.services import import_sources


def _leftover_creature(tmp_path: Path) -> Section:
    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="enrich",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    book = Book.objects.create(
        snapshot=snap,
        slug="leftover-book",
        title="Leftover Book",
        relative_path="reviewed/leftover.md",
    )
    return Section.objects.create(
        book=book,
        level=3,
        title="Shade of the Forgotten Well",
        slug="shade-of-the-forgotten-well",
        path="creatures/shade",
        body_markdown=(
            "**Faerie Might:** 15 (Corpus)\n\n"
            "A thin spirit that guards the well and whispers names.\n"
        ),
        content_hash="shade-hash",
        stable_id="shade-leftover",
        position=0,
    )


@pytest.mark.django_db
def test_dry_run_skips_untyped_by_default(tmp_path: Path):
    snap = SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="noise",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    book = Book.objects.create(
        snapshot=snap,
        slug="noise-book",
        title="Noise Book",
        relative_path="reviewed/noise.md",
    )
    Section.objects.create(
        book=book,
        level=2,
        title="A Long Narrative Chapter About Travel",
        slug="travel",
        path="travel",
        body_markdown="Travelers walk for many days through forests and fields without rest. " * 3,
        content_hash="travel",
        stable_id="travel-noise",
        position=0,
    )
    Section.objects.create(
        book=book,
        level=3,
        title="Bog Spectre",
        slug="bog-spectre",
        path="creatures/bog",
        body_markdown="**Magic Might:** 10 (Mentem)\n\nIt haunts the fen at dusk.\n",
        content_hash="bog",
        stable_id="bog-signal",
        position=1,
    )
    hints = collect_proposals(DryRunHeuristicProvider(), limit=20)
    assert len(hints) == 1
    assert hints[0].proposed_entry_type == CatalogEntry.EntryType.CREATURE
    assert hints[0].confidence >= 0.4
    assert hints[0].proposed_name == "Bog Spectre"


@pytest.mark.django_db
def test_accept_proposal_writes_catalog_entry(tmp_path: Path):
    section = _leftover_creature(tmp_path)
    hint = DryRunHeuristicProvider().propose(section)
    assert hint is not None
    persist_proposals([hint])
    proposal = EnrichmentProposal.objects.get(section_stable_id=section.stable_id)
    entry = accept_proposal(proposal)
    assert entry is not None
    assert entry.extractor == "heuristic"
    assert entry.entry_type == CatalogEntry.EntryType.CREATURE
    proposal.refresh_from_db()
    assert proposal.status == EnrichmentProposal.Status.ACCEPTED


@pytest.mark.django_db
def test_enrich_catalog_clear_noise(fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    call_command("enrich_catalog", "--include-untyped", "--limit", "10")
    assert EnrichmentProposal.objects.filter(proposed_entry_type="").exists()
    call_command("enrich_catalog", "--clear-noise")
    assert not EnrichmentProposal.objects.filter(
        status=EnrichmentProposal.Status.PENDING,
        proposed_entry_type="",
    ).exists()


@pytest.mark.django_db
def test_enrich_catalog_command_dry_run(tmp_path: Path, capsys):
    _leftover_creature(tmp_path)
    call_command("enrich_catalog", "--dry-run", "--limit", "20")
    out = capsys.readouterr().out
    assert "creature" in out
    assert "typed/signal only" in out
    assert EnrichmentProposal.objects.count() == 0
