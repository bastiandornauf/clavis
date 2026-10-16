"""ClavisGen pages: home and the detailed-creation worksheet."""

from __future__ import annotations

import json
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods, require_POST

from apps.campaigns.models import Campaign
from apps.chargen.catalog import core_book, core_entries
from apps.chargen.core_tables import HOUSES, PATHS, TYPE_BUDGETS
from apps.chargen.creation import experience_pools
from apps.chargen.models import Character
from apps.chargen.pdf_fill import (
    PdfFillError,
    fill_character_pdf,
    filled_filename,
    read_uploaded_pdf,
)
from apps.chargen.worksheet import (
    ERRORS_KEY,
    SESSION_KEY,
    STEP_DESTINATIONS,
    STEP_LABELS,
    apply_post,
    blocking_steps,
    canonical_ability_name,
    default_state,
    house_slot_offer,
    house_suggestion_rows,
    learnable_spell_rows,
    life_path,
    load_state,
    meter_for,
    neighbor_steps,
    note_placeholder,
    open_replaces_working_copy,
    save_state,
    sheet_context,
    sheet_json,
    sheet_markdown,
    step_brief,
    step_checklist,
    steps_for,
    suggested_pick_groups,
    target_prompt,
    validate_step,
    vf_category_options,
    virtue_sheet_name,
    working_copy_name,
    write_overlay,
)

VF_PAGE_SIZE = 12


def _chosen_virtues(state: dict) -> list[dict]:
    rows = []
    for pick in state.get("virtues_flaws") or []:
        if not isinstance(pick, dict):
            continue
        name = str(pick.get("name") or "")
        target = str(pick.get("target") or "")
        structured = target_prompt(str(pick.get("slug") or "")) is not None
        rows.append(
            {
                **pick,
                "note_label": "" if structured else note_placeholder(name),
                "sheet_name": virtue_sheet_name(name, target),
                "house_slot_offer": house_slot_offer(state, pick),
            }
        )
    return rows


def _vf_page(raw: str | None, pages: int) -> int:
    try:
        page = int(raw or 1)
    except ValueError:
        page = 1
    return max(1, min(page, max(1, pages)))


def _vf_query(
    *,
    kind: str,
    magnitude: str,
    category: str,
    query: str,
    page: int,
) -> str:
    params: dict[str, str] = {"step": "virtues", "kind": kind}
    if magnitude:
        params["vf_magnitude"] = magnitude
    if category:
        params["vf_category"] = category
    if query:
        params["vf_q"] = query
    if page > 1:
        params["vf_page"] = str(page)
    return urlencode(params)


def _return_to_step(request: HttpRequest, step: str) -> HttpResponseRedirect:
    """Stay on this step. Virtue filters travel with the redirect."""
    if step == "virtues":
        kind = request.POST.get("kind", "virtue").strip()
        if kind not in {"virtue", "flaw"}:
            kind = "virtue"
        query = _vf_query(
            kind=kind,
            magnitude=request.POST.get("vf_magnitude", "").strip(),
            category=request.POST.get("vf_category", "").strip(),
            query=request.POST.get("vf_q", "").strip(),
            page=_vf_page(request.POST.get("vf_page"), 10_000),
        )
        return HttpResponseRedirect(f"{reverse('chargen:new')}?{query}")
    return HttpResponseRedirect(f"{reverse('chargen:new')}?step={step}")


def _spell_query(*, step: str, query: str, technique: str, form: str, page: int) -> str:
    params: dict[str, str] = {"step": step}
    if technique:
        params["spell_filter_te"] = technique
    if form:
        params["spell_filter_fo"] = form
    if query:
        params["spell_q"] = query
    if page > 1:
        params["spell_page"] = str(page)
    return urlencode(params)


def _chargen_shell() -> dict:
    return {
        "clavis_app_name": "ClavisGen",
        "clavis_tagline": "character generator",
        "chargen_home": True,
    }


def _type_sentence(key: str, flaw_points: int, pools) -> str:
    if key == "magus":
        return (
            f"{flaw_points} Flaw points, {pools.later_life_xp} later-life XP at age 25, "
            f"{pools.apprenticeship_xp} apprenticeship XP, and "
            f"{pools.apprenticeship_spell_levels} spell levels."
        )
    return f"{flaw_points} Flaw points and {pools.later_life_xp} later-life XP at age 25."


def home(request: HttpRequest) -> HttpResponse:
    book = core_book()
    stored = request.session.get(SESSION_KEY)
    in_progress = isinstance(stored, dict) and bool(
        str(stored.get("name") or "").strip() or stored.get("character_type")
    )
    choosing_type = request.GET.get("choose") == "1"
    begin = request.GET.get("begin", "").strip()
    types = []
    for key, budget in TYPE_BUDGETS.items():
        pools = experience_pools(character_type=key, age=25)
        types.append(
            {
                "key": key,
                "label": key.title(),
                "sentence": _type_sentence(key, budget.max_flaw_points, pools),
            }
        )
    last_step = str((stored or {}).get("last_step") or "start")
    if begin in TYPE_BUDGETS and in_progress:
        begin_type = next(item for item in types if item["key"] == begin)
        return render(
            request,
            "chargen/begin_confirm.html",
            {
                **_chargen_shell(),
                "page_title": "Replace the working copy?",
                "begin_type": begin_type,
                "working_name": working_copy_name(stored),
                "working_type": str(stored.get("character_type") or "").title(),
                "breadcrumbs": [
                    {"label": "ClavisGen", "url": reverse("chargen:home")},
                    {"label": "Create a character", "url": None},
                ],
            },
        )
    return render(
        request,
        "chargen/index.html",
        {
            **_chargen_shell(),
            "core_book": book,
            "types": types,
            "in_progress": in_progress and not choosing_type,
            "choosing_type": choosing_type and in_progress,
            "confirm_new_type": in_progress and not choosing_type,
            "progress_name": stored.get("name", "") if isinstance(stored, dict) else "",
            "progress_type": stored.get("character_type", "") if isinstance(stored, dict) else "",
            "progress_age": stored.get("age", "") if isinstance(stored, dict) else "",
            "progress_step": STEP_LABELS.get(last_step, "Concept"),
            "houses": HOUSES,
            "paths": PATHS,
            "core_slug": book.slug if book else "",
            "breadcrumbs": [{"label": "ClavisGen", "url": reverse("chargen:home")}],
        },
    )


def new_character(request: HttpRequest) -> HttpResponse:
    book = core_book()
    if book is None:
        return render(
            request,
            "chargen/index.html",
            {
                **_chargen_shell(),
                "core_book": None,
                "counts": {},
                "types": [],
                "houses": HOUSES,
                "paths": PATHS,
                "core_slug": "",
                "breadcrumbs": [{"label": "ClavisGen", "url": reverse("chargen:home")}],
            },
        )

    state = load_state(request)
    if request.method == "POST":
        return _handle_worksheet_post(request, state)

    begin = request.GET.get("as", "").strip()
    if begin in TYPE_BUDGETS:
        previous = str(state.get("character_type") or "")
        if previous and previous != begin:
            state["type_switch_from"] = previous
        state["character_type"] = begin
        if begin != "magus":
            state["house"] = ""
        save_state(request, state)
    elif not state.get("character_type"):
        return HttpResponseRedirect(reverse("chargen:home"))

    notice = str(state.pop("form_notice", "") or "")
    if notice:
        save_state(request, state)
    step = request.GET.get("step") or state.get("last_step") or "start"
    errors = request.session.pop(ERRORS_KEY, [])
    ctx = _worksheet_context(request, state, step, errors=errors, form_notice=notice)
    state["last_step"] = ctx["step"]
    save_state(request, state)
    return render(request, "chargen/worksheet.html", ctx)


def _handle_worksheet_post(request: HttpRequest, state: dict) -> HttpResponse:
    action = request.POST.get("action") or "save"
    if action == "reset":
        save_state(request, default_state())
        request.session.pop(ERRORS_KEY, None)
        return HttpResponseRedirect(reverse("chargen:new"))
    step = request.POST.get("step") or "start"
    before_package = state.get("childhood_package") or ""
    before_minima = bool(state.get("apply_minima"))
    before_type = state.get("character_type") or ""
    state = apply_post(step, state, request.POST)
    save_state(request, state)
    if request.headers.get("HX-Request") and action == "live":
        ctx = _worksheet_context(request, state, step)
        ctx["refresh_editor"] = (
            (state.get("childhood_package") or "") != before_package
            or bool(state.get("apply_minima")) != before_minima
            or (state.get("character_type") or "") != before_type
        )
        ctx["show_gaps"] = bool(ctx["step_checklist"])
        ctx["focus_gaps"] = False
        return render(request, "chargen/live.html", ctx)
    prev_step, next_step = neighbor_steps(state, step)
    if action == "next":
        errors = validate_step(step, state)
        if not errors and step == "start":
            state.pop("type_switch_from", None)
            save_state(request, state)
        if errors:
            request.session[ERRORS_KEY] = [
                {"code": item.code, "message": item.message, "cite": item.cite}
                for item in errors
            ]
            return _return_to_step(request, step)
        target = next_step or step
        return HttpResponseRedirect(f"{reverse('chargen:new')}?step={target}")
    if action == "back" and prev_step:
        return HttpResponseRedirect(f"{reverse('chargen:new')}?step={prev_step}")
    return _return_to_step(request, step)


def _worksheet_context(
    request: HttpRequest,
    state: dict,
    step: str,
    *,
    errors: list | None = None,
    form_notice: str = "",
) -> dict:
    steps = steps_for(state)
    if step not in steps:
        step = steps[0]
    ctx = sheet_context(state)
    ctx["chosen_virtues"] = _chosen_virtues(state)
    ctx["suggested_groups"] = suggested_pick_groups(
        ctx["kind"], state, has_social_status=ctx["has_social_status"]
    )
    ctx["house_suggestions"] = house_suggestion_rows(state)
    prev_step, next_step = neighbor_steps(state, step)
    vf_query = request.GET.get("vf_q", "").strip()
    vf_kind = request.GET.get("kind", "virtue")
    vf_magnitude = request.GET.get("vf_magnitude", "").strip()
    vf_category = request.GET.get("vf_category", "").strip()
    if vf_kind not in {"virtue", "flaw"}:
        vf_kind = "virtue"
    catalog_qs = core_entries(vf_kind)
    if vf_query:
        catalog_qs = catalog_qs.filter(name__icontains=vf_query)
    if vf_magnitude:
        catalog_qs = catalog_qs.filter(magnitude__iexact=vf_magnitude)
    if vf_category:
        catalog_qs = catalog_qs.filter(category__icontains=vf_category)
    vf_filtered = bool(vf_query or vf_magnitude or vf_category)
    vf_available = core_entries(vf_kind).count()
    vf_match_count = catalog_qs.count()
    vf_pages = max(1, (vf_match_count + VF_PAGE_SIZE - 1) // VF_PAGE_SIZE)
    vf_page = _vf_page(request.GET.get("vf_page"), vf_pages)
    vf_offset = (vf_page - 1) * VF_PAGE_SIZE
    catalog = list(catalog_qs[vf_offset : vf_offset + VF_PAGE_SIZE]) if vf_filtered else []
    for entry in catalog:
        entry.target_prompt = target_prompt(entry.slug)
        entry.note_label = "" if entry.target_prompt else note_placeholder(entry.name)
        meta = ", ".join(part for part in (entry.magnitude, entry.category) if part)
        summary = (entry.summary or "").strip()
        entry.show_summary = bool(summary) and summary.casefold() != meta.casefold()
    vf_page_start = vf_offset + 1 if catalog else 0
    vf_page_end = vf_offset + len(catalog)
    vf_categories = vf_category_options(
        list(
            core_entries(vf_kind)
            .exclude(category="")
            .order_by("category")
            .values_list("category", flat=True)
            .distinct()
        )
    )
    catalog_abilities = []
    seen_abilities: set[str] = set()
    for entry in core_entries("ability"):
        name = canonical_ability_name(entry.name)
        key = name.casefold()
        if not name or key in seen_abilities:
            continue
        seen_abilities.add(key)
        catalog_abilities.append({"name": name, "category": entry.category or "General"})
    if step == "childhood":
        allowed = {name.casefold() for name in ctx["childhood_list"]}
        ability_choices = [
            row for row in catalog_abilities if row["name"].casefold() in allowed
        ]
        have = {row["name"].casefold() for row in ability_choices}
        ability_choices.extend(
            {"name": name, "category": "Childhood"}
            for name in ctx["childhood_list"]
            if name.casefold() not in have
        )
    else:
        ability_choices = catalog_abilities
    ability_choices.sort(key=lambda row: (row["category"], row["name"]))
    spell_query = request.GET.get("spell_q", "").strip()
    spell_te = request.GET.get("spell_filter_te", "").strip()
    spell_fo = request.GET.get("spell_filter_fo", "").strip()
    spell_catalog: list = []
    spell_match_count = 0
    spell_pages = 1
    spell_page = 1
    spell_page_start = 0
    spell_page_end = 0
    if step in {"spells", "after"}:
        spell_qs = core_entries("spell").filter(device_effect=False)
        if spell_query:
            spell_qs = spell_qs.filter(name__icontains=spell_query)
        if spell_te:
            spell_qs = spell_qs.filter(technique__iexact=spell_te)
        if spell_fo:
            spell_qs = spell_qs.filter(form__iexact=spell_fo)
        learnable = learnable_spell_rows(ctx, spell_qs)
        spell_match_count = len(learnable)
        spell_pages = max(1, (spell_match_count + VF_PAGE_SIZE - 1) // VF_PAGE_SIZE)
        spell_page = _vf_page(request.GET.get("spell_page"), spell_pages)
        spell_offset = (spell_page - 1) * VF_PAGE_SIZE
        spell_catalog = learnable[spell_offset : spell_offset + VF_PAGE_SIZE]
        spell_page_start = spell_offset + 1 if spell_catalog else 0
        spell_page_end = spell_offset + len(spell_catalog)
    book = ctx["core_book"]
    blocks = blocking_steps(state, ctx)
    locks = {"sheet": bool(blocks)}
    path = life_path(step, ctx, locks)
    checklist = step_checklist(step, state, ctx) if step != "sheet" else []
    focus_gaps = bool(errors)
    show_gaps = focus_gaps or (step != "start" and bool(checklist))
    current = next((item for item in path if item["current"]), path[0])
    saved_id = int(state.get("saved_id") or 0)
    saved_character = Character.objects.filter(pk=saved_id).first() if saved_id else None
    return {
        **_chargen_shell(),
        **ctx,
        "campaigns": Campaign.objects.all(),
        "saved_character": saved_character,
        "page_title": state.get("name") or "New character",
        "step": step,
        "step_label": STEP_LABELS[step],
        "step_destination": STEP_DESTINATIONS[step],
        "step_brief": step_brief(step, ctx),
        "step_checklist": checklist,
        "show_gaps": show_gaps,
        "focus_gaps": focus_gaps,
        "meter_line": meter_for(step, ctx),
        "sheet_blocks": blocks,
        "form_notice": form_notice or str(state.get("form_notice") or ""),
        "vf_quick": [
            cat
            for cat in ("Social Status", "Hermetic", "General", "Personality", "Story")
            if cat in vf_categories
        ],
        "step_n": current["n"],
        "life_path": path,
        "refresh_editor": False,
        "steps": [{"key": key, "label": STEP_LABELS[key]} for key in steps],
        "prev_step": prev_step,
        "next_step": next_step,
        "errors": errors or [],
        "vf_kind": vf_kind,
        "vf_query": vf_query,
        "vf_magnitude": vf_magnitude,
        "vf_category": vf_category,
        "vf_categories": vf_categories,
        "vf_filtered": vf_filtered,
        "vf_match_count": vf_match_count,
        "vf_available": vf_available,
        "vf_page": vf_page,
        "vf_pages": vf_pages,
        "vf_page_start": vf_page_start,
        "vf_page_end": vf_page_end,
        "vf_prev_page": vf_page - 1 if vf_page > 1 else 0,
        "vf_next_page": vf_page + 1 if vf_page < vf_pages else 0,
        "vf_prev_qs": _vf_query(
            kind=vf_kind,
            magnitude=vf_magnitude,
            category=vf_category,
            query=vf_query,
            page=vf_page - 1,
        ),
        "vf_next_qs": _vf_query(
            kind=vf_kind,
            magnitude=vf_magnitude,
            category=vf_category,
            query=vf_query,
            page=vf_page + 1,
        ),
        "ability_choices": ability_choices,
        "catalog": catalog,
        "spell_query": spell_query,
        "spell_te": spell_te,
        "spell_fo": spell_fo,
        "spell_add_name": "after_add_spell_id" if step == "after" else "add_spell_id",
        "spell_level_prefix": "after_" if step == "after" else "",
        "spell_catalog": spell_catalog,
        "spell_match_count": spell_match_count,
        "spell_pages": spell_pages,
        "spell_page": spell_page,
        "spell_page_start": spell_page_start,
        "spell_page_end": spell_page_end,
        "spell_prev_page": spell_page - 1 if spell_page > 1 else 0,
        "spell_next_page": spell_page + 1 if spell_page < spell_pages else 0,
        "spell_prev_qs": _spell_query(
            step=step,
            query=spell_query,
            technique=spell_te,
            form=spell_fo,
            page=spell_page - 1,
        ),
        "spell_next_qs": _spell_query(
            step=step,
            query=spell_query,
            technique=spell_te,
            form=spell_fo,
            page=spell_page + 1,
        ),
        "core_slug": book.slug if book else "",
        "breadcrumbs": [
            {"label": "ClavisGen", "url": reverse("chargen:home")},
            {"label": "New character", "url": reverse("chargen:new")},
        ],
    }


def reset_character(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        state = default_state()
        begin = request.POST.get("as", "").strip()
        if begin in TYPE_BUDGETS:
            state["character_type"] = begin
        save_state(request, state)
        request.session.pop(ERRORS_KEY, None)
    return HttpResponseRedirect(reverse("chargen:new"))


def _worksheet_or_home(request: HttpRequest) -> dict | HttpResponseRedirect:
    state = load_state(request)
    if not state.get("character_type"):
        return HttpResponseRedirect(reverse("chargen:home"))
    return state


def print_sheet(request: HttpRequest) -> HttpResponse:
    state = _worksheet_or_home(request)
    if isinstance(state, HttpResponseRedirect):
        return state
    ctx = sheet_context(state)
    ctx["print_view"] = True
    ctx["aging_any"] = 0
    ctx["aging_crises"] = 0
    return render(request, "chargen/print.html", ctx)


def download_markdown(request: HttpRequest) -> HttpResponse:
    state = _worksheet_or_home(request)
    if isinstance(state, HttpResponseRedirect):
        return state
    ctx = sheet_context(state)
    text = sheet_markdown(ctx)
    filename = slugify(str(state.get("name") or "").strip()) or "character"
    response = HttpResponse(text, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}.md"'
    return response


@require_POST
def fill_pdf(request: HttpRequest) -> HttpResponse:
    state = _worksheet_or_home(request)
    if isinstance(state, HttpResponseRedirect):
        return state
    try:
        raw = read_uploaded_pdf(request.FILES.get("sheet_pdf"))
        data = fill_character_pdf(raw, sheet_context(state))
    except PdfFillError as exc:
        state["form_notice"] = str(exc)
        save_state(request, state)
        return HttpResponseRedirect(f"{reverse('chargen:new')}?step=sheet")
    filename = filled_filename(sheet_context(state))
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def download_json(request: HttpRequest) -> HttpResponse:
    state = _worksheet_or_home(request)
    if isinstance(state, HttpResponseRedirect):
        return state
    ctx = sheet_context(state)
    payload = sheet_json(ctx)
    filename = slugify(str(state.get("name") or "").strip()) or "character"
    body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    response = HttpResponse(body, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}.json"'
    return response


@require_POST
def save_character(request: HttpRequest) -> HttpResponse:
    state = _worksheet_or_home(request)
    if isinstance(state, HttpResponseRedirect):
        return state
    campaign_raw = str(request.POST.get("campaign") or "").strip()
    campaign_id = int(campaign_raw) if campaign_raw.isdigit() else None
    character = write_overlay(state, campaign_id=campaign_id)
    state["saved_id"] = character.pk
    save_state(request, state)
    messages.success(request, f"Saved “{character.name}” to Workspace.")
    return HttpResponseRedirect(f"{reverse('chargen:new')}?step=sheet")


def _apply_opened_character(request: HttpRequest, character: Character) -> None:
    state = dict(character.state or {})
    state["saved_id"] = character.pk
    if not state.get("character_type"):
        state["character_type"] = character.character_type
    save_state(request, state)
    request.session.pop(ERRORS_KEY, None)


@require_http_methods(["GET", "POST"])
def open_character(request: HttpRequest, pk: int) -> HttpResponse:
    character = get_object_or_404(Character, pk=pk)
    current = load_state(request)
    if request.method != "POST" and open_replaces_working_copy(current, character):
        saved_id = int(current.get("saved_id") or 0)
        working_saved = (
            saved_id != character.pk and Character.objects.filter(pk=saved_id).exists()
        )
        return render(
            request,
            "chargen/open_confirm.html",
            {
                **_chargen_shell(),
                "page_title": "Replace the working copy?",
                "character": character,
                "working_name": working_copy_name(current),
                "working_type": str(current.get("character_type") or "").title(),
                "same_row": saved_id == character.pk,
                "working_saved": working_saved,
                "breadcrumbs": [
                    {"label": "ClavisGen", "url": reverse("chargen:home")},
                    {"label": "Open character", "url": None},
                ],
            },
        )
    _apply_opened_character(request, character)
    return HttpResponseRedirect(f"{reverse('chargen:new')}?step=sheet")
