from django.contrib import admin

from apps.sources.models import SourceSnapshot


@admin.register(SourceSnapshot)
class SourceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("commit_sha", "status", "is_current", "imported_at")
    list_filter = ("status", "is_current")
