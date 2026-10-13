"""Saga-prep extractors: beasts, boons/hooks, orgs, places, enchanted items."""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.catalog.extractors import (
    CREATURE_LEAD_WINDOW,
    MIGHT_LINE_RE,
    SKIP_TITLE_RE,
    ExtractedEntry,
    _clean_body,
    _section_title,
)
from apps.library.models import Section
from clavis.markdown.normalize import unescape_markdown_text

_FIRST_SENTENCE = re.compile(r"([^.!?\n]{12,200}[.!?])")

# Mundane beasts: Characteristics with Cun + Size/Qualities, no Realm Might.
BEAST_CHARS_RE = re.compile(
    r"^Characteristics:\s*.*\bCun\b",
    re.I | re.M,
)
BEAST_SIZE_RE = re.compile(r"^Size:\s*", re.I | re.M)
BEAST_QUALITIES_RE = re.compile(r"^Qualities:\s*", re.I | re.M)
SKIP_BEAST_TITLE_RE = re.compile(
    r"^(beasts in combat|creating (mundane )?beasts|mundane beasts|"
    r"book of mundane beasts|appendix)\b|"
    r"\bforms?\b",
    re.I,
)

BOON_HOOK_SECTION_RE = re.compile(
    r"^(?P<mag>Major|Minor)\s+"
    r"(?:(?P<cat>Site|Fortifications|Resources|Residents?|External Relations|"
    r"Surroundings|Relations)\s+)?"
    r"(?P<kind>Boons?|Hooks?)$",
    re.I,
)
BOON_HOOK_BOLD_RE = re.compile(
    r"^\*\*(?P<name>[^*]+?)(?::\*\*|\*\*:|\*\*)\s*",
    re.M,
)
BOON_HOOK_PLAIN_RE = re.compile(
    r"^(?P<name>[A-Z][A-Za-z0-9][A-Za-z0-9 '’(),/-]{1,70}):\s+\S",
    re.M,
)
# Through the Aegis applied picks.
APPLIED_BOON_HOOK_RE = re.compile(
    r"^\*\*(?P<name>.+?)\s*\((?P<mag>Major|Minor)\s+(?P<cat>[^)]+?)\s+"
    r"(?P<kind>Boon|Hook)\)(?::\*\*|\*\*:|\*\*)\s*",
    re.I | re.M,
)

_HERMETIC_HOUSES = (
    "Bjornaer",
    "Bonisagus",
    "Criamon",
    "Ex Miscellanea",
    "Flambeau",
    "Guernicus",
    "Jerbiton",
    "Mercere",
    "Merinita",
    "Tremere",
    "Tytalus",
    "Verditius",
)
HOUSE_TITLE_RE = re.compile(
    r"^House\s+(?P<house>"
    + "|".join(h.replace(" ", r"\s+") for h in _HERMETIC_HOUSES)
    + r")\s*$",
    re.I,
)
SKIP_ORG_TITLE_RE = re.compile(
    r"^(house organization|house utilities|house nomenclature|house culture|"
    r"house acclaim|organization|the houses of hermes|assignments|"
    r"hierarchy|guilds|bishops|archdeacons|canon law|chapters)\b",
    re.I,
)

COVENANT_PLACE_TITLE_RE = re.compile(
    r"(?:"
    r":\s*A\s+(?:Spring|Summer|Autumn|Winter)\s+Covenant\b|"
    r"^(?:The\s+)?(?:Oppidum|Covenant)\s+of\b|"
    r"^The\s+Lost\s+Covenant\s+of\b|"
    r"^Collem\s+Leonis$"
    r")",
    re.I,
)
SKIP_PLACE_TITLE_RE = re.compile(
    r"(story ideas|oath of covenant|^introduction\b|play aids|background covenant)",
    re.I,
)
CORE_SEASON_COVENANT_RE = re.compile(
    r"^(Vernus|Aestas|Autumnus|Hiems)\b",
    re.I,
)

ENCHANTED_ITEM_LEAD_RE = re.compile(r"\bThis enchanted item\b", re.I)
SKIP_ITEM_TITLE_RE = re.compile(
    r"^(types? of enchanted|enchanted items?|invested items?|"
    r"lesser enchantments?|charged items?|shape and material|"
    r"preparation for enchantment|instilling|using enchanted|"
    r"talisman|laboratory|vis|description|disadvantages|"
    r"effect modifications|constant effect|arcane connection|"
    r"examples? of|forging|enchanting)\b",
    re.I,
)


def _summary(text: str) -> str:
    cleaned = re.sub(r"[*_`>#]+", "", text).strip()
    match = _FIRST_SENTENCE.search(cleaned)
    if match:
        return match.group(1).strip()[:512]
    return cleaned[:180].strip()


def _path_has(section: Section, fragment: str) -> bool:
    return fragment in (section.path or "").lower()


def extract_beast(section: Section) -> ExtractedEntry | None:
    """Mundane animal writeups (Cun characteristics, no Realm Might)."""
    title = _section_title(section)
    if SKIP_BEAST_TITLE_RE.search(title) or SKIP_TITLE_RE.match(title):
        return None
    if section.level < 2:
        return None

    body = _clean_body(section.body_markdown)
    head = body[:CREATURE_LEAD_WINDOW]
    if MIGHT_LINE_RE.search(head):
        return None
    if not BEAST_CHARS_RE.search(head):
        return None
    if not (BEAST_SIZE_RE.search(head) or BEAST_QUALITIES_RE.search(body[:800])):
        return None

    size = ""
    size_match = re.search(r"^Size:\s*(?P<size>[^\n]+)", head, re.I | re.M)
    if size_match:
        size = size_match.group("size").strip()

    summary_bits = ["Mundane beast"]
    if size:
        summary_bits.append(f"Size {size}")

    return ExtractedEntry(
        entry_type="beast",
        name=title,
        slug=slugify(title)[:200] or "beast",
        summary="; ".join(summary_bits),
        section=section,
        category="",
        evidence=head.splitlines()[0][:240] if head else title,
    )


def extract_boons_and_hooks(section: Section) -> list[ExtractedEntry]:
    """Covenant Boon/Hook definitions and applied Aegis-style lists."""
    title = _section_title(section)
    body = _clean_body(section.body_markdown)
    found: list[ExtractedEntry] = []
    seen: set[str] = set()

    section_match = BOON_HOOK_SECTION_RE.match(title)
    if section_match:
        magnitude = section_match.group("mag").title()
        category = (section_match.group("cat") or "").strip().title()
        kind = section_match.group("kind").lower()
        entry_type = "hook" if kind.startswith("hook") else "boon"
        for match in BOON_HOOK_BOLD_RE.finditer(body):
            name = unescape_markdown_text(match.group("name")).strip().rstrip(":")
            if not name or len(name) < 2:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            rest = body[match.end() : match.end() + 400]
            found.append(
                ExtractedEntry(
                    entry_type=entry_type,
                    name=name,
                    slug=slugify(name)[:200] or entry_type,
                    summary=_summary(rest) or f"{magnitude} {entry_type}",
                    section=section,
                    magnitude=magnitude,
                    category=category,  # only from section title (Site, …)
                    evidence=match.group(0).strip()[:240],
                )
            )
        # Core Minor Hooks: some entries are plain "Contested Resource: …"
        if not found or entry_type == "hook":
            for match in BOON_HOOK_PLAIN_RE.finditer(body):
                name = match.group("name").strip()
                if name.casefold() in seen:
                    continue
                # Skip if this line is already bold-captured nearby.
                if f"**{name}" in body:
                    continue
                seen.add(name.casefold())
                rest = body[match.end() : match.end() + 400]
                found.append(
                    ExtractedEntry(
                        entry_type=entry_type,
                        name=name,
                        slug=slugify(name)[:200] or entry_type,
                        summary=_summary(rest) or f"{magnitude} {entry_type}",
                        section=section,
                        magnitude=magnitude,
                        category=category,
                        evidence=match.group(0).strip()[:240],
                    )
                )
        return found

    # Applied lists (Through the Aegis "Boons & Hooks" sections).
    if re.search(r"boons?\s*&\s*hooks?", title, re.I) or title.casefold() in {
        "boons and hooks",
        "boons & hooks",
    }:
        for match in APPLIED_BOON_HOOK_RE.finditer(body):
            name = unescape_markdown_text(match.group("name")).strip()
            kind = match.group("kind").lower()
            entry_type = "hook" if kind.startswith("hook") else "boon"
            key = f"{entry_type}:{name.casefold()}"
            if key in seen:
                continue
            seen.add(key)
            rest = body[match.end() : match.end() + 400]
            cat = match.group("cat").strip().title()
            found.append(
                ExtractedEntry(
                    entry_type=entry_type,
                    name=name,
                    slug=slugify(name)[:200] or entry_type,
                    summary=_summary(rest),
                    section=section,
                    magnitude=match.group("mag").title(),
                    category=cat,  # explicit in "(Major Surroundings Boon)"
                    evidence=match.group(0).strip()[:240],
                )
            )
    return found


def extract_organization(section: Section) -> ExtractedEntry | None:
    """Hermetic Houses and major House offices."""
    title = _section_title(section)
    if SKIP_ORG_TITLE_RE.match(title):
        return None

    body = _clean_body(section.body_markdown)
    if len(body.strip()) < 80:
        return None

    house_match = HOUSE_TITLE_RE.match(title)
    if house_match and section.level <= 3:
        house = re.sub(r"\s+", " ", house_match.group("house")).title()
        if house.lower() == "ex miscellanea":
            house = "Ex Miscellanea"
        return ExtractedEntry(
            entry_type="organization",
            name=f"House {house}" if not title.lower().startswith("house") else title,
            slug=slugify(title)[:200] or "organization",
            summary=_summary(body) or f"Hermetic House {house}",
            section=section,
            category="",
            form=house,
            evidence=title,
        )

    # True Lineages-style offices: only under House chapter organization paths.
    path = (section.path or "").lower()
    house_office_path = bool(
        re.search(r"house-[a-z-]+/.*(?:house-)?organization", path)
        or "house-organization" in path
    )
    if section.level == 3 and house_office_path:
        if SKIP_TITLE_RE.match(title):
            return None
        house = ""
        for part in (section.path or "").split("/"):
            hm = re.match(r"chapter-\w+-house-(?P<h>.+)", part)
            if hm:
                house = hm.group("h").replace("-", " ").title()
                if house.lower() == "ex miscellanea":
                    house = "Ex Miscellanea"
                break
        if not house:
            return None
        return ExtractedEntry(
            entry_type="organization",
            name=title,
            slug=slugify(title)[:200] or "organization",
            summary=_summary(body),
            section=section,
            category="",
            form=house,
            evidence=title,
        )
    return None


def extract_place(section: Section) -> ExtractedEntry | None:
    """Named covenants / oppida / season example covenants."""
    title = _section_title(section)
    if SKIP_TITLE_RE.match(title) or SKIP_PLACE_TITLE_RE.search(title):
        return None

    body = _clean_body(section.body_markdown)
    if len(body.strip()) < 40:
        return None

    if COVENANT_PLACE_TITLE_RE.search(title) and section.level <= 2:
        pass
    elif CORE_SEASON_COVENANT_RE.match(title) and _path_has(
        section, "covenant-season"
    ):
        pass
    else:
        return None

    aura = ""
    aura_match = re.search(
        r"\b((?:Magic|Faerie|Divine|Infernal)\s+)?[Aa]ura\s+(?:of\s+)?(\d+)\b",
        body[:600],
    )
    if aura_match:
        aura = aura_match.group(0)

    summary = _summary(body)
    if aura and aura not in summary:
        summary = f"{summary} ({aura})" if summary else aura

    return ExtractedEntry(
        entry_type="place",
        name=title,
        slug=slugify(title)[:200] or "place",
        summary=summary[:512],
        section=section,
        category="",
        evidence=title,
    )


def extract_item(section: Section) -> ExtractedEntry | None:
    """Named enchanted-item writeups (not lab procedure chapters)."""
    title = _section_title(section)
    if SKIP_ITEM_TITLE_RE.match(title) or SKIP_TITLE_RE.match(title):
        return None
    if section.level < 3:
        return None

    body = _clean_body(section.body_markdown)
    head = body[:500]
    if MIGHT_LINE_RE.search(head):
        return None
    lead = ENCHANTED_ITEM_LEAD_RE.search(head)
    if not lead:
        return None
    path = (section.path or "").lower()
    if "chapter-8-laboratory" in path or "laboratories/" in path:
        return None

    return ExtractedEntry(
        entry_type="item",
        name=title,
        slug=slugify(title)[:200] or "item",
        summary=_summary(body),
        section=section,
        category="",
        evidence=lead.group(0)[:240],
    )
