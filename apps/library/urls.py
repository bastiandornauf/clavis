from django.urls import path

from apps.library import views

app_name = "library"

urlpatterns = [
    path("", views.library_index, name="index"),
    path("gallery/", views.gallery_index, name="gallery"),
    path("gallery/file/<path:relative_path>", views.gallery_image, name="gallery_file"),
]
