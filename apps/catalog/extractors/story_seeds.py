"""Story seed extraction."""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.library.models import Section

from .common import ExtractedEntry, _clean_body, _section_title

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
