from django.urls import path

from apps.catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.catalog_index, name="index"),
    path("coverage/", views.catalog_coverage, name="coverage"),
    path("<slug:entry_type>/", views.catalog_list, name="list"),
    path("<slug:entry_type>/<slug:slug>/", views.catalog_detail, name="detail"),
]
