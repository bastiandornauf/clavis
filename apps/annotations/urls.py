from django.urls import path

from apps.annotations import views

app_name = "annotations"

urlpatterns = [
    path("bookmarks/", views.bookmark_list, name="bookmarks"),
    path("bookmarks/toggle/", views.bookmark_toggle, name="bookmark_toggle"),
    path("notes/", views.note_list, name="notes"),
    path("notes/save/", views.note_save, name="note_save"),
]
