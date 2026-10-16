from django.urls import path

from apps.chargen import views

app_name = "chargen"

urlpatterns = [
    path("", views.home, name="home"),
    path("new/", views.new_character, name="new"),
    path("new/reset/", views.reset_character, name="reset"),
    path("new/print/", views.print_sheet, name="print"),
    path("new/markdown/", views.download_markdown, name="markdown"),
    path("new/json/", views.download_json, name="json"),
    path("new/pdf/", views.fill_pdf, name="fill_pdf"),
    path("new/save/", views.save_character, name="save"),
    path("open/<int:pk>/", views.open_character, name="open"),
]
