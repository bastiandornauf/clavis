"""Rule-based extractors for catalog entry types."""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.utils.text import slugify

from apps.library.models import Section
from clavis.markdown.normalize import normalize_source_markdown, unescape_markdown_text

LEVEL_HEADING_RE = re.compile(r"^LEVEL\s+(\d+)\b", re.I)
SPELL_PARAMS_RE = re.compile(
    r"^R:\s*(?P<range>[^,;\n]+?),\s*D:\s*(?P<duration>[^,;\n]+?),\s*T:\s*(?P<target>[^,<\n]+)",
    re.I | re.M,
)
# Blockquote / bold-label writeups: ``**R:** Eye, **D:** Sun, **T:** Ind, **Level 25**``
SPELL_PARAMS_BOLD_RE = re.compile(
    r"^(?:>\s*)?\*\*R:\*\*\s*(?P<range>[^,;\n]+?),\s*"
    r"\*\*D:\*\*\s*(?P<duration>[^,;\n]+?),\s*"
    r"\*\*T:\*\*\s*(?P<target>[^,;\n*]+)"
    r"(?:,\s*\*\*Level\s+(?P<level>\d+)\*\*)?",
    re.I | re.M,
)
# Callout spell name: ``>**MY NEW BEST FRIEND**`` or ``> #### Title`` then bold name.
BQ_SPELL_NAME_RE = re.compile(
    r"^(?:>\s*)?(?:#{2,6}\s+(?P<head_tech>Creo|Intellego|Muto|Perdo|Rego)\s+"
    r"(?P<head_form>Animal|Aquam|Auram|Corpus|Herbam|Ignem|Imaginem|Mentem|Terram|Vim)"
    r"\s+Spells?\s*$|\*\*(?P<name>[^*]{3,80})\*\*\s*$)",
    re.I | re.M,
)
SPELL_BLOCK_WINDOW = 1200
TECHNIQUE_FORM_RE = re.compile(
    r"\b(?P<tech>Creo|Intellego|Muto|Perdo|Rego)\s+"
    r"(?P<form>Animal|Aquam|Auram|Corpus|Herbam|Ignem|Imaginem|Mentem|Terram|Vim)\b",
    re.I,
)
# Classic Core: *Major, Hermetic* — Art & Academe: *Social Status, Major*
VF_ITALIC_RE = re.compile(
    r"^\*(?:"
    r"(?P<mag_first>Major|Minor|Free),\s*(?P<cat_after>[^*]+)"
    r"|"
    r"(?P<cat_before>[^*]+?),\s*(?P<mag_after>Major|Minor|Free)"
    r")\*",
    re.I | re.M,
)
VF_PLAIN_RE = re.compile(
    r"^(?P<mag>Major|Minor|Free)\s+(?P<cat>.+?)\s+(?P<kind>Virtue|Flaw)\b",
    re.I | re.M,
)
VF_ALT_RE = re.compile(
    r"^(?P<mag>Major|Minor|Free)\s+(?P<kind>Virtue|Flaw)\b(?:,\s*(?P<cat>.+))?",
    re.I | re.M,
)
# Art & Academe university chapter: **Jurist**<br>\n*Social Status, Minor*
VF_BOLD_BLOCK_RE = re.compile(
    r"^\*\*(?P<name>[^*]{2,90})\*\*(?:<br\s*/?>)?\s*\n"
    r"\*(?:"
    r"(?P<mag_first>Major|Minor|Free),\s*(?P<cat_after>[^*]+)"
    r"|"
    r"(?P<cat_before>[^*]+?),\s*(?P<mag_after>Major|Minor|Free)"
    r")\*",
    re.I | re.M,
)

SKIP_TITLE_RE = re.compile(
    r"^(list of|types? of|choosing|quick and easy|virtues and flaws|"
    r"social status virtues|virtues$|flaws$|guidelines?$|level\s+\d+|"
    r"example |new .*virtue|new .*flaw|"
    r"creatures?( of)?|chapter\b|the houses?\b|covenants?$)",
    re.I,
)

STORY_SEED_TITLE_RE = re.compile(r"^Story Seeds?\s*:\s*(?P<name>.+?)\s*$", re.I)
STORY_SEED_LINE_RE = re.compile(
    r"^(?:>\s*)?(?:#{1,6}\s+)?Story Seeds?\s*:\s*(?P<name>.+?)\s*$",
    re.I | re.M,
)
# Front-matter / TOC sections list seed titles without being the writeups.
SKIP_STORY_SEED_SECTION_RE = re.compile(
    r"^(contents|table of contents|credits?|copyright|dedication|index|"
    r"acknowledgements?|about this book)$",
    re.I,
)

# Used to keep spells/VF away from creature writeups.
CREATURE_LEAD_RE = re.compile(
    r"^\s*(\*\*)?(Magic Might|Faerie Might|Infernal Might|Divine Might|"
    r"Characteristics|Season:|Size:)\b",
    re.I | re.M,
)

# Allow optional blockquote markers and bold wrappers around the label/colon
# (Contested Isle callouts use ``> **Faerie Might:** 50``).
# Colon may sit inside or outside bold: ``**Faerie Might:** 20`` or ``**Magic Might**: 20``.
MIGHT_LINE_RE = re.compile(
    r"^(?:>\s*)?(?:\*\*)?(?P<realm>Magic|Faerie|Infernal|Divine)\s+Might"
    r"(?:\*\*)?\s*:(?:\*\*)?\s*"
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

GUIDELINE_TITLE_RE = re.compile(
    r"^(?P<tech>Creo|Intellego|Muto|Perdo|Rego)\s+"
    r"(?P<form>Animal|Aquam|Auram|Corpus|Herbam|Ignem|Imaginem|Mentem|Terram|Vim)"
    r"\s+Guidelines?\s*$",
    re.I,
)
GUIDELINE_ROW_RE = re.compile(
    r"^\|\s*(?P<level>\d+)\s*\|\s*(?P<body>.+?)\s*\|\s*$",
    re.M,
)
ABILITY_SPECIALTIES_RE = re.compile(
    r"\*Specialties?:\*\s*[^\n]+\((?P<cat>General|Academic|Arcane|Martial|Supernatural)\)",
    re.I,
)
SKIP_ABILITY_TITLE_RE = re.compile(
    r"^(general|academic|arcane|martial|supernatural)\s+abilities$|"
    r"^abilities\b|by type$",
    re.I,
)

# Spell parameter lines must appear near the top of the section body.
SPELL_PARAM_WINDOW = 280
CREATURE_LEAD_WINDOW = 400
CHARACTER_AGE_WINDOW = 280


def _vf_italic_groups(match: re.Match[str]) -> tuple[str, str]:
    """Return (magnitude, category) from either italic order."""
    if match.groupdict().get("mag_first"):
        return match.group("mag_first").title(), match.group("cat_after").strip().rstrip(".")
    return match.group("mag_after").title(), match.group("cat_before").strip().rstrip(".")


def _virtue_or_flaw_from_path(path: str) -> str:
    """Infer virtue vs flaw from path segments, not substrings."""
    segments = path.lower().split("/")
    for segment in reversed(segments):
        # Mixed chapters (…/new-virtues-and-flaws/…) are ambiguous — skip.
        if "virtue" in segment and "flaw" in segment:
            continue
        if segment in {"flaws", "new-flaws"} or segment.startswith("flaws-"):
            return "flaw"
        if segment in {"virtues", "new-virtues"} or segment.startswith("virtues-"):
            return "virtue"
    return ""


def _virtue_or_flaw_from_ancestors(section: Section) -> str:
    """Infer kind from exclusive Virtues/Flaws ancestor titles or prior siblings."""
    kind = _virtue_or_flaw_from_path(section.path)
    if kind:
        return kind

    current = section.parent
    while current is not None:
        title = current.title.strip().lower()
        has_virtue = bool(re.search(r"\bvirtues?\b", title))
        has_flaw = bool(re.search(r"\bflaws?\b", title))
        if has_flaw and not has_virtue:
            return "flaw"
        if has_virtue and not has_flaw:
            return "virtue"
        current = current.parent

    parent = section.parent
    if parent is None or parent.id is None:
        return ""
    # Under "New Virtues and Flaws", earlier siblings like #### New Virtues mark the side.
    siblings = (
        Section.objects.filter(parent_id=parent.id, position__lt=section.position)
        .order_by("-position")
        .values_list("title", flat=True)[:20]
    )
    for title in siblings:
        low = title.strip().lower()
        has_virtue = bool(re.search(r"\bvirtues?\b", low))
        has_flaw = bool(re.search(r"\bflaws?\b", low))
        if has_flaw and not has_virtue:
            return "flaw"
        if has_virtue and not has_flaw:
            return "virtue"
    return ""


@dataclass
class ExtractedEntry:
    entry_type: str
    name: str
    slug: str
    summary: str
    section: Section
    kind: str = "definition"
    technique: str = ""
    form: str = ""
    level: int | None = None
    range: str = ""
    duration: str = ""
    target: str = ""
    magnitude: str = ""
    category: str = ""
    evidence: str = ""


def _clean_body(body: str) -> str:
    return normalize_source_markdown(body)


def _section_title(section: Section) -> str:
    return unescape_markdown_text(section.title.strip())


def _parent_level(section: Section) -> int | None:
    current = section.parent
    while current is not None:
        match = LEVEL_HEADING_RE.match(current.title.strip())
        if match:
            return int(match.group(1))
        current = current.parent
    return None


def _parent_technique_form(section: Section) -> tuple[str, str]:
    current = section.parent
    while current is not None:
        match = TECHNIQUE_FORM_RE.search(current.title)
        if match:
            return match.group("tech").title(), match.group("form").title()
        current = current.parent
    return "", ""


def _spell_entry(
    *,
    section: Section,
    name: str,
    params: re.Match[str],
    technique: str = "",
    form: str = "",
    level: int | None = None,
) -> ExtractedEntry:
    if level is None and params.groupdict().get("level"):
        level = int(params.group("level"))
    summary_bits: list[str] = []
    if technique and form:
        summary_bits.append(f"{technique} {form}")
    if level is not None:
        summary_bits.append(f"Level {level}")
    summary_bits.extend(
        [
            f"R: {params.group('range').strip()}",
            f"D: {params.group('duration').strip()}",
            f"T: {params.group('target').strip()}",
        ]
    )
    return ExtractedEntry(
        entry_type="spell",
        name=name,
        slug=slugify(name)[:200] or "spell",
        summary="; ".join(summary_bits),
        section=section,
        technique=technique,
        form=form,
        level=level,
        range=params.group("range").strip(),
        duration=params.group("duration").strip(),
        target=params.group("target").strip(),
        evidence=params.group(0).strip()[:240],
    )


def extract_spell(section: Section) -> ExtractedEntry | None:
    body = _clean_body(section.body_markdown)
    if CREATURE_LEAD_RE.search(body[:CREATURE_LEAD_WINDOW]):
        return None
    if SKIP_TITLE_RE.match(_section_title(section)):
        return None
    if section.level < 3:
        return None

    head = body[:SPELL_PARAM_WINDOW]
    # Classic section-as-spell only (plain R:/D:/T:). Bold callouts are harvested
    # separately so narrative sections like "Magi" are not mislabeled as spells.
    params = SPELL_PARAMS_RE.search(head)
    if not params:
        return None

    level = _parent_level(section)
    technique, form = _parent_technique_form(section)
    if not technique or not form:
        tf = TECHNIQUE_FORM_RE.search(body[:800])
        if tf:
            technique = tf.group("tech").title()
            form = tf.group("form").title()

    # Prefer true formulaic spell writeups: LEVEL parent and/or Tech+Form.
    # Bare R/D/T later in creature powers is already excluded by the window.
    if level is None and not (technique and form):
        # Still accept classic writeups that open with R/D/T under a named spell
        # heading (some books omit LEVEL wrappers).
        if not params.start() <= 40:
            return None

    return _spell_entry(
        section=section,
        name=_section_title(section),
        params=params,
        technique=technique,
        form=form,
        level=level,
    )


def extract_blockquote_spells(section: Section) -> list[ExtractedEntry]:
    """Harvest spell callouts embedded in narrative sections (e.g. Rhine Magi)."""
    body = _clean_body(section.body_markdown)
    if not SPELL_PARAMS_BOLD_RE.search(body):
        return []

    found: list[ExtractedEntry] = []
    seen: set[str] = set()
    for params in SPELL_PARAMS_BOLD_RE.finditer(body):
        window_start = max(0, params.start() - 240)
        prefix = body[window_start : params.start()]
        name = ""
        technique = ""
        form = ""
        for match in BQ_SPELL_NAME_RE.finditer(prefix):
            if match.group("name"):
                candidate = unescape_markdown_text(match.group("name")).strip()
                if re.match(
                    r"^(R|D|T|Level|Requisite|Range|Duration|Target)\b",
                    candidate,
                    re.I,
                ):
                    continue
                name = candidate
            if match.group("head_tech"):
                technique = match.group("head_tech").title()
                form = match.group("head_form").title()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        head_chunk = prefix[-200:] + body[params.start() : params.start() + 200]
        tf = TECHNIQUE_FORM_RE.search(head_chunk)
        if tf:
            technique = technique or tf.group("tech").title()
            form = form or tf.group("form").title()
        seen.add(key)
        found.append(
            _spell_entry(
                section=section,
                name=name,
                params=params,
                technique=technique,
                form=form,
            )
        )
    return found


def extract_spells(section: Section) -> list[ExtractedEntry]:
    boxed = extract_blockquote_spells(section)
    primary = extract_spell(section)
    if primary is None:
        return boxed
    names = {entry.name.casefold() for entry in boxed}
    if primary.name.casefold() not in names:
        return [primary, *boxed]
    return boxed


def _vf_entry(
    *,
    section: Section,
    kind: str,
    name: str,
    mag: str,
    category: str,
    evidence: str,
) -> ExtractedEntry:
    summary_parts = [p for p in (mag, category) if p]
    return ExtractedEntry(
        entry_type=kind,
        name=name,
        slug=slugify(name)[:200] or kind,
        summary=", ".join(summary_parts),
        section=section,
        magnitude=mag,
        category=category,
        evidence=evidence,
    )


def _extract_vf_bold_blocks(section: Section, kind: str) -> list[ExtractedEntry]:
    """Harvest **Name** + italic magnitude lines packed into a chapter body."""
    if kind not in {"virtue", "flaw"}:
        return []
    body = _clean_body(section.body_markdown)
    out: list[ExtractedEntry] = []
    seen: set[str] = set()
    for match in VF_BOLD_BLOCK_RE.finditer(body):
        name = match.group("name").strip()
        if not name or SKIP_TITLE_RE.match(name):
            continue
        key = name.casefold()
        if key in seen:
            continue
        mag, category = _vf_italic_groups(match)
        seen.add(key)
        out.append(
            _vf_entry(
                section=section,
                kind=kind,
                name=name,
                mag=mag,
                category=category,
                evidence=match.group(0)[:240],
            )
        )
    return out


def extract_virtue_or_flaw(section: Section) -> ExtractedEntry | None:
    title = _section_title(section)
    if SKIP_TITLE_RE.match(title):
        return None
    if section.level < 3:
        return None
    if CREATURE_LEAD_RE.search(section.body_markdown[:CREATURE_LEAD_WINDOW]):
        return None

    body = _clean_body(section.body_markdown)
    head = body[:400]
    mag = ""
    category = ""
    kind = ""
    evidence = ""

    italic = VF_ITALIC_RE.search(head)
    if italic:
        mag, category = _vf_italic_groups(italic)
        evidence = italic.group(0)
        kind = _virtue_or_flaw_from_ancestors(section)
        # Italic lines without a virtues/flaws path or chapter context are too
        # ambiguous (story text, lists, house mysteries).
        if not kind:
            return None

    if not kind:
        plain = VF_PLAIN_RE.search(head)
        if plain:
            mag = plain.group("mag").title()
            category = plain.group("cat").strip()
            kind = plain.group("kind").lower()
            evidence = plain.group(0)

    if not kind:
        alt = VF_ALT_RE.search(head)
        if alt:
            mag = alt.group("mag").title()
            kind = alt.group("kind").lower()
            category = (alt.group("cat") or "").strip(" ,")
            evidence = alt.group(0)

    if kind not in {"virtue", "flaw"}:
        return None
    if not mag:
        return None

    return _vf_entry(
        section=section,
        kind=kind,
        name=title,
        mag=mag,
        category=category,
        evidence=evidence,
    )


def extract_virtues_and_flaws(section: Section) -> list[ExtractedEntry]:
    """Heading writeups plus bold-packed entries under Virtues/Flaws chapters."""
    if CREATURE_LEAD_RE.search(section.body_markdown[:CREATURE_LEAD_WINDOW]):
        return []

    kind = _virtue_or_flaw_from_ancestors(section)
    results = _extract_vf_bold_blocks(section, kind) if kind else []

    single = extract_virtue_or_flaw(section)
    if single is None:
        return results

    names = {entry.name.casefold() for entry in results}
    if single.name.casefold() not in names:
        results.insert(0, single)
    return results


def _story_seed_label(raw: str) -> tuple[str, str]:
    """Short display name + summary. Prose seeds (no real title) are abbreviated."""
    raw = raw.strip().rstrip(" .")
    words = raw.split()
    # Titles stay as-is; long/sentence-like leads become short labels.
    is_prose = len(raw) > 40 or len(words) > 6 or ". " in raw
    if not is_prose:
        return raw, "Story seed"

    label_parts: list[str] = []
    length = 0
    for word in words[:3]:
        extra = len(word) + (1 if label_parts else 0)
        if label_parts and length + extra > 20:
            break
        label_parts.append(word)
        length += extra
    label = " ".join(label_parts).rstrip(",;:")
    if len(words) > len(label_parts) or len(raw) > len(label):
        label += "…"
    summary = raw if len(raw) <= 512 else f"{raw[:509]}…"
    return label, summary


def extract_story_seeds(section: Section) -> list[ExtractedEntry]:
    """Recognize Story Seed headings and in-body / blockquote seed lines."""
    if SKIP_STORY_SEED_SECTION_RE.match(_section_title(section)):
        return []

    found: list[ExtractedEntry] = []
    seen: set[str] = set()

    def add(raw_name: str, evidence: str) -> None:
        raw_name = raw_name.strip().rstrip(" .")
        if not raw_name or raw_name.lower() in {"story seed", "story seeds"}:
            return
        key = raw_name.casefold()
        if key in seen:
            return
        seen.add(key)
        name, summary = _story_seed_label(raw_name)
        found.append(
            ExtractedEntry(
                entry_type="story_seed",
                name=name,
                slug=slugify(raw_name)[:200] or "story-seed",
                summary=summary,
                section=section,
                evidence=evidence.strip()[:240],
            )
        )

    title_match = STORY_SEED_TITLE_RE.match(_section_title(section))
    if title_match:
        add(title_match.group("name"), _section_title(section))

    body = _clean_body(section.body_markdown)
    for match in STORY_SEED_LINE_RE.finditer(body):
        add(match.group("name"), match.group(0))

    return found


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
        found.append(
            _creature_entry(section=section, name=name, might=might, scan=flat)
        )
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


def _extract_house(header: str) -> str:
    """Return Hermetic house from a title/header, or empty string."""
    match = CHAR_HOUSE_RE.search(header)
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


def extract_characters(section: Section) -> list[ExtractedEntry]:
    """Named people: bold Magus headers and Age-led section writeups."""
    body = _clean_body(section.body_markdown)
    if MIGHT_LINE_RE.search(body[:CREATURE_LEAD_WINDOW]):
        return []

    found: list[ExtractedEntry] = []
    seen: set[str] = set()

    def add(name: str, house: str, age: str, evidence: str) -> None:
        key = name.casefold()
        if key in seen:
            return
        seen.add(key)
        summary_bits = [bit for bit in (house, f"Age {age}" if age else "") if bit]
        found.append(
            ExtractedEntry(
                entry_type="character",
                name=name,
                slug=slugify(name)[:200] or "character",
                summary="; ".join(summary_bits) or "Named character",
                section=section,
                category=house,
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
    if SKIP_TITLE_RE.match(title) or section.level < 3:
        return []
    head = body[:CHARACTER_AGE_WINDOW]
    age_match = AGE_LINE_RE.search(head)
    if not age_match:
        return []
    if not PERSONALITY_RE.search(head):
        return []
    parsed = _character_name_and_house(title)
    if parsed:
        name, house = parsed
    else:
        name, house = re.sub(r"\s+", " ", title).strip(), ""
    add(name, house, age_match.group("age"), title)
    return found


def _guideline_bullet_label(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" •-")
    if len(text) > 90:
        text = text[:87].rstrip() + "…"
    return text


def extract_guidelines(section: Section) -> list[ExtractedEntry]:
    """Tech+Form guideline tables (Core spell design chapters)."""
    title = _section_title(section)
    match = GUIDELINE_TITLE_RE.match(title)
    if not match:
        return []

    technique = match.group("tech").title()
    form = match.group("form").title()
    body = _clean_body(section.body_markdown)
    found: list[ExtractedEntry] = []
    seen: set[str] = set()

    for row in GUIDELINE_ROW_RE.finditer(body):
        level = int(row.group("level"))
        cell = row.group("body")
        parts = re.split(r"(?:<br\s*/?>|\s*•\s*)", cell, flags=re.I)
        for part in parts:
            label = _guideline_bullet_label(part)
            if not label or label.lower().startswith("level"):
                continue
            key = f"{level}:{label.casefold()}"
            if key in seen:
                continue
            seen.add(key)
            name = f"{technique} {form} {level}: {label}"
            found.append(
                ExtractedEntry(
                    entry_type="guideline",
                    name=name[:512],
                    slug=slugify(name)[:200] or "guideline",
                    summary=f"{technique} {form}; Base {level}",
                    section=section,
                    technique=technique,
                    form=form,
                    level=level,
                    evidence=label[:240],
                )
            )

    if found:
        return found

    # Section matched but table missing — keep one bookmark entry.
    return [
        ExtractedEntry(
            entry_type="guideline",
            name=title,
            slug=slugify(title)[:200] or "guideline",
            summary=f"{technique} {form} guidelines",
            section=section,
            technique=technique,
            form=form,
            evidence=title,
        )
    ]


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


def extract_from_section(section: Section) -> list[ExtractedEntry]:
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

    # Dedicated spell sections win exclusively; callout spells merge with other types.
    primary_spell = extract_spell(section)
    boxed_spells = extract_blockquote_spells(section)
    if primary_spell is not None:
        return extract_spells(section)

    vf = extract_virtues_and_flaws(section)
    if vf:
        return vf

    boons_hooks = extract_boons_and_hooks(section)
    if boons_hooks:
        return [*boons_hooks, *seeds]

    creatures = extract_creatures(section)
    if creatures:
        return [*creatures, *boxed_spells, *seeds]

    beast = extract_beast(section)
    if beast:
        return [beast, *boxed_spells, *seeds]

    characters = extract_characters(section)
    if characters:
        return [*characters, *boxed_spells, *seeds]

    organization = extract_organization(section)
    if organization:
        return [organization, *boxed_spells, *seeds]

    place = extract_place(section)
    if place:
        return [place, *boxed_spells, *seeds]

    item = extract_item(section)
    if item:
        return [item, *boxed_spells, *seeds]

    ability = extract_ability(section)
    if ability:
        return [ability, *boxed_spells, *seeds]
    if boxed_spells:
        return [*boxed_spells, *seeds]
    return seeds
