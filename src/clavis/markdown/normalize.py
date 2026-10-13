"""Normalize quirks in Ars Magica Open License Markdown before parse/render."""

from __future__ import annotations

import re

BR_RE = re.compile(r"<br\s*/?>", re.I)
# Any ASCII punctuation may be backslash-escaped in CommonMark.
MD_ESCAPE_RE = re.compile(r"""\\([!"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])""")


def unescape_markdown_text(text: str) -> str:
    """Decode CommonMark escapes for plain-text titles and labels.

    Heading titles are stored and shown outside the Markdown renderer, so
    ``Ceremony\\*`` would otherwise appear with a visible backslash.
    """
    if not text:
        return ""
    text = MD_ESCAPE_RE.sub(r"\1", text)
    # Incomplete trailing escapes occasionally survive OCR/export quirks.
    return text.rstrip("\\")


def normalize_source_markdown(source: str) -> str:
    """Convert source-corpus HTML line breaks into Markdown hard breaks.

    The Open License Markdown uses ``<br>`` for line breaks (including in
    tables). With HTML disabled in the renderer those tags otherwise appear
    literally in the reader.
    """
    if not source:
        return ""
    # Two trailing spaces + newline = CommonMark hard line break.
    return BR_RE.sub("  \n", source)
