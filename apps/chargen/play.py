"""In-play totals derived from a finished sheet. Core formulas, no book prose."""

from __future__ import annotations

from typing import Any

from apps.chargen.core_tables import HERMETIC_FORMS, HERMETIC_TECHNIQUES
from apps.chargen.vf_effects import vf_slug

FATIGUE_LEVELS = ("OK", "0", "−1", "−3", "−5", "Unconscious")
WOUND_LABELS = ("Light", "Medium", "Heavy", "Incapacitated", "Dead")
WOUND_PENALTIES = (-1, -3, -5, None, None)

# Casting Score modifiers. Voice: Loud +1, Firm 0, Soft −5, None −10.
# Gestures: Exaggerated +1, Bold 0, Subtle −2, None −5.
VOICE = (("loud", 1), ("firm", 0), ("soft", -5), ("none", -10))
GESTURE = (("exaggerated", 1), ("bold", 0), ("subtle", -2), ("none", -5))

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


def ability_total(abilities: list[dict[str, Any]], name: str) -> int:
    """Score plus Puissant bonus, or 0 if the Ability is absent."""
    key = name.casefold()
    for row in abilities:
        if str(row.get("name") or "").casefold() == key:
            return int(row.get("score") or 0) + int(row.get("bonus") or 0)
    return 0


def art_total(arts: list[dict[str, Any]], name: str) -> int:
    key = name.casefold()
    for row in arts:
        if str(row.get("key") or "") == key or str(row.get("name") or "").casefold() == key:
            return int(row.get("score") or 0) + int(row.get("bonus") or 0)
    return 0


def wound_levels(size: int) -> list[dict[str, Any]]:
    """Wound brackets. Each level is 5 + Size points of damage, at least 1."""
    width = max(1, 5 + size)
    rows = []
    start = 1
    for index, (label, penalty) in enumerate(zip(WOUND_LABELS, WOUND_PENALTIES, strict=True)):
        last = index == len(WOUND_LABELS) - 1
        high = None if last else start + width - 1
        rows.append(
            {
                "name": label,
                "penalty": penalty,
                "low": start,
                "high": high,
            }
        )
        if high is not None:
            start = high + 1
    return rows


def _vf_rows(rows: object) -> list[dict[str, Any]]:
    return [row for row in (rows or []) if isinstance(row, dict)]


def _has_slug(rows: list[dict[str, Any]], slug: str) -> bool:
    for row in rows:
        got = str(row.get("slug") or "") or vf_slug(str(row.get("name") or ""))
        if got == slug:
            return True
    return False


def _major_slug(rows: list[dict[str, Any]], slug: str) -> bool:
    for row in rows:
        got = str(row.get("slug") or "") or vf_slug(str(row.get("name") or ""))
        if got == slug and str(row.get("magnitude") or "").casefold() == "major":
            return True
    return False


def voice_penalties(virtues_flaws: list[dict[str, Any]]) -> dict[str, int]:
    """Resolved voice modifiers, including Quiet Magic."""
    quiet = _has_slug(virtues_flaws, "quiet-magic")
    major = _major_slug(virtues_flaws, "quiet-magic")
    out = dict(VOICE)
    if quiet:
        out["soft"] = 0
        out["none"] = 0 if major else -5
    return out


def gesture_penalties(virtues_flaws: list[dict[str, Any]]) -> dict[str, int]:
    """Resolved gesture modifiers, including Subtle Magic."""
    subtle = _has_slug(virtues_flaws, "subtle-magic")
    major = _major_slug(virtues_flaws, "subtle-magic")
    out = dict(GESTURE)
    if subtle:
        out["subtle"] = 0
        out["none"] = 0 if major else -5
    return out


def casting_parts(total: int) -> dict[str, int]:
    """Formulaic, fatigue spont (no die), and no-fatigue spont from a Casting Score."""
    return {
        "formulaic": total,
        "fatigue_spont": total // 2,
        "no_fatigue": total // 5,
    }


def _mod(value: int) -> str:
    if value < 0:
        return f"−{abs(value)}"
    if value > 0:
        return f"+{value}"
    return "0"


def casting_notes(voice: dict[str, int], gesture: dict[str, int]) -> list[str]:
    """Short key under the casting grid. Penalties apply before dividing."""
    return [
        (
            "Casting Score = Te+Fo+Sta. "
            f"Voice soft {_mod(voice['soft'])}, none {_mod(voice['none'])}. "
            f"Gestures subtle {_mod(gesture['subtle'])}, none {_mod(gesture['none'])}."
        ),
        "Spont: fatigue /2, no fatigue /5",
    ]


def play_overlay(
    *,
    kind: str,
    characteristics: dict[str, int],
    size: int,
    abilities: list[dict[str, Any]],
    arts: list[dict[str, Any]],
    virtues_flaws: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Soak, wounds, unarmed combat, and magus casting/lab totals."""
    vf = _vf_rows(virtues_flaws)
    sta = int(characteristics.get("sta") or 0)
    qik = int(characteristics.get("qik") or 0)
    dex = int(characteristics.get("dex") or 0)
    strength = int(characteristics.get("str") or 0)
    intelligence = int(characteristics.get("int") or 0)
    perception = int(characteristics.get("per") or 0)
    brawl = ability_total(abilities, "Brawl")
    finesse = ability_total(abilities, "Finesse")
    concentration = ability_total(abilities, "Concentration")
    awareness = ability_total(abilities, "Awareness")
    theory = ability_total(abilities, "Magic Theory")
    parma = ability_total(abilities, "Parma Magica")
    artes = ability_total(abilities, "Artes Liberales")
    philos = ability_total(abilities, "Philosophiae")
    wounds = wound_levels(size)
    overlay: dict[str, Any] = {
        "soak": sta,
        "encumbrance": 0,
        "fatigue": list(FATIGUE_LEVELS),
        "wounds": wounds,
        "combat": [
            {
                "name": "Dodge",
                "init": qik,
                "attack": None,
                "defense": qik + brawl,
                "damage": None,
            },
            {
                "name": "Brawl (fist)",
                "init": qik,
                "attack": dex + brawl,
                "defense": qik + brawl,
                "damage": strength,
            },
        ],
        "weapons": [],
        "armor": [],
    }
    if kind != "magus":
        overlay["casting"] = None
        overlay["lab"] = None
        overlay["modifiers"] = None
        overlay["casting_rows"] = []
        overlay["casting_notes"] = []
        return overlay
    voice = voice_penalties(vf)
    gesture = gesture_penalties(vf)
    grid = []
    for technique in HERMETIC_TECHNIQUES:
        te = art_total(arts, technique)
        te_ab = _ART_ABBREV[technique.casefold()]
        for form in HERMETIC_FORMS:
            fo = art_total(arts, form)
            fo_ab = _ART_ABBREV[form.casefold()]
            score = te + fo + sta
            parts = casting_parts(score)
            grid.append(
                {
                    "technique": technique,
                    "form": form,
                    "abbrev": f"{te_ab}{fo_ab}",
                    **parts,
                }
            )
    table_rows = []
    for technique in HERMETIC_TECHNIQUES:
        table_rows.append(
            {
                "technique": technique,
                "abbrev": _ART_ABBREV[technique.casefold()],
                "cells": [cell for cell in grid if cell["technique"] == technique],
            }
        )
    overlay["casting"] = {
        "stamina": sta,
        "grid": grid,
        "table": {
            "forms": [
                {"name": name, "abbrev": _ART_ABBREV[name.casefold()]}
                for name in HERMETIC_FORMS
            ],
            "rows": table_rows,
        },
        "voice": voice,
        "gestures": gesture,
    }
    overlay["lab"] = {
        "intelligence": intelligence,
        "magic_theory": theory,
        "base": intelligence + theory,
        "note": "Int + Magic Theory + Te + Fo + Aura.",
    }
    overlay["modifiers"] = {
        "fast_cast": qik + finesse,
        "concentration": sta + concentration,
        "magic_resistance": parma * 5,
        "ceremonial": artes + philos,
        "targeting": perception + finesse,
        "determining_effect": perception + awareness,
    }
    overlay["casting_rows"] = [
        {
            "label": "Laboratory",
            "value": intelligence + theory,
            "note": "Int + Magic Theory + Te + Fo + Aura.",
        },
        {
            "label": "Fast Cast",
            "value": qik + finesse,
            "note": "Qik + Finesse.",
        },
        {
            "label": "Concentration",
            "value": sta + concentration,
            "note": "Sta + Concentration.",
        },
        {
            "label": "Magic Resistance",
            "value": parma * 5,
            "note": "Parma Magica × 5 + Fo.",
        },
        {
            "label": "Ceremonial",
            "value": artes + philos,
            "note": "Artes Liberales + Philosophiae.",
        },
        {
            "label": "Targeting",
            "value": perception + finesse,
            "note": "Per + Finesse.",
        },
    ]
    overlay["casting_notes"] = casting_notes(voice, gesture)
    return overlay
