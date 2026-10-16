"""Shared chargen value types. Imported by creation and vf_effects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VirtueFlaw:
    name: str
    kind: str  # "virtue" | "flaw"
    magnitude: str  # "Minor" | "Major" | "Free"
    category: str = ""
    slug: str = ""
    granted: bool = False  # House benefit: keep the magnitude, do not spend points


@dataclass(frozen=True)
class Issue:
    """A Core rule the sheet breaks (error) or a further step the rules require (note)."""

    severity: str  # "error" | "note"
    code: str
    message: str
    cite: str

    @property
    def blocks(self) -> bool:
        return self.severity == "error"
