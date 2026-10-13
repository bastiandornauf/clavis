"""Campaign collections that link to source sections without copying them."""

from __future__ import annotations

from django.db import models
from django.utils.text import slugify


class Campaign(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base = slugify(self.name) or "campaign"
            slug = base
            counter = 2
            while Campaign.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class CampaignItem(models.Model):
    class ItemType(models.TextChoices):
        SECTION = "section", "Section"
        EXCERPT = "excerpt", "Excerpt"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(max_length=16, choices=ItemType.choices, default=ItemType.SECTION)
    section_stable_id = models.CharField(max_length=64, db_index=True)
    book_slug = models.SlugField(max_length=255)
    section_path = models.CharField(max_length=1024)
    title = models.CharField(max_length=512)
    note = models.TextField(blank=True)
    # Excerpt stores a content hash of the selected text at add time.
    excerpt_text = models.TextField(blank=True)
    excerpt_hash = models.CharField(max_length=64, blank=True)
    source_changed = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "created_at"]

    def __str__(self) -> str:
        return f"{self.campaign.name}: {self.title}"
