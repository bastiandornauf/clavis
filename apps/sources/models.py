"""Source repository snapshots."""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class SourceSnapshot(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    repo_url = models.URLField()
    commit_sha = models.CharField(max_length=64, blank=True)
    local_path = models.CharField(max_length=1024)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    message = models.TextField(blank=True)
    imported_at = models.DateTimeField(default=timezone.now)
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-imported_at"]

    def __str__(self) -> str:
        short = self.commit_sha[:7] if self.commit_sha else "unknown"
        return f"{short} ({self.status})"

    @classmethod
    def current(cls) -> SourceSnapshot | None:
        return cls.objects.filter(is_current=True).first()
