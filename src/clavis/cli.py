"""Command-line entry point for Clavis."""

from __future__ import annotations

import os
import sys


def main() -> None:
    """Run Django management commands via the ``clavis`` console script."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    # Ensure the project root (containing config/ and apps/) is importable.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from django.core.management import execute_from_command_line

    argv = ["clavis", *sys.argv[1:]] if len(sys.argv) > 1 else ["clavis", "help"]
    execute_from_command_line(argv)
