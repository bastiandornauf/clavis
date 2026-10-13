"""Books and sections imported from Markdown sources."""

from __future__ import annotations

from django.db import models

from apps.sources.models import SourceSnapshot


class Book(models.Model):
    class Edition(models.TextChoices):
        FIFTH = "5e", "5th Edition"
        FOURTH = "4e", "4th Edition"
        THIRD = "3e", "3rd Edition"
        OTHER = "other", "Other"
        UNKNOWN = "unknown", "Unknown"

    class ReviewStatus(models.TextChoices):
        REVIEWED = "reviewed", "Reviewed"
        WIP = "wip", "Work in progress"
        THIRD_PARTY = "third_party", "Third party"

    snapshot = models.ForeignKey(
        SourceSnapshot,
        on_delete=models.CASCADE,
        related_name="books",
    )
    slug = models.SlugField(max_length=255)
    title = models.CharField(max_length=512)
    edition = models.CharField(
        max_length=16,
        choices=Edition.choices,
        default=Edition.UNKNOWN,
    )
    review_status = models.CharField(
        max_length=16,
        choices=ReviewStatus.choices,
        default=ReviewStatus.WIP,
    )
    relative_path = models.CharField(max_length=1024)
    source_file_hash = models.CharField(max_length=64, blank=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "slug"],
                name="library_book_unique_slug_per_snapshot",
            )
        ]

    def __str__(self) -> str:
        return self.title


class Section(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="sections")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    level = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=512)
    slug = models.SlugField(max_length=255)
    path = models.CharField(max_length=1024, db_index=True)
    body_markdown = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64)
    stable_id = models.CharField(max_length=64, db_index=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["book_id", "position"]
        indexes = [
            models.Index(fields=["book", "path"]),
            models.Index(fields=["stable_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["book", "path"],
                name="library_section_unique_path_per_book",
            )
        ]

    def __str__(self) -> str:
        return f"{self.book.title}: {self.title}"

    @property
    def display_title(self) -> str:
        """Title with CommonMark escapes decoded (Ceremony\\* → Ceremony*)."""
        from clavis.markdown.normalize import unescape_markdown_text

        return unescape_markdown_text(self.title)

    @property
    def chapter(self) -> Section | None:
        """Nearest ancestor at level 1, or self if already a top-level section."""
        if self.level <= 1:
            return self
        current = self.parent
        while current is not None:
            if current.level <= 1:
                return current
            current = current.parent
        return self
