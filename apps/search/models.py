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


class SectionChunkEmbedding(models.Model):
    """Vectors for the text of long sections past the first embedding window.

    ``start``/``end`` are offsets into ``Section.body_markdown`` so search can show
    the passage that matched. ``content_hash`` is the section's hash at embed time.
    """

    section = models.ForeignKey(
        Section, on_delete=models.CASCADE, related_name="chunk_embeddings"
    )
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="chunk_embeddings")
    model_name = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64)
    chunk_index = models.PositiveSmallIntegerField()
    start = models.PositiveIntegerField()
    end = models.PositiveIntegerField()
    vector = models.BinaryField()
    dimensions = models.PositiveSmallIntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["section", "model_name", "chunk_index"],
                name="uniq_section_chunk_per_model",
            )
        ]
        indexes = [
            models.Index(fields=["book", "model_name"]),
            models.Index(fields=["model_name", "content_hash"]),
        ]

    def __str__(self) -> str:
        return f"ChunkEmbedding({self.section_id}#{self.chunk_index}, {self.model_name})"
