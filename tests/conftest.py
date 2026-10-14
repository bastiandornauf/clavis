from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def _hashing_embeddings(settings):
    """Never download the real embedding model during tests."""
    settings.CLAVIS_EMBEDDINGS_BACKEND = "hashing-v1"


@pytest.fixture
def fixture_markdown_dir() -> Path:
    return Path(settings.BASE_DIR) / "tests" / "fixtures" / "markdown"
