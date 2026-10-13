from django.contrib import admin

from apps.catalog.models import CatalogEntry


@admin.register(CatalogEntry)
class CatalogEntryAdmin(admin.ModelAdmin):
    list_display = ("name", "entry_type", "kind", "book", "magnitude", "level")
    list_filter = ("entry_type", "kind", "magnitude", "technique", "form")
    search_fields = ("name", "summary", "slug")
