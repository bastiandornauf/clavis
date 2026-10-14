"""Virtue and Flaw extraction."""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.library.models import Section

from .common import SKIP_TITLE_RE, ExtractedEntry, _clean_body, _section_title
from .creatures import CREATURE_LEAD_RE, CREATURE_LEAD_WINDOW

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


def _vf_italic_groups(match: re.Match[str]) -> tuple[str, str]:
    """Return (magnitude, category) from either italic order."""
    if match.groupdict().get("mag_first"):
        return match.group("mag_first").title(), match.group("cat_after").strip().rstrip(".")
    return match.group("mag_after").title(), match.group("cat_before").strip().rstrip(".")


# `*Major, Supernatural Virtue*` names its kind; titles like `New Flaw: Name` too.
VF_CATEGORY_KIND_RE = re.compile(r"\s*\b(?P<kind>Virtue|Flaw)s?\s*$", re.I)
VF_TITLE_KIND_RE = re.compile(r"^(?:New\s+)?(?P<kind>Virtue|Flaw)\s*:", re.I)


def _split_category_kind(category: str) -> tuple[str, str]:
    """Return (category without trailing Virtue/Flaw, kind or empty string)."""
    match = VF_CATEGORY_KIND_RE.search(category)
    if not match:
        return category, ""
    return category[: match.start()].strip(), match.group("kind").lower()


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
        category, own_kind = _split_category_kind(category)
        seen.add(key)
        out.append(
            _vf_entry(
                section=section,
                kind=own_kind or kind,
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
        category, kind = _split_category_kind(category)
        title_kind = VF_TITLE_KIND_RE.match(section.title.strip())
        kind = kind or (title_kind.group("kind").lower() if title_kind else "")
        kind = kind or _virtue_or_flaw_from_ancestors(section)
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
