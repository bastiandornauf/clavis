"""Saved character overlays. Workspace rows, not Lexicon entries."""

from __future__ import annotations

from django.db import models


class Character(models.Model):
    name = models.CharField(max_length=255)
    character_type = models.CharField(max_length=32, blank=True)
    house = models.CharField(max_length=64, blank=True)
    age = models.PositiveIntegerField(default=0)
    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.SET_NULL,
        related_name="characters",
        null=True,
        blank=True,
    )
    state = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "name"]

    def __str__(self) -> str:
        return self.name
