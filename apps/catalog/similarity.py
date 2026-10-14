"""Lexicon features built on the section meaning index (apps.search.semantic)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from django.db.models import Count, QuerySet

from apps.catalog.models import CatalogEntry
from apps.library.models import Section
from apps.search.semantic import active_index, is_listable, query_vector, rank_sections
from apps.sources.models import SourceSnapshot

DESCRIBE_LIMIT = 50
SIMILAR_LIMIT = 6
CANDIDATE_LIMIT = 40
CANDIDATE_NEIGHBORS = 3
# Below this, rules-recognized entries outnumber real misses (spot-checked per type).
CANDIDATE_MIN_KNOWN = 10


def _section_ids_by_stable(stable_ids: set[str]) -> dict[str, int]:
    current = SourceSnapshot.current()
    if not current or not stable_ids:
        return {}
    return dict(
        Section.objects.filter(book__snapshot=current, stable_id__in=stable_ids).values_list(
            "stable_id", "id"
        )
    )


def entries_by_description(
    entries: QuerySet[CatalogEntry], text: str, *, limit: int = DESCRIBE_LIMIT
) -> list[CatalogEntry]:
    """Entries whose source section reads most like ``text``."""
    index = active_index()
    if index is None:
        return []
    pool = list(entries)
    section_of = _section_ids_by_stable({e.primary_section_stable_id for e in pool})
    by_section: dict[int, list[CatalogEntry]] = {}
    for entry in pool:
        section_id = section_of.get(entry.primary_section_stable_id)
        if section_id is not None:
            by_section.setdefault(section_id, []).append(entry)
    ranked = rank_sections(index, query_vector(text), section_ids=by_section, limit=limit)
    ordered: list[CatalogEntry] = []
    for section_id, _ in ranked:
        ordered.extend(by_section[section_id])
        if len(ordered) >= limit:
            break
    return ordered[:limit]


def similar_entries(entry: CatalogEntry, *, limit: int = SIMILAR_LIMIT) -> list[CatalogEntry]:
    """Same-type entries from other sections whose text reads like this one."""
    index = active_index()
    if index is None:
        return []
    own_id = _section_ids_by_stable({entry.primary_section_stable_id}).get(
        entry.primary_section_stable_id
    )
    if own_id is None or own_id not in index.positions:
        return []
    peers = list(
        CatalogEntry.objects.filter(
            snapshot=entry.snapshot,
            entry_type=entry.entry_type,
            kind=CatalogEntry.Kind.DEFINITION,
        )
        .exclude(primary_section_stable_id=entry.primary_section_stable_id)
        .exclude(slug=entry.slug)
        .select_related("book")
    )
    section_of = _section_ids_by_stable({p.primary_section_stable_id for p in peers})
    first_by_section: dict[int, CatalogEntry] = {}
    for peer in peers:
        section_id = section_of.get(peer.primary_section_stable_id)
        if section_id is not None:
            first_by_section.setdefault(section_id, peer)
    vector = index.matrix[index.positions[own_id]]
    ranked = rank_sections(index, vector, section_ids=first_by_section, limit=limit)
    return [first_by_section[section_id] for section_id, _ in ranked]


@dataclass
class Candidate:
    section: Section
    score: float


def candidate_types() -> list[tuple[str, str]]:
    """Entry types with enough recognized examples to compare against."""
    current = SourceSnapshot.current()
    if not current:
        return []
    counts = dict(
        CatalogEntry.objects.filter(snapshot=current, kind=CatalogEntry.Kind.DEFINITION)
        .values_list("entry_type")
        .annotate(total=Count("id"))
    )
    return [
        (value, label)
        for value, label in CatalogEntry.EntryType.choices
        if counts.get(value, 0) >= CANDIDATE_MIN_KNOWN
    ]


def missed_entry_candidates(entry_type: str, *, limit: int = CANDIDATE_LIMIT) -> list[Candidate]:
    """Sections without any lexicon entry that read like known ``entry_type`` entries.

    Score = mean similarity to the closest few known entries. Review aid only —
    nothing is added to the lexicon automatically.
    """
    index = active_index()
    current = SourceSnapshot.current()
    if index is None or not current:
        return []
    stable_to_id = dict(
        Section.objects.filter(book__snapshot=current).values_list("stable_id", "id")
    )
    hosting_stable = set(
        CatalogEntry.objects.filter(snapshot=current).values_list(
            "primary_section_stable_id", flat=True
        )
    )
    known_stable = set(
        CatalogEntry.objects.filter(
            snapshot=current, entry_type=entry_type, kind=CatalogEntry.Kind.DEFINITION
        ).values_list("primary_section_stable_id", flat=True)
    )
    known_rows = [
        index.positions[stable_to_id[s]]
        for s in known_stable
        if s in stable_to_id and stable_to_id[s] in index.positions
    ]
    if len(known_rows) < CANDIDATE_MIN_KNOWN:
        return []
    hosting_ids = {stable_to_id[s] for s in hosting_stable if s in stable_to_id}
    free_rows = np.fromiter(
        (row for sid, row in index.positions.items() if sid not in hosting_ids),
        dtype=np.int64,
    )
    if not len(free_rows):
        return []
    similarity = index.matrix[free_rows] @ index.matrix[known_rows].T
    neighbors = min(CANDIDATE_NEIGHBORS, similarity.shape[1])
    scores = np.sort(similarity, axis=1)[:, -neighbors:].mean(axis=1)
    order = np.argsort(-scores)[: limit * 3]
    section_ids = [int(index.section_ids[free_rows[i]]) for i in order]
    sections = {s.id: s for s in Section.objects.filter(id__in=section_ids).select_related("book")}
    found: list[Candidate] = []
    for i, section_id in zip(order, section_ids, strict=True):
        section = sections.get(section_id)
        if section is None or not is_listable(section):
            continue
        found.append(Candidate(section=section, score=float(scores[i])))
        if len(found) >= limit:
            break
    return found
