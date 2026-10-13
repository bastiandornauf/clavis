"""Personal bookmarks, notes, and reading position overlays."""

from __future__ import annotations

from django.db import models

from apps.library.models import Section


class Bookmark(models.Model):
    section_stable_id = models.CharField(max_length=64, db_index=True)
    book_slug = models.SlugField(max_length=255)
    section_path = models.CharField(max_length=1024)
    title = models.CharField(max_length=512)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["section_stable_id"],
                name="annotations_bookmark_unique_stable_id",
            )
        ]

    def __str__(self) -> str:
        return self.title


class Note(models.Model):
    section_stable_id = models.CharField(max_length=64, db_index=True)
    book_slug = models.SlugField(max_length=255)
    section_path = models.CharField(max_length=1024)
    title = models.CharField(max_length=512)
    body = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["section_stable_id"],
                name="annotations_note_unique_stable_id",
            )
        ]

    def __str__(self) -> str:
        return f"Note: {self.title}"


class ReadingPosition(models.Model):
    book_slug = models.SlugField(max_length=255, unique=True)
    section_stable_id = models.CharField(max_length=64)
    section_path = models.CharField(max_length=1024)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.book_slug} @ {self.section_path}"

    @property
    def section(self) -> Section | None:
        return (
            Section.objects.filter(stable_id=self.section_stable_id)
            .select_related("book")
            .first()
        )
