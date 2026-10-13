from __future__ import annotations

import json
from pathlib import Path

from django.urls import reverse

from apps.library.guides import clear_guides_cache, load_guides_catalog


def test_load_guides_catalog_from_shipped_json():
    clear_guides_cache()
    catalog = load_guides_catalog()
    assert catalog.intro
    assert catalog.categories
    assert all(cat.items for cat in catalog.categories)
    assert any(
        item.url.startswith("https://")
        for cat in catalog.categories
        for item in cat.items
    )


def test_load_guides_catalog_skips_empty_items(tmp_path: Path):
    clear_guides_cache()
    path = tmp_path / "guides.json"
    path.write_text(
        json.dumps(
            {
                "intro": "Test intro",
                "categories": [
                    {
                        "id": "a",
                        "title": "Alpha",
                        "description": "Desc",
                        "items": [
                            {"title": "", "url": "https://example.com"},
                            {
                                "title": "Kept",
                                "url": "https://example.com/kept",
                                "summary": "Yes",
                            },
                        ],
                    },
                    {"id": "empty", "title": "Empty", "items": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    catalog = load_guides_catalog(str(path))
    assert catalog.intro == "Test intro"
    assert len(catalog.categories) == 1
    assert catalog.categories[0].items[0].title == "Kept"
    clear_guides_cache()


def test_guides_page_renders(client):
    clear_guides_cache()
    response = client.get(reverse("library:guides"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Guides" in body
    assert "Ars Magica Open License" in body
    assert "https://atlas-games.com/arsmagica/openars" in body
