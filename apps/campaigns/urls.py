from django.urls import path

from apps.campaigns import views

app_name = "campaigns"

urlpatterns = [
    path("", views.campaign_list, name="list"),
    path("new/", views.campaign_create, name="create"),
    path("add/", views.campaign_add_section, name="add"),
    path("<slug:slug>/", views.campaign_detail, name="detail"),
    path("<slug:slug>/add/", views.campaign_add_section, name="add_to"),
    path("<slug:slug>/items/<int:item_id>/remove/", views.campaign_remove_item, name="remove"),
    path(
        "<slug:slug>/items/<int:item_id>/note/",
        views.campaign_update_item_note,
        name="update_note",
    ),
]
