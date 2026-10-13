"""Format Book → Chapter → Section citations with source commit."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Citation:
    book_title: str
    chapter_title: str | None
    section_title: str
    commit_sha: str | None = None
    review_status: str | None = None

    @property
    def short_commit(self) -> str | None:
        if not self.commit_sha:
            return None
        return self.commit_sha[:7]


def format_citation(citation: Citation) -> str:
    """Return a human-readable citation string."""
    parts = [citation.book_title]
    if citation.chapter_title and citation.chapter_title != citation.section_title:
        parts.append(citation.chapter_title)
    if citation.section_title and citation.section_title != citation.book_title:
        if citation.section_title not in parts:
            parts.append(citation.section_title)
    text = " → ".join(parts)
    if citation.short_commit:
        text = f"{text} ({citation.short_commit})"
    return text
