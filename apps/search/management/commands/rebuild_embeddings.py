"""Rebuild local section embeddings for semantic / hybrid search."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.library.models import Book
from apps.search.embeddings import get_embedder, rebuild_embeddings_for_books
from apps.sources.models import SourceSnapshot


class Command(BaseCommand):
    help = "Rebuild section embeddings for the current snapshot (hashing-v1 by default)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--backend",
            default=None,
            help="Embedding backend (default: settings.CLAVIS_EMBEDDINGS_BACKEND)",
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

        try:
            embedder = get_embedder(options["backend"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        updated = rebuild_embeddings_for_books(book_ids, embedder=embedder)
        self.stdout.write(
            self.style.SUCCESS(
                f"Embeddings ready ({embedder.model_name}): "
                f"{updated} section(s) updated across {len(book_ids)} book(s)."
            )
        )
