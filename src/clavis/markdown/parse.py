"""Split Markdown documents into a heading-based section tree."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from clavis.markdown.normalize import normalize_source_markdown, unescape_markdown_text

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    slug = SLUG_RE.sub("-", text.lower().strip()).strip("-")
    return slug or "section"


@dataclass
class ParsedSection:
    level: int
    title: str
    body: str
    slug: str
    path_slugs: tuple[str, ...]
    content_hash: str
    children: list[ParsedSection] = field(default_factory=list)

    @property
    def path(self) -> str:
        return "/".join(self.path_slugs)


def content_hash(title: str, body: str) -> str:
    payload = f"{title}\n{body}".encode()
    return hashlib.sha256(payload).hexdigest()


def parse_sections(markdown: str) -> list[ParsedSection]:
    """Parse a Markdown document into top-level section trees.

    Content before the first heading becomes a synthetic section titled
    ``Front Matter`` at level 1 so every book has navigable content.
    """
    text = normalize_source_markdown(markdown.replace("\r\n", "\n").replace("\r", "\n"))
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        body = text.strip()
        if not body:
            return []
        return [
            ParsedSection(
                level=1,
                title="Front Matter",
                body=body,
                slug="front-matter",
                path_slugs=("front-matter",),
                content_hash=content_hash("Front Matter", body),
            )
        ]

    roots: list[ParsedSection] = []
    stack: list[ParsedSection] = []
    used_paths: dict[str, int] = {}

    preamble = text[: matches[0].start()].strip()
    if preamble:
        front = ParsedSection(
            level=1,
            title="Front Matter",
            body=preamble,
            slug="front-matter",
            path_slugs=("front-matter",),
            content_hash=content_hash("Front Matter", preamble),
        )
        roots.append(front)
        stack.append(front)
        used_paths["front-matter"] = 1

    for index, match in enumerate(matches):
        level = len(match.group(1))
        # Titles are plain text in the UI — decode \\* markers etc. here.
        title = unescape_markdown_text(match.group(2).strip())
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        while stack and stack[-1].level >= level:
            stack.pop()

        parent_path = stack[-1].path_slugs if stack else ()
        base_slug = slugify(title)
        path_key = "/".join((*parent_path, base_slug))
        count = used_paths.get(path_key, 0) + 1
        used_paths[path_key] = count
        slug = base_slug if count == 1 else f"{base_slug}-{count}"
        path_slugs = (*parent_path, slug)

        section = ParsedSection(
            level=level,
            title=title,
            body=body,
            slug=slug,
            path_slugs=path_slugs,
            content_hash=content_hash(title, body),
        )
        if stack:
            stack[-1].children.append(section)
        else:
            roots.append(section)
        stack.append(section)

    return roots


def walk_sections(sections: list[ParsedSection]) -> list[ParsedSection]:
    """Depth-first flatten of a section tree."""
    result: list[ParsedSection] = []

    def visit(node: ParsedSection) -> None:
        result.append(node)
        for child in node.children:
            visit(child)

    for section in sections:
        visit(section)
    return result
