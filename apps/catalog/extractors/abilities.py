"""Ability extraction."""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.library.models import Section

from .common import SKIP_TITLE_RE, ExtractedEntry, _clean_body, _section_title
from .creatures import CREATURE_LEAD_RE, CREATURE_LEAD_WINDOW

_CATEGORY = r"General|Academic|Arcane|Martial|Supernatural"
# The book writes the specialties line several ways: bold colon inside or
# outside, British "specialities", and a bare "Specialties*:".
ABILITY_SPECIALTIES_RE = re.compile(
    rf"(?:\*|_)?Special(?:ties|ities)(?:\*|_)?\s*:?\s*[^\n]{{0,500}}?"
    rf"\((?P<cat>{_CATEGORY})\)",
    re.I,
)
TRAILING_CATEGORY_RE = re.compile(rf"\((?P<cat>{_CATEGORY})\)\s*\Z", re.I)
SKIP_ABILITY_TITLE_RE = re.compile(
    r"^(general|academic|arcane|martial|supernatural)\s+abilities$|"
    r"^abilities\b|by type$|"
    r".*\b(?:modifiers|effects|ease factors)\b",
    re.I,
)


def _implied_ability_category(section: Section, title: str, body: str) -> str:
    """Short Ability-list stubs name the type at the end, or are Supernatural."""
    if "ability-list" not in (section.path or ""):
        return ""
    match = TRAILING_CATEGORY_RE.search(body)
    if match:
        return match.group("cat").title()
    if title.endswith("*"):
        return "Supernatural"
    return ""


def extract_ability(section: Section) -> ExtractedEntry | None:
    """Core-style Ability writeups with Specialties + category."""
    title = _section_title(section)
    if not title or SKIP_ABILITY_TITLE_RE.search(title) or SKIP_TITLE_RE.match(title):
        return None
    if section.level < 3:
        return None
    if CREATURE_LEAD_RE.search(section.body_markdown[:CREATURE_LEAD_WINDOW]):
        return None

    body = _clean_body(section.body_markdown)
    stripped = body.strip()
    if not stripped or stripped.startswith("|"):
        return None
    specialties = ABILITY_SPECIALTIES_RE.search(body)
    if specialties:
        category = specialties.group("cat").title()
        evidence = specialties.group(0)[:240]
    else:
        category = _implied_ability_category(section, title, stripped)
        evidence = stripped[:240]
        if not category:
            return None
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
        evidence=evidence,
    )
