"""Static file storage that keeps browsers from serving stale CSS/JS."""

from __future__ import annotations

import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    """Appends ``?v=<mtime-size>`` so an edited file gets a new URL.

    Works with ``runserver`` and ``collectstatic`` alike (no manifest step).
    """

    def url(self, name: str | None) -> str:
        url = super().url(name)
        if not name:
            return url
        path = finders.find(name)
        if isinstance(path, list):
            path = path[0] if path else None
        if not path and self.exists(name):
            path = self.path(name)
        if not path:
            return url
        stat = os.stat(path)
        return f"{url}?v={stat.st_mtime_ns:x}{stat.st_size:x}"
