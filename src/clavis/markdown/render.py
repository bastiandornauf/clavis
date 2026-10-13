"""Render Markdown to safe HTML for the reader and search snippets."""

from __future__ import annotations

import bleach
from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin

from clavis.markdown.normalize import normalize_source_markdown

ALLOWED_TAGS = [
    "p",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "em",
    "strong",
    "a",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "img",
    "sup",
    "sub",
    "del",
    "span",
    "div",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title"],
    "th": ["align", "colspan", "rowspan"],
    "td": ["align", "colspan", "rowspan"],
    "code": ["class"],
    "span": ["class"],
    "div": ["class"],
}

_md: MarkdownIt | None = None


def _renderer() -> MarkdownIt:
    global _md
    if _md is None:
        _md = (
            MarkdownIt("commonmark", {"html": False, "linkify": True})
            .enable("table")
            .enable("strikethrough")
            .use(footnote_plugin)
        )
    return _md


def render_markdown(source: str) -> str:
    """Convert Markdown to sanitized HTML."""
    if not source:
        return ""
    normalized = normalize_source_markdown(source)
    html = _renderer().render(normalized)
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
