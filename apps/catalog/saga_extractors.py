"""Saga-prep extractors: beasts, boons/hooks, orgs, places, enchanted items."""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.catalog.extractors import (
    CREATURE_LEAD_WINDOW,
    MIGHT_LINE_RE,
    SKIP_TITLE_RE,
    ExtractedEntry,
    _art_lead,
    _clean_body,
    _section_title,
)
from apps.library.models import Section
from clavis.markdown.normalize import unescape_markdown_text

_FIRST_SENTENCE = re.compile(r"([^.!?\n]{12,200}[.!?])")

# Mundane beasts: Characteristics with Cun + Size/Qualities, no Realm Might.
# Plain or bold labels; Size may follow Characteristics on the same line.
BEAST_CHARS_RE = re.compile(
    r"^\**Characteristics\**\s*:\**\s*.*\bCun\b",
    re.I | re.M,
)
BEAST_SIZE_RE = re.compile(
    r"(?:^|\*\*)\s*Size\**\s*:\**\s*(?P<size>[+\-–−]?[\s*]*\d+)?", re.I | re.M
)
BEAST_QUALITIES_RE = re.compile(r"^\**Qualities\**\s*:", re.I | re.M)
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
    r"^House\s+(?P<house>" + "|".join(h.replace(" ", r"\s+") for h in _HERMETIC_HOUSES) + r")\s*$",
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
    r"(story ideas|oath of covenant|^introduction\b|play aids|background covenant|"
    r"^chapter\b|^story seed|^(?:features|details) of\b|statistics|^resources$|"
    r"cost saving|creation|hierarchy|governance|attributes)",
    re.I,
)
# Aura stat line near the start: `**Aura:** Magic 5`, `Magic Aura 3`, `Aura: 4`.
PLACE_AURA_LINE_RE = re.compile(
    r"^\**(?:(?:Magic|Faerie|Divine|Infernal)\s+)?Aura\**\s*:?\**\s*"
    r"(?:(?:Magic|Faerie|Divine|Infernal)\s+)?\d+",
    re.I | re.M,
)
PLACE_AURA_WINDOW = 500
# Subsection titles of a covenant writeup (Tribunal books: Covenfolk / History / Magi).
COVENANT_PART_RE = re.compile(
    r"^(?:the\s+)?(?P<part>covenfolk|grogs|laborator(?:y|ies)|librar(?:y|ies)|vis sources?|"
    r"vis|boons?\s*(?:&|and)\s*hooks|charter|magi|history|resources|inhabitants|site|"
    r"specialists|income|fortifications?|defen[cs]es|the covenant)\b",
    re.I,
)
COVENANT_MARKER_RE = re.compile(r"^(covenfolk|grogs|laborator|librar|vis|boon|charter)", re.I)
COVENANT_MIN_PARTS = 3

ORG_NAME_RE = re.compile(
    r"^(?:The\s+)?(?:Cult|Order|League|Brotherhood|Confraternity|Fraternity|Societas|"
    r"Sisterhood|Knights)\s+of\s+(?:the\s+)?[A-Z]"
    r"|^(?:The\s+)?(?:[A-Z][\w'-]+\s+){1,3}(?:Brotherhood|Knights|Order|Cult|Societas|"
    r"Confraternity)$"
    r"|^Knights\s+(?:Templar|Hospitaller)$"
)
# Topic sections about a group ("History of …", "… and the Order", "… Today").
SKIP_ORG_NAME_RE = re.compile(
    r"^(?:The\s+)?(History|Story|Stories|Saga|Secrets|Structure|Ranks|Masters|Entering|"
    r"Inventing|Progression|Locating|Other|Spread|Resurrecting|Damaging|Prosecution|"
    r"Attitude|Incorporation|Induction|Before|After|Reverence|Rivals|War|Against|Face|News|"
    r"Converts|Allies|Magi|How|Appendix|Chapter|Growth|Fall|Foundation|Founding|"
    r"Partitioning|Crises|Relationship|Preservers|Revenge|Endangering|Rejoining|Hermetic|"
    r"Mundane|Organization|Holy|Erudite|Scrying|Demonically|Mercurian|Poor)\b"
    r"|\s(?:in|and|Today|Alternatives|Forms)\b|[:{&]",
)
ORG_MIN_BODY = 300
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
# Device effect line: ``Pen +0, 6/day``, ``**Pen:** 0, 24 uses per day``,
# ``Penetration +32, constant effect``.
ITEM_USE_RE = re.compile(
    r"\bPen(?:etration)?\**:?\**\s*(?:[+-]?\s*\d+|n/a)\s*,\s*"
    r"(?P<use>constant effect|(?P<count>\d+|unlimited)\s*(?:uses?\s*)?(?:per|/|a)\s*day)",
    re.I,
)
ITEM_USE_WINDOW = 400
# Theurgy daimon gifts (Ancient Magic "Example Azai Effects") share the use line.
NOT_DEVICE_PATH_RE = re.compile(r"(?:^|/)example-[a-z-]+-effects/")
NOT_DEVICE_TITLE_RE = re.compile(r":\s*$|\(cont['’]?d\)", re.I)
DEVICE_TITLE_RE = re.compile(
    r"^(?P<kind>Talisman|Invested Device|Lesser Enchanted Device|Charged Item)s?:\s*"
    r"(?P<name>\S.*)$",
    re.I,
)


def _item_use_label(use: re.Match[str]) -> str:
    count = use.group("count")
    if count is None:
        return "Constant effect"
    if count.lower() == "unlimited":
        return "Unlimited uses/day"
    return f"{count}/day"


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
    size_match = BEAST_SIZE_RE.search(head)
    if size_match and size_match.group("size"):
        size = re.sub(r"[\s*]+", "", size_match.group("size"))

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
        re.search(r"house-[a-z-]+/.*(?:house-)?organization", path) or "house-organization" in path
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

    # Named orders, cults, leagues: "The Cult of Mercury", "The Teutonic Knights".
    if (
        ORG_NAME_RE.match(title)
        and not SKIP_ORG_NAME_RE.search(title)
        and len(body.strip()) >= ORG_MIN_BODY
    ):
        return ExtractedEntry(
            entry_type="organization",
            name=title,
            slug=slugify(title)[:200] or "organization",
            summary=_summary(body),
            section=section,
            category="",
            evidence=title,
        )
    return None


def _child_titles(section: Section) -> list[str]:
    """Subsection titles; boxes (unsaved pseudo-sections) have none."""
    if section.pk is None:
        return []
    return [child.title for child in section.children.all()]


def _is_covenant_writeup(section: Section) -> bool:
    """Subsections read like a covenant: ≥3 typical parts, one covenant-only."""
    parts = set()
    for title in _child_titles(section):
        match = COVENANT_PART_RE.match(title.strip())
        if match:
            parts.add(match.group("part").casefold())
    return len(parts) >= COVENANT_MIN_PARTS and any(map(COVENANT_MARKER_RE.match, parts))


def extract_place(section: Section) -> ExtractedEntry | None:
    """Named covenants / oppida / season example covenants."""
    title = _section_title(section)
    if SKIP_TITLE_RE.match(title) or SKIP_PLACE_TITLE_RE.search(title):
        return None

    body = _clean_body(section.body_markdown)
    if len(body.strip()) < 40:
        return None

    category = "Covenant"
    if COVENANT_PLACE_TITLE_RE.search(title) and section.level <= 2:
        pass
    elif CORE_SEASON_COVENANT_RE.match(title) and _path_has(section, "covenant-season"):
        pass
    elif section.level <= 3 and _is_covenant_writeup(section):
        pass
    elif PLACE_AURA_LINE_RE.search(body[:PLACE_AURA_WINDOW]):
        category = ""
    else:
        return None

    aura = ""
    aura_match = PLACE_AURA_LINE_RE.search(body[:PLACE_AURA_WINDOW]) or re.search(
        r"\b((?:Magic|Faerie|Divine|Infernal)\s+)?[Aa]ura\s+(?:of\s+)?(\d+)\b",
        body[:600],
    )
    if aura_match:
        aura = re.sub(r"\s+", " ", aura_match.group(0).replace("*", "")).strip()

    summary = _summary(body)
    if aura and aura not in summary:
        summary = f"{summary} ({aura})" if summary else aura

    return ExtractedEntry(
        entry_type="place",
        name=title.title() if title.islower() else title,
        slug=slugify(title)[:200] or "place",
        summary=summary[:512],
        section=section,
        category=category,
        evidence=title,
    )


def extract_item(section: Section) -> ExtractedEntry | None:
    """Enchanted devices and their effects (not lab procedure chapters).

    Recognized: ``Talisman: Name`` style device headings, sections whose head
    carries a device use line (``Pen +0, 6/day``, ``constant effect``), and
    ``This enchanted item …`` writeups.
    """
    title = _section_title(section)
    path = (section.path or "").lower()
    if "chapter-8-laboratory" in path or "laboratories/" in path:
        return None
    body = _clean_body(section.body_markdown)

    device = DEVICE_TITLE_RE.match(title)
    if device:
        name = device.group("name").strip()
        return ExtractedEntry(
            entry_type="item",
            name=name,
            slug=slugify(name)[:200] or "item",
            summary=_summary(body),
            section=section,
            category=device.group("kind").capitalize(),
            evidence=title[:240],
        )

    if SKIP_ITEM_TITLE_RE.match(title) or SKIP_TITLE_RE.match(title):
        return None
    head = body[:ITEM_USE_WINDOW]
    if MIGHT_LINE_RE.search(head):
        return None

    use = ITEM_USE_RE.search(head)
    if use and not (NOT_DEVICE_PATH_RE.search(path) or NOT_DEVICE_TITLE_RE.search(title)):
        art = _art_lead(head)
        return ExtractedEntry(
            entry_type="item",
            name=title,
            slug=slugify(title)[:200] or "item",
            summary=_summary(body),
            section=section,
            category=_item_use_label(use),
            technique=art.technique,
            form=art.form,
            level=art.level,
            evidence=use.group(0)[:240],
        )

    if section.level < 3:
        return None
    lead = ENCHANTED_ITEM_LEAD_RE.search(head)
    if not lead:
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
