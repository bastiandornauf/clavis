"""Vis source extraction: renewing vis sites, not one-off pawns or creature vis."""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.library.models import Section

from .common import SKIP_TITLE_RE, ExtractedEntry, _clean_body, _section_title, normalize_art_names
from .creatures import CREATURE_LEAD_WINDOW, MIGHT_LINE_RE

_ARTS = (
    "Creo",
    "Intellego",
    "Muto",
    "Perdo",
    "Rego",
    "Animal",
    "Aquam",
    "Auram",
    "Corpus",
    "Herbam",
    "Ignem",
    "Imaginem",
    "Mentem",
    "Terram",
    "Vim",
)
_NUMBER_WORDS = {
    "a": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
# `6 pawns of Perdo`, `Four pawns of Rego vis`, `7 Imaginem vis`, list-only `4 Herbam`.
VIS_AMOUNT_RE = re.compile(
    rf"\b(?P<count>\d+|{'|'.join(_NUMBER_WORDS)})\s+(?P<pawns>pawns?\s+(?:of\s+)?)?"
    rf"(?P<art>{'|'.join(_ARTS)})\b(?P<vis>\s+vis\b)?",
    re.I,
)
VIS_RENEW_RE = re.compile(
    r"\b(?:per|each|every|a)\s+year\b|\bper\s+season\b|"
    r"\b(?:each|every)\s+(?:winter|summer|spring|autumn|midsummer|solstice|equinox)\b|"
    r"\bannually\b|\byearly\b",
    re.I,
)
# Objects of Virtue hold vis once; they are not renewing sources.
VIS_OBJECT_RE = re.compile(r"\bof\s+Virtue\b", re.I)
VIS_TITLE_PREFIX_RE = re.compile(r"^vis\s+(?:site|source)s?:\s*(?P<name>.+)$", re.I)
VIS_LIST_TITLE_RE = re.compile(r"\bvis\s+(?:sources?|sites?)\b|^vis$", re.I)
VIS_NAME_LINE_RE = re.compile(
    r"^(?:\*\*(?P<bold>[^*\n]{2,70})\*\*|\*(?P<italic>[^*\n]{2,70})\*)\s*:?\s*(?P<rest>.*)$",
    re.M,
)
VIS_HEAD_WINDOW = 300
VIS_LIST_WINDOW = 250


def _amounts(text: str, *, need_unit: bool) -> list[re.Match[str]]:
    return [
        match
        for match in VIS_AMOUNT_RE.finditer(text)
        if not need_unit or match.group("pawns") or match.group("vis")
    ]


def _first_paragraph(body: str) -> str:
    for paragraph in re.split(r"\n\s*\n", body):
        if paragraph.strip():
            return paragraph.strip()[:VIS_HEAD_WINDOW]
    return ""


def _vis_entry(section: Section, name: str, text: str, amounts: list[re.Match[str]]):
    arts: list[str] = []
    counts: list[int] = []
    for match in amounts:
        art = match.group("art").title()
        if art not in arts:
            arts.append(art)
        count = match.group("count").lower()
        counts.append(int(count) if count.isdigit() else _NUMBER_WORDS[count])
    # "Either 6 Aquam or 6 Ignem" yields one of them, not both.
    alternatives = re.search(r"\b(?:either|or)\b", text, re.I)
    pawns = (max(counts) if alternatives else sum(counts)) if counts else 0
    summary = re.sub(r"\s+", " ", re.sub(r"[*_]+", "", text)).strip()
    return ExtractedEntry(
        entry_type="vis_source",
        name=name,
        slug=slugify(name)[:200] or "vis-source",
        summary=summary[:240],
        section=section,
        form=", ".join(arts),
        level=pawns or None,
        category=arts[0] if len(arts) == 1 else ("Mixed" if arts else ""),
        evidence=summary[:240],
    )


def _listed_sources(section: Section, body: str) -> list[ExtractedEntry]:
    """Name lines in a Vis Sources section, each followed by its yearly amount."""
    found = []
    # Sites that also have their own (sub- or sibling) section are extracted there.
    subsections: set[str] = set()
    for holder in (section, section.parent):
        if holder is not None and holder.pk is not None:
            subsections |= {child.title.strip().casefold() for child in holder.children.all()}
    for line in VIS_NAME_LINE_RE.finditer(body):
        name = (line.group("bold") or line.group("italic")).strip().rstrip(":.")
        if _amounts(name, need_unit=False) or name.casefold() in subsections:
            continue
        window = line.group("rest") + "\n" + body[line.end() : line.end() + VIS_LIST_WINDOW]
        window = re.split(r"\n\s*\n(?=\*)", window.strip(), maxsplit=1)[0]
        amounts = _amounts(window, need_unit=False)
        if amounts:
            found.append(_vis_entry(section, name, window, amounts))
    return found


def extract_vis_sources(section: Section) -> list[ExtractedEntry]:
    """Renewing vis sources: per-site sections, ``Vis Site:`` titles, and source lists."""
    title = _section_title(section)
    body = normalize_art_names(_clean_body(section.body_markdown))
    if MIGHT_LINE_RE.search(body[:CREATURE_LEAD_WINDOW]):
        return []

    if VIS_LIST_TITLE_RE.search(title) and not VIS_TITLE_PREFIX_RE.match(title):
        return _listed_sources(section, body)

    prefixed = VIS_TITLE_PREFIX_RE.match(title)
    lead = _first_paragraph(body)
    under_list = section.parent is not None and VIS_LIST_TITLE_RE.search(
        _section_title(section.parent)
    )
    if prefixed:
        amounts = _amounts(body[: VIS_HEAD_WINDOW * 2], need_unit=True)
        return [_vis_entry(section, prefixed.group("name").strip(), lead, amounts)]
    if SKIP_TITLE_RE.match(title) or VIS_OBJECT_RE.search(title) or VIS_OBJECT_RE.search(lead):
        return []
    if under_list:
        text = body[: VIS_HEAD_WINDOW + VIS_LIST_WINDOW]
        amounts = _amounts(text, need_unit=True)
        if amounts and VIS_RENEW_RE.search(text):
            return [_vis_entry(section, title, lead, amounts[:1])]
        return []
    amounts = _amounts(lead, need_unit=True)
    if amounts and VIS_RENEW_RE.search(lead):
        return [_vis_entry(section, title, lead, amounts)]
    return []
