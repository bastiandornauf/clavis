from django.contrib import admin

from apps.catalog.models import CatalogEntry, EnrichmentProposal


@admin.register(CatalogEntry)
class CatalogEntryAdmin(admin.ModelAdmin):
    list_display = ("name", "entry_type", "kind", "book", "magnitude", "level", "extractor")
    list_filter = ("entry_type", "kind", "magnitude", "technique", "form", "extractor")
    search_fields = ("name", "summary", "slug")


@admin.register(EnrichmentProposal)
class EnrichmentProposalAdmin(admin.ModelAdmin):
    list_display = (
        "proposed_name",
        "proposed_entry_type",
        "status",
        "confidence",
        "provider",
        "book",
    )
    list_filter = ("status", "proposed_entry_type", "provider", "extractor")
    search_fields = ("proposed_name", "proposed_summary", "section_stable_id")
