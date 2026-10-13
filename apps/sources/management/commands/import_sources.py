"""Management command to sync and import Ars Magica Markdown sources."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.sources.services import SourceSyncError, import_sources


class Command(BaseCommand):
    help = "Sync the Ars Magica Open License repository and import Markdown books."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--no-sync",
            action="store_true",
            help="Import from the existing local clone without pulling.",
        )
        parser.add_argument(
            "--pilot",
            action="store_true",
            help="Import only the three Phase-1 pilot books.",
        )
        parser.add_argument(
            "--path",
            type=str,
            default="",
            help="Import Markdown from a local directory instead of the git repo.",
        )

    def handle(self, *args, **options) -> None:
        local = Path(options["path"]) if options["path"] else None
        try:
            snapshot = import_sources(
                sync=not options["no_sync"] and local is None,
                pilot_only=options["pilot"],
                local_path=local,
            )
        except SourceSyncError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"{snapshot.message} (commit {snapshot.commit_sha[:12]})"
            )
        )
