from django.urls import path

from apps.reader import views

app_name = "reader"

urlpatterns = [
    path("<slug:book_slug>/", views.read_book, name="book"),
    path("<slug:book_slug>/<path:section_path>/", views.read_section, name="section"),
]
