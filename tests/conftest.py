from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings


@pytest.fixture
def fixture_markdown_dir() -> Path:
    return Path(settings.BASE_DIR) / "tests" / "fixtures" / "markdown"
