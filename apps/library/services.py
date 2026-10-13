"""Import Markdown books into the library."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from django.db import transaction
from django.utils.text import slugify

from apps.library.models import Book, Section
from apps.sources.models import SourceSnapshot
from clavis.markdown.parse import parse_sections, walk_sections

PILOT_BOOK_FRAGMENTS = (
    "definitive edition",
    "guardians of the forests",
    "realms of power - magic",
    "realms of power — magic",
)

EDITION_PATTERNS = (
    (re.compile(r"\b5e\b|\b5th\b|definitive edition", re.I), Book.Edition.FIFTH),
    (re.compile(r"\b4e\b|\b4th\b", re.I), Book.Edition.FOURTH),
    (re.compile(r"\b3e\b|\b3rd\b", re.I), Book.Edition.THIRD),
)


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative_path: str
    review_status: str
    title: str
    edition: str


def detect_edition(name: str) -> str:
    for pattern, edition in EDITION_PATTERNS:
        if pattern.search(name):
            return edition
    return Book.Edition.UNKNOWN


def title_from_filename(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"^Ars Magica\s*", "", stem, flags=re.I)
    stem = re.sub(r"^\d+e\b", "", stem, flags=re.I)
    stem = re.sub(r"^[\s\-–—:]+", "", stem)
    return stem.strip() or Path(name).stem


# When WIP and reviewed name the same work differently, map to one key.
# Prefer reviewed at import time (see list_source_markdown_files).
_WORK_ALIASES = {
    "core-rules": "5e-core-rules",
    "definitive-edition-core-rules": "5e-core-rules",
}

_REVIEW_RANK = {
    Book.ReviewStatus.REVIEWED: 3,
    Book.ReviewStatus.WIP: 2,
    Book.ReviewStatus.THIRD_PARTY: 1,
}


def book_work_key(*, title: str, filename: str) -> str:
    """Identity used to prefer reviewed over wip of the same work."""
    alias = _WORK_ALIASES.get(slugify(title))
    if alias:
        return f"work:{alias}"
    return f"file:{Path(filename).name.lower()}"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_section_id(book_slug: str, path: str) -> str:
    payload = f"{book_slug}:{path}".encode()
    return hashlib.sha256(payload).hexdigest()


def list_source_markdown_files(root: Path, *, pilot_only: bool = False) -> list[SourceFile]:
    """Prefer reviewed over wip for the same work; include 3rd-party separately.

    Same filename across folders still dedupes. Known aliases (e.g. WIP
    ``Core Rules`` vs reviewed ``Definitive Edition (Core Rules)``) share a
    work key so the reviewed file wins.
    """
    candidates: dict[str, SourceFile] = {}

    def consider(folder: Path, review_status: str) -> None:
        if not folder.is_dir():
            return
        for path in sorted(folder.glob("*.md")):
            rel = str(path.relative_to(root))
            title = title_from_filename(path.name)
            edition = detect_edition(path.name)
            info = SourceFile(
                path=path,
                relative_path=rel,
                review_status=review_status,
                title=title,
                edition=edition,
            )
            key = book_work_key(title=title, filename=path.name)
            existing = candidates.get(key)
            if existing is None or _REVIEW_RANK.get(review_status, 0) > _REVIEW_RANK.get(
                existing.review_status, 0
            ):
                candidates[key] = info

    # Flat fixture directories (tests / --path) contain markdown at the root.
    root_mds = list(root.glob("*.md"))
    if root_mds and not (root / "reviewed").exists() and not (root / "wip").exists():
        for path in sorted(root_mds):
            title = title_from_filename(path.name)
            key = book_work_key(title=title, filename=path.name)
            candidates[key] = SourceFile(
                path=path,
                relative_path=path.name,
                review_status=Book.ReviewStatus.REVIEWED,
                title=title,
                edition=detect_edition(path.name),
            )
    else:
        consider(root / "reviewed", Book.ReviewStatus.REVIEWED)
        consider(root / "wip", Book.ReviewStatus.WIP)
        consider(root / "3rd-party", Book.ReviewStatus.THIRD_PARTY)

    files = list(candidates.values())
    if pilot_only:
        files = [
            f
            for f in files
            if any(fragment in f.title.lower() for fragment in PILOT_BOOK_FRAGMENTS)
            or any(fragment in f.path.name.lower() for fragment in PILOT_BOOK_FRAGMENTS)
        ]
    return sorted(files, key=lambda f: f.title.lower())


def _book_slug_for(info: SourceFile) -> str:
    base = slugify(info.title) or "book"
    return base[:200]


@transaction.atomic
def import_book_file(info: SourceFile, snapshot: SourceSnapshot) -> Book:
    text = info.path.read_text(encoding="utf-8", errors="replace")
    sections_tree = parse_sections(text)
    book_slug = _book_slug_for(info)
    source_hash = file_hash(info.path)

    book, _created = Book.objects.update_or_create(
        snapshot=snapshot,
        slug=book_slug,
        defaults={
            "title": info.title,
            "edition": info.edition,
            "review_status": info.review_status,
            "relative_path": info.relative_path,
            "source_file_hash": source_hash,
        },
    )

    # Replace sections for this book (idempotent per snapshot).
    book.sections.all().delete()

    position = 0
    id_map: dict[str, Section] = {}

    flat = walk_sections(sections_tree)
    for parsed in flat:
        parent = None
        if len(parsed.path_slugs) > 1:
            parent_path = "/".join(parsed.path_slugs[:-1])
            parent = id_map.get(parent_path)

        section = Section.objects.create(
            book=book,
            parent=parent,
            level=parsed.level,
            title=parsed.title,
            slug=parsed.slug,
            path=parsed.path,
            body_markdown=parsed.body,
            content_hash=parsed.content_hash,
            stable_id=stable_section_id(book_slug, parsed.path),
            position=position,
        )
        id_map[parsed.path] = section
        position += 1

    return book


def citation_parts(section: Section) -> dict[str, str | None]:
    chapter = section.chapter
    commit = section.book.snapshot.commit_sha if section.book.snapshot_id else None
    return {
        "book_title": section.book.title,
        "chapter_title": chapter.title if chapter and chapter.pk != section.pk else None,
        "section_title": section.display_title,
        "commit_sha": commit,
        "review_status": section.book.review_status,
    }
