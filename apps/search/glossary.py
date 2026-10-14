"""Ars Magica search glossary: Art abbreviations, rules short forms, spelling variants.

Keyword search ORs each known term with its counterpart (``CrIg`` ↔ ``Creo Ignem``,
``Pen`` ↔ ``Penetration``); meaning search embeds the written-out form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TECHNIQUES = {"cr": "Creo", "in": "Intellego", "mu": "Muto", "pe": "Perdo", "re": "Rego"}
FORMS = {
    "an": "Animal",
    "aq": "Aquam",
    "au": "Auram",
    "co": "Corpus",
    "he": "Herbam",
    "ig": "Ignem",
    "im": "Imaginem",
    "me": "Mentem",
    "te": "Terram",
    "vi": "Vim",
}
# Only short forms that are not ordinary English words (no Per, Int, Arc, Ind).
TERMS = {
    "pen": "Penetration",
    "init": "Initiative",
    "atk": "Attack",
    "dfn": "Defense",
    "mr": "Magic Resistance",
    "bp": "Build Points",
    "xp": "experience points",
    "conc": "Concentration",
    "diam": "Diameter",
    "mom": "Momentary",
    "qik": "Quickness",
    "dex": "Dexterity",
    "cun": "Cunning",
    "str": "Strength",
    "sta": "Stamina",
}
SPELLING_VARIANTS = (
    ("corpus", "corporem"),
    ("imaginem", "imagonem"),
    ("intellego", "intelligo"),
)

_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)
# Art abbreviations that are also English words expand only as written `MuTe`.
_ENGLISH_ART_SHORTS = {"mute", "pete"}
_CAMEL_ART_RE = re.compile(r"[A-Z][a-z][A-Z][a-z]")


@dataclass(frozen=True)
class GlossaryMatch:
    """Query words at ``start`` (``length`` tokens) and their alternative phrases."""

    start: int
    length: int
    alternatives: tuple[tuple[str, ...], ...]
    note: str


def _short_forms() -> dict[str, tuple[str, ...]]:
    forms = {short: tuple(long.split()) for short, long in TERMS.items()}
    for t_short, technique in TECHNIQUES.items():
        for f_short, form in FORMS.items():
            forms[t_short + f_short] = (technique, form)
    return forms


_SHORT_FORMS = _short_forms()
_LONG_FORMS = {tuple(w.casefold() for w in long): short for short, long in _SHORT_FORMS.items()}
_VARIANTS = {word: group for group in SPELLING_VARIANTS for word in group}
_MAX_LONG = max(len(long) for long in _LONG_FORMS)


def _display_short(short: str) -> str:
    if short[:2] in TECHNIQUES and short[2:] in FORMS and len(short) == 4:
        return short[:2].title() + short[2:].title()
    return short.upper() if len(short) <= 2 else short.title()


def _match_at(tokens: list[str], index: int) -> GlossaryMatch | None:
    folded = [token.casefold() for token in tokens]
    for length in range(min(_MAX_LONG, len(tokens) - index), 1, -1):
        phrase = tuple(folded[index : index + length])
        if phrase in _LONG_FORMS:
            short = _LONG_FORMS[phrase]
            return GlossaryMatch(
                index,
                length,
                (tuple(tokens[index : index + length]), (_display_short(short),)),
                f"{' '.join(tokens[index : index + length])} ↔ {_display_short(short)}",
            )
    word = folded[index]
    if word in _ENGLISH_ART_SHORTS and not _CAMEL_ART_RE.fullmatch(tokens[index]):
        return None
    if word in _SHORT_FORMS:
        long = _SHORT_FORMS[word]
        return GlossaryMatch(
            index, 1, ((tokens[index],), long), f"{tokens[index]} ↔ {' '.join(long)}"
        )
    if (word,) in _LONG_FORMS:
        short = _display_short(_LONG_FORMS[(word,)])
        return GlossaryMatch(index, 1, ((tokens[index],), (short,)), f"{tokens[index]} ↔ {short}")
    if word in _VARIANTS:
        group = _VARIANTS[word]
        return GlossaryMatch(
            index,
            1,
            tuple((variant,) for variant in group),
            " ↔ ".join(variant.title() for variant in group),
        )
    return None


def query_tokens(raw: str) -> list[str]:
    return [token for token in _TOKEN_RE.split(raw.strip()) if token]


def glossary_matches(tokens: list[str]) -> list[GlossaryMatch]:
    """Non-overlapping glossary matches, longest written-out form first."""
    matches: list[GlossaryMatch] = []
    index = 0
    while index < len(tokens):
        match = _match_at(tokens, index)
        if match:
            matches.append(match)
            index += match.length
        else:
            index += 1
    return matches


def glossary_notes(raw: str) -> list[str]:
    """Human-readable expansions applied to ``raw`` (for the results page)."""
    return [match.note for match in glossary_matches(query_tokens(raw))]


def expand_for_meaning(raw: str) -> str:
    """Write out short forms so the embedding model sees full words."""
    tokens = query_tokens(raw)
    out: list[str] = []
    index = 0
    for match in glossary_matches(tokens):
        out.extend(tokens[index : match.start])
        word = tokens[match.start].casefold()
        if match.length == 1 and word in _SHORT_FORMS:
            out.extend(_SHORT_FORMS[word])
        else:
            out.extend(tokens[match.start : match.start + match.length])
        index = match.start + match.length
    out.extend(tokens[index:])
    return " ".join(out) if out else raw
