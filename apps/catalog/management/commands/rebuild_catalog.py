"""Rebuild the rule-based Lexicon and show what changed."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.services import rebuild_catalog_with_diff
from apps.library.models import Book
from apps.sources.models import SourceSnapshot


class Command(BaseCommand):
    help = (
        "Re-run the Lexicon rules over the current snapshot and print per-type counts "
        "before/after plus entries that disappeared. Use --dry-run to check rule "
        "changes without saving."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--book",
            action="append",
            dest="books",
            default=[],
            help="Limit to book slug (repeatable)",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Report the diff, then roll back"
        )
        parser.add_argument(
            "--show",
            type=int,
            default=25,
            help="How many removed/added entries to list (default 25)",
        )
        parser.add_argument("--show-added", action="store_true", help="Also list added entries")

    def handle(self, *args, **options) -> None:
        current = SourceSnapshot.current()
        if not current:
            raise CommandError("No current source snapshot. Import sources first.")
        books = Book.objects.filter(snapshot=current)
        if options["books"]:
            books = books.filter(slug__in=options["books"])
        book_ids = list(books.values_list("id", flat=True))
        if not book_ids:
            raise CommandError("No matching books.")

        diff = rebuild_catalog_with_diff(book_ids, dry_run=options["dry_run"])

        self.stdout.write(f"{'type':<14}{'before':>8}{'after':>8}{'change':>9}")
        total_before = total_after = 0
        for entry_type, before, after in diff.counts():
            total_before += before
            total_after += after
            self.stdout.write(f"{entry_type:<14}{before:>8}{after:>8}{after - before:>+9}")
        self.stdout.write(
            f"{'total':<14}{total_before:>8}{total_after:>8}{total_after - total_before:>+9}"
        )

        limit = options["show"]
        removed = diff.removed
        if removed:
            self.stdout.write(self.style.WARNING(f"\nRemoved ({len(removed)}):"))
            for entry_type, name, _ in removed[:limit]:
                self.stdout.write(f"  - {entry_type}: {name}")
        if options["show_added"] and diff.added:
            self.stdout.write(f"\nAdded ({len(diff.added)}):")
            for entry_type, name, _ in diff.added[:limit]:
                self.stdout.write(f"  + {entry_type}: {name}")

        verb = "Checked (rolled back)" if options["dry_run"] else "Rebuilt"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{verb} {len(book_ids)} book(s): +{len(diff.added)} / -{len(removed)} entries."
            )
        )
