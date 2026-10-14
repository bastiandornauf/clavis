"""Shared extractor building blocks: entry type, title/body cleanup, Art names."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from apps.library.models import Section
from clavis.markdown.normalize import normalize_source_markdown, unescape_markdown_text

SKIP_TITLE_RE = re.compile(
    r"^(list of|types? of|choosing|quick and easy|virtues and flaws|"
    r"social status virtues|virtues$|flaws$|guidelines?$|level\s+\d+|"
    r"example |new .*virtue|new .*flaw|"
    r"creatures?( of)?|chapter\b|the houses?\b|covenants?$)",
    re.I,
)


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
    level_general: bool = False
    device_effect: bool = False
    range: str = ""
    duration: str = ""
    target: str = ""
    magnitude: str = ""
    category: str = ""
    evidence: str = ""


_ACCENTED_VOWELS = {
    "a": "aáàâäã",
    "e": "eéèêë",
    "i": "iíìîï",
    "o": "oóòôöõ",
    "u": "uúùûü",
}
# Canonical Art name -> spellings seen in the corpus (some books mark stress
# accents, e.g. "Intéllego", "Córporem", "Imágonem").
_ART_SPELLINGS = {
    "Creo": ("creo",),
    "Intellego": ("intellego",),
    "Muto": ("muto",),
    "Perdo": ("perdo",),
    "Rego": ("rego",),
    "Animal": ("animal",),
    "Aquam": ("aquam",),
    "Auram": ("auram",),
    "Corpus": ("corpus", "corporem"),
    "Herbam": ("herbam",),
    "Ignem": ("ignem",),
    "Imaginem": ("imaginem", "imagonem"),
    "Mentem": ("mentem",),
    "Terram": ("terram",),
    "Vim": ("vim",),
}


def _accent_tolerant(word: str) -> str:
    return "".join(
        f"[{_ACCENTED_VOWELS[ch]}]" if ch in _ACCENTED_VOWELS else re.escape(ch) for ch in word
    )


_ART_VARIANT_RE = re.compile(
    r"\b(?:"
    + "|".join(
        f"(?P<{canonical}>{'|'.join(_accent_tolerant(s) for s in spellings)})"
        for canonical, spellings in _ART_SPELLINGS.items()
    )
    + r")\b",
    re.I,
)


# Dashes and curly quotes are common; only accented vowels can hide an Art name.
_ART_VARIANT_HINT_RE = re.compile(r"[áàâäãéèêëíìîïóòôöõúùûü]|orporem|magonem", re.I)


@lru_cache(maxsize=8192)
def normalize_art_names(text: str) -> str:
    """Spell Technique/Form names canonically: no accents, Corporem → Corpus.

    Only whole Art words change; other accented text (names, places) is kept.
    """
    if not _ART_VARIANT_HINT_RE.search(text):
        return text

    def canonical(match: re.Match[str]) -> str:
        name = match.lastgroup or ""
        found = match.group(0)
        if found.isupper() and len(found) > 1:
            return name.upper()
        if found.islower():
            return name.lower()
        return name

    return _ART_VARIANT_RE.sub(canonical, text)


def _clean_body(body: str) -> str:
    return normalize_art_names(normalize_source_markdown(body))


NEW_TYPE_PREFIX_RE = re.compile(
    r"^(?:New\s+(?:Spells?|Abilit(?:y|ies)|Items?|Rituals?)|(?:New\s+)?(?:Virtues?|Flaws?))\s*:\s*",
    re.I,
)


def _section_title(section: Section) -> str:
    """Display title without a ``New Spell:`` style prefix (may become empty)."""
    title = NEW_TYPE_PREFIX_RE.sub("", unescape_markdown_text(section.title.strip()))
    return normalize_art_names(title)


def _level_token(token: str) -> tuple[int | None, bool]:
    """``"15"`` → (15, False); ``"Gen"`` / ``"General"`` → (None, True)."""
    return (int(token), False) if token.isdigit() else (None, True)
