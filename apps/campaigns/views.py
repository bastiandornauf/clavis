"""Campaign and personal workspace views."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.annotations.models import Bookmark, Note
from apps.campaigns.models import Campaign, CampaignItem
from apps.campaigns.services import add_excerpt_item, add_section_item, resolve_section
from apps.library.models import Section

WORKSPACE_TABS = frozenset({"campaigns", "bookmarks", "notes"})


def workspace(request: HttpRequest) -> HttpResponse:
    """Combined prep surface: campaigns, bookmarks, and notes."""
    tab = request.GET.get("tab", "campaigns").strip().lower()
    if tab not in WORKSPACE_TABS:
        tab = "campaigns"
    return render(
        request,
        "workspace/index.html",
        {
            "tab": tab,
            "campaigns": Campaign.objects.all(),
            "bookmarks": Bookmark.objects.all(),
            "notes": Note.objects.all(),
            "page_title": "Workspace",
        },
    )


def campaign_list(request: HttpRequest) -> HttpResponse:
    from django.urls import reverse

    return redirect(f"{reverse('campaigns:workspace')}?tab=campaigns")


@require_http_methods(["GET", "POST"])
def campaign_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        if not name:
            messages.error(request, "Campaign name is required.")
        else:
            campaign = Campaign.objects.create(name=name, description=description)
            messages.success(request, f"Created campaign “{campaign.name}”.")
            return redirect("campaigns:detail", slug=campaign.slug)
    from django.urls import reverse

    return render(
        request,
        "campaigns/create.html",
        {
            "page_title": "New campaign",
            "breadcrumbs": [
                {"label": "Workspace", "url": reverse("campaigns:workspace")},
                {"label": "New campaign", "url": None},
            ],
        },
    )


def campaign_detail(request: HttpRequest, slug: str) -> HttpResponse:
    campaign = get_object_or_404(Campaign, slug=slug)
    items = []
    for item in campaign.items.all():
        section = resolve_section(item.section_stable_id)
        items.append({"item": item, "section": section})
    from django.urls import reverse

    return render(
        request,
        "campaigns/detail.html",
        {
            "campaign": campaign,
            "items": items,
            "page_title": campaign.name,
            "breadcrumbs": [
                {
                    "label": "Workspace",
                    "url": f"{reverse('campaigns:workspace')}?tab=campaigns",
                },
                {"label": campaign.name, "url": None},
            ],
        },
    )


@require_POST
def campaign_add_section(request: HttpRequest, slug: str | None = None) -> HttpResponse:
    campaign_slug = slug or request.POST.get("campaign", "")
    campaign = get_object_or_404(Campaign, slug=campaign_slug)
    stable_id = request.POST.get("stable_id", "")
    section = resolve_section(stable_id) or get_object_or_404(Section, stable_id=stable_id)
    note = request.POST.get("note", "")
    excerpt = request.POST.get("excerpt", "").strip()
    if excerpt:
        add_excerpt_item(campaign, section, excerpt, note=note)
        messages.success(request, "Excerpt added to campaign.")
    else:
        add_section_item(campaign, section, note=note)
        messages.success(request, "Section added to campaign.")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)
    return redirect("campaigns:detail", slug=campaign.slug)


@require_POST
def campaign_remove_item(request: HttpRequest, slug: str, item_id: int) -> HttpResponse:
    campaign = get_object_or_404(Campaign, slug=slug)
    item = get_object_or_404(CampaignItem, campaign=campaign, pk=item_id)
    item.delete()
    messages.success(request, "Removed from campaign.")
    return redirect("campaigns:detail", slug=campaign.slug)


@require_POST
def campaign_update_item_note(request: HttpRequest, slug: str, item_id: int) -> HttpResponse:
    campaign = get_object_or_404(Campaign, slug=slug)
    item = get_object_or_404(CampaignItem, campaign=campaign, pk=item_id)
    item.note = request.POST.get("note", "").strip()
    item.save(update_fields=["note"])
    messages.success(request, "Campaign note updated.")
    return redirect("campaigns:detail", slug=campaign.slug)
