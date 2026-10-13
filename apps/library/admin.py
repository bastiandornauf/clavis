from django.contrib import admin

from apps.library.models import Book, Section


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    fields = ("position", "level", "title", "path", "stable_id")
    readonly_fields = fields
    show_change_link = True


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "edition", "review_status", "snapshot")
    list_filter = ("edition", "review_status")
    search_fields = ("title", "slug")
    inlines = [SectionInline]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("title", "book", "level", "path")
    list_filter = ("level", "book")
    search_fields = ("title", "path", "stable_id")
