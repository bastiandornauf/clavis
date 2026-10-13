from django.contrib import admin

from apps.annotations.models import Bookmark, Note, ReadingPosition


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ("title", "book_slug", "created_at")


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("title", "book_slug", "updated_at")


@admin.register(ReadingPosition)
class ReadingPositionAdmin(admin.ModelAdmin):
    list_display = ("book_slug", "section_path", "updated_at")
