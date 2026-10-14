"""Spell guideline extraction from Technique + Form guideline lists and tables."""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.library.models import Section

from .common import ExtractedEntry, _clean_body, _section_title

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


def _guideline_bullet_label(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" •-")
    if len(text) > 90:
        text = text[:87].rstrip() + "…"
    return text


def _join_table_rows(body: str) -> str:
    """Rejoin table rows whose cells wrap onto following lines (``•`` lists in Core)."""
    lines: list[str] = []
    pending = ""
    for line in body.splitlines():
        stripped = line.strip()
        if pending:
            pending += " " + stripped
            if stripped.endswith("|"):
                lines.append(pending)
                pending = ""
            continue
        if stripped.startswith("|") and not stripped.endswith("|"):
            pending = stripped
            continue
        lines.append(line)
    if pending:
        lines.append(pending)
    return "\n".join(lines)


def extract_guidelines(section: Section) -> list[ExtractedEntry]:
    """Tech+Form guideline tables (Core spell design chapters)."""
    title = _section_title(section)
    match = GUIDELINE_TITLE_RE.match(title)
    if not match:
        return []

    technique = match.group("tech").title()
    form = match.group("form").title()
    body = _join_table_rows(_clean_body(section.body_markdown))
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
