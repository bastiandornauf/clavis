"""Session worksheet for detailed character creation.

The working copy lives in the session. Workspace `Character` rows store the
same JSON so a saved sheet can be opened back into this worksheet.
"""

from __future__ import annotations

import re
from typing import Any

from django.http import HttpRequest, QueryDict
from django.utils.text import slugify

from apps.campaigns.models import Campaign
from apps.chargen.catalog import core_book, core_entries
from apps.chargen.core_tables import (
    APPRENTICESHIP_REQUIRED,
    APPRENTICESHIP_YEARS,
    CHARACTERISTIC_LABELS,
    CHARACTERISTIC_POINTS,
    CHARACTERISTICS,
    CHILDHOOD_ABILITIES,
    CHILDHOOD_YEARS,
    FERAL_CHILDHOOD_ABILITIES,
    GATED_ABILITY_NAMES,
    HERMETIC_FORMS,
    HERMETIC_TECHNIQUES,
    HOUSES,
    LIVING_CONDITIONS,
    NATIVE_LANGUAGE_XP,
    PATHS,
    POST_GAUNTLET_LAB_SEASON_COST,
    POST_GAUNTLET_POINTS,
    RECOMMENDED_GAUNTLET_ABILITIES,
    SAMPLE_CHILDHOODS,
    TYPE_BUDGETS,
)
from apps.chargen.creation import (
    Issue,
    VirtueFlaw,
    ability_learnable,
    ability_score_from_xp,
    ability_xp_for_score,
    aging_year_ages,
    art_score_from_xp,
    art_xp_for_score,
    can_know_spell,
    characteristic_cost,
    characteristics_for_play,
    characteristics_remaining,
    check_apprenticeship_minima,
    check_virtues_and_flaws,
    childhood_ability_allowed,
    experience_pools,
    known_spell,
    max_ability_score,
    post_gauntlet_year_points,
    recommended_gauntlet_xp,
    resolve_aging,
    sample_childhood,
    simple_die,
    size_for_play,
    spell_creation_cost,
    spell_level_cap,
    starting_confidence,
    stress_die,
)
from apps.chargen.models import Character
from apps.chargen.play import play_overlay
from apps.chargen.types import VirtueFlaw as VF
from apps.chargen.vf_effects import apply_vf_effects, boost_xp, target_spec, vf_slug

SESSION_KEY = "chargen_worksheet"
ERRORS_KEY = "chargen_errors"

STEP_LABELS = {
    "start": "Concept",
    "virtues": "Virtues and Flaws",
    "characteristics": "Characteristics",
    "childhood": "Early childhood",
    "later_life": "Later life",
    "apprenticeship": "Apprenticeship",
    "spells": "Spells",
    "after": "After apprenticeship",
    "aging": "Aging",
    "details": "Personality and equipment",
    "sheet": "Character sheet",
}

STEP_DESTINATIONS = {
    "start": "Name, type, House, and age go on the sheet header.",
    "virtues": "Virtues and Flaws list; some also change XP, Art bonuses, or Ability gates.",
    "characteristics": "The eight Characteristic scores on the sheet.",
    "childhood": "Early Ability scores: Native Language 5 plus the childhood package.",
    "later_life": "Ability scores from the years after childhood.",
    "apprenticeship": "Ability scores, Art scores, and the remaining apprenticeship pool.",
    "spells": "Known spells on the sheet, paid in spell levels.",
    "after": "Extra Ability, Art, and spell scores after Gauntlet.",
    "aging": "Aging results, kept separate from the scores you bought.",
    "details": "Personality traits, Reputation, Confidence, and equipment.",
    "sheet": "The character, legal or with the rules still open.",
}

# Same order as the characteristic form: mental, then physical.
CHAR_DISPLAY = ("int", "per", "pre", "com", "str", "sta", "dex", "qik")

TARGET_LABELS = {
    "characteristic": "Characteristic",
    "ability": "Ability",
    "art": "Art",
    "form": "Form",
    "technique": "Technique",
    "category": "Ability category",
    "realm": "Realm",
}

_RULE_NAMES = {
    "summary": "Detailed character creation",
    "virtues_flaws": "Virtues and Flaws",
    "characteristics": "Characteristics",
    "abilities": "Abilities",
    "childhood": "Early childhood",
    "later_life": "Later life",
    "apprenticeship": "Apprenticeship",
    "after_apprenticeship": "After apprenticeship",
    "house": "Hermetic House",
    "houses_table": "Hermetic Houses",
    "experience": "Experience points",
    "the_gift": "The Gift",
    "hermetic_magus": "Hermetic Magus",
    "wealthy": "Wealthy",
    "poor": "Poor",
    "privileged_upbringing": "Privileged Upbringing",
    "grog": "Grogs",
    "companion": "Companions",
    "magus": "Magi",
    "starting_age": "Starting age",
    "templates": "Character templates",
    "sample_childhoods": "Sample childhoods",
    "choosing_vf": "Choosing Virtues and Flaws",
    "quick_vf": "Quick and easy Virtues and Flaws",
    "vf_guidelines": "Virtues and Flaws guidelines",
    "personality": "Personality",
    "confidence": "Confidence",
    "equipment": "Equipment",
    "minima": "Recommended minima",
    "aging": "Aging",
    "child_characters": "Child characters",
    "arts": "Hermetic Arts",
    "combat": "Combat",
    "wounds": "Wounds",
    "fatigue": "Fatigue",
    "casting": "Casting spells",
    "laboratory": "Laboratory",
}

_CHAR_ABBREV = {
    "int": "Int",
    "per": "Per",
    "pre": "Pre",
    "com": "Com",
    "str": "Str",
    "sta": "Sta",
    "dex": "Dex",
    "qik": "Qik",
}
_ART_ABBREV = {
    "creo": "Cr",
    "intellego": "In",
    "muto": "Mu",
    "perdo": "Pe",
    "rego": "Re",
    "animal": "An",
    "aquam": "Aq",
    "auram": "Au",
    "corpus": "Co",
    "herbam": "He",
    "ignem": "Ig",
    "imaginem": "Im",
    "mentem": "Me",
    "terram": "Te",
    "vim": "Vi",
}
_ART_SHEET_LINES = (
    ("creo", "intellego", "muto", "perdo", "rego"),
    ("animal", "aquam", "auram", "corpus", "herbam"),
    ("ignem", "imaginem", "mentem", "terram", "vim"),
)
# Parentheticals that are blanks to fill, not part of the Virtue's name.
_NOTE_SLOTS = frozenset(
    {
        "ability",
        "art",
        "being",
        "beings",
        "characteristic",
        "commodity",
        "faculty",
        "form",
        "land",
        "realm",
        "role",
        "sin",
        "subject",
        "terrain",
    }
)
_NOTE_SLOT = re.compile(r"\(([^)]+)\)")
ABILITY_SCORE_COSTS = tuple((n, ability_xp_for_score(n)) for n in range(1, 6))
ART_SCORE_COSTS = tuple((n, art_xp_for_score(n)) for n in range(1, 11))
CUSTOM_ABILITY = "__custom__"

SUGGESTED_FREE = {
    "grog": (
        VF("Covenfolk", "virtue", "Free", "Social Status", "covenfolk"),
    ),
    "companion": (
        VF("Wanderer", "virtue", "Free", "Social Status", "wanderer"),
    ),
    "magus": (
        VF("The Gift", "virtue", "Free", "Special", "the-gift"),
        VF("Hermetic Magus", "virtue", "Free", "Social Status", "hermetic-magus"),
    ),
}
_ALTERNATE_STATUS = frozenset({"wanderer", "covenfolk"})
_SUGGESTION_COVERS = {
    "the-gift": frozenset({"magus_needs_gift"}),
    "hermetic-magus": frozenset({"magus_needs_status", "need_social_status"}),
    "wanderer": frozenset({"need_social_status"}),
    "covenfolk": frozenset({"need_social_status"}),
}
CLUMSY_MAGIC = VF("Clumsy Magic", "flaw", "Minor", "Hermetic", "clumsy-magic")
_VF_BUCKET_SPLIT = re.compile(r"\s*(?:,|;|/|\s+and\s+|\s+or\s+)\s*", re.I)
_VF_BUCKET_ORDER = (
    "Hermetic",
    "General",
    "Social Status",
    "Story",
    "Supernatural",
    "Personality",
    "Special",
    "Tainted",
)
_CHECKLIST_FILTERS = {
    "magus_needs_hermetic_flaw": {
        "filter_kind": "flaw",
        "filter_category": "Hermetic",
        "filter_label": "Show Hermetic Flaws",
    },
    "need_social_status": {
        "filter_kind": "virtue",
        "filter_category": "Social Status",
        "filter_label": "Show Social Status",
    },
    "house_flaw": {
        "filter_kind": "flaw",
        "filter_category": "Hermetic",
        "filter_magnitude": "Major",
        "filter_label": "Show Major Hermetic Flaws",
    },
}


def _suggestion_taken(item: VF, picks: list[dict[str, Any]]) -> bool:
    for row in picks:
        if str(row.get("slug") or "") == item.slug:
            return True
        if str(row.get("name") or "").strip().casefold() == item.name.casefold():
            return True
    return False


def _open_suggestions(
    kind: str, state: dict[str, Any], *, has_social_status: bool
) -> tuple[VF, ...]:
    picks = [row for row in (state.get("virtues_flaws") or []) if isinstance(row, dict)]
    open_items: list[VF] = []
    for item in SUGGESTED_FREE.get(kind, ()):
        if _suggestion_taken(item, picks):
            continue
        if item.slug in _ALTERNATE_STATUS and has_social_status:
            continue
        open_items.append(item)
    return tuple(open_items)


def _house_pick_as_vf(spec) -> VF:
    return VF(spec.name, spec.kind, spec.magnitude, spec.category, spec.slug)


def _house_open_suggestions(state: dict[str, Any]) -> tuple[VF, ...]:
    house = _selected_house(state)
    if house is None or not house.suggestions:
        return ()
    picks = [row for row in (state.get("virtues_flaws") or []) if isinstance(row, dict)]
    return tuple(
        _house_pick_as_vf(spec)
        for spec in house.suggestions
        if not _suggestion_taken(_house_pick_as_vf(spec), picks)
    )


def _hermetic_flaw_suggestions(kind: str, state: dict[str, Any]) -> tuple[VF, ...]:
    if kind != "magus":
        return ()
    picks = [row for row in (state.get("virtues_flaws") or []) if isinstance(row, dict)]
    if any(
        str(row.get("kind") or "") == "flaw"
        and "hermetic" in str(row.get("category") or "").casefold()
        for row in picks
    ):
        return ()
    if _suggestion_taken(CLUMSY_MAGIC, picks):
        return ()
    return (CLUMSY_MAGIC,)


def _suggestion_row(item: VF) -> dict[str, Any]:
    return {
        "name": item.name,
        "slug": item.slug,
        "kind": item.kind,
        "magnitude": item.magnitude,
        "note_label": note_placeholder(item.name),
    }


def suggested_pick_groups(
    kind: str, state: dict[str, Any], *, has_social_status: bool
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    free = _open_suggestions(kind, state, has_social_status=has_social_status)
    gift = [item for item in free if item.slug == "the-gift"]
    status = [item for item in free if item.slug != "the-gift"]
    if gift:
        groups.append({"heading": "The Gift", "items": [_suggestion_row(item) for item in gift]})
    if status:
        groups.append(
            {"heading": "Social Status", "items": [_suggestion_row(item) for item in status]}
        )
    hermetic = _hermetic_flaw_suggestions(kind, state)
    if hermetic:
        groups.append(
            {"heading": "Hermetic Flaw", "items": [_suggestion_row(item) for item in hermetic]}
        )
    return groups


def house_suggestion_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [_suggestion_row(item) for item in _house_open_suggestions(state)]


def _all_suggestion_vfs(state: dict[str, Any]) -> list[VF]:
    items: list[VF] = []
    for rows in SUGGESTED_FREE.values():
        items.extend(rows)
    items.extend(_house_open_suggestions(state))
    items.extend(_hermetic_flaw_suggestions(str(state.get("character_type") or ""), state))
    house = _selected_house(state)
    if house is not None:
        items.extend(_house_pick_as_vf(spec) for spec in house.suggestions)
    items.append(CLUMSY_MAGIC)
    return items


def _suggestion_heading(items: tuple[VF, ...]) -> str:
    if items and all(item.category == "Social Status" for item in items):
        return "Social Status"
    return ""

ART_KEYS = tuple(name.casefold() for name in (*HERMETIC_TECHNIQUES, *HERMETIC_FORMS))


def default_state() -> dict[str, Any]:
    return {
        "concept": "",
        "name": "",
        "character_type": "",
        "age": 25,
        "house": "",
        "apprenticeship_start_age": 10,
        "native_language": "",
        "virtues_flaws": [],
        "characteristics": {key: 0 for key in CHARACTERISTICS},
        "great_target": "",
        "poor_target": "",
        "childhood_package": "",
        "childhood": [],
        "later_life": [],
        "apply_minima": False,
        "apprenticeship": [],
        "arts": {key: 0 for key in ART_KEYS},
        "spells": [],
        "post_lab_seasons": 0,
        "after_abilities": [],
        "after_arts": {key: 0 for key in ART_KEYS},
        "after_spells": [],
        "personality": [],
        "reputation": "",
        "equipment": "",
        "aging_dice": [],
        "aging_early": {},
        "aging_crisis": {},
        "aging_assign": [],
        "aging_living": {},
        "aging_longevity": {},
        "living_conditions": 0,
        "longevity": 0,
        "longevity_since": 0,
        "house_choice": "",
        "house_declined": [],
        "saved_id": 0,
        "show_play": False,
    }


def load_state(request: HttpRequest) -> dict[str, Any]:
    stored = request.session.get(SESSION_KEY)
    if not isinstance(stored, dict):
        return default_state()
    state = default_state()
    state.update(stored)
    return state


def save_state(request: HttpRequest, state: dict[str, Any]) -> None:
    request.session[SESSION_KEY] = state
    request.session.modified = True


def has_working_copy(state: dict[str, Any]) -> bool:
    """True when this browser holds a character, named or not."""
    return bool(str(state.get("name") or "").strip() or state.get("character_type"))


def working_copy_name(state: dict[str, Any]) -> str:
    return str(state.get("name") or "").strip() or "Unnamed character"


def _working_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    skip = {"form_notice", "last_step", "saved_id"}
    return {key: value for key, value in overlay_payload(state).items() if key not in skip}


def open_replaces_working_copy(state: dict[str, Any], character: Character) -> bool:
    """True when loading this Workspace row would throw away the session copy."""
    if not has_working_copy(state):
        return False
    if _as_int(state.get("saved_id"), 0) == character.pk:
        return _working_snapshot(state) != _working_snapshot(character.state or {})
    return True


def steps_for(state: dict[str, Any]) -> tuple[str, ...]:
    kind = state.get("character_type") or ""
    age = _as_int(state.get("age"), 25)
    steps = ["start", "virtues", "characteristics", "childhood", "later_life"]
    if kind == "magus":
        steps.append("apprenticeship")
        steps.append("spells")
        start = _as_int(state.get("apprenticeship_start_age"), 10)
        if age >= start + 15 and age > start + 15:
            steps.append("after")
    if age > 35:
        steps.append("aging")
    steps.extend(["details", "sheet"])
    return tuple(steps)


def picks_from_state(state: dict[str, Any]) -> list[VirtueFlaw]:
    picks: list[VirtueFlaw] = []
    for row in state.get("virtues_flaws") or []:
        picks.append(
            VirtueFlaw(
                name=str(row.get("name") or ""),
                kind=str(row.get("kind") or "virtue"),
                magnitude=str(row.get("magnitude") or "Minor"),
                category=str(row.get("category") or ""),
                slug=str(row.get("slug") or vf_slug(str(row.get("name") or ""))),
                granted=bool(row.get("house_grant")),
            )
        )
    return picks


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def canonical_ability_name(name: str) -> str:
    """Book lists mark some Abilities with a trailing asterisk. One name on the sheet."""
    return name.strip().rstrip("*").strip()


def _ability_key(name: str) -> str:
    return canonical_ability_name(name).casefold()


_ABILITY_PHASES = ("childhood", "later_life", "apprenticeship", "after_abilities")


def _xp_rows(rows: object) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    if not isinstance(rows, list):
        return []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = canonical_ability_name(str(row.get("name") or ""))
        xp = max(0, _as_int(row.get("xp"), 0))
        specialty = str(row.get("specialty") or "").strip()
        if not name or (not xp and not specialty):
            continue
        key = name.casefold()
        current = merged.get(key)
        if current is None:
            order.append(key)
            merged[key] = {"name": name, "xp": xp, "specialty": specialty}
        else:
            current["xp"] += xp
            if specialty:
                current["specialty"] = specialty
    return [merged[key] for key in order]


def combined_ability_xp(state: dict[str, Any], name: str) -> int:
    folded = _ability_key(name)
    total = 0
    native = _ability_key(str(state.get("native_language") or ""))
    if folded.startswith("native language") or (native and folded == native):
        applied = apply_vf_effects(picks_from_state(state))
        if applied.childhood != "feral":
            total += NATIVE_LANGUAGE_XP
    for key in _ABILITY_PHASES:
        for row in _xp_rows(state.get(key)):
            if _ability_key(row["name"]) == folded:
                total += row["xp"]
    return total


def combined_art_xp(state: dict[str, Any], art: str) -> int:
    key = art.casefold()
    total = _as_int((state.get("arts") or {}).get(key), 0)
    total += _as_int((state.get("after_arts") or {}).get(key), 0)
    return total


def sheet_context(state: dict[str, Any]) -> dict[str, Any]:
    sync_house_grants(state)
    kind = str(state.get("character_type") or "")
    age = _as_int(state.get("age"), 25)
    picks = picks_from_state(state)
    applied = apply_vf_effects(picks)
    vf_totals = (
        check_virtues_and_flaws(kind, picks)
        if kind in TYPE_BUDGETS
        else check_virtues_and_flaws("companion", [])
    )
    start_age = _as_int(state.get("apprenticeship_start_age"), 10)
    pools = experience_pools(
        character_type=kind or "companion",
        age=age,
        apprenticeship_start_age=start_age if kind == "magus" else None,
        extra_xp=applied.extra_xp,
        apprenticeship_xp_delta=applied.apprenticeship_xp_delta,
        apprenticeship_spell_delta=applied.apprenticeship_spell_delta,
        feral_childhood=applied.childhood == "feral",
        later_life_xp_per_year=applied.later_life_xp_per_year,
    )
    bought = {
        key: _as_int((state.get("characteristics") or {}).get(key), 0) for key in CHARACTERISTICS
    }
    extra_points = applied.characteristic_points_delta
    try:
        remaining_char = characteristics_remaining(bought, extra_points=extra_points)
        char_ok = True
    except ValueError:
        remaining_char = 0
        char_ok = False
    play = characteristics_for_play(bought, age)
    if applied.str_sta_bonus:
        play["str"] = play.get("str", 0) + applied.str_sta_bonus
        play["sta"] = play.get("sta", 0) + applied.str_sta_bonus
    vf_rows = list(state.get("virtues_flaws") or [])
    has_great = any(_entry_slug(row) == "great-characteristic" for row in vf_rows)
    has_poor = any(_entry_slug(row) == "poor-characteristic" for row in vf_rows)
    _apply_characteristic_adjustments(
        play,
        vf_rows,
        slug="great-characteristic",
        delta=1,
        fallback=str(state.get("great_target") or "") if has_great else "",
    )
    _apply_characteristic_adjustments(
        play,
        vf_rows,
        slug="poor-characteristic",
        delta=-1,
        fallback=str(state.get("poor_target") or "") if has_poor else "",
    )
    size = size_for_play(age=age, virtue_size=applied.size)
    childhood_spent = sum(row["xp"] for row in _xp_rows(state.get("childhood")))
    later_spent = sum(row["xp"] for row in _xp_rows(state.get("later_life")))
    appr_ability_xp = sum(row["xp"] for row in _xp_rows(state.get("apprenticeship")))
    arts_xp = sum(_as_int(v, 0) for v in (state.get("arts") or {}).values())
    if state.get("apply_minima"):
        appr_ability_xp += recommended_gauntlet_xp()
    appr_ability_xp += _required_apprenticeship_gap_xp(state)
    spell_cost = sum(
        spell_creation_cost(_as_int(s.get("level"), 1)) for s in state.get("spells") or []
    )
    after_ability = sum(row["xp"] for row in _xp_rows(state.get("after_abilities")))
    after_arts = sum(_as_int(v, 0) for v in (state.get("after_arts") or {}).values())
    after_spells = sum(
        spell_creation_cost(_as_int(s.get("level"), 1)) for s in state.get("after_spells") or []
    )
    lab = min(4, max(0, _as_int(state.get("post_lab_seasons"), 0)))
    after_available = pools.post_gauntlet_years * post_gauntlet_year_points(lab)
    abilities = _ability_scores(state, age, applied)
    arts = _art_scores(state, applied)
    childhood_pool = _pool_status(childhood_spent, pools.childhood_xp)
    later_pool = _pool_status(later_spent, pools.later_life_xp)
    appr_spent = appr_ability_xp + arts_xp
    appr_pool = _pool_status(appr_spent, pools.apprenticeship_xp)
    appr_art_pool = _pool_status(appr_spent, pools.apprenticeship_xp, kind="art")
    spell_left = max(0, pools.apprenticeship_spell_levels - spell_cost)
    after_spent = after_ability + after_arts + after_spells
    after_pool = _pool_status(after_spent, after_available)
    after_art_pool = _pool_status(after_spent, after_available, kind="art")
    confidence = starting_confidence(kind) if kind in TYPE_BUDGETS else None
    issues = list(vf_totals.issues) + list(applied.issues) + list(pools.issues)
    if kind == "magus" and pools.apprenticeship_xp:
        scores = {row["name"]: row["score"] for row in abilities}
        issues.extend(check_apprenticeship_minima(scores))
    house_name = str(state.get("house") or "")
    selected_house = next((item for item in HOUSES if item.name == house_name), None)
    suggested_free = _open_suggestions(
        kind, state, has_social_status=vf_totals.has_social_status
    )
    aging = _aging_state(state, play)
    if aging["filled"] >= aging["winters"] and not aging["crisis_open"]:
        issues = [item for item in issues if item.code != "aging"]
    return {
        "state": state,
        "kind": kind,
        "age": age,
        "picks": picks,
        "applied": applied,
        "vf_totals": vf_totals,
        "pools": pools,
        "bought": bought,
        "play": play,
        "size": size,
        "remaining_char": remaining_char,
        "char_ok": char_ok,
        "extra_points": extra_points,
        "childhood_spent": childhood_spent,
        "childhood_budget": pools.childhood_xp,
        "childhood_pool": childhood_pool,
        "ability_cap": _ability_cap(age, applied),
        "childhood_rows": _phase_editor_rows(state, "childhood", applied),
        "later_spent": later_spent,
        "later_pool": later_pool,
        "later_rows": _phase_editor_rows(state, "later_life", applied),
        "appr_ability_xp": appr_ability_xp,
        "arts_xp": arts_xp,
        "apprenticeship_spent": appr_spent,
        "apprenticeship_rows": _phase_editor_rows(state, "apprenticeship", applied),
        "appr_pool": appr_pool,
        "appr_art_pool": appr_art_pool,
        "spell_cost": spell_cost,
        "spell_left": spell_left,
        "after_spent": after_spent,
        "after_available": after_available,
        "after_pool": after_pool,
        "after_art_pool": after_art_pool,
        "after_rows": _phase_editor_rows(state, "after_abilities", applied),
        "ability_costs": ABILITY_SCORE_COSTS,
        "art_costs": ART_SCORE_COSTS,
        "abilities": abilities,
        "arts": arts,
        "confidence": confidence,
        "issues": tuple(issues),
        "labels": CHARACTERISTIC_LABELS,
        "char_rows": _char_rows(bought, play, aging),
        "aging_slots": _aging_slots(aging),
        "personality_rows": state.get("personality") or [{"trait": "", "score": ""}],
        "houses": HOUSES,
        "selected_house": selected_house,
        "house_grant_line": _house_grant_line(state),
        "paths": PATHS,
        "core_book": core_book(),
        "childhood_list": FERAL_CHILDHOOD_ABILITIES
        if applied.childhood == "feral"
        else CHILDHOOD_ABILITIES,
        "packages": [
            {
                "name": pack.name,
                "summary": ", ".join(
                    f"{name} {score}"
                    for name, score in pack.abilities
                    if not name.casefold().startswith("native language")
                ),
            }
            for pack in SAMPLE_CHILDHOODS
        ],
        "minima": RECOMMENDED_GAUNTLET_ABILITIES,
        "minima_xp": recommended_gauntlet_xp(),
        "techniques": HERMETIC_TECHNIQUES,
        "forms": HERMETIC_FORMS,
        "suggested_free": suggested_free,
        "suggested_heading": _suggestion_heading(suggested_free),
        "has_great": has_great,
        "has_poor": has_poor,
        "has_social_status": vf_totals.has_social_status,
        "required_minima": APPRENTICESHIP_REQUIRED,
        "reputation_open": _reputation_open(state),
        "type_notes": _type_notes(state, kind, arts),
        "after_math": _after_math(state, pools),
        "aging": aging,
        "aging_inputs": aging["inputs"],
        "aging_die_values": _aging_die_values(aging["inputs"]),
        "living_choices": living_condition_choices(),
        "aging_any": aging["any_points"],
        "aging_apparent": aging["apparent"],
        "aging_crises": aging["crises"],
        "sheet": _character_sheet(
            state,
            kind=kind,
            age=age,
            house=house_name,
            size=size,
            confidence=confidence,
            play=play,
            aging=aging,
            abilities=abilities,
            arts=arts,
        ),
        "play_numbers": play_overlay(
            kind=kind,
            characteristics={
                key: play.get(key, 0) - aging["penalties"].get(key, 0) for key in CHARACTERISTICS
            },
            size=size,
            abilities=abilities,
            arts=arts,
            virtues_flaws=list(state.get("virtues_flaws") or []),
        ),
    }


def _add_ability_total(
    totals: dict[str, dict[str, Any]], name: str, xp: int, specialty: str = ""
) -> None:
    clean = canonical_ability_name(name)
    if not clean:
        return
    key = clean.casefold()
    if xp <= 0:
        current = totals.get(key)
        if current is not None and specialty:
            current["specialty"] = specialty
        return
    current = totals.get(key)
    if current is None:
        totals[key] = {"name": clean, "xp": xp, "specialty": specialty}
    else:
        current["xp"] += xp
        if specialty:
            current["specialty"] = specialty


def _ability_scores(state: dict[str, Any], age: int, applied) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    if applied.childhood != "feral":
        native = str(state.get("native_language") or "Native Language")
        _add_ability_total(totals, native, NATIVE_LANGUAGE_XP)
    for name, score in applied.free_abilities:
        _add_ability_total(totals, name, ability_xp_for_score(score))
    for key in _ABILITY_PHASES:
        for row in _xp_rows(state.get(key)):
            _add_ability_total(totals, row["name"], row["xp"], row["specialty"])
    if state.get("apply_minima"):
        for name, score in RECOMMENDED_GAUNTLET_ABILITIES:
            _add_ability_total(totals, name, ability_xp_for_score(score))
    if str(state.get("character_type") or "") == "magus":
        for name, minimum in APPRENTICESHIP_REQUIRED:
            have = totals.get(name.casefold(), {}).get("xp", 0)
            need = ability_xp_for_score(minimum)
            if have < need:
                _add_ability_total(totals, name, need - have)
    puissant = _puissant_ability_names(state)
    for key, name in puissant.items():
        totals.setdefault(key, {"name": name, "xp": 0, "specialty": ""})
    cap = max_ability_score(age, affinity=applied.age_cap_bonus > 0)
    rows = []
    for item in sorted(totals.values(), key=lambda row: row["name"]):
        score, leftover = ability_score_from_xp(item["xp"])
        rows.append(
            {
                "name": item["name"],
                "xp": item["xp"],
                "score": score,
                "leftover": leftover,
                "bonus": 2 if item["name"].casefold() in puissant else 0,
                "specialty": item["specialty"],
                "over_cap": score > cap,
            }
        )
    return rows


def _puissant_ability_names(state: dict[str, Any]) -> dict[str, str]:
    """Display names for Puissant Ability. The bonus is +2 and is not bought with XP."""
    found: dict[str, str] = {}
    for row in state.get("virtues_flaws") or []:
        if not isinstance(row, dict):
            continue
        slug = str(row.get("slug") or "") or vf_slug(str(row.get("name") or ""))
        if slug != "puissant-ability":
            continue
        name = canonical_ability_name(str(row.get("target") or ""))
        if name:
            found[name.casefold()] = name
    return found


def _art_scores(state: dict[str, Any], applied) -> list[dict[str, Any]]:
    rows = []
    affinity_arts = {
        str(row.get("target") or "").casefold()
        for row in state.get("virtues_flaws") or []
        if vf_slug(str(row.get("name") or "")) == "affinity-with-art"
    }
    puissant = {
        str(row.get("target") or "").casefold(): 3
        for row in state.get("virtues_flaws") or []
        if vf_slug(str(row.get("name") or "")) == "puissant-art"
    }
    for name in (*HERMETIC_TECHNIQUES, *HERMETIC_FORMS):
        spent = _as_int((state.get("arts") or {}).get(name.casefold()), 0)
        after = _as_int((state.get("after_arts") or {}).get(name.casefold()), 0)
        raw_xp = spent + after
        xp = boost_xp(raw_xp, extra_per=2) if name.casefold() in affinity_arts else raw_xp
        score, leftover = art_score_from_xp(xp)
        raw_score, raw_toward = art_score_from_xp(raw_xp)
        bought_score, bought_toward = art_score_from_xp(spent)
        bonus = puissant.get(name.casefold(), 0)
        rows.append(
            {
                "name": name,
                "key": name.casefold(),
                "spent": spent,
                "after": after,
                "bought_score": bought_score,
                "bought_toward": bought_toward,
                "raw_score": raw_score,
                "raw_toward": raw_toward,
                "paid_score": bought_score,
                "xp": xp,
                "score": score,
                "leftover": leftover,
                "bonus": bonus,
                "display": f"{score}+{bonus}" if bonus else str(score),
            }
        )
    return rows


def validate_step(
    step: str, state: dict[str, Any], ctx: dict[str, Any] | None = None
) -> tuple[Issue, ...]:
    ctx = sheet_context(state) if ctx is None else ctx
    issues: list[Issue] = []
    if step == "start":
        if not str(state.get("name") or "").strip():
            issues.append(Issue("error", "need_name", "Name the character.", PATHS["summary"]))
        if state.get("character_type") not in TYPE_BUDGETS:
            issues.append(
                Issue("error", "need_type", "Choose grog, companion, or magus.", PATHS["summary"])
            )
        if state.get("character_type") == "magus" and not str(state.get("house") or "").strip():
            issues.append(
                Issue("error", "need_house", "A magus must pick a House.", PATHS["house"])
            )
    elif step == "virtues":
        issues.extend(i for i in ctx["vf_totals"].issues if i.blocks)
        issues.extend(i for i in ctx["applied"].issues if i.blocks)
        issues.extend(_missing_target_issues(state))
        issues.extend(_house_requirement_issues(state))
    elif step == "characteristics":
        if not ctx["char_ok"] or ctx["remaining_char"] != 0:
            issues.append(
                Issue(
                    "error",
                    "char_points",
                    "Spend every characteristic point (remaining must be 0).",
                    PATHS["characteristics"],
                )
            )
    elif step == "childhood":
        budget = ctx["pools"].childhood_xp
        if ctx["childhood_spent"] > budget:
            issues.append(
                Issue(
                    "error",
                    "childhood_overspend",
                    f"Childhood XP {ctx['childhood_spent']} exceeds {budget}.",
                    PATHS["childhood"],
                )
            )
        feral = ctx["applied"].childhood == "feral"
        for row in _xp_rows(state.get("childhood")):
            if not childhood_ability_allowed(row["name"], feral=feral):
                issues.append(
                    Issue(
                        "error",
                        "childhood_ability",
                        f"{row['name']} is not on the early-childhood list.",
                        PATHS["childhood"],
                    )
                )
    elif step == "later_life":
        if ctx["later_spent"] > ctx["pools"].later_life_xp:
            issues.append(
                Issue(
                    "error",
                    "later_overspend",
                    f"Later-life XP {ctx['later_spent']} exceeds {ctx['pools'].later_life_xp}.",
                    PATHS["later_life"],
                )
            )
        granted = ctx["applied"].granted_categories
        granted_abs = ctx["applied"].granted_abilities
        for row in _xp_rows(state.get("later_life")):
            entry = _ability_category(row["name"])
            if not ability_learnable(
                category=entry,
                phase="later_life",
                name=row["name"],
                granted_categories=granted,
                granted_abilities=granted_abs,
            ):
                issues.append(
                    Issue(
                        "error",
                        "later_ability",
                        f"{row['name']} needs a Virtue that grants that Ability.",
                        PATHS["choosing_vf"],
                    )
                )
    elif step == "apprenticeship":
        spent = ctx["apprenticeship_spent"]
        budget = ctx["pools"].apprenticeship_xp
        if spent > budget:
            issues.append(
                Issue(
                    "error",
                    "appr_overspend",
                    f"Apprenticeship XP {spent} exceeds {budget}.",
                    PATHS["apprenticeship"],
                )
            )
        issues.extend(i for i in ctx["issues"] if i.code == "apprenticeship_minimum")
    elif step == "spells":
        budget = ctx["pools"].apprenticeship_spell_levels
        if ctx["spell_cost"] > budget:
            issues.append(
                Issue(
                    "error",
                    "spell_overspend",
                    f"Spell levels {ctx['spell_cost']} exceed {budget}.",
                    PATHS["apprenticeship"],
                )
            )
        issues.extend(_spell_cap_issues(state, ctx, state.get("spells") or []))
    elif step == "after":
        if ctx["after_spent"] > ctx["after_available"]:
            issues.append(
                Issue(
                    "error",
                    "after_overspend",
                    f"Post-Gauntlet points {ctx['after_spent']} exceed {ctx['after_available']}.",
                    PATHS["after_apprenticeship"],
                )
            )
        issues.extend(_spell_cap_issues(state, ctx, state.get("after_spells") or []))
    elif step == "aging":
        aging = ctx["aging"]
        if aging["filled"] < aging["winters"]:
            issues.append(
                Issue(
                    "error",
                    "aging",
                    f"Enter a stress die for each of {aging['winters']} aging winter(s).",
                    PATHS["aging"],
                )
            )
        for year in aging["crisis_open"]:
            issues.append(
                Issue(
                    "error",
                    "aging_crisis",
                    f"Enter the crisis die for age {year}.",
                    PATHS["aging"],
                )
            )
    elif step == "details":
        traits = state.get("personality") or []
        kind = state.get("character_type")
        names = {str(t.get("trait") or "").casefold() for t in traits}
        if kind == "grog" and "loyal" not in names:
            issues.append(
                Issue(
                    "error",
                    "need_loyal",
                    "Grogs should have a Loyal personality trait.",
                    PATHS["personality"],
                )
            )
    return tuple(issues)


def _ability_category(name: str) -> str:
    folded = name.casefold()
    entry = core_entries("ability").filter(name__iexact=name).first()
    if entry and entry.category:
        cat = entry.category.casefold()
        for token in ("academic", "arcane", "martial", "supernatural", "general"):
            if token in cat:
                return token
    if folded.startswith("dead language") or folded.startswith("latin"):
        return "academic"
    return GATED_ABILITY_NAMES.get(folded, "general")


def _spell_cap_issues(state: dict[str, Any], ctx: dict[str, Any], spells: list) -> list[Issue]:
    arts = {row["name"].casefold(): row["score"] + row["bonus"] for row in ctx["arts"]}
    intelligence = ctx["play"].get("int", 0)
    theory = _effective_magic_theory(ctx["abilities"])
    issues: list[Issue] = []
    for spell in spells:
        try:
            known = known_spell(
                str(spell.get("name") or "Spell"),
                str(spell.get("technique") or ""),
                str(spell.get("form") or ""),
                _as_int(spell.get("level"), 0),
            )
        except ValueError as exc:
            issues.append(Issue("error", "bad_spell", str(exc), PATHS["apprenticeship"]))
            continue
        te = arts.get(known.technique.casefold(), 0)
        fo = arts.get(known.form.casefold(), 0)
        if not can_know_spell(
            known.level, technique=te, form=fo, intelligence=intelligence, magic_theory=theory
        ):
            issues.append(
                Issue(
                    "error",
                    "spell_cap",
                    f"{known.name} ({known.level}) exceeds "
                    "Technique + Form + Int + Magic Theory + 3.",
                    PATHS["minima"],
                )
            )
    return issues


def apply_post(step: str, state: dict[str, Any], post: QueryDict) -> dict[str, Any]:
    state.pop("form_notice", None)
    if step == "start":
        state["concept"] = post.get("concept", "").strip()
        state["name"] = post.get("name", "").strip()
        kind = post.get("character_type", "").strip()
        if kind in TYPE_BUDGETS:
            state["character_type"] = kind
        state["age"] = max(0, _as_int(post.get("age"), 25))
        if state.get("character_type") == "magus":
            new_house = post.get("house", "").strip()
            previous_house = str(state.get("house") or "")
            if new_house != previous_house:
                state["house_declined"] = []
                state["house_choice"] = ""
            if "house_choice" in post:
                posted_choice = post.get("house_choice", "").strip()
                if _choice_belongs(new_house, posted_choice):
                    state["house_choice"] = posted_choice
                elif new_house == previous_house:
                    state["house_choice"] = ""
            state["house"] = new_house
            start_age = _as_int(post.get("apprenticeship_start_age"), 10)
            state["apprenticeship_start_age"] = max(5, start_age)
        else:
            state["house"] = ""
            state["house_choice"] = ""
            state["house_declined"] = []
        sync_house_grants(state)
        if "native_language" in post:
            state["native_language"] = post.get("native_language", "").strip()
    elif step == "virtues":
        state = _apply_virtues_post(state, post)
    elif step == "characteristics":
        scores = {}
        for key in CHARACTERISTICS:
            scores[key] = max(-3, min(3, _as_int(post.get(key), 0)))
        state["characteristics"] = scores
        if "great_target" in post:
            state["great_target"] = post.get("great_target", "").strip()
        if "poor_target" in post:
            state["poor_target"] = post.get("poor_target", "").strip()
        if "aging_assign" in post:
            state["aging_assign"] = [
                key
                for raw in post.getlist("aging_assign")
                if (key := _characteristic_key(raw))
            ]
    elif step == "childhood":
        package = post.get("childhood_package", "").strip()
        previous = str(state.get("childhood_package") or "")
        state["childhood_package"] = package
        if package and package != previous:
            state["childhood"] = _package_rows(package, state.get("childhood"))
        else:
            state["childhood"] = _rows_from_post(
                post,
                "child_name",
                "child_score",
                "child_spec",
                xp_key="child_xp",
                prior=_xp_outside_phase(state, "childhood"),
                remove_key="child_remove",
            )
    elif step == "later_life":
        state["later_life"] = _rows_from_post(
            post,
            "later_name",
            "later_score",
            "later_spec",
            xp_key="later_xp",
            prior=_xp_outside_phase(state, "later_life"),
            remove_key="later_remove",
        )
    elif step == "apprenticeship":
        state["apply_minima"] = post.get("apply_minima") == "1"
        state["apprenticeship"] = _rows_from_post(
            post,
            "appr_name",
            "appr_score",
            "appr_spec",
            xp_key="appr_xp",
            prior=_xp_outside_phase(state, "apprenticeship"),
            remove_key="appr_remove",
        )
        state["arts"] = _arts_from_post(post, prefix="art_")
    elif step == "spells":
        state["spells"] = _spells_from_post(
            post, existing=state.get("spells") or [], state=state
        )
        _note_missing_spell_level(state, post, prefix="")
    elif step == "after":
        state["post_lab_seasons"] = min(4, max(0, _as_int(post.get("post_lab_seasons"), 0)))
        state["after_abilities"] = _rows_from_post(
            post,
            "after_name",
            "after_score",
            "after_spec",
            xp_key="after_xp",
            prior=_xp_outside_phase(state, "after_abilities"),
            remove_key="after_remove",
        )
        state["after_arts"] = _arts_from_post(
            post, prefix="after_art_", prior=state.get("arts") or {}
        )
        state["after_spells"] = _spells_from_post(
            post, existing=state.get("after_spells") or [], prefix="after_", state=state
        )
        _note_missing_spell_level(state, post, prefix="after_")
    elif step == "aging":
        _apply_aging_post(state, post)
    elif step == "details":
        traits = []
        names = post.getlist("trait_name")
        scores = post.getlist("trait_score")
        for name, score in zip(names, scores, strict=False):
            raw_score = "" if str(score).strip() == "" else _as_int(score, 0)
            traits.append({"trait": name.strip(), "score": raw_score})
        suggest = post.get("suggest_trait", "").strip()
        if suggest and not any(row["trait"].casefold() == suggest.casefold() for row in traits):
            traits.append({"trait": suggest, "score": 3})
        if post.get("action") == "add_trait":
            traits.append({"trait": "", "score": ""})
        else:
            traits = [row for row in traits if row["trait"] or row["score"] != ""]
        state["personality"] = traits
        if _reputation_open(state):
            state["reputation"] = post.get("reputation", "").strip()
        state["equipment"] = post.get("equipment", "").strip()
    elif step == "sheet":
        state["show_play"] = post.get("show_play") == "1"
    return state


def _rows_from_post(
    post: QueryDict,
    name_key: str,
    score_key: str,
    spec_key: str,
    *,
    xp_key: str = "",
    prior: dict[str, int] | None = None,
    remove_key: str = "",
) -> list[dict[str, Any]]:
    """Store the XP this phase adds, including points that do not finish a score."""
    paid = prior or {}
    merged: dict[str, dict[str, Any]] = {}

    def store(name: str, score: object, spec: str, toward: object) -> None:
        clean = canonical_ability_name(name)
        if not clean:
            return
        key = clean.casefold()
        wanted = max(0, _as_int(score, 0))
        extra = max(0, _as_int(toward, 0))
        target = ability_xp_for_score(wanted) + extra
        already = paid.get(key, 0)
        delta = max(0, target - already)
        specialty = spec.strip()
        if delta == 0 and already > 0:
            if specialty:
                current = merged.get(key)
                if current is None:
                    merged[key] = {"name": clean, "xp": 0, "specialty": specialty}
                elif not current["specialty"]:
                    current["specialty"] = specialty
            return
        current = merged.get(key)
        if current is None or delta >= current["xp"]:
            merged[key] = {"name": clean, "xp": delta, "specialty": specialty}
        elif specialty and not current["specialty"]:
            current["specialty"] = specialty

    names = post.getlist(name_key)
    scores = post.getlist(score_key)
    specs = post.getlist(spec_key)
    extras = post.getlist(xp_key) if xp_key else []
    for index, (name, score, spec) in enumerate(zip(names, scores, specs, strict=False)):
        toward = extras[index] if index < len(extras) else 0
        store(name, score, spec, toward)
    extra_name = post.get(f"{name_key}_new", "").strip()
    if extra_name in {"", CUSTOM_ABILITY}:
        extra_name = post.get(f"{name_key}_custom", "").strip()
    extra_score = max(0, _as_int(post.get(f"{score_key}_new"), 0))
    action = post.get("action")
    if extra_name and (extra_score or action in {"add_row", "next"}):
        store(extra_name, extra_score, post.get(f"{spec_key}_new", ""), 0)
    remove_name = canonical_ability_name(post.get(remove_key, "")) if remove_key else ""
    if remove_name:
        merged.pop(remove_name.casefold(), None)
    return list(merged.values())


def _arts_from_post(
    post: QueryDict, *, prefix: str, prior: dict[str, int] | None = None
) -> dict[str, int]:
    """Store this phase's XP, including points that do not finish the next score.

    The posted score is the sheet score. With prior XP, only the difference is stored.
    """
    arts = {}
    already = prior or {}
    for key in ART_KEYS:
        score = max(0, _as_int(post.get(f"{prefix}{key}"), 0))
        toward = max(0, _as_int(post.get(f"{prefix}xp_{key}"), 0))
        target = art_xp_for_score(score) + toward
        if prior is None:
            arts[key] = target
        else:
            arts[key] = max(0, target - _as_int(already.get(key), 0))
    return arts


def _ability_cap(age: int, applied) -> int:
    return max_ability_score(age, affinity=applied.age_cap_bonus > 0)


def _score_row(
    *,
    name: str,
    score: int,
    min_score: int,
    xp: int,
    leftover: int,
    specialty: str,
    paid_score: int,
    paid_xp: int,
    phase_xp: int,
    removable: bool,
    cap: int,
) -> dict[str, Any]:
    return {
        "name": name,
        "score": score,
        "min_score": min_score,
        "xp": xp,
        "sheet_score": score,
        "leftover": leftover,
        "specialty": specialty,
        "paid_score": paid_score,
        "paid_xp": paid_xp,
        "phase_xp": phase_xp,
        "removable": removable,
        "cap": cap,
        "over_cap": score > cap,
        "needs_specialty": False,
        "toward": leftover,
        "phase_note": f"+{phase_xp}" if phase_xp else "",
        "oob_id": slugify(name),
    }


def _package_rows(package_name: str, previous: object = None) -> list[dict[str, Any]]:
    try:
        pack = sample_childhood(package_name)
    except ValueError:
        return []
    specs: dict[str, str] = {}
    if isinstance(previous, list):
        for row in previous:
            if not isinstance(row, dict):
                continue
            name = canonical_ability_name(str(row.get("name") or ""))
            specialty = str(row.get("specialty") or "").strip()
            if name and specialty:
                specs[name.casefold()] = specialty
    return [
        {
            "name": name,
            "xp": ability_xp_for_score(score),
            "specialty": specs.get(name.casefold(), ""),
        }
        for name, score in pack.abilities
        if not name.casefold().startswith("native language")
    ]


def _aging_slots(aging: dict[str, Any]) -> list[str]:
    assigned = list(aging.get("assignments") or [])
    total = int(aging.get("any_total") or 0)
    return [assigned[index] if index < len(assigned) else "" for index in range(total)]


def _xp_before_phase(state: dict[str, Any], phase: str, applied) -> dict[str, dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    if phase != "childhood" and applied.childhood != "feral":
        native = str(state.get("native_language") or "Native Language")
        _add_ability_total(totals, native, NATIVE_LANGUAGE_XP)
    if phase != "childhood":
        for name, score in applied.free_abilities:
            _add_ability_total(totals, name, ability_xp_for_score(score))
    for key in _ABILITY_PHASES:
        if key == phase:
            break
        for row in _xp_rows(state.get(key)):
            _add_ability_total(totals, row["name"], row["xp"], row["specialty"])
    if phase == "apprenticeship" and state.get("apply_minima"):
        for name, score in RECOMMENDED_GAUNTLET_ABILITIES:
            _add_ability_total(totals, name, ability_xp_for_score(score))
    if phase == "after_abilities" and state.get("apply_minima"):
        for name, score in RECOMMENDED_GAUNTLET_ABILITIES:
            _add_ability_total(totals, name, ability_xp_for_score(score))
    return totals


def _xp_outside_phase(state: dict[str, Any], phase: str) -> dict[str, int]:
    """XP from every phase except this one, so a posted sheet score is not paid twice."""
    applied = apply_vf_effects(picks_from_state(state))
    totals = _xp_before_phase(state, phase, applied)
    passed = False
    for key in _ABILITY_PHASES:
        if not passed:
            if key == phase:
                passed = True
            continue
        for row in _xp_rows(state.get(key)):
            _add_ability_total(totals, row["name"], row["xp"], row["specialty"])
    if state.get("apply_minima") and phase in {"childhood", "later_life"}:
        for name, score in RECOMMENDED_GAUNTLET_ABILITIES:
            _add_ability_total(totals, name, ability_xp_for_score(score))
    return {key: item["xp"] for key, item in totals.items()}


def _gauntlet_package_xp(state: dict[str, Any], phase: str) -> dict[str, int]:
    """Recommended gauntlet Abilities are paid from the apprenticeship pool."""
    if phase != "apprenticeship" or not state.get("apply_minima"):
        return {}
    return {
        canonical_ability_name(name).casefold(): ability_xp_for_score(score)
        for name, score in RECOMMENDED_GAUNTLET_ABILITIES
    }


def _required_apprenticeship_names() -> dict[str, tuple[str, int]]:
    return {
        canonical_ability_name(name).casefold(): (canonical_ability_name(name), minimum)
        for name, minimum in APPRENTICESHIP_REQUIRED
    }


def _required_apprenticeship_gap_xp(state: dict[str, Any]) -> int:
    """XP still needed to put the Order-admission scores on the sheet."""
    if str(state.get("character_type") or "") != "magus":
        return 0
    have: dict[str, int] = {}
    for row in _xp_rows(state.get("apprenticeship")):
        key = row["name"].casefold()
        have[key] = have.get(key, 0) + row["xp"]
    if state.get("apply_minima"):
        for name, score in RECOMMENDED_GAUNTLET_ABILITIES:
            key = canonical_ability_name(name).casefold()
            have[key] = have.get(key, 0) + ability_xp_for_score(score)
    gap = 0
    for name, minimum in APPRENTICESHIP_REQUIRED:
        need = ability_xp_for_score(minimum)
        gap += max(0, need - have.get(name.casefold(), 0))
    return gap


def _phase_editor_rows(state: dict[str, Any], phase: str, applied) -> list[dict[str, Any]]:
    """Every phase shows the sheet score. This phase's column is only what it pays.

    The score cannot fall below XP that belongs to other phases.
    """
    before = _xp_before_phase(state, phase, applied)
    outside = _xp_outside_phase(state, phase)
    package = _gauntlet_package_xp(state, phase)
    required = (
        _required_apprenticeship_names()
        if phase == "apprenticeship" and str(state.get("character_type") or "") == "magus"
        else {}
    )
    current: dict[str, dict[str, Any]] = {}
    for row in state.get(phase) or []:
        if not isinstance(row, dict):
            continue
        name = canonical_ability_name(str(row.get("name") or ""))
        if not name:
            continue
        key = name.casefold()
        xp = max(0, _as_int(row.get("xp"), 0))
        specialty = str(row.get("specialty") or "").strip()
        found = current.get(key)
        if found is None:
            current[key] = {"name": name, "xp": xp, "specialty": specialty}
        else:
            found["xp"] += xp
            if specialty:
                found["specialty"] = specialty
    keys = list(before)
    for key in current:
        if key not in before:
            keys.append(key)
    for key in required:
        if key not in keys:
            keys.append(key)
    rows = []
    for key in keys:
        earlier = before.get(key)
        bought = current.get(key)
        required_name, required_min = required.get(key, ("", 0))
        name = (bought or earlier or {}).get("name") or required_name
        if not name:
            continue
        earlier_xp = earlier["xp"] if earlier else 0
        bought_xp = bought["xp"] if bought else 0
        package_xp = package.get(key, 0)
        if package_xp:
            earlier_xp = max(0, earlier_xp - package_xp)
        need_xp = ability_xp_for_score(required_min) if required_min else 0
        gap_xp = max(0, need_xp - bought_xp - package_xp)
        phase_xp = bought_xp + package_xp + gap_xp
        outside_xp = outside.get(key, 0)
        total = outside_xp + bought_xp + gap_xp
        score, leftover = ability_score_from_xp(total)
        before_score, _ = ability_score_from_xp(earlier_xp)
        floor, _ = ability_score_from_xp(outside_xp)
        min_score = max(floor, required_min)
        specialty = ""
        if bought and bought["specialty"]:
            specialty = bought["specialty"]
        elif earlier and earlier["specialty"]:
            specialty = earlier["specialty"]
        rows.append(
            _score_row(
                name=name,
                score=score,
                min_score=min_score,
                xp=phase_xp,
                leftover=leftover,
                specialty=specialty,
                paid_score=before_score,
                paid_xp=earlier_xp,
                phase_xp=phase_xp,
                removable=bought is not None and key not in required,
                cap=_ability_cap(_as_int(state.get("age"), 25), applied),
            )
        )
    rows.sort(key=lambda row: row["name"])
    return rows


def _pool_status(spent: int, budget: int, *, kind: str = "ability") -> dict[str, Any]:
    left = max(0, budget - spent)
    costs = ART_SCORE_COSTS if kind == "art" else ABILITY_SCORE_COSTS
    fits = [{"score": score, "xp": xp} for score, xp in costs if xp <= left]
    return {"spent": spent, "budget": budget, "left": left, "fits": fits}


def _characteristic_cost(score: int) -> int:
    try:
        return characteristic_cost(score)
    except ValueError:
        return 0


def _effective_magic_theory(abilities: list[dict[str, Any]]) -> int:
    """Magic Theory as it plays, including Puissant Ability."""
    for row in abilities:
        if _ability_key(row["name"]) == "magic theory":
            return int(row["score"]) + int(row.get("bonus") or 0)
    return 0


def learnable_spell_rows(ctx: dict[str, Any], entries) -> list[dict[str, Any]]:
    """Core spells this magus can learn from the Arts they have now."""
    arts = {row["name"].casefold(): row["score"] + row["bonus"] for row in ctx["arts"]}
    theory = _effective_magic_theory(ctx["abilities"])
    intelligence = ctx["play"].get("int", 0)
    rows = []
    for entry in entries:
        technique = entry.technique or ""
        form = entry.form or ""
        cap = spell_level_cap(
            technique=arts.get(technique.casefold(), 0),
            form=arts.get(form.casefold(), 0),
            intelligence=intelligence,
            magic_theory=theory,
        )
        if cap < 1:
            continue
        if entry.level and entry.level > cap:
            continue
        needs_level = not entry.level
        rows.append(
            {
                "name": entry.name,
                "technique": technique,
                "form": form,
                "level": entry.level,
                "needs_level": needs_level,
                "cap": cap,
                "suggested_level": None if needs_level else entry.level,
                "summary": getattr(entry, "summary", "") or "",
                "section_path": entry.section_path,
                "stable_id": entry.primary_section_stable_id,
            }
        )
    return rows


def _combination_cap(state: dict[str, Any], technique: str, form: str) -> int:
    """Level cap for one Technique and Form, not the best Arts on the sheet."""
    ctx = sheet_context(state)
    arts = {row["name"].casefold(): row["score"] + row["bonus"] for row in ctx["arts"]}
    return spell_level_cap(
        technique=arts.get(technique.casefold(), 0),
        form=arts.get(form.casefold(), 0),
        intelligence=ctx["play"].get("int", 0),
        magic_theory=_effective_magic_theory(ctx["abilities"]),
    )


def _refuse_over_cap(
    state: dict[str, Any] | None, name: str, technique: str, form: str, level: int
) -> bool:
    if state is None or level < 1:
        return False
    cap = _combination_cap(state, technique, form)
    if level <= cap:
        return False
    state["form_notice"] = (
        f"{name} ({technique} {form} {level}) is over the cap of {cap} for {technique} {form}."
    )
    return True


def _spells_from_post(
    post: QueryDict, *, existing: list, prefix: str = "", state: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    remove = post.get(f"{prefix}remove_spell", "")
    spells = [s for i, s in enumerate(existing) if str(i) != remove]
    add_id = post.get(f"{prefix}add_spell_id", "").strip()
    if add_id:
        entry = core_entries("spell").filter(primary_section_stable_id=add_id).first()
        if entry is not None:
            technique = entry.technique or "Creo"
            form = entry.form or "Ignem"
            level = entry.level or _as_int(
                post.get(f"{prefix}spell_level_{add_id}"),
                0,
            )
            if level >= 1 and not _refuse_over_cap(state, entry.name, technique, form, level):
                spells.append(
                    {
                        "name": entry.name,
                        "technique": technique,
                        "form": form,
                        "level": level,
                        "stable_id": entry.primary_section_stable_id,
                    }
                )
    name = post.get(f"{prefix}spell_name", "").strip()
    level = _as_int(post.get(f"{prefix}spell_level"), 0)
    technique = post.get(f"{prefix}spell_te", "Creo").strip() or "Creo"
    form = post.get(f"{prefix}spell_fo", "Ignem").strip() or "Ignem"
    if name and level >= 1 and not _refuse_over_cap(state, name, technique, form, level):
        spells.append(
            {
                "name": name,
                "technique": technique,
                "form": form,
                "level": level,
                "stable_id": post.get(f"{prefix}spell_stable_id", "").strip(),
            }
        )
    return spells


def _entry_slug(pick: dict[str, Any]) -> str:
    return str(pick.get("slug") or "").strip() or vf_slug(str(pick.get("name") or ""))


def _characteristic_key(raw: object) -> str:
    folded = str(raw or "").strip().casefold()
    if folded in CHARACTERISTICS:
        return folded
    for key, label in CHARACTERISTIC_LABELS.items():
        if label.casefold() == folded:
            return key
    return ""


def _apply_characteristic_adjustments(
    play: dict[str, int],
    picks: list[dict[str, Any]],
    *,
    slug: str,
    delta: int,
    fallback: str,
) -> None:
    applied = False
    for pick in picks:
        if _entry_slug(pick) != slug:
            continue
        key = _characteristic_key(pick.get("target"))
        if key:
            play[key] = play.get(key, 0) + delta
            applied = True
    if not applied:
        key = _characteristic_key(fallback)
        if key:
            play[key] = play.get(key, 0) + delta


def _already_picked(picks: list[dict[str, Any]], slug: str, target: str) -> bool:
    folded = target.casefold()
    return any(
        str(row.get("slug") or "") == slug
        and str(row.get("target") or "").casefold() == folded
        for row in picks
    )


def _choice_belongs(house_name: str, choice: str) -> bool:
    house = next((item for item in HOUSES if item.name == house_name), None)
    if house is None or not choice:
        return False
    return any(_grant_key(spec.slug, spec.target) == choice for spec in house.choices)


def _selected_house(state: dict[str, Any]):
    if state.get("character_type") != "magus":
        return None
    name = str(state.get("house") or "")
    return next((item for item in HOUSES if item.name == name), None)


def _grant_key(slug: str, target: str) -> str:
    return f"{slug}|{target.strip()}"


def _pick_key(pick: dict[str, Any]) -> str:
    return _grant_key(_entry_slug(pick), str(pick.get("target") or ""))


def _slot_for(pick: dict[str, Any], slots: tuple[str, ...]) -> str:
    kind = str(pick.get("kind") or "")
    magnitude = str(pick.get("magnitude") or "")
    category = str(pick.get("category") or "").casefold()
    hermetic = "hermetic" in category
    social = "social status" in category
    for slot in slots:
        if slot == "minor-hermetic" and kind == "virtue" and magnitude == "Minor" and hermetic:
            return slot
        if (
            slot == "major-nonhermetic"
            and kind == "virtue"
            and magnitude == "Major"
            and not hermetic
        ):
            return slot
        if slot == "major-hermetic-flaw" and kind == "flaw" and magnitude == "Major" and hermetic:
            return slot
        if (
            slot == "minor-mundane"
            and kind == "virtue"
            and magnitude == "Minor"
            and not hermetic
            and not social
        ):
            return slot
    return ""


def house_slot_offer(state: dict[str, Any], pick: dict[str, Any]) -> str:
    """Open House slot this chosen row can fill. A grant that is already marked is not offered."""
    if pick.get("house_grant"):
        return ""
    house = _selected_house(state)
    if house is None:
        return ""
    return _slot_for(pick, house.open_slots)


def _grant_house_slot(state: dict[str, Any], picks: list[dict[str, Any]], index: int) -> None:
    house = _selected_house(state)
    if house is None or not 0 <= index < len(picks):
        return
    slot = _slot_for(picks[index], house.open_slots)
    if not slot:
        return
    for other in picks:
        if other.get("house_slot") == slot:
            other["house_grant"] = False
            other.pop("house_slot", None)
    picks[index]["house_grant"] = True
    picks[index]["house_slot"] = slot


def _decline_house_pick(state: dict[str, Any], pick: dict[str, Any]) -> None:
    if not pick.get("house_grant") and pick.get("source") != "house":
        return
    declined = [str(item) for item in state.get("house_declined") or []]
    key = _pick_key(pick)
    if key not in declined:
        declined.append(key)
    state["house_declined"] = declined


def _house_pick_dict(spec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "kind": spec.kind,
        "magnitude": spec.magnitude,
        "category": spec.category,
        "slug": spec.slug,
        "stable_id": "",
        "path": "",
        "target": spec.target,
        "house_grant": True,
        "source": "house",
    }


def _matches_spec(pick: dict[str, Any], spec) -> bool:
    target = str(pick.get("target") or "").casefold()
    return _entry_slug(pick) == spec.slug and target == spec.target.casefold()


def sync_house_grants(state: dict[str, Any]) -> None:
    """Recompute free House Virtues. Switching House drops the old discount."""
    house = _selected_house(state)
    picks = [row for row in state.get("virtues_flaws") or [] if isinstance(row, dict)]
    if house is None:
        kept = [
            _without_house_grant(row) for row in picks if row.get("source") != "house"
        ]
        state["virtues_flaws"] = kept
        return
    wanted = list(house.picks)
    choice = str(state.get("house_choice") or "")
    for spec in house.choices:
        if _grant_key(spec.slug, spec.target) == choice:
            wanted.append(spec)
            break
    wanted_keys = {_grant_key(spec.slug, spec.target) for spec in wanted}
    declined = {str(item) for item in state.get("house_declined") or []}
    kept = []
    for pick in picks:
        if pick.get("source") == "house" and (
            _pick_key(pick) not in wanted_keys or _pick_key(pick) in declined
        ):
            continue
        kept.append(pick)
    for pick in kept:
        if pick.get("source") == "house":
            pick["house_grant"] = True
            continue
        slot = str(pick.get("house_slot") or "")
        if slot and slot in house.open_slots and _slot_for(pick, (slot,)):
            pick["house_grant"] = True
            continue
        matched = next((spec for spec in wanted if _matches_spec(pick, spec)), None)
        if matched is not None and _grant_key(matched.slug, matched.target) not in declined:
            pick["house_grant"] = True
            continue
        if pick.get("house_grant") or pick.get("house_slot"):
            pick["house_grant"] = False
            pick.pop("house_slot", None)
    for spec in wanted:
        key = _grant_key(spec.slug, spec.target)
        if key in declined or any(_matches_spec(pick, spec) for pick in kept):
            continue
        kept.append(_house_pick_dict(spec))
    state["virtues_flaws"] = kept


def _without_house_grant(pick: dict[str, Any]) -> dict[str, Any]:
    if not pick.get("house_grant") and not pick.get("house_slot"):
        return pick
    cleaned = dict(pick)
    cleaned["house_grant"] = False
    cleaned.pop("house_slot", None)
    return cleaned


def _house_grant_line(state: dict[str, Any]) -> str:
    parts = []
    for row in state.get("virtues_flaws") or []:
        if not isinstance(row, dict) or not row.get("house_grant"):
            continue
        parts.append(
            virtue_sheet_name(str(row.get("name") or ""), str(row.get("target") or ""))
        )
    return ", ".join(parts)


def _house_requirement_issues(state: dict[str, Any]) -> list[Issue]:
    house = _selected_house(state)
    if house is None or not house.required_slots:
        return []
    picks = [row for row in state.get("virtues_flaws") or [] if isinstance(row, dict)]
    issues = []
    for _slot in house.required_slots:
        marked = any(
            row.get("house_grant") and row.get("house_slot") == _slot for row in picks
        )
        if not marked:
            issues.append(
                Issue(
                    "error",
                    "house_flaw",
                    f"House {house.name} requires a Major Hermetic Flaw. "
                    "Mark it as the House benefit. It does not add Flaw points.",
                    PATHS["house"],
                )
            )
    return issues


def _apply_virtue_notes(picks: list[dict[str, Any]], post: QueryDict) -> None:
    """Store the detail typed on a chosen row. Indexes match the page, before removals."""
    for index, pick in enumerate(picks):
        if not isinstance(pick, dict):
            continue
        key = f"vf_note_{index}"
        if key not in post or target_prompt(_entry_slug(pick)):
            continue
        pick["target"] = post.get(key, "").strip()


def _apply_virtues_post(state: dict[str, Any], post: QueryDict) -> dict[str, Any]:
    picks = list(state.get("virtues_flaws") or [])
    _apply_virtue_notes(picks, post)
    if "house_choice" in post:
        posted_choice = post.get("house_choice", "").strip()
        house_name = str(state.get("house") or "")
        if _choice_belongs(house_name, posted_choice):
            state["house_choice"] = posted_choice
        else:
            state["house_choice"] = ""
    slot_index = post.get("house_slot", "")
    if slot_index not in (None, ""):
        _grant_house_slot(state, picks, _as_int(slot_index, -1))
    remove = post.get("remove_index")
    if remove not in (None, ""):
        idx = _as_int(remove, -1)
        if 0 <= idx < len(picks):
            _decline_house_pick(state, picks[idx])
            picks.pop(idx)
    add_slug = post.get("add_slug", "").strip()
    target = post.get("add_target", "").strip()
    if add_slug:
        row_target = post.get(f"add_target_{add_slug}", "").strip()
        if row_target:
            target = row_target
    prompt = target_prompt(add_slug) if add_slug else None
    if add_slug and prompt and not target:
        state["form_notice"] = (
            f"Choose the {prompt['label']} on that row before adding it to the sheet."
        )
    elif add_slug and not _already_picked(picks, add_slug, target):
        for suggested in _all_suggestion_vfs(state):
            if suggested.slug == add_slug:
                picks.append(_pick_dict(suggested, target=target))
                break
        else:
            entry = core_entries(post.get("add_kind", "virtue")).filter(slug=add_slug).first()
            if entry is None:
                entry = core_entries("flaw").filter(slug=add_slug).first()
            if entry is not None:
                kind = "flaw" if entry.entry_type == "flaw" else "virtue"
                picks.append(
                    {
                        "name": entry.name,
                        "kind": kind,
                        "magnitude": entry.magnitude or "Minor",
                        "category": entry.category or "",
                        "slug": entry.slug,
                        "stable_id": entry.primary_section_stable_id,
                        "path": entry.section_path,
                        "target": target,
                    }
                )
    state["virtues_flaws"] = picks
    sync_house_grants(state)
    return state


def _pick_dict(pick: VF, *, target: str = "") -> dict[str, Any]:
    return {
        "name": pick.name,
        "kind": pick.kind,
        "magnitude": pick.magnitude,
        "category": pick.category,
        "slug": pick.slug,
        "stable_id": "",
        "path": "",
        "target": target,
    }


def _apply_aging_post(state: dict[str, Any], post: QueryDict) -> None:
    age = _as_int(state.get("age"), 25)
    slots: list[int | None] = []
    for raw in post.getlist("aging_die"):
        slots.append(None if str(raw).strip() == "" else max(0, _as_int(raw, 0)))
    early: dict[str, int] = {}
    for year in range(1, 36):
        key = f"aging_early_{year}"
        if key not in post:
            continue
        raw = str(post.get(key, "")).strip()
        if raw != "":
            early[str(year)] = max(0, _as_int(raw, 0))
    roll_age = str(post.get("roll_age", "")).strip()
    if roll_age:
        year = _as_int(roll_age, 0)
        if year >= 36:
            index = year - 36
            if 0 <= index <= age - 36:
                while len(slots) <= index:
                    slots.append(None)
                slots[index] = stress_die()
        elif year > 0:
            early[str(year)] = stress_die()
    while slots and slots[-1] is None:
        slots.pop()
    if age < 36:
        slots = []
    elif len(slots) > age - 35:
        slots = slots[: age - 35]
    state["aging_dice"] = slots
    state["aging_early"] = early
    crisis = {str(key): value for key, value in (state.get("aging_crisis") or {}).items()}
    for key in post:
        if not str(key).startswith("crisis_die_"):
            continue
        year = str(key).removeprefix("crisis_die_")
        raw = str(post.get(key, "")).strip()
        if raw == "":
            crisis.pop(year, None)
        else:
            crisis[year] = max(0, _as_int(raw, 0))
    roll_crisis = str(post.get("roll_crisis", "")).strip()
    if roll_crisis:
        crisis[str(_as_int(roll_crisis, 0))] = simple_die()
    state["aging_crisis"] = crisis
    living = _year_posted(post, "aging_living_")
    ritual = _year_posted(post, "aging_longevity_", minimum=0)
    if any(str(key).startswith("aging_living_") for key in post):
        state["aging_living"] = living
        if living:
            state["living_conditions"] = int(next(reversed(living.values())))
    if any(str(key).startswith("aging_longevity_") for key in post):
        state["aging_longevity"] = ritual
        if ritual:
            state["longevity"] = int(next(reversed(ritual.values())))
    if "longevity_since" in post:
        raw = str(post.get("longevity_since", "")).strip()
        state["longevity_since"] = 0 if raw == "" else max(0, _as_int(raw, 0))
    if "aging_assign" in post:
        state["aging_assign"] = [
            key for raw in post.getlist("aging_assign") if (key := _characteristic_key(raw))
        ]


def _year_posted(post: QueryDict, prefix: str, *, minimum: int | None = None) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in post:
        name = str(key)
        if not name.startswith(prefix):
            continue
        year = name.removeprefix(prefix)
        if not year.isdigit():
            continue
        value = _as_int(post.get(key), 0)
        if minimum is not None:
            value = max(minimum, value)
        out[year] = value
    return out


def _winter_mod(stored: object, year: int, fallback: int) -> int:
    blob = stored if isinstance(stored, dict) else {}
    if str(year) in blob:
        return _as_int(blob.get(str(year)), fallback)
    if year in blob:
        return _as_int(blob.get(year), fallback)
    return fallback


def _aging_inputs(
    state: dict[str, Any], years: list[int], results: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    post35 = list(state.get("aging_dice") or [])
    early = state.get("aging_early") or {}
    living_fallback = _as_int(state.get("living_conditions"), 0)
    ritual_fallback = _as_int(state.get("longevity"), 0)
    rows = []
    for year in years:
        if year >= 36:
            index = year - 36
            raw = post35[index] if index < len(post35) else ""
            early_year = False
        else:
            raw = early.get(str(year), "")
            early_year = True
        result = results.get(year)
        living = (
            int(result["living"])
            if result and "living" in result
            else _winter_mod(state.get("aging_living"), year, living_fallback)
        )
        ritual = (
            int(result["longevity"])
            if result and "longevity" in result
            else _winter_mod(state.get("aging_longevity"), year, ritual_fallback)
        )
        rows.append(
            {
                "age": year,
                "die": "" if raw in (None, "") else str(raw),
                "early": early_year,
                "living": living,
                "longevity": ritual,
                "result": result,
            }
        )
    return rows


def _aging_die_values(inputs: list[dict[str, Any]]) -> dict[str, str]:
    values: dict[str, str] = {}
    for row in inputs:
        values[f"aging-die-{row['age']}"] = str(row["die"])
        values[f"aging-living-{row['age']}"] = str(row["living"])
        values[f"aging-longevity-{row['age']}"] = str(row["longevity"])
        result = row.get("result") or {}
        if result.get("crisis"):
            raw = result.get("crisis_die")
            values[f"crisis-die-{row['age']}"] = "" if raw is None else str(raw)
    return values


def _aging_state(state: dict[str, Any], play: dict[str, int]) -> dict[str, Any]:
    age = _as_int(state.get("age"), 25)
    since = _as_int(state.get("longevity_since"), 0)
    living_fallback = _as_int(state.get("living_conditions"), 0)
    ritual_fallback = _as_int(state.get("longevity"), 0)
    extra = []
    for blob in (state.get("aging_early"), state.get("aging_living"), state.get("aging_longevity")):
        if not isinstance(blob, dict):
            continue
        for key in blob:
            try:
                year = int(key)
            except (TypeError, ValueError):
                continue
            if 0 < year < 36:
                extra.append(year)
    years = aging_year_ages(age=age, since=since, extra=extra)
    living = {year: _winter_mod(state.get("aging_living"), year, living_fallback) for year in years}
    longevity = {
        year: _winter_mod(state.get("aging_longevity"), year, ritual_fallback) for year in years
    }
    assigned = []
    for raw in state.get("aging_assign") or []:
        key = raw if raw in CHARACTERISTICS else _characteristic_key(str(raw))
        if key:
            assigned.append(key)
    resolved = resolve_aging(
        age=age,
        post35=list(state.get("aging_dice") or []),
        early=dict(state.get("aging_early") or {}),
        crisis_dice=dict(state.get("aging_crisis") or {}),
        living=living,
        longevity=longevity,
        since=since,
        play=play,
        assignments=assigned,
    )
    resolved["filled"] = sum(1 for year in years if year in resolved["years"])
    resolved["winters"] = len(years)
    resolved["crisis_open"] = sorted(
        year
        for year, row in resolved["years"].items()
        if row["crisis"] and row["crisis_die"] is None
    )
    resolved["inputs"] = _aging_inputs(state, years, resolved["years"])
    return resolved


def neighbor_steps(state: dict[str, Any], step: str) -> tuple[str | None, str | None]:
    steps = steps_for(state)
    if step not in steps:
        step = steps[0]
    idx = steps.index(step)
    prev_step = steps[idx - 1] if idx > 0 else None
    next_step = steps[idx + 1] if idx + 1 < len(steps) else None
    return prev_step, next_step


def life_path(
    step: str, ctx: dict[str, Any], locks: dict[str, bool] | None = None
) -> list[dict[str, Any]]:
    """Core Chapter 3 sequence. The rail carries a short count; the step has the sentence."""
    state = ctx["state"]
    keys = steps_for(state)
    current = step if step in keys else keys[0]
    current_idx = keys.index(current)
    locked = locks or {}
    rows = []
    for index, key in enumerate(keys):
        summary = _path_summary(key, ctx)
        if locked.get(key):
            summary = f"{summary} · blocked"
        rows.append(
            {
                "key": key,
                "n": index + 1,
                "label": STEP_LABELS[key],
                "years": _path_years(key, ctx),
                "summary": summary,
                "current": key == current,
                "done": index < current_idx and not locked.get(key),
                "locked": bool(locked.get(key)),
            }
        )
    return rows


def step_brief(step: str, ctx: dict[str, Any]) -> str:
    """Plain instruction for the current step, with this character's numbers."""
    pools = ctx["pools"]
    kind = ctx["kind"]
    age = ctx["age"]
    start = _as_int(ctx["state"].get("apprenticeship_start_age"), 10)
    gauntlet = start + APPRENTICESHIP_YEARS
    char_budget = CHARACTERISTIC_POINTS + ctx["extra_points"]
    if step == "start":
        if kind == "magus":
            return (
                "Name the magus, set age, and pick a House. Childhood ends at 5. "
                f"Apprenticeship starts at {start} and lasts {APPRENTICESHIP_YEARS} years."
            )
        if kind == "grog":
            return (
                "Name the grog and set age. Later life is 15 XP per year after childhood "
                "(age 5). Grogs take only Minor Virtues and Flaws."
            )
        if kind == "companion":
            return (
                "Name the companion and set age. Later life is 15 XP per year after "
                "childhood (age 5), unless Wealthy or Poor changes the rate."
            )
        return (
            "Start with the character type. It decides the Virtue and Flaw budget "
            "and which years you spend experience."
        )
    if step == "virtues":
        if kind == "grog":
            return (
                "Flaws pay for Virtues. Up to 3 Minor Flaws, matching Minor Virtues. "
                "No Major, Story, or Gift."
            )
        return (
            "Flaws pay for Virtues. Up to 10 Flaw points, matching Virtue points, "
            "and at most five Minor Flaws."
        )
    if step == "characteristics":
        extra = ""
        if ctx.get("has_great") or ctx.get("has_poor"):
            extra = " Great or Poor Characteristic, if you took it, is chosen below."
        return (
            f"Spend all {char_budget} points across the eight scores (−3 to +3). "
            f"+3 costs 6 points; −3 gives 6 back.{extra}"
        )
    if step == "childhood":
        native = ctx["state"].get("native_language") or "Native Language"
        return (
            f"{native} 5 is already on the sheet. Spend the remaining "
            f"{pools.childhood_xp} XP on early-childhood Abilities, or take a package."
        )
    if step == "later_life":
        if kind == "magus":
            window = f"from age {CHILDHOOD_YEARS} until apprenticeship at {start}"
        else:
            window = f"from age {CHILDHOOD_YEARS} to {age}"
        return (
            f"Later life is {window}: {pools.later_life_years} years × "
            f"{pools.later_life_xp_per_year} XP = {pools.later_life_xp} XP. "
            "Academic, Arcane, Martial, and Supernatural Abilities need a Virtue."
        )
    if step == "apprenticeship":
        return (
            f"Fifteen years (ages {start}–{gauntlet}). Spend {pools.apprenticeship_xp} XP "
            "on Abilities and Arts. Magi need Parma Magica 1, Magic Theory 1, and Latin 1."
        )
    if step == "spells":
        return (
            f"Spend {pools.apprenticeship_spell_levels} spell levels. "
            "Each spell's cap is its Technique + its Form + Intelligence + Magic Theory + 3."
        )
    if step == "after":
        return (
            f"Years after Gauntlet (ages {gauntlet}–{age}). "
            "Spend the points below on Abilities, Arts, and spells."
        )
    if step == "aging":
        return (
            f"Each of {ctx['aging']['winters']} winters needs a stress die. "
            "Living conditions and the Longevity Ritual can change by year; "
            "both are subtracted from that winter's total."
        )
    if step == "details":
        if kind == "grog":
            return (
                "Add personality traits — as many as you want. Grogs should include Loyal. "
                "Grogs do not have Confidence."
            )
        return (
            "Add personality traits — as many as you want. Warriors should include Brave. "
            "Confidence Score 1 (3 points) is added automatically."
        )
    if step == "sheet":
        return ""
    if blocking_steps(ctx["state"], ctx):
        return "Creation rules are still open. They are listed beside the sheet."
    return "Nothing left to enter. The framed block below is the character."


def step_checklist(
    step: str, state: dict[str, Any], ctx: dict[str, Any] | None = None
) -> list[dict[str, str]]:
    """Rules this step still needs before Continue will advance."""
    ctx = sheet_context(state) if ctx is None else ctx
    issues = list(validate_step(step, state, ctx))
    if step == "virtues":
        covered: set[str] = set()
        for item in _open_suggestions(
            ctx["kind"], state, has_social_status=ctx["vf_totals"].has_social_status
        ):
            covered |= _SUGGESTION_COVERS.get(item.slug, frozenset())
        issues = [item for item in issues if item.code not in covered]
    rows = []
    for item in issues:
        row = {"message": item.message, "cite": item.cite, "rule": rule_name(item.cite)}
        extra = _CHECKLIST_FILTERS.get(item.code)
        if extra:
            row.update(extra)
        rows.append(row)
    return rows


def _path_years(key: str, ctx: dict[str, Any]) -> str:
    age = ctx["age"]
    start = _as_int(ctx["state"].get("apprenticeship_start_age"), 10)
    gauntlet = start + APPRENTICESHIP_YEARS
    if key == "childhood":
        return f"Ages 0–{min(CHILDHOOD_YEARS, age)}"
    if key == "later_life":
        end = start if ctx["kind"] == "magus" else age
        return f"Ages {CHILDHOOD_YEARS}–{end}"
    if key == "apprenticeship":
        return f"Ages {start}–{gauntlet}"
    if key == "after":
        return f"Ages {gauntlet}–{age}"
    if key == "aging":
        return f"Winters after 35, to {age}"
    return ""


def _path_summary(key: str, ctx: dict[str, Any]) -> str:
    state = ctx["state"]
    if key == "start":
        bits = [ctx["kind"].title() or "Type unset"]
        if state.get("house"):
            bits.append(str(state["house"]))
        bits.append(f"age {ctx['age']}")
        return " · ".join(bits)
    if key == "virtues":
        vf = ctx["vf_totals"]
        return f"{vf.virtue_points} vp · {vf.flaw_points} fp"
    if key == "characteristics":
        budget = CHARACTERISTIC_POINTS + ctx["extra_points"]
        spent = 0 if not ctx["char_ok"] else budget - ctx["remaining_char"]
        return f"{spent}/{budget}"
    if key == "childhood":
        pool = ctx["childhood_pool"]
        text = f"{pool['spent']}/{pool['budget']} XP"
        if state.get("childhood_package"):
            text = f"{text} · {state['childhood_package']}"
        return text
    if key == "later_life":
        pool = ctx["later_pool"]
        return f"{pool['spent']}/{pool['budget']} XP"
    if key == "apprenticeship":
        pool = ctx["appr_pool"]
        return f"{pool['spent']}/{pool['budget']} XP"
    if key == "spells":
        levels = ctx["pools"].apprenticeship_spell_levels
        return f"{ctx['spell_cost']}/{levels}"
    if key == "after":
        pool = ctx["after_pool"]
        return f"{pool['spent']}/{pool['budget']} XP"
    if key == "aging":
        aging = ctx["aging"]
        return f"{aging['filled']}/{aging['winters']}"
    if key == "details":
        named = [
            row
            for row in state.get("personality") or []
            if str(row.get("trait") or "").strip()
        ]
        n = len(named)
        return f"{n} trait{'' if n == 1 else 's'}"
    return "Character sheet"


def pool_sentence(spent: int, budget: int, unit: str) -> str:
    """One spend sentence: spent, budget, remainder, unit."""
    left = budget - spent
    if left < 0:
        return f"{spent} of {budget} {unit} spent, {-left} over."
    return f"{spent} of {budget} {unit} spent, {left} left."


def meter_for(step: str, ctx: dict[str, Any]) -> str:
    """The spend sentence shown once on the step. The rail uses a short count."""
    if step == "virtues":
        vf = ctx["vf_totals"]
        if vf.virtue_points == 0 and vf.flaw_points == 0:
            sentence = "No Virtue or Flaw points spent yet."
        else:
            if vf.remaining < 0:
                tail = f"{-vf.remaining} over"
            else:
                tail = f"{vf.remaining} left"
            sentence = (
                f"{vf.virtue_points} Virtue points spent against "
                f"{vf.flaw_points} Flaw points, {tail}."
            )
        if any(pick.granted for pick in ctx["picks"]):
            sentence += " House benefits are not counted."
        return sentence
    if step == "characteristics":
        budget = CHARACTERISTIC_POINTS + ctx["extra_points"]
        if not ctx["char_ok"]:
            return f"0 of {budget} points spent. Scores must stay between −3 and +3."
        spent = budget - ctx["remaining_char"]
        return pool_sentence(spent, budget, "points")
    if step == "childhood":
        pool = ctx["childhood_pool"]
        return pool_sentence(pool["spent"], pool["budget"], "XP")
    if step == "later_life":
        pool = ctx["later_pool"]
        return pool_sentence(pool["spent"], pool["budget"], "XP")
    if step == "apprenticeship":
        pool = ctx["appr_pool"]
        return pool_sentence(pool["spent"], pool["budget"], "XP")
    if step == "spells":
        levels = ctx["pools"].apprenticeship_spell_levels
        return pool_sentence(ctx["spell_cost"], levels, "spell levels")
    if step == "after":
        pool = ctx["after_pool"]
        return pool_sentence(pool["spent"], pool["budget"], "points")
    if step == "aging":
        aging = ctx["aging"]
        return pool_sentence(aging["filled"], aging["winters"], "winters")
    return ""


def rule_name(cite: str) -> str:
    """Short rule title for a Reader path. Never the word “rule” by itself."""
    for key, path in PATHS.items():
        if path == cite:
            return _RULE_NAMES.get(key, key.replace("_", " ").title())
    tail = cite.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").strip()
    if not tail:
        return "Rule"
    return " ".join(part.capitalize() for part in tail.split())


def living_condition_choices(
    rows: tuple[tuple[int, str], ...] = LIVING_CONDITIONS,
) -> tuple[tuple[int, str], ...]:
    """Named living-condition stages. Starred cumulative notes are not choices."""
    return tuple((value, label) for value, label in rows if not str(label).lstrip().startswith("*"))


def vf_category_options(raw: list[str]) -> list[str]:
    """Atomic lexicon buckets. Join strings are not listed as their own options."""
    seen: dict[str, str] = {}
    for item in raw:
        for part in _VF_BUCKET_SPLIT.split(str(item or "")):
            label = part.strip().strip(".")
            if not label:
                continue
            key = label.casefold()
            if key not in seen:
                seen[key] = label
    ordered = [seen.pop(name.casefold()) for name in _VF_BUCKET_ORDER if name.casefold() in seen]
    rest = sorted(seen.values(), key=str.casefold)
    return ordered + rest


def note_placeholder(name: str) -> str:
    """What the optional detail field asks for. A blank in the name, or Notes."""
    slots = [
        inner.strip()
        for inner in _NOTE_SLOT.findall(name)
        if inner.strip().casefold() in _NOTE_SLOTS
    ]
    if slots:
        return ", ".join(slot[:1].upper() + slot[1:] if slot else slot for slot in slots)
    folded = name.strip().casefold()
    for slot in ("characteristic", "ability", "technique", "form", "art"):
        if folded == slot or folded.endswith(f" {slot}") or folded.endswith(f"({slot})"):
            return slot[:1].upper() + slot[1:]
    return "Notes"


def _aging_point_line(aging: dict[str, Any]) -> str:
    bits = []
    points = aging.get("points_left") or {}
    for key in CHAR_DISPLAY:
        count = _as_int(points.get(key), 0)
        if count:
            bits.append(f"{CHARACTERISTIC_LABELS[key]} {count}")
    if not bits:
        return ""
    return "Aging points: " + ", ".join(bits)


def _sheet_number(score: int) -> str:
    if score < 0:
        return f"−{-score}"
    return str(score)


def _char_sheet_number(score: int) -> str:
    if score > 0:
        return f"+{score}"
    return _sheet_number(score)


def _identity_line(
    *,
    kind: str,
    house: str,
    age: int,
    apparent_age: int,
    size: int,
    confidence: tuple[int, int] | None,
    decrepitude: tuple[int, int] | None = None,
) -> str:
    parts = [kind.title() or "Character"]
    if house:
        parts.append(f"House {house}")
    if apparent_age != age:
        parts.append(f"Age {age} (apparent {apparent_age})")
    else:
        parts.append(f"Age {age}")
    parts.append(f"Size {_sheet_number(size)}")
    if confidence:
        parts.append(f"Conf {confidence[0]} ({confidence[1]})")
    if decrepitude is not None and (age > 35 or decrepitude[0] or decrepitude[1]):
        score, left = decrepitude
        text = f"Decrepitude {score}"
        if left:
            text += f" ({left} xp)"
        parts.append(text)
    return ", ".join(parts)


def _char_sheet_lines(play: dict[str, int], aging: dict[str, Any]) -> tuple[str, str]:
    penalties = aging["penalties"]

    def cell(key: str) -> str:
        shown = play.get(key, 0) - penalties.get(key, 0)
        return f"{_CHAR_ABBREV[key]} {_char_sheet_number(shown)}"

    mental = " ".join(cell(key) for key in CHAR_DISPLAY[:4])
    physical = " ".join(cell(key) for key in CHAR_DISPLAY[4:])
    return mental, physical


def _virtue_phrase(pick: dict[str, Any]) -> str:
    name = virtue_sheet_name(str(pick.get("name") or ""), str(pick.get("target") or ""))
    magnitude = str(pick.get("magnitude") or "").strip()
    category = str(pick.get("category") or "").strip()
    detail = " ".join(bit for bit in (magnitude, category) if bit)
    if pick.get("house_grant"):
        detail = f"{detail}, House" if detail else "House"
    if detail:
        return f"{name} ({detail})"
    return name


def _ability_phrase(row: dict[str, Any]) -> str:
    leftover = int(row.get("leftover") or 0)
    bonus = int(row.get("bonus") or 0)
    score = int(row.get("score") or 0)
    if not score and not leftover and not bonus:
        return ""
    body = f"{score}+{bonus}" if bonus else str(score)
    text = f"{row['name']} {body}"
    specialty = str(row.get("specialty") or "").strip()
    if specialty:
        text = f"{text} ({specialty})"
    if leftover:
        return f"{text} ({leftover} xp)"
    return text


def _art_token(row: dict[str, Any]) -> str:
    abbr = _ART_ABBREV[row["key"]]
    body = f"{row['score']}+{row['bonus']}" if row["bonus"] else str(row["score"])
    token = f"{abbr} {body}"
    leftover = int(row.get("leftover") or 0)
    if leftover:
        return f"{token} ({leftover} xp)"
    return token


def _art_sheet_lines(arts: list[dict[str, Any]]) -> list[str]:
    by_key = {row["key"]: row for row in arts}
    return [
        " ".join(_art_token(by_key[key]) for key in keys) for keys in _ART_SHEET_LINES
    ]


def _spell_sheet_line(spell: dict[str, Any], arts_by: dict[str, int], stamina: int) -> str:
    technique = str(spell.get("technique") or "").casefold()
    form = str(spell.get("form") or "").casefold()
    te = _ART_ABBREV.get(technique, str(spell.get("technique") or ""))
    fo = _ART_ABBREV.get(form, str(spell.get("form") or ""))
    level = _as_int(spell.get("level"), 0)
    total = arts_by.get(technique, 0) + arts_by.get(form, 0) + stamina
    sign = f"+{total}" if total >= 0 else f"−{-total}"
    return f"{spell.get('name') or 'Spell'} ({te}{fo} {level}/{sign})"


def _spell_sheet_lines(
    state: dict[str, Any], arts: list[dict[str, Any]], stamina: int
) -> list[str]:
    arts_by = {row["key"]: row["score"] + row["bonus"] for row in arts}
    lines = []
    for key in ("spells", "after_spells"):
        for spell in state.get(key) or []:
            if isinstance(spell, dict) and spell.get("name"):
                lines.append(_spell_sheet_line(spell, arts_by, stamina))
    return lines


def _personality_line(rows: object) -> str:
    if not isinstance(rows, list):
        return ""
    parts = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        trait = str(row.get("trait") or "").strip()
        if not trait:
            continue
        parts.append(f"{trait} {_sheet_number(_as_int(row.get('score'), 0))}")
    return ", ".join(parts)


def _character_sheet(
    state: dict[str, Any],
    *,
    kind: str,
    age: int,
    house: str,
    size: int,
    confidence: tuple[int, int] | None,
    play: dict[str, int],
    aging: dict[str, Any],
    abilities: list[dict[str, Any]],
    arts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compact character block. Generator notes stay outside this text."""
    penalties = aging["penalties"]
    mental, physical = _char_sheet_lines(play, aging)
    stamina = play.get("sta", 0) - penalties.get("sta", 0)
    virtues = [
        _virtue_phrase(pick)
        for pick in state.get("virtues_flaws") or []
        if isinstance(pick, dict) and str(pick.get("name") or "").strip()
    ]
    ability_line = ", ".join(phrase for row in abilities if (phrase := _ability_phrase(row)))
    return {
        "identity": _identity_line(
            kind=kind,
            house=house if kind == "magus" else "",
            age=age,
            apparent_age=age + _as_int(aging.get("apparent"), 0),
            size=size,
            confidence=confidence,
            decrepitude=(
                _as_int(aging.get("decrepitude_score"), 0),
                _as_int(aging.get("decrepitude_leftover"), 0),
            ),
        ),
        "aging_points": _aging_point_line(aging),
        "char_mental": mental,
        "char_physical": physical,
        "concept": str(state.get("concept") or "").strip(),
        "virtue_line": ", ".join(virtues),
        "ability_line": ability_line,
        "art_lines": _art_sheet_lines(arts) if kind == "magus" else [],
        "spell_lines": _spell_sheet_lines(state, arts, stamina) if kind == "magus" else [],
        "personality_line": _personality_line(state.get("personality")),
        "reputation": str(state.get("reputation") or "").strip(),
        "equipment": str(state.get("equipment") or "").strip(),
    }


def sheet_markdown(ctx: dict[str, Any]) -> str:
    """The character as Markdown. Same sections as the HTML sheet."""
    sheet = ctx["sheet"]
    name = str(ctx["state"].get("name") or "").strip() or "Unnamed character"
    blocks = [
        f"# {name}",
        "",
        sheet["identity"],
        "",
        "## Characteristics",
        sheet["char_mental"],
        sheet["char_physical"],
    ]
    if sheet.get("aging_points"):
        blocks.append(sheet["aging_points"])
    blocks.extend(["", "## Virtues and Flaws"])
    if sheet.get("concept"):
        blocks.append(sheet["concept"])
    blocks.append(sheet.get("virtue_line") or "None")
    blocks.extend(["", "## Abilities", sheet.get("ability_line") or "None"])
    if ctx.get("kind") == "magus":
        arts = list(sheet.get("art_lines") or [])
        spells = list(sheet.get("spell_lines") or [])
        blocks.extend(["", "## Arts", *arts, "", "## Spells", *(spells or ["None"])])
    blocks.extend(["", "## Personality", sheet.get("personality_line") or "None"])
    if sheet.get("reputation"):
        blocks.append(f"Reputation: {sheet['reputation']}")
    equipment = sheet.get("equipment") or "None"
    blocks.extend(["", "## Equipment", equipment])
    if ctx["state"].get("show_play"):
        blocks.extend(_play_markdown_blocks(ctx.get("play_numbers") or {}, ctx.get("kind") or ""))
    return "\n".join(blocks).rstrip() + "\n"


CHARACTER_SCHEMA = "clavis.character/1"


def _play_markdown_blocks(overlay: dict[str, Any], kind: str) -> list[str]:
    wounds = ", ".join(
        f"{row['name']} {row['low']}"
        + (f"–{row['high']}" if row.get("high") is not None else "+")
        for row in overlay.get("wounds") or []
    )
    combat = []
    for row in overlay.get("combat") or []:
        bits = [row["name"], f"Init {row['init']}"]
        if row.get("attack") is not None:
            bits.append(f"Atk {row['attack']}")
        bits.append(f"Dfn {row['defense']}")
        if row.get("damage") is not None:
            bits.append(f"Dam {row['damage']}")
        combat.append(", ".join(bits))
    blocks = [
        "",
        "## Play",
        f"Soak {overlay.get('soak', 0)}",
        f"Fatigue: {', '.join(overlay.get('fatigue') or ())}",
        f"Wounds: {wounds}",
        *combat,
    ]
    if kind != "magus" or not overlay.get("casting"):
        return blocks
    for row in overlay.get("casting_rows") or []:
        blocks.append(f"{row['label']} {row['value']} — {row['note']}")
    blocks.extend(overlay.get("casting_notes") or [])
    blocks.append("")
    blocks.extend(_casting_markdown_table(overlay["casting"]))
    return blocks


def _casting_markdown_table(casting: dict[str, Any]) -> list[str]:
    """Techniques down, forms across. Cell is formulaic, then fatigue/no fatigue."""
    forms = casting["table"]["forms"]
    header = "| | " + " | ".join(form["abbrev"] for form in forms) + " |"
    rule = "| --- | " + " | ".join("---:" for _ in forms) + " |"
    rows = [header, rule]
    for row in casting["table"]["rows"]:
        cells = [
            f"{cell['formulaic']} · {cell['fatigue_spont']}/{cell['no_fatigue']}"
            for cell in row["cells"]
        ]
        rows.append(f"| {row['abbrev']} | " + " | ".join(cells) + " |")
    return rows


def sheet_json(ctx: dict[str, Any]) -> dict[str, Any]:
    """Structured character for other tools. Always includes play numbers."""
    state = ctx["state"]
    aging = ctx.get("aging") or {}
    penalties = aging.get("penalties") or {}
    characteristics = {}
    for key in CHARACTERISTICS:
        characteristics[key] = {
            "score": int(ctx["play"].get(key, 0)) - int(penalties.get(key, 0)),
            "aging": int((aging.get("points_left") or {}).get(key, 0) or 0),
        }
    abilities = [
        {
            "name": row["name"],
            "score": row["score"],
            "bonus": row["bonus"],
            "specialty": row.get("specialty") or "",
            "xp": row["xp"],
            "leftover": row["leftover"],
        }
        for row in ctx.get("abilities") or []
    ]
    arts = [
        {
            "name": row["name"],
            "key": row["key"],
            "score": row["score"],
            "bonus": row["bonus"],
            "xp": row["xp"],
            "leftover": row["leftover"],
        }
        for row in ctx.get("arts") or []
    ]
    spells = []
    arts_by = {row["key"]: row["score"] + row["bonus"] for row in ctx.get("arts") or []}
    stamina = characteristics.get("sta", {}).get("score", 0)
    for key in ("spells", "after_spells"):
        for spell in state.get(key) or []:
            if not isinstance(spell, dict) or not spell.get("name"):
                continue
            te = str(spell.get("technique") or "").casefold()
            fo = str(spell.get("form") or "").casefold()
            spells.append(
                {
                    "name": spell.get("name"),
                    "technique": spell.get("technique") or "",
                    "form": spell.get("form") or "",
                    "level": _as_int(spell.get("level"), 0),
                    "casting_total": arts_by.get(te, 0) + arts_by.get(fo, 0) + stamina,
                    "catalog_stable_id": str(spell.get("catalog_stable_id") or ""),
                }
            )
    virtues = []
    for pick in state.get("virtues_flaws") or []:
        if not isinstance(pick, dict) or not str(pick.get("name") or "").strip():
            continue
        virtues.append(
            {
                "name": pick.get("name") or "",
                "slug": pick.get("slug") or vf_slug(str(pick.get("name") or "")),
                "kind": pick.get("kind") or "",
                "magnitude": pick.get("magnitude") or "",
                "category": pick.get("category") or "",
                "target": pick.get("target") or "",
                "house_grant": bool(pick.get("house_grant")),
            }
        )
    confidence = ctx.get("confidence")
    return {
        "schema": CHARACTER_SCHEMA,
        "name": str(state.get("name") or "").strip() or "Unnamed character",
        "character_type": str(state.get("character_type") or ""),
        "house": str(state.get("house") or ""),
        "age": ctx.get("age") or 0,
        "size": ctx.get("size") or 0,
        "concept": str(state.get("concept") or "").strip(),
        "identity": ctx["sheet"]["identity"],
        "confidence": {"score": confidence[0], "points": confidence[1]} if confidence else None,
        "decrepitude": {
            "score": _as_int(aging.get("decrepitude_score"), 0),
            "leftover": _as_int(aging.get("decrepitude_leftover"), 0),
        },
        "characteristics": characteristics,
        "virtues_flaws": virtues,
        "abilities": abilities,
        "arts": arts if ctx.get("kind") == "magus" else [],
        "spells": spells if ctx.get("kind") == "magus" else [],
        "personality": [
            {"trait": row.get("trait"), "score": row.get("score")}
            for row in (state.get("personality") or [])
            if isinstance(row, dict) and str(row.get("trait") or "").strip()
        ],
        "reputation": str(state.get("reputation") or "").strip(),
        "equipment": str(state.get("equipment") or "").strip(),
        "play": ctx.get("play_numbers") or {},
        "worksheet": overlay_payload(state),
    }


def overlay_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Worksheet state stored on a Workspace character, minus notices."""
    return {key: value for key, value in state.items() if key != "form_notice"}


def write_overlay(state: dict[str, Any], *, campaign_id: int | None = None) -> Character:
    """Create or update the Workspace row for this worksheet."""
    payload = overlay_payload(state)
    fields = {
        "name": str(state.get("name") or "").strip() or "Unnamed character",
        "character_type": str(state.get("character_type") or ""),
        "house": str(state.get("house") or ""),
        "age": _as_int(state.get("age"), 0),
        "state": payload,
        "campaign": Campaign.objects.filter(pk=campaign_id).first() if campaign_id else None,
    }
    pk = _as_int(state.get("saved_id"), 0)
    if pk:
        character = Character.objects.filter(pk=pk).first()
        if character is not None:
            for key, value in fields.items():
                setattr(character, key, value)
            character.save()
            return character
    return Character.objects.create(**fields)


def virtue_sheet_name(name: str, target: str) -> str:
    """Sheet name. One filled blank replaces (Subject); anything else is appended."""
    detail = target.strip()
    if not detail:
        return name
    slots = [
        match
        for match in _NOTE_SLOT.finditer(name)
        if match.group(1).strip().casefold() in _NOTE_SLOTS
    ]
    if len(slots) == 1:
        match = slots[0]
        return f"{name[: match.start()]}({detail}){name[match.end() :]}"
    return f"{name} ({detail})"


def target_prompt(slug: str) -> dict[str, Any] | None:
    """Select or text field for a Virtue or Flaw that must name a target."""
    spec = target_spec(slug)
    if spec is None:
        return None
    kind, restrict = spec
    options: list[str] = []
    if kind == "characteristic":
        options = [CHARACTERISTIC_LABELS[key] for key in CHAR_DISPLAY]
    elif kind == "art":
        options = [*HERMETIC_TECHNIQUES, *HERMETIC_FORMS]
    elif kind == "form":
        options = list(HERMETIC_FORMS)
    elif kind == "technique":
        options = list(HERMETIC_TECHNIQUES)
    elif kind == "realm":
        options = [item.title() for item in (restrict or ("divine", "faerie", "infernal", "magic"))]
    elif restrict:
        options = [item.replace("-", " ").title() for item in restrict]
    return {"label": TARGET_LABELS.get(kind, "Target"), "options": options}


def blocking_steps(state: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, str]]:
    """Open rules, in life-path order, with a step to jump to."""
    found = []
    for key in steps_for(state):
        if key == "sheet":
            continue
        for issue in validate_step(key, state, ctx):
            found.append(
                {
                    "step": key,
                    "step_label": STEP_LABELS[key],
                    "message": issue.message,
                    "cite": issue.cite,
                    "rule": rule_name(issue.cite),
                }
            )
    return found


def _char_rows(
    bought: dict[str, int], play: dict[str, int], aging: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = []
    for key in CHAR_DISPLAY:
        score = bought[key]
        played = play.get(key, score)
        cost = _characteristic_cost(score)
        phrase = ""
        if cost > 0:
            phrase = f"costs {cost}"
        elif cost < 0:
            phrase = f"returns {-cost}"
        if score != played:
            phrase = f"{phrase} · plays as {played}".strip(" ·")
        rows.append(
            {
                "key": key,
                "label": CHARACTERISTIC_LABELS[key],
                "abbrev": _CHAR_ABBREV[key],
                "bought": score,
                "play": played,
                "cost": cost,
                "phrase": phrase,
                "aging": aging["penalties"].get(key, 0),
            }
        )
    return rows




def _reputation_open(state: dict[str, Any]) -> bool:
    for row in state.get("virtues_flaws") or []:
        if not isinstance(row, dict):
            continue
        blob = f"{row.get('name', '')} {row.get('category', '')}".casefold()
        if "reputation" in blob:
            return True
    return False


def _type_notes(state: dict[str, Any], kind: str, arts: list[dict[str, Any]]) -> list[str]:
    notes = []
    previous = str(state.get("type_switch_from") or "")
    if previous and previous != kind:
        notes.append(
            f"Changed from {previous} to {kind}. "
            "Virtues, Abilities, and Arts already entered stay on the sheet."
        )
    stored = [row["name"] for row in arts if row["spent"] or row["after"] or row["bonus"]]
    if stored and kind != "magus":
        notes.append(f"Arts stay stored and are not part of a {kind}: {', '.join(stored)}.")
    elif stored and previous and previous != "magus" and kind == "magus":
        notes.append(f"Arts already stored are on the sheet again: {', '.join(stored)}.")
    if kind != "magus":
        mismatched = []
        for row in state.get("virtues_flaws") or []:
            if not isinstance(row, dict):
                continue
            slug = _entry_slug(row)
            category = str(row.get("category") or "")
            if slug in {"the-gift", "hermetic-magus"} or "hermetic" in category.casefold():
                mismatched.append(str(row.get("name") or slug))
        if mismatched:
            notes.append(f"These do not fit a {kind}: {', '.join(mismatched)}.")
    return notes


def _after_math(state: dict[str, Any], pools) -> str:
    years = pools.post_gauntlet_years
    lab = min(4, max(0, _as_int(state.get("post_lab_seasons"), 0)))
    gross = years * POST_GAUNTLET_POINTS
    per_year = post_gauntlet_year_points(lab)
    total = years * per_year
    withheld = lab * POST_GAUNTLET_LAB_SEASON_COST
    return (
        f"{years} years × {POST_GAUNTLET_POINTS} = {gross} points. "
        f"{lab} laboratory season(s) withhold {withheld} points per year, "
        f"leaving {per_year} per year, {total} in all."
    )


def _missing_target_issues(state: dict[str, Any]) -> list[Issue]:
    issues = []
    for row in state.get("virtues_flaws") or []:
        if not isinstance(row, dict):
            continue
        prompt = target_prompt(_entry_slug(row))
        if prompt and not str(row.get("target") or "").strip():
            name = str(row.get("name") or "This Virtue or Flaw")
            issues.append(
                Issue(
                    "error",
                    "need_target",
                    f"{name} needs a {prompt['label']} before it counts.",
                    str(row.get("path") or PATHS["virtues_flaws"]),
                )
            )
    return issues


def _note_missing_spell_level(state: dict[str, Any], post: QueryDict, *, prefix: str) -> None:
    add_id = post.get(f"{prefix}add_spell_id", "").strip()
    if add_id:
        entry = core_entries("spell").filter(primary_section_stable_id=add_id).first()
        if entry is not None and not entry.level:
            level = _as_int(post.get(f"{prefix}spell_level_{add_id}"), 0)
            if level < 1:
                state["form_notice"] = (
                    f"{entry.name} needs a level. "
                    "The cap for that Technique and Form is on the row."
                )
                return
    name = post.get(f"{prefix}spell_name", "").strip()
    if name and _as_int(post.get(f"{prefix}spell_level"), 0) < 1:
        state["form_notice"] = f"{name} needs a level before it goes on the sheet."
