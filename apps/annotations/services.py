"""Annotation helpers keyed by stable section IDs."""

from __future__ import annotations

from apps.annotations.models import Bookmark, Note, ReadingPosition
from apps.library.models import Book, Section


def get_bookmarks_for_book(book: Book) -> list[Bookmark]:
    return list(Bookmark.objects.filter(book_slug=book.slug))


def get_notes_for_book(book: Book) -> list[Note]:
    return list(Note.objects.filter(book_slug=book.slug))


def toggle_bookmark(section: Section) -> bool:
    existing = Bookmark.objects.filter(section_stable_id=section.stable_id).first()
    if existing:
        existing.delete()
        return False
    Bookmark.objects.create(
        section_stable_id=section.stable_id,
        book_slug=section.book.slug,
        section_path=section.path,
        title=section.title,
    )
    return True


def upsert_note(section: Section, body: str) -> Note | None:
    body = body.strip()
    if not body:
        Note.objects.filter(section_stable_id=section.stable_id).delete()
        return None
    note, _ = Note.objects.update_or_create(
        section_stable_id=section.stable_id,
        defaults={
            "book_slug": section.book.slug,
            "section_path": section.path,
            "title": section.title,
            "body": body,
        },
    )
    return note


def set_last_read(section: Section) -> ReadingPosition:
    position, _ = ReadingPosition.objects.update_or_create(
        book_slug=section.book.slug,
        defaults={
            "section_stable_id": section.stable_id,
            "section_path": section.path,
        },
    )
    return position


def get_last_read(book: Book) -> ReadingPosition | None:
    return ReadingPosition.objects.filter(book_slug=book.slug).first()
