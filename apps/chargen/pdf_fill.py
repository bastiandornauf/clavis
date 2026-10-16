"""Fill a user-supplied Ars Magica AcroForm from a ClavisGen worksheet.

The player uploads their own PDF. Clavis never fetches a URL and does not
vendor Atlas blanks. Templates are identified by AcroForm field names.
"""

from __future__ import annotations

import io
import re
from typing import Any

from django.utils.text import slugify
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError, PdfStreamError
from pypdf.generic import NameObject, TextStringObject

from apps.chargen.core_tables import CHARACTERISTICS
from apps.chargen.worksheet import virtue_sheet_name

MAX_PDF_BYTES = 10 * 1024 * 1024
MINUS = "\u2212"

TEMPLATE_ARMD = "armd_fillable"
TEMPLATE_GERMANITAS = "germanitas"
TEMPLATE_UNKNOWN = "unknown"
TEMPLATE_EMPTY = "no_fields"

# Distinctive names shared by ArMD B&W FILLABLE and COLOR FILLABLE.
ARMD_MARKERS = frozenset({"Creo", "ABILITY 1", "ABILITY 30", "Virtues 1", "SPELL"})

MSG_NO_FILE = "Choose the fillable PDF you own, then Fill and download."
MSG_EMPTY = "That file is empty. Upload the Ars Magica fillable sheet you own."
MSG_TOO_LARGE = "That PDF is larger than 10 MB."
MSG_NOT_PDF = "That file is not a PDF. Upload a fillable character sheet."
MSG_BAD_PDF = "Clavis could not read that PDF."
MSG_ENCRYPTED = "That PDF is encrypted. Unlock it, then upload it again."
MSG_NO_FIELDS = (
    "This file has no fillable fields. Classic Atlas print sheets cannot be "
    "filled. Upload the Ars Magica Definitive Edition B&W or COLOR FILLABLE "
    "sheet you already own."
)
MSG_GERMANITAS = (
    "This looks like the Germanitas fillable sheet (numbered Text fields). "
    "Clavis cannot map those fields yet. Upload the Ars Magica Definitive "
    "Edition B&W or COLOR FILLABLE sheet instead."
)
MSG_UNKNOWN = (
    "Clavis does not recognize this form. Upload the Ars Magica Definitive "
    "Edition B&W or COLOR FILLABLE sheet you own. Clavis will not write into "
    "an unknown layout."
)

_TEXT_FIELD = re.compile(r"^Text\d+[a-z]?$")
_CHAR_KEYS = ("int", "per", "str", "sta", "pre", "com", "dex", "qik")
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

# Page-3 art SCORE boxes on the ArMD fillable sheet (this file's names).
_ARMD_ART_SCORES = {
    "creo": "SCORE 1_2",
    "intellego": "SCORE 2_2",
    "muto": "SCORE 3_2",
    "perdo": "SCORE 4_2",
    "rego": "Base Casting Totals",
    "animal": "SCORE 1_3",
    "aquam": "SCORE 2_3",
    "auram": "SCORE 3_3",
    "corpus": "SCORE 4_3",
    "herbam": "Lab",
    "ignem": "SCORE 1_4",
    "imaginem": "SCORE 2_4",
    "mentem": "SCORE 3_4",
    "terram": "SCORE 4_4",
    "vim": "SCORE 5_2",
}


class PdfFillError(Exception):
    """English notice for the sheet step. Safe to show as-is."""


def sheet_number(score: int) -> str:
    if score < 0:
        return f"{MINUS}{-score}"
    return str(score)


def characteristic_posted(score: int) -> str:
    if score > 0:
        return f"+{score}"
    return sheet_number(score)


def ability_score_posted(row: dict[str, Any]) -> str:
    bonus = int(row.get("bonus") or 0)
    score = int(row.get("score") or 0)
    if bonus:
        return f"{score}+{bonus}"
    return str(score)


def art_score_posted(row: dict[str, Any]) -> str:
    bonus = int(row.get("bonus") or 0)
    score = int(row.get("score") or 0)
    if bonus:
        return f"{score}+{bonus}"
    return str(score)


def virtue_posted(pick: dict[str, Any]) -> str:
    name = virtue_sheet_name(str(pick.get("name") or ""), str(pick.get("target") or ""))
    magnitude = str(pick.get("magnitude") or "").strip()
    category = str(pick.get("category") or "").strip()
    detail = " ".join(bit for bit in (magnitude, category) if bit)
    if pick.get("house_grant"):
        detail = f"{detail}, House" if detail else "House"
    if detail:
        return f"{name} ({detail})"
    return name


def field_names(pdf_bytes: bytes) -> list[str]:
    reader = _reader(pdf_bytes)
    fields = reader.get_fields() or {}
    return sorted(str(name) for name in fields)


def identify_template(names: list[str] | set[str]) -> str:
    have = {str(name) for name in names}
    if not have:
        return TEMPLATE_EMPTY
    if ARMD_MARKERS <= have:
        return TEMPLATE_ARMD
    text_fields = [name for name in have if _TEXT_FIELD.match(name)]
    if len(text_fields) >= 40 and "ABILITY 1" not in have and "Creo" not in have:
        return TEMPLATE_GERMANITAS
    return TEMPLATE_UNKNOWN


def filled_filename(ctx: dict[str, Any]) -> str:
    name = str((ctx.get("state") or {}).get("name") or "").strip()
    slug = slugify(name) or "character"
    return f"{slug}-filled.pdf"


def read_uploaded_pdf(upload: Any) -> bytes:
    """Read a multipart file. Never follows a URL."""
    if upload is None:
        raise PdfFillError(MSG_NO_FILE)
    size = int(getattr(upload, "size", 0) or 0)
    if size <= 0:
        raise PdfFillError(MSG_EMPTY)
    if size > MAX_PDF_BYTES:
        raise PdfFillError(MSG_TOO_LARGE)
    raw = upload.read()
    if not raw:
        raise PdfFillError(MSG_EMPTY)
    if not raw.startswith(b"%PDF"):
        raise PdfFillError(MSG_NOT_PDF)
    ctype = (getattr(upload, "content_type", None) or "").split(";", 1)[0]
    ctype = ctype.strip().casefold()
    allowed = {
        "",
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
        "binary/octet-stream",
    }
    if ctype not in allowed:
        raise PdfFillError(MSG_NOT_PDF)
    return raw


def fill_character_pdf(pdf_bytes: bytes, ctx: dict[str, Any]) -> bytes:
    """Return a filled copy. Raises PdfFillError for unknown or empty forms."""
    names = set(field_names(pdf_bytes))
    kind = identify_template(names)
    if kind == TEMPLATE_EMPTY:
        raise PdfFillError(MSG_NO_FIELDS)
    if kind == TEMPLATE_GERMANITAS:
        raise PdfFillError(MSG_GERMANITAS)
    if kind != TEMPLATE_ARMD:
        raise PdfFillError(MSG_UNKNOWN)
    values = values_for_armd(ctx, names)
    return _write_filled(pdf_bytes, values, ctx)


def values_for_armd(ctx: dict[str, Any], names: set[str]) -> dict[str, str]:
    """Map worksheet values onto ArMD fillable field names that exist."""
    out: dict[str, str] = {}
    state = ctx.get("state") or {}
    aging = ctx.get("aging") or {}
    penalties = aging.get("penalties") or {}
    play = ctx.get("play") or {}
    overlay = ctx.get("play_numbers") or {}
    chars = {
        key: int(play.get(key, 0)) - int(penalties.get(key, 0)) for key in CHARACTERISTICS
    }

    def put(field: str, value: object) -> None:
        if field not in names or value is None:
            return
        text = value if isinstance(value, str) else str(value)
        if text == "":
            return
        out[field] = text

    name = str(state.get("name") or "").strip()
    put("Text140", name)
    put("Name", name)
    put("Character", name)
    put("Text6", str(state.get("house") or "").strip())
    put("House", str(state.get("house") or "").strip())
    put("Text10", str(state.get("house") or "").strip())
    put("Text7", str(ctx.get("age") or 0))
    put("Age", str(ctx.get("age") or 0))
    put("Text8", sheet_number(int(ctx.get("size") or 0)))
    # Named Size on this sheet is the familiar block. Only fill an alias.
    if "Text8" not in names:
        put("Size", sheet_number(int(ctx.get("size") or 0)))
    confidence = ctx.get("confidence")
    if confidence:
        put("Text9", f"{confidence[0]} ({confidence[1]})")
        put("Confidence", f"{confidence[0]} ({confidence[1]})")
    kind = str(ctx.get("kind") or "").strip()
    put("TitleProfession", kind.title() if kind else "")
    decrepitude = (
        f"{int(aging.get('decrepitude_score') or 0)}"
        if not int(aging.get("decrepitude_leftover") or 0)
        else (
            f"{int(aging.get('decrepitude_score') or 0)} "
            f"({int(aging.get('decrepitude_leftover') or 0)} xp)"
        )
    )
    put("Decrepitude", decrepitude)
    aging_line = str((ctx.get("sheet") or {}).get("aging_points") or "").strip()
    put("Effects of Aging 1", aging_line)

    if "Intelligence Score" in names:
        put("Intelligence Score", characteristic_posted(chars.get("int", 0)))
    else:
        for key, field in (
            ("int", "Int"),
            ("per", "Per"),
            ("str", "Str"),
            ("sta", "Sta"),
            ("pre", "Pre"),
            ("com", "Com"),
            ("dex", "Dex"),
            ("qik", "Qik"),
        ):
            put(field, characteristic_posted(chars.get(key, 0)))

    virtues, flaws = _split_virtues(state.get("virtues_flaws") or [])
    for index, pick in enumerate(virtues, start=1):
        put(f"Virtues {index}", virtue_posted(pick))
    for index, pick in enumerate(flaws, start=1):
        put(f"Flaws {index}", virtue_posted(pick))

    abilities = [
        row
        for row in (ctx.get("abilities") or [])
        if int(row.get("score") or 0)
        or int(row.get("leftover") or 0)
        or int(row.get("bonus") or 0)
    ]
    for index, row in enumerate(abilities[:30], start=1):
        put(f"ABILITY {index}", row["name"])
        leftover = int(row.get("leftover") or 0)
        if leftover:
            put("Exp" if index == 1 else f"Exp {index}", leftover)

    if ctx.get("kind") == "magus":
        for row in ctx.get("arts") or []:
            key = str(row.get("key") or "")
            put(row["name"], int(row.get("xp") or 0))
            put(_ARMD_ART_SCORES.get(key, ""), art_score_posted(row))
            put(row["name"] + " Score", art_score_posted(row))
        _put_spells(out, names, ctx)

    traits = [
        row
        for row in (state.get("personality") or [])
        if isinstance(row, dict) and str(row.get("trait") or "").strip()
    ]
    for index, row in enumerate(traits[:8], start=1):
        put(f"Personality Traits {index}", str(row.get("trait") or "").strip())
        put(f"SCORE {index}", sheet_number(int(row.get("score") or 0)))
    reputation = str(state.get("reputation") or "").strip()
    put("Reputations 1", reputation)
    put("Reputation", reputation)
    equipment = str(state.get("equipment") or "").strip()
    lines = [line.strip() for line in equipment.splitlines() if line.strip()]
    equipment_fields = ("1_4", "2_4", "3_2", "4_2", "5_2", "6_2", "7_2", "8_2")
    if lines and any(field in names for field in equipment_fields):
        for field, line in zip(equipment_fields, lines, strict=False):
            put(field, line)
        if len(lines) == 1:
            put("1_4", lines[0])
    else:
        put("Equipment", equipment)
        put("Possessions", equipment)

    soak = overlay.get("soak")
    if soak is not None and "Text8" in names:
        # Combat soak on this B&W sheet is an unnamed box; COLOR may use Soak.
        if "Intelligence Score" not in names:
            put("Soak", soak)
    elif soak is not None and "Intelligence Score" not in names:
        put("Soak", soak)
    wounds = overlay.get("wounds") or []
    wound_fields = ("Text23", "Text24", "Text25", "Text26", "Text27")
    for field, row in zip(wound_fields, wounds, strict=False):
        put(field, _wound_range(row))
    for index, row in enumerate(overlay.get("combat") or [], start=1):
        put(f"Weapons {index}", _combat_line(row))
    lab = overlay.get("lab") or {}
    if lab.get("base") is not None:
        put("Lab Total", lab.get("base"))
    return out


def _split_virtues(rows: object) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    virtues: list[dict[str, Any]] = []
    flaws: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return virtues, flaws
    for pick in rows:
        if not isinstance(pick, dict) or not str(pick.get("name") or "").strip():
            continue
        kind = str(pick.get("kind") or "").casefold()
        if kind == "flaw":
            flaws.append(pick)
        else:
            virtues.append(pick)
    return virtues, flaws


def _put_spells(out: dict[str, str], names: set[str], ctx: dict[str, Any]) -> None:
    state = ctx.get("state") or {}
    arts_by = {
        row["key"]: int(row.get("score") or 0) + int(row.get("bonus") or 0)
        for row in (ctx.get("arts") or [])
    }
    aging = ctx.get("aging") or {}
    penalties = aging.get("penalties") or {}
    stamina = int((ctx.get("play") or {}).get("sta", 0)) - int(penalties.get("sta", 0))
    spells: list[dict[str, Any]] = []
    for key in ("spells", "after_spells"):
        for spell in state.get(key) or []:
            if isinstance(spell, dict) and spell.get("name"):
                spells.append(spell)
    posted = list((ctx.get("sheet") or {}).get("spell_lines") or [])
    split = "Form" in names or "Technique" in names or "Level" in names
    for index, spell in enumerate(spells[:12], start=1):
        field = "SPELL" if index == 1 else f"SPELL_{index}"
        suffix = "" if index == 1 else f"_{index}"
        if split:
            if field in names:
                out[field] = str(spell.get("name") or "")
            te = str(spell.get("technique") or "")
            fo = str(spell.get("form") or "")
            if f"Technique{suffix}" in names:
                out[f"Technique{suffix}"] = _ART_ABBREV.get(te.casefold(), te)
            if f"Form{suffix}" in names:
                out[f"Form{suffix}"] = _ART_ABBREV.get(fo.casefold(), fo)
            level = int(spell.get("level") or 0)
            if f"Level{suffix}" in names:
                out[f"Level{suffix}"] = str(level)
            total = arts_by.get(te.casefold(), 0) + arts_by.get(fo.casefold(), 0) + stamina
            bonus = f"+{total}" if total >= 0 else sheet_number(total)
            if f"Bonus{suffix}" in names:
                out[f"Bonus{suffix}"] = bonus
        elif field in names:
            out[field] = posted[index - 1] if index <= len(posted) else str(spell.get("name"))


def _wound_range(row: dict[str, Any]) -> str:
    low = row.get("low")
    high = row.get("high")
    if high is None:
        return f"{low}+"
    return f"{low}{MINUS}{high}"


def _combat_line(row: dict[str, Any]) -> str:
    bits = [str(row.get("name") or "")]
    if row.get("init") is not None:
        bits.append(f"Init {row['init']}")
    if row.get("attack") is not None:
        bits.append(f"Atk {row['attack']}")
    if row.get("defense") is not None:
        bits.append(f"Dfn {row['defense']}")
    if row.get("damage") is not None:
        bits.append(f"Dam {row['damage']}")
    return ", ".join(bit for bit in bits if bit)


def _reader(pdf_bytes: bytes) -> PdfReader:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except (PdfReadError, PdfStreamError, ValueError) as exc:
        raise PdfFillError(MSG_BAD_PDF) from exc
    if reader.is_encrypted:
        raise PdfFillError(MSG_ENCRYPTED)
    return reader


def _write_filled(pdf_bytes: bytes, values: dict[str, str], ctx: dict[str, Any]) -> bytes:
    reader = _reader(pdf_bytes)
    writer = PdfWriter()
    writer.append(reader)
    if values:
        writer.update_page_form_field_values(
            None,
            values,
            auto_regenerate=False,
        )
    writer.set_need_appearances_writer(True)
    _fill_page1_characteristics(writer, ctx)
    _fill_page1_ability_columns(writer, ctx)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _fill_page1_characteristics(writer: PdfWriter, ctx: dict[str, Any]) -> None:
    """ArMD page 1 score column uses colliding undefined_* names. Set by position."""
    if not writer.pages:
        return
    aging = ctx.get("aging") or {}
    penalties = aging.get("penalties") or {}
    play = ctx.get("play") or {}
    scores = [
        characteristic_posted(int(play.get(key, 0)) - int(penalties.get(key, 0)))
        for key in _CHAR_KEYS
    ]
    boxes = []
    for annot in writer.pages[0].get("/Annots") or []:
        widget = annot.get_object()
        if widget.get("/Subtype") != "/Widget":
            continue
        rect = [float(x) for x in (widget.get("/Rect") or [])]
        if len(rect) < 4:
            continue
        x0, y0, x1, _y1 = rect
        if 268 <= x0 <= 280 and 298 <= x1 <= 310 and 340 <= y0 <= 450:
            boxes.append((y0, widget))
    boxes.sort(key=lambda item: -item[0])
    for (_y, widget), value in zip(boxes[:8], scores, strict=False):
        _set_value(widget, value)


def _fill_page1_ability_columns(writer: PdfWriter, ctx: dict[str, Any]) -> None:
    """Specialty and score sit in undefined_* boxes next to ABILITY 1–30."""
    if not writer.pages:
        return
    abilities = [
        row
        for row in (ctx.get("abilities") or [])
        if int(row.get("score") or 0)
        or int(row.get("leftover") or 0)
        or int(row.get("bonus") or 0)
    ]
    rows: dict[int, dict[str, Any]] = {}
    extras: list[tuple[float, Any]] = []
    for annot in writer.pages[0].get("/Annots") or []:
        widget = annot.get_object()
        if widget.get("/Subtype") != "/Widget":
            continue
        name = str(widget.get("/T") or "")
        rect = [float(x) for x in (widget.get("/Rect") or [])]
        if len(rect) < 4:
            continue
        x0, y0 = rect[0], rect[1]
        match = re.fullmatch(r"ABILITY (\d+)", name)
        if match:
            rows[int(match.group(1))] = {"y": y0, "specialty": None, "score": None, "exp": None}
            continue
        extras.append((y0, widget))
    for row in rows.values():
        y = row["y"]
        for y0, widget in extras:
            if abs(y0 - y) > 3:
                continue
            x0 = float(widget.get("/Rect")[0])
            if 410 <= x0 <= 420:
                row["specialty"] = widget
            elif 490 <= x0 <= 500:
                row["score"] = widget
            elif 308 <= x0 <= 318:
                row["exp"] = widget
    for index, ability in enumerate(abilities[:30], start=1):
        slots = rows.get(index)
        if not slots:
            continue
        specialty = str(ability.get("specialty") or "").strip()
        leftover = int(ability.get("leftover") or 0)
        if slots["specialty"] is not None and specialty:
            _set_value(slots["specialty"], specialty)
        if slots["score"] is not None:
            _set_value(slots["score"], ability_score_posted(ability))
        if slots["exp"] is not None and leftover:
            _set_value(slots["exp"], str(leftover))


def _set_value(widget: Any, value: str) -> None:
    widget.update({NameObject("/V"): TextStringObject(value)})
    parent = widget.get("/Parent")
    if parent is not None:
        parent.get_object().update({NameObject("/V"): TextStringObject(value)})
