"""Load the curated Guides link catalog (JSON, not imported books)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

GUIDES_PATH = Path(__file__).with_name("guides.json")


@dataclass(frozen=True)
class GuideItem:
    title: str
    url: str
    summary: str


@dataclass(frozen=True)
class GuideCategory:
    id: str
    title: str
    description: str
    items: tuple[GuideItem, ...]


@dataclass(frozen=True)
class GuidesCatalog:
    intro: str
    categories: tuple[GuideCategory, ...]


def _parse_catalog(payload: dict) -> GuidesCatalog:
    categories: list[GuideCategory] = []
    for raw in payload.get("categories") or []:
        items = tuple(
            GuideItem(
                title=str(item.get("title", "")).strip(),
                url=str(item.get("url", "")).strip(),
                summary=str(item.get("summary", "")).strip(),
            )
            for item in raw.get("items") or []
            if str(item.get("title", "")).strip() and str(item.get("url", "")).strip()
        )
        if not items:
            continue
        categories.append(
            GuideCategory(
                id=str(raw.get("id") or raw.get("title", "category")).strip(),
                title=str(raw.get("title", "")).strip() or "Guides",
                description=str(raw.get("description", "")).strip(),
                items=items,
            )
        )
    return GuidesCatalog(
        intro=str(payload.get("intro", "")).strip(),
        categories=tuple(categories),
    )


@lru_cache(maxsize=1)
def load_guides_catalog(path: str | None = None) -> GuidesCatalog:
    catalog_path = Path(path) if path else GUIDES_PATH
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("guides.json must contain a JSON object")
    return _parse_catalog(payload)


def clear_guides_cache() -> None:
    load_guides_catalog.cache_clear()
