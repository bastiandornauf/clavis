"""Campaign item helpers and excerpt integrity checks."""

from __future__ import annotations

import hashlib

from apps.campaigns.models import Campaign, CampaignItem
from apps.library.models import Section
from apps.sources.models import SourceSnapshot


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def resolve_section(stable_id: str) -> Section | None:
    current = SourceSnapshot.current()
    qs = Section.objects.filter(stable_id=stable_id).select_related("book", "book__snapshot")
    if current:
        section = qs.filter(book__snapshot=current).first()
        if section:
            return section
    return qs.first()


def _next_position(campaign: Campaign) -> int:
    latest = campaign.items.order_by("-position").values_list("position", flat=True).first()
    return (latest or 0) + 1


def add_section_item(campaign: Campaign, section: Section, note: str = "") -> CampaignItem:
    position = _next_position(campaign)
    return CampaignItem.objects.create(
        campaign=campaign,
        item_type=CampaignItem.ItemType.SECTION,
        section_stable_id=section.stable_id,
        book_slug=section.book.slug,
        section_path=section.path,
        title=section.title,
        note=note.strip(),
        position=position,
    )


def add_excerpt_item(
    campaign: Campaign,
    section: Section,
    excerpt_text: str,
    note: str = "",
) -> CampaignItem:
    excerpt_text = excerpt_text.strip()
    position = _next_position(campaign)
    return CampaignItem.objects.create(
        campaign=campaign,
        item_type=CampaignItem.ItemType.EXCERPT,
        section_stable_id=section.stable_id,
        book_slug=section.book.slug,
        section_path=section.path,
        title=section.title,
        note=note.strip(),
        excerpt_text=excerpt_text,
        excerpt_hash=_hash_text(excerpt_text),
        position=position,
    )


def refresh_excerpt_flags() -> int:
    """Mark excerpts whose selected text is no longer present in the source section."""
    changed = 0
    for item in CampaignItem.objects.filter(item_type=CampaignItem.ItemType.EXCERPT):
        section = resolve_section(item.section_stable_id)
        broken = False
        if section is None:
            broken = True
        elif item.excerpt_text and item.excerpt_text not in section.body_markdown:
            broken = True
        if item.source_changed != broken:
            item.source_changed = broken
            item.save(update_fields=["source_changed"])
            changed += 1
    return changed
