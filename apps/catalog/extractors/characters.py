"""Character extraction from Age / Personality stat blocks."""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.library.models import Section

from .common import SKIP_TITLE_RE, ExtractedEntry, _clean_body, _section_title
from .creatures import CREATURE_LEAD_WINDOW, MIGHT_LINE_RE

AGE_LINE_RE = re.compile(r"^\*\*Age:\*\*\s*(?P<age>\d+)", re.I | re.M)
PERSONALITY_RE = re.compile(r"^\*\*Personality Traits:\*\*", re.I | re.M)
BOLD_LINE_RE = re.compile(r"^\*\*(?P<header>[^*]{2,90})\*\*\s*$", re.M)
SKIP_CHAR_HEADER_RE = re.compile(
    r"^(Age|Personality Traits|Characteristics|Virtues and Flaws|Combat|"
    r"Soak|Powers|Abilities|Pretenses|Warping|Decrepitude|Confidence|"
    r"Wound Penalties|Equipment|Encumbrance|Reputations?|Arts|"
    r"Twilight Scars|Appearance|Casting Sigil|Voting Sigil)\b",
    re.I,
)
# Canonical Hermetic houses (plus Ex Miscellanea).
_HERMETIC_HOUSES = (
    "Bjornaer",
    "Bonisagus",
    "Criamon",
    "Flambeau",
    "Guernicus",
    "Jerbiton",
    "Mercere",
    "Merinita",
    "Tremere",
    "Tytalus",
    "Verditius",
    "Miscellanea",
)
_HOUSE_ALT = "|".join(_HERMETIC_HOUSES)
CHAR_HOUSE_RE = re.compile(
    rf"(?:,\s*)?(?:"
    rf"FOLLOWER\s+OF(?:\s+House)?|"
    rf"(?:Magus|Maga)\s+of(?:\s+House)?|"
    rf"of\s+House|"
    rf"of\s+Ex|"
    rf"of"
    rf")\s+(?:House\s+)?(?P<house>{_HOUSE_ALT})\b",
    re.I,
)
CHARACTER_AGE_WINDOW = 280

# Stat blocks without a bold person header: `**Characteristics:** Int +1 …`,
# bare `Intelligence +2 Presence +1`, and uppercase `AGE: 22` / `VIRTUES & FLAWS:`.
STAT_CHARACTERISTIC_RE = re.compile(
    r"\bInt\s*[+\-−–]\s*\d|\bInt\s*\d+\s*(?:\(\d+\))?\s*,?\s*Per\b|\bIntelligence\s*[+\-−–]?\s*\d",
    re.I,
)
STAT_LABEL_RE = re.compile(
    r"(?:^|\*\*)\s*\**(?P<label>Characteristics|Age|Personality Traits?|"
    r"Virtues\s*(?:&|and)\s*Flaws|Abilities|Confidence|Soak|Techniques\s*(?:&|and)\s*Forms|"
    r"Arts|Encumbrance|Decrepitude|Warping|Reputations?|Combat|Wound Penalties|Equipment|"
    r"Weapons\s*(?:&|and)\s*Armou?r|Size)\**\s*:",
    re.I | re.M,
)
STAT_BLOCK_START_WINDOW = 600
STAT_BLOCK_SCAN = 2500
# Powers / spells right before the block mean the stat lines belong to someone else.
STAT_POWER_BEFORE_RE = re.compile(r"\bR:\**\s*\w+.*\bD:\**\s*\w+", re.I)
STAT_SKIP_TITLE_RE = re.compile(
    r"[?:]$|:\s*\d|\b(Laboratory|Sanctum|Covenant)\b|^(After|Before|When|During)\b|"
    r"\b(Virtue|Flaw|Base Scores|Form|Trees)$",
    re.I,
)
TEMPLATE_PATH_RE = re.compile(r"(?:^|/|-)(templates?|vocations?|archetypes?)(?:/|-|$)")
PAREN_HOUSE_RE = re.compile(rf"\((?:House\s+)?(?:Ex\s+)?(?P<house>{_HOUSE_ALT})\)", re.I)
EX_HOUSE_RE = re.compile(rf"\b(?:Magus|Maga)\s+ex\s+(?P<house>{_HOUSE_ALT})\b", re.I)


def _extract_house(header: str) -> str:
    """Return Hermetic house from a title/header, or empty string."""
    match = (
        CHAR_HOUSE_RE.search(header) or PAREN_HOUSE_RE.search(header) or EX_HOUSE_RE.search(header)
    )
    if not match:
        return ""
    house = match.group("house").title()
    if house == "Miscellanea":
        return "Ex Miscellanea"
    return house


def _soft_person_title(text: str) -> str:
    """Title-case ALL-CAPS person lines without turning 'of' into 'Of'."""
    small = {"of", "the", "and", "van", "de", "di", "filius", "filia", "ex"}
    parts: list[str] = []
    for index, word in enumerate(text.split()):
        lower = word.lower()
        if index > 0 and lower in small:
            parts.append("Ex" if lower == "ex" else lower)
        else:
            parts.append(word.capitalize())
    return " ".join(parts)


def _character_name_and_house(header: str) -> tuple[str, str] | None:
    """Return (display_name, house). Keep house wording in the display name.

    Recognized house cues include ``of House X``, ``of X``, ``Follower of X``,
    and ``of Ex Miscellanea``.
    """
    header = header.strip().rstrip(".")
    if not header or SKIP_CHAR_HEADER_RE.match(header):
        return None
    if ":" in header:
        return None
    if re.search(r"\d", header):
        return None

    house = _extract_house(header)
    display = re.sub(r"\s+", " ", header).strip()
    if display.isupper():
        display = _soft_person_title(display)

    # Without a house cue, require Magus/Maga / ALL-CAPS / Title-Case person line.
    if not house:
        if not re.search(r"\b(Magus|Maga|Archmage|Archmaga)\b", header, re.I) and not (
            header.isupper() or re.match(r"^[A-Z][\w' \-]+$", header)
        ):
            return None

    if len(display) < 2 or len(display) > 90:
        return None
    # Avoid chapter-like titles mistaken for people.
    if re.search(r"\b(Chapter|Tribunal|Covenant|Guidelines?)\b", display, re.I):
        return None
    return display, house


def _stat_block_age(body: str) -> str | None:
    """Age of a stat block near the section start, ``""`` without Age, else None."""
    characteristics = STAT_CHARACTERISTIC_RE.search(body)
    if not characteristics or characteristics.start() > STAT_BLOCK_START_WINDOW:
        return None
    before = body[: characteristics.start()]
    if MIGHT_LINE_RE.search(before) or STAT_POWER_BEFORE_RE.search(before):
        return None
    block = body[: characteristics.start() + STAT_BLOCK_SCAN]
    labels = {match.group("label").split()[0].casefold() for match in STAT_LABEL_RE.finditer(block)}
    if "virtues" not in labels or not {"age", "abilities"} & labels or len(labels) < 3:
        return None
    age = re.search(r"\bAge\**\s*:\**\s*(?P<age>\d+)", block, re.I)
    return age.group("age") if age else ""


def extract_characters(section: Section) -> list[ExtractedEntry]:
    """Named people: bold Magus headers and Age-led section writeups."""
    body = _clean_body(section.body_markdown)
    if MIGHT_LINE_RE.search(body[:CREATURE_LEAD_WINDOW]):
        return []

    found: list[ExtractedEntry] = []
    seen: set[str] = set()
    template = bool(TEMPLATE_PATH_RE.search(section.path))

    def add(name: str, house: str, age: str, evidence: str) -> None:
        key = name.casefold()
        if key in seen:
            return
        seen.add(key)
        summary_bits = [
            bit
            for bit in ("Template" if template else "", house, f"Age {age}" if age else "")
            if bit
        ]
        found.append(
            ExtractedEntry(
                entry_type="character",
                name=name,
                slug=slugify(name)[:200] or "character",
                summary="; ".join(summary_bits) or "Named character",
                section=section,
                category="Template" if template else house,
                evidence=evidence.strip()[:240],
            )
        )

    for match in BOLD_LINE_RE.finditer(body):
        parsed = _character_name_and_house(match.group("header"))
        if not parsed:
            continue
        name, house = parsed
        window = body[match.end() : match.end() + CHARACTER_AGE_WINDOW]
        age_match = AGE_LINE_RE.search(window)
        if not age_match:
            continue
        # Prefer writeups that also show Personality Traits nearby.
        if not PERSONALITY_RE.search(window) and not house:
            continue
        add(name, house, age_match.group("age"), match.group(0))

    if found:
        return found

    # Single-character section: title is the name (often "Name of House X").
    title = _section_title(section)
    if SKIP_TITLE_RE.match(title):
        return []
    head = body[:CHARACTER_AGE_WINDOW]
    age_match = AGE_LINE_RE.search(head)
    if section.level >= 3 and age_match and PERSONALITY_RE.search(head):
        age = age_match.group("age")
    else:
        stat_age = None if STAT_SKIP_TITLE_RE.search(title) else _stat_block_age(body)
        if stat_age is None:
            return []
        age = stat_age
    parsed = _character_name_and_house(title)
    if parsed:
        name, house = parsed
    else:
        name, house = re.sub(r"\s+", " ", title).strip(), _extract_house(title)
    if name.isupper():
        name = _soft_person_title(name)
    add(name, house, age, title)
    return found
