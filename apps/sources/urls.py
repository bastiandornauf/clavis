from django.urls import path

from apps.sources import views

app_name = "sources"

urlpatterns = [
    path("", views.sources_status, name="status"),
    path("history.txt", views.import_history_download, name="history_download"),
]
