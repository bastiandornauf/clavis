from django.contrib import admin

from apps.campaigns.models import Campaign, CampaignItem


class CampaignItemInline(admin.TabularInline):
    model = CampaignItem
    extra = 0


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CampaignItemInline]
