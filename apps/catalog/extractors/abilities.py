"""Ability extraction."""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.library.models import Section

from .common import SKIP_TITLE_RE, ExtractedEntry, _clean_body, _section_title
from .creatures import CREATURE_LEAD_RE, CREATURE_LEAD_WINDOW

ABILITY_SPECIALTIES_RE = re.compile(
    r"\*Specialties?:\*\s*[^\n]+\((?P<cat>General|Academic|Arcane|Martial|Supernatural)\)",
    re.I,
)
SKIP_ABILITY_TITLE_RE = re.compile(
    r"^(general|academic|arcane|martial|supernatural)\s+abilities$|"
    r"^abilities\b|by type$",
    re.I,
)


def extract_ability(section: Section) -> ExtractedEntry | None:
    """Core-style Ability writeups with Specialties + category."""
    title = _section_title(section)
    if SKIP_ABILITY_TITLE_RE.match(title) or SKIP_TITLE_RE.match(title):
        return None
    if section.level < 3:
        return None
    if CREATURE_LEAD_RE.search(section.body_markdown[:CREATURE_LEAD_WINDOW]):
        return None

    body = _clean_body(section.body_markdown)
    specialties = ABILITY_SPECIALTIES_RE.search(body[:600])
    if not specialties:
        return None

    category = specialties.group("cat").title()
    # First prose sentence as summary lead.
    lead = re.split(r"\n\s*\n", body.strip(), maxsplit=1)[0]
    lead = re.sub(r"\*Specialties?:?\*.*", "", lead, flags=re.I | re.S)
    lead = re.sub(r"\s+", " ", lead).strip()
    if len(lead) > 180:
        lead = lead[:177].rstrip() + "…"

    return ExtractedEntry(
        entry_type="ability",
        name=title,
        slug=slugify(title)[:200] or "ability",
        summary=lead or category,
        section=section,
        category=category,
        evidence=specialties.group(0)[:240],
    )
