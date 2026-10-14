"""Creature extraction from Might / Size / Season stat lines."""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.library.models import Section
from clavis.markdown.normalize import unescape_markdown_text

from .common import SKIP_TITLE_RE, ExtractedEntry, _clean_body, _section_title

# Used to keep spells/VF away from creature writeups.
CREATURE_LEAD_RE = re.compile(
    r"^\s*(\*\*)?(Magic Might|Faerie Might|Infernal Might|Divine Might|"
    r"Characteristics|Season:|Size:)\b",
    re.I | re.M,
)

# Allow optional blockquote markers and bold wrappers around the label/colon
# (Contested Isle callouts use ``> **Faerie Might:** 50``).
# Colon may sit inside or outside bold: ``**Faerie Might:** 20`` or ``**Magic Might**: 20``.
# Might may follow an ``Order:`` / ``Season:`` label on the same line, and some
# books drop the colon (``**Magic Might** 20``).
MIGHT_LINE_RE = re.compile(
    r"^(?:>\s*)?"
    r"(?:(?:\*\*)?(?:Order|Season)(?:\*\*)?\s*:(?:\*\*)?[^\n]{0,80}?\s)?"
    r"(?:\*\*)?(?P<realm>Magic|Faerie|Infernal|Divine)\s+Might"
    r"(?:\*\*)?\s*:?(?:\*\*)?\s*"
    r"(?P<might>\d+)\s*(?:\((?P<form>[^)]+)\))?",
    re.I | re.M,
)
SIZE_LINE_RE = re.compile(
    r"^(?:>\s*)?(?:\*\*)?Size:(?:\*\*)?\s*(?P<size>[^\n*<]+)",
    re.I | re.M,
)
SEASON_LINE_RE = re.compile(
    r"^(?:>\s*)?(?:\*\*)?Season:(?:\*\*)?\s*(?P<season>\w+)",
    re.I | re.M,
)
# Stat-block callouts nested under a story section: ``> ### Donn``
BQ_CREATURE_HEADING_RE = re.compile(r"^>\s*#{2,6}\s+(?P<title>.+?)\s*$", re.M)
CREATURE_BLOCK_WINDOW = 1600
CREATURE_LEAD_WINDOW = 400


def _creature_entry(
    *,
    section: Section,
    name: str,
    might: re.Match[str],
    scan: str,
) -> ExtractedEntry:
    realm = might.group("realm").title()
    score = int(might.group("might"))
    form = (might.group("form") or "").strip().title()
    size = ""
    season = ""
    # Prefer Size/Season near the Might line (callouts often put prose first).
    around = scan[max(0, might.start() - 120) : might.end() + 400]
    size_match = SIZE_LINE_RE.search(around) or SIZE_LINE_RE.search(scan[:1200])
    if size_match:
        size = size_match.group("size").strip()
    season_match = SEASON_LINE_RE.search(around) or SEASON_LINE_RE.search(scan[:1200])
    if season_match:
        season = season_match.group("season").strip().title()

    summary_bits = [f"{realm} Might {score}"]
    if form:
        summary_bits[0] += f" ({form})"
    if size:
        summary_bits.append(f"Size {size}")
    if season:
        summary_bits.append(season)

    return ExtractedEntry(
        entry_type="creature",
        name=name,
        slug=slugify(name)[:200] or "creature",
        summary="; ".join(summary_bits),
        section=section,
        level=score,
        form=form,
        category=realm,
        evidence=might.group(0).strip()[:240],
    )


def extract_creature(section: Section) -> ExtractedEntry | None:
    """Might-led creature / spirit / beast writeups."""
    title = _section_title(section)
    if SKIP_TITLE_RE.match(title):
        return None
    # Top-level (level 1) creature chapters are common in adventure books.
    if section.level < 1:
        return None

    body = _clean_body(section.body_markdown)
    head = body[:CREATURE_LEAD_WINDOW]
    might = MIGHT_LINE_RE.search(head)
    if not might:
        return None
    return _creature_entry(section=section, name=title, might=might, scan=body)


def extract_blockquote_creatures(section: Section) -> list[ExtractedEntry]:
    """Harvest ``> ### Name`` callout stat blocks embedded in a story section."""
    body = _clean_body(section.body_markdown)
    headings = list(BQ_CREATURE_HEADING_RE.finditer(body))
    if not headings:
        return []

    found: list[ExtractedEntry] = []
    seen: set[str] = set()
    for index, heading in enumerate(headings):
        name = unescape_markdown_text(heading.group("title").strip())
        if not name or SKIP_TITLE_RE.match(name):
            continue
        key = name.casefold()
        if key in seen:
            continue
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        chunk = body[start:end]
        # Drop blockquote markers so Might/Size lines match cleanly.
        flat = re.sub(r"^>\s?", "", chunk, flags=re.M)
        might = MIGHT_LINE_RE.search(flat[:CREATURE_BLOCK_WINDOW])
        if not might:
            continue
        seen.add(key)
        found.append(_creature_entry(section=section, name=name, might=might, scan=flat))
    return found


def extract_creatures(section: Section) -> list[ExtractedEntry]:
    boxed = extract_blockquote_creatures(section)
    primary = extract_creature(section)
    if primary is None:
        return boxed
    names = {entry.name.casefold() for entry in boxed}
    if primary.name.casefold() not in names:
        return [primary, *boxed]
    return boxed
