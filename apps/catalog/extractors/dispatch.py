"""Per-section dispatch: which extractors run, plus titled boxes inside a section."""

from __future__ import annotations

import re

from apps.library.models import Section

from .abilities import extract_ability
from .characters import extract_characters
from .common import ExtractedEntry, _section_title
from .creatures import extract_blockquote_creatures, extract_creatures
from .guidelines import extract_guidelines
from .spells import extract_blockquote_spells, extract_spell, extract_spells
from .story_seeds import STORY_SEED_TITLE_RE, extract_story_seeds
from .virtues import extract_virtues_and_flaws
from .vis_sources import extract_vis_sources

BOX_HEADING_RE = re.compile(r"^>\s*#{1,6}\s+(?P<title>.+?)\s*#*\s*$")
BOX_QUOTE_RE = re.compile(r"^>\s?")


def boxed_sections(section: Section) -> list[Section]:
    """Titled ``> ### Heading`` boxes as unsaved pseudo-sections.

    The importer only splits on unquoted headings, so a box stays inside its
    section. Unquoting each titled box lets every rule read it like a real
    subsection; entries still point at the enclosing section.
    """
    boxes: list[Section] = []
    title: str | None = None
    lines: list[str] = []

    def close() -> None:
        body = "\n".join(lines).strip()
        if title and body:
            boxes.append(
                Section(
                    book=section.book,
                    parent=section,
                    level=min(section.level + 1, 6),
                    title=title,
                    slug=section.slug,
                    path=section.path,
                    body_markdown=body,
                    content_hash=section.content_hash,
                    stable_id=section.stable_id,
                    position=section.position,
                )
            )

    for line in (section.body_markdown or "").splitlines():
        if line.startswith(">"):
            heading = BOX_HEADING_RE.match(line)
            if heading:
                close()
                title = heading.group("title").strip("* ").strip() or None
                lines = []
            elif title is not None:
                lines.append(BOX_QUOTE_RE.sub("", line, count=1))
        elif not line.strip():
            if title is not None:
                lines.append("")
        else:
            close()
            title, lines = None, []
    close()
    return boxes


def extract_from_section(section: Section) -> list[ExtractedEntry]:
    """Entries of a section plus those of its titled boxes (deduplicated)."""
    # Slug, not name: the catalog stores one entry per type + slug + section.
    entries: list[ExtractedEntry] = []
    seen: set[tuple[str, str]] = set()
    candidates = [
        *_extract_section_entries(section),
        *(entry for box in boxed_sections(section) for entry in _extract_section_entries(box)),
    ]
    for entry in candidates:
        key = (entry.entry_type, entry.slug)
        if not entry.name.strip() or key in seen:
            continue
        seen.add(key)
        entry.section = section
        entries.append(entry)
    return entries


def _extract_section_entries(section: Section) -> list[ExtractedEntry]:
    # Imported here to keep saga patterns in a dedicated module without cycles
    # at import time for the helpers above.
    from apps.catalog.saga_extractors import (
        extract_beast,
        extract_boons_and_hooks,
        extract_item,
        extract_organization,
        extract_place,
    )

    seeds = extract_story_seeds(section)
    title_is_seed = bool(STORY_SEED_TITLE_RE.match(_section_title(section)))
    if title_is_seed:
        return seeds

    guidelines = extract_guidelines(section)
    if guidelines:
        return guidelines

    # Dedicated spell sections win over other section types, but an enchanted item
    # whose effect reads like a spell keeps its item entry, and boxed creatures stay.
    primary_spell = extract_spell(section)
    boxed_spells = extract_blockquote_spells(section)
    if primary_spell is not None:
        item = extract_item(section)
        spells = extract_spells(section)
        if item:
            for spell in spells:
                if spell.name.casefold() == item.name.casefold():
                    spell.device_effect = True
        return [
            *([item] if item else []),
            *spells,
            *extract_blockquote_creatures(section),
        ]

    vf = extract_virtues_and_flaws(section)
    if vf:
        return vf

    boons_hooks = extract_boons_and_hooks(section)
    if boons_hooks:
        return [*boons_hooks, *seeds]

    vis_sources = extract_vis_sources(section)
    if vis_sources:
        return [*vis_sources, *boxed_spells, *seeds]

    # A place describes the whole section, so it stays next to its residents.
    place = extract_place(section)
    extras = [*([place] if place else []), *boxed_spells, *seeds]

    creatures = extract_creatures(section)
    if creatures:
        return [*creatures, *extras]

    beast = extract_beast(section)
    if beast:
        return [beast, *extras]

    characters = extract_characters(section)
    if characters:
        return [*characters, *extras]

    organization = extract_organization(section)
    if organization:
        return [organization, *extras]

    if place:
        return extras

    item = extract_item(section)
    if item:
        return [item, *boxed_spells, *seeds]

    ability = extract_ability(section)
    if ability:
        return [ability, *boxed_spells, *seeds]
    if boxed_spells:
        return [*boxed_spells, *seeds]
    return seeds
