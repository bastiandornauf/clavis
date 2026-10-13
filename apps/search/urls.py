from django.urls import path

from apps.search import views

app_name = "search"

urlpatterns = [
    path("", views.search_page, name="index"),
]
