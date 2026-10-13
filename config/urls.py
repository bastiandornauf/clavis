"""URL configuration for Clavis."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

from config import views as project_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("notice/", project_views.notice, name="notice"),
    path("", include("apps.library.urls")),
    path("read/", include("apps.reader.urls")),
    path("search/", include("apps.search.urls")),
    path("lexicon/", include("apps.catalog.urls")),
    path("sources/", include("apps.sources.urls")),
    path("annotations/", include("apps.annotations.urls")),
    path("campaigns/", include("apps.campaigns.urls")),
]
