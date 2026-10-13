"""Persistent indexes beyond FTS5 (section embeddings for semantic search)."""

from __future__ import annotations

from django.db import models

from apps.library.models import Book, Section


class SectionEmbedding(models.Model):
    section = models.OneToOneField(
        Section,
        on_delete=models.CASCADE,
        related_name="embedding",
        primary_key=True,
    )
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="embeddings")
    model_name = models.CharField(max_length=64, db_index=True)
    content_hash = models.CharField(max_length=64)
    vector = models.BinaryField()
    dimensions = models.PositiveSmallIntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["book", "model_name"]),
        ]

    def __str__(self) -> str:
        return f"Embedding({self.section_id}, {self.model_name})"
