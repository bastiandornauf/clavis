"""Spell extraction: params blocks, art leads, blockquoted spells."""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.utils.text import slugify

from apps.library.models import Section
from clavis.markdown.normalize import unescape_markdown_text

from .common import (
    SKIP_TITLE_RE,
    ExtractedEntry,
    _clean_body,
    _level_token,
    _section_title,
    normalize_art_names,
)
from .creatures import CREATURE_LEAD_RE, CREATURE_LEAD_WINDOW

# ``LEVEL 15`` / ``LEVEL GEN`` / Core's bare ``GENERAL`` band before LEVEL 5.
LEVEL_HEADING_RE = re.compile(
    r"^(?:LEVEL\s+(?P<level>\d+|GEN(?:ERAL)?)\b|(?P<general>GENERAL)\s*$)", re.I
)
# Level after the target on the params line: ``T: Ind, Level 35, Ritual``.
PARAMS_TAIL_LEVEL_RE = re.compile(r",\s*\**Level\s+(?P<level>\d+|Gen(?:eral)?)\b", re.I)
SPELL_PARAMS_RE = re.compile(
    r"^R:\s*(?P<range>[^,;\n]+?),\s*D:\s*(?P<duration>[^,;\n]+?),\s*T:\s*(?P<target>[^,<\n]+)",
    re.I | re.M,
)
# Blockquote / bold-label writeups: ``**R:** Eye, **D:** Sun, **T:** Ind, **Level 25**``
SPELL_PARAMS_BOLD_RE = re.compile(
    r"^(?:>\s*)?\*\*R:\*\*\s*(?P<range>[^,;\n]+?),\s*"
    r"\*\*D:\*\*\s*(?P<duration>[^,;\n]+?),\s*"
    r"\*\*T:\*\*\s*(?P<target>[^,;\n*]+)"
    r"(?:,\s*\*\*Level\s+(?P<level>\d+|Gen(?:eral)?)\*\*)?",
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
# Supplement spell leads: ``MuCo 5``, ``CrHe(An) 10``, ``**ReHe 48**``, ``PeVi Gen``.
# ``[Il]m`` tolerates the OCR slip ``Mulm`` for MuIm.
SPELL_ART_LEAD_RE = re.compile(
    r"^\**\s*(?P<tech>Cr|In|Mu|Pe|Re)(?:\s*\([A-Za-z, ]+\))?"
    r"(?P<form>An|Aq|Au|Co|He|Ig|[Il]m|Me|Te|Vi)"
    r"(?:\s*\([A-Za-z, ]+\))?\**\s+(?:Level\s+)?(?P<level>\d+|Gen(?:eral)?)\b",
    re.M,
)
# Only trusted after an art lead opens the section: R/D/T on the lead line, or with
# slips like ``R: Touch D: Sun, T Room`` (missing comma / colon).
SPELL_PARAMS_LENIENT_RE = re.compile(
    r"\bR:\**\s*(?P<range>[^,;\n*]+?),?\s+\**D:\**\s*(?P<duration>[^,;\n*]+?),\s*"
    r"\**T:?\**\s+(?P<target>[^,<\n*]+)",
    re.I,
)
ART_LEAD_PARAM_WINDOW = 320
# Creature / character powers share R/D/T lines but are not spells:
# ``1 point, Init: Qik–1, Animal`` · ``Corpus, Pen +0, 1 use/day``.
POWER_LEAD_RE = re.compile(
    r"\b\d+\s+points?\b|\bno cost\b|\bInit(?:iative)?\s*[:(]"
    r"|\bPen\s*\+\d+,\s*(?:\d+|unlimited)\s+uses?\b",
    re.I,
)
# Non-Hermetic spell leads: ``Level 10`` (Amazons), ``Aloe 30`` (Soqotra),
# ``Evocation/Beguile 15`` (faerie wizardry), ``Threads of Fate Ease Factor 30``.
FOREIGN_SPELL_LEAD_RE = re.compile(
    r"^\**\s*(?P<label>[A-Z][A-Za-z'/ ]{1,40}?)\s+(?P<ease>Ease Factor\s+)?"
    r"(?P<level>\d+|General)\b",
    re.M,
)
# Full-name lead: ``Rego Herbam (Animal) 15`` (enchanted device effects).
FULL_ART_LEAD_RE = re.compile(
    r"^\**\s*(?P<tech>Creo|Intellego|Muto|Perdo|Rego)(?:\s*\([A-Za-z, ]+\))?\s+"
    r"(?P<form>Animal|Aquam|Auram|Corpus|Herbam|Ignem|Imaginem|Mentem|Terram|Vim)"
    r"(?:\s*\([A-Za-z, ]+\))?\**\s+(?:Level\s+)?(?P<level>\d+|Gen(?:eral)?)\b",
    re.M,
)
NON_HERMETIC = "Non-Hermetic"
TECHNIQUE_ABBREVIATIONS = {
    "Cr": "Creo",
    "In": "Intellego",
    "Mu": "Muto",
    "Pe": "Perdo",
    "Re": "Rego",
}
FORM_ABBREVIATIONS = {
    "An": "Animal",
    "Aq": "Aquam",
    "Au": "Auram",
    "Co": "Corpus",
    "He": "Herbam",
    "Ig": "Ignem",
    "Im": "Imaginem",
    "lm": "Imaginem",
    "Me": "Mentem",
    "Te": "Terram",
    "Vi": "Vim",
}

# Spell parameter lines must appear near the top of the section body.
SPELL_PARAM_WINDOW = 280


def _parent_level(section: Section) -> tuple[int | None, bool]:
    current = section.parent
    while current is not None:
        match = LEVEL_HEADING_RE.match(current.title.strip())
        if match:
            if match.group("general"):
                return None, True
            return _level_token(match.group("level"))
        current = current.parent
    return None, False


def _parent_technique_form(section: Section) -> tuple[str, str]:
    current = section.parent
    while current is not None:
        match = TECHNIQUE_FORM_RE.search(normalize_art_names(current.title))
        if match:
            return match.group("tech").title(), match.group("form").title()
        current = current.parent
    return "", ""


_PAREN_RE = re.compile(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)")


@dataclass
class _ArtLead:
    technique: str = ""
    form: str = ""
    level: int | None = None
    general: bool = False


def _art_lead(text: str) -> _ArtLead:
    """Technique, form and level from a lead like ``MuCo 5`` or ``Rego Herbam 15``.

    Also checks parentheses: ``Air of Friendly Magic (MuVi 30)``.
    """
    match = SPELL_ART_LEAD_RE.search(text)
    if not match:
        for inner in _PAREN_RE.finditer(text):
            match = SPELL_ART_LEAD_RE.match(inner.group(1).strip())
            if match:
                break
    if match:
        technique = TECHNIQUE_ABBREVIATIONS[match.group("tech")]
        form = FORM_ABBREVIATIONS[match.group("form")]
    else:
        match = FULL_ART_LEAD_RE.search(text)
        if not match:
            return _ArtLead()
        technique, form = match.group("tech").title(), match.group("form").title()
    level, general = _level_token(match.group("level"))
    return _ArtLead(technique, form, level, general)


def _spell_entry(
    *,
    section: Section,
    name: str,
    params: re.Match[str],
    technique: str = "",
    form: str = "",
    level: int | None = None,
    general: bool = False,
    tradition: str = "",
) -> ExtractedEntry:
    if level is None and not general and params.groupdict().get("level"):
        level, general = _level_token(params.group("level"))
    summary_bits: list[str] = []
    if tradition:
        summary_bits.append(tradition)
    if technique and form:
        summary_bits.append(f"{technique} {form}")
    if level is not None:
        summary_bits.append(f"Level {level}")
    elif general:
        summary_bits.append("Level General")
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
        level_general=general,
        range=params.group("range").strip(),
        duration=params.group("duration").strip(),
        target=params.group("target").strip(),
        category=tradition,
        evidence=params.group(0).strip()[:240],
    )


def extract_spell(section: Section) -> ExtractedEntry | None:
    body = _clean_body(section.body_markdown)
    if CREATURE_LEAD_RE.search(body[:CREATURE_LEAD_WINDOW]):
        return None
    if SKIP_TITLE_RE.match(_section_title(section)):
        return None
    # A section that opens with ``MuMe 10`` / ``ReVi Gen`` is a spell writeup even
    # when its R/D/T line is bold, inline, or sloppy.
    first_line = body.lstrip().split("\n", 1)[0]
    opens_with_art = bool(SPELL_ART_LEAD_RE.match(first_line) or FULL_ART_LEAD_RE.match(first_line))
    if section.level < 3 and not opens_with_art:
        return None

    head = body[:SPELL_PARAM_WINDOW]
    # Classic section-as-spell (plain R:/D:/T:). Other bold callouts are harvested
    # separately so narrative sections like "Magi" are not mislabeled as spells.
    params = SPELL_PARAMS_RE.search(head)
    if not params and opens_with_art:
        art_head = body[:ART_LEAD_PARAM_WINDOW]
        params = SPELL_PARAMS_BOLD_RE.search(art_head) or SPELL_PARAMS_LENIENT_RE.search(art_head)
    if not params:
        # Bold params that open the section and carry their own level
        # (``**R:** Per, **D:** Sun, **T:** Vision, **Level Gen**``).
        bold = SPELL_PARAMS_BOLD_RE.search(head)
        if bold and bold.group("level") and not head[: bold.start()].strip():
            params = bold
    if not params:
        return None

    level, general = _parent_level(section)
    technique, form = _parent_technique_form(section)
    lead = head[: params.start()]
    art = _art_lead(lead)
    if not art.technique:
        art = _art_lead(_section_title(section))
    if not technique or not form:
        technique, form = art.technique, art.form
    if not technique or not form:
        tf = TECHNIQUE_FORM_RE.search(body[:800])
        if tf:
            technique = tf.group("tech").title()
            form = tf.group("form").title()
    if level is None and not general:
        level, general = art.level, art.general
    if level is None and not general and params.groupdict().get("level"):
        level, general = _level_token(params.group("level"))
    if level is None and not general:
        line_end = body.find("\n", params.end())
        tail = PARAMS_TAIL_LEVEL_RE.search(body[params.end() : line_end if line_end >= 0 else None])
        if tail:
            level, general = _level_token(tail.group("level"))

    tradition = ""
    if not (technique and form):
        around = head[: params.end() + 80]
        if POWER_LEAD_RE.search(around):
            return None
        foreign = FOREIGN_SPELL_LEAD_RE.search(lead)
        if foreign and foreign.group("label").strip().lower() != "general":
            tradition = NON_HERMETIC
            if level is None and not foreign.group("ease") and foreign.group("level").isdigit():
                level = int(foreign.group("level"))

    # Prefer true formulaic spell writeups: LEVEL parent and/or Tech+Form.
    # Bare R/D/T later in creature powers is already excluded by the window.
    if level is None and not general and not (technique and form):
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
        general=general,
        tradition=tradition,
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
        art = _art_lead(prefix[-120:])
        if not (technique and form) and art.technique:
            technique, form = art.technique, art.form
        tf = TECHNIQUE_FORM_RE.search(head_chunk)
        if tf:
            technique = technique or tf.group("tech").title()
            form = form or tf.group("form").title()
        if not (technique and form) and POWER_LEAD_RE.search(prefix[-160:]):
            continue
        seen.add(key)
        found.append(
            _spell_entry(
                section=section,
                name=name,
                params=params,
                technique=technique,
                form=form,
                level=None if params.groupdict().get("level") else art.level,
                general=False if params.groupdict().get("level") else art.general,
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
