"""Structured lexicon entries derived from library sections."""

from __future__ import annotations

from django.db import models

from apps.library.models import Book
from apps.sources.models import SourceSnapshot


class CatalogEntry(models.Model):
    class EntryType(models.TextChoices):
        SPELL = "spell", "Spell"
        VIRTUE = "virtue", "Virtue"
        FLAW = "flaw", "Flaw"
        STORY_SEED = "story_seed", "Story seed"
        CREATURE = "creature", "Creature"
        BEAST = "beast", "Beast"
        CHARACTER = "character", "Character"
        GUIDELINE = "guideline", "Guideline"
        ABILITY = "ability", "Ability"
        BOON = "boon", "Boon"
        HOOK = "hook", "Hook"
        ORGANIZATION = "organization", "Organization"
        PLACE = "place", "Place"
        ITEM = "item", "Item"
        VIS_SOURCE = "vis_source", "Vis source"

    class Kind(models.TextChoices):
        DEFINITION = "definition", "Definition"
        MENTION = "mention", "Mention"

    snapshot = models.ForeignKey(
        SourceSnapshot,
        on_delete=models.CASCADE,
        related_name="catalog_entries",
    )
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="catalog_entries")
    entry_type = models.CharField(max_length=16, choices=EntryType.choices, db_index=True)
    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
        default=Kind.DEFINITION,
        db_index=True,
    )
    name = models.CharField(max_length=512)
    slug = models.SlugField(max_length=255)
    summary = models.CharField(max_length=512, blank=True)
    primary_section_stable_id = models.CharField(max_length=64, db_index=True)
    section_path = models.CharField(max_length=1024)
    # JSON-ish text fields kept simple for Phase 2 rules.
    technique = models.CharField(max_length=64, blank=True)
    form = models.CharField(max_length=64, blank=True)
    level = models.PositiveSmallIntegerField(null=True, blank=True)
    # General spells (``Gen``) have no fixed level; distinct from "level not found".
    level_general = models.BooleanField(default=False)
    # Spell-style effect of an enchanted device (also listed as an item).
    device_effect = models.BooleanField(default=False)
    range = models.CharField(max_length=64, blank=True)
    duration = models.CharField(max_length=64, blank=True)
    target = models.CharField(max_length=64, blank=True)
    magnitude = models.CharField(max_length=32, blank=True)  # Major / Minor
    category = models.CharField(max_length=128, blank=True)
    evidence = models.TextField(blank=True)
    extractor = models.CharField(max_length=64, default="rules")

    class Meta:
        ordering = ["entry_type", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "entry_type", "slug", "primary_section_stable_id"],
                name="catalog_entry_unique_per_section",
            )
        ]
        indexes = [
            models.Index(fields=["snapshot", "entry_type", "kind"]),
            models.Index(fields=["technique", "form", "level"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_entry_type_display()}: {self.name}"


class EnrichmentProposal(models.Model):
    """Reviewable leftover suggestions (heuristic dry-run or optional LLM)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        SKIPPED = "skipped", "Skipped"

    snapshot = models.ForeignKey(
        SourceSnapshot,
        on_delete=models.CASCADE,
        related_name="enrichment_proposals",
    )
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="enrichment_proposals")
    section_stable_id = models.CharField(max_length=64, db_index=True)
    section_path = models.CharField(max_length=1024)
    proposed_entry_type = models.CharField(max_length=16, blank=True)
    proposed_name = models.CharField(max_length=512)
    proposed_summary = models.CharField(max_length=512, blank=True)
    evidence = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    extractor = models.CharField(max_length=64, default="llm")
    provider = models.CharField(max_length=64, default="dry-run")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "section_stable_id", "proposed_name", "provider"],
                name="enrichment_proposal_unique_hint",
            )
        ]
        indexes = [
            models.Index(fields=["snapshot", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.proposed_name} ({self.status})"
