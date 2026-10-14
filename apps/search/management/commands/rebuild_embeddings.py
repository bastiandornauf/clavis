"""Rebuild local section embeddings for semantic / hybrid search."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.library.models import Book
from apps.search.embeddings import get_embedder, rebuild_embeddings_for_books
from apps.sources.models import SourceSnapshot


class Command(BaseCommand):
    help = (
        "Build section embeddings for the current snapshot with the local model "
        "(downloaded once on first run). Unchanged sections are skipped."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--backend",
            default=None,
            help="local (default) or hashing-v1; default: settings.CLAVIS_EMBEDDINGS_BACKEND",
        )
        parser.add_argument(
            "--book",
            action="append",
            dest="books",
            default=[],
            help="Limit to book slug (repeatable)",
        )

    def handle(self, *args, **options) -> None:
        current = SourceSnapshot.current()
        if not current:
            raise CommandError("No current source snapshot. Import sources first.")

        books = Book.objects.filter(snapshot=current)
        if options["books"]:
            books = books.filter(slug__in=options["books"])
        book_ids = list(books.values_list("id", flat=True))
        if not book_ids:
            raise CommandError("No matching books to embed.")

        self.stdout.write("Loading embedding model…")
        try:
            embedder = get_embedder(options["backend"])
        except (ValueError, ImportError) as exc:
            raise CommandError(str(exc)) from exc

        def reporter(label: str):
            def progress(done: int, total: int) -> None:
                self.stdout.write(f"  embedded {done}/{total} {label}", ending="\r")
                self.stdout.flush()

            return progress

        updated = rebuild_embeddings_for_books(
            book_ids,
            embedder=embedder,
            progress=reporter("sections"),
            chunk_progress=reporter("long-text passages"),
        )
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Embeddings ready ({embedder.model_name}): "
                f"{updated} section(s) updated across {len(book_ids)} book(s)."
            )
        )
