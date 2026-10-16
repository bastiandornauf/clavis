"""Pure Core character-creation arithmetic. No database, no templates."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil

from apps.chargen.core_tables import (
    AGING_AGE,
    APPRENTICESHIP_REQUIRED,
    APPRENTICESHIP_SPELL_LEVELS,
    APPRENTICESHIP_UNLOCKS,
    APPRENTICESHIP_XP,
    APPRENTICESHIP_YEARS,
    ART_ALIASES,
    CHARACTERISTIC_COST,
    CHARACTERISTIC_LABELS,
    CHARACTERISTIC_POINTS,
    CHARACTERISTICS,
    CHILD_AGE_MODIFIERS,
    CHILDHOOD_ABILITIES,
    CHILDHOOD_XP,
    CHILDHOOD_YEARS,
    CONFIDENCE_POINTS,
    CONFIDENCE_SCORE,
    DEFAULT_SIZE,
    FERAL_CHILDHOOD_ABILITIES,
    FERAL_CHILDHOOD_XP,
    FORM_ABBREV,
    FRESH_PARMA_CAP,
    GATED_ABILITY_CATEGORIES,
    HERMETIC_FORMS,
    HERMETIC_TECHNIQUES,
    LATER_LIFE_XP,
    MAX_MAJOR_PERSONALITY_FLAWS,
    MAX_MINOR_FLAWS_CENTRAL,
    MAX_PERSONALITY_FLAWS_GUIDELINE,
    MAX_STORY_FLAWS_GUIDELINE,
    NATIVE_LANGUAGE_XP,
    PATHS,
    POOR_XP,
    POST_GAUNTLET_LAB_SEASON_COST,
    POST_GAUNTLET_POINTS,
    PRIVILEGED_UPBRINGING_XP,
    READING_ARTES_LIBERALES,
    READING_LATIN,
    RECOMMENDED_GAUNTLET_ABILITIES,
    SAMPLE_CHILDHOODS,
    TECHNIQUE_ABBREV,
    TYPE_BUDGETS,
    VF_POINTS,
    WEAK_MAGIC_THEORY,
    WEALTHY_XP,
    ChildhoodPackage,
)
from apps.chargen.types import Issue, VirtueFlaw

GIFT_NAMES = frozenset({"the gift", "gift"})
WEALTHY_NAMES = frozenset({"wealthy"})
POOR_NAMES = frozenset({"poor"})
PRIVILEGED_NAMES = frozenset({"privileged upbringing"})
HERMETIC_MAGUS_NAMES = frozenset({"hermetic magus"})


@dataclass(frozen=True)
class VirtueFlawTotals:
    virtue_points: int
    flaw_points: int
    remaining: int
    minor_flaws: int
    has_gift: bool
    has_hermetic_magus: bool
    has_social_status: bool
    wealthy: bool
    poor: bool
    privileged_upbringing: bool
    issues: tuple[Issue, ...]

    @property
    def legal(self) -> bool:
        return not any(issue.blocks for issue in self.issues)


@dataclass(frozen=True)
class ExperiencePools:
    childhood_years: int
    native_language_xp: int
    childhood_xp: int
    later_life_years: int
    later_life_xp_per_year: int
    later_life_xp: int
    extra_xp: int
    apprenticeship_xp: int
    apprenticeship_spell_levels: int
    post_gauntlet_years: int
    post_gauntlet_points: int
    aging_years: int
    issues: tuple[Issue, ...]

    @property
    def aging_warning(self) -> bool:
        return self.aging_years > 0


def vf_points(magnitude: str) -> int:
    try:
        return VF_POINTS[magnitude.title()]
    except KeyError as exc:
        raise ValueError(f"Unknown Virtue/Flaw magnitude: {magnitude!r}") from exc


def characteristic_cost(score: int) -> int:
    try:
        return CHARACTERISTIC_COST[score]
    except KeyError as exc:
        raise ValueError(f"Characteristic score {score} is outside +3…−3 at creation") from exc


def characteristics_spent(scores: dict[str, int]) -> int:
    unknown = [key for key in scores if key.casefold() not in CHARACTERISTICS]
    if unknown:
        raise ValueError(f"Unknown characteristic(s): {', '.join(unknown)}")
    return sum(characteristic_cost(int(scores.get(key, 0))) for key in CHARACTERISTICS)


def characteristics_remaining(scores: dict[str, int], *, extra_points: int = 0) -> int:
    return CHARACTERISTIC_POINTS + extra_points - characteristics_spent(scores)


def ability_xp_for_score(score: int) -> int:
    if score < 0:
        raise ValueError("Ability score cannot be negative")
    return 5 * score * (score + 1) // 2


def art_xp_for_score(score: int) -> int:
    if score < 0:
        raise ValueError("Art score cannot be negative")
    return score * (score + 1) // 2


def _score_from_xp(xp: int, cost_for: Callable[[int], int]) -> tuple[int, int]:
    if xp < 0:
        raise ValueError("Experience points cannot be negative")
    score = 0
    while cost_for(score + 1) <= xp:
        score += 1
    return score, xp - cost_for(score)


def ability_score_from_xp(xp: int) -> tuple[int, int]:
    """Return (score, leftover XP) for an Ability."""
    return _score_from_xp(xp, ability_xp_for_score)


def art_score_from_xp(xp: int) -> tuple[int, int]:
    """Return (score, leftover XP) for a Hermetic Art."""
    return _score_from_xp(xp, art_xp_for_score)


def max_ability_score(age: int, *, affinity: bool = False) -> int:
    if age < 30:
        cap = 5
    elif age <= 35:
        cap = 6
    elif age <= 40:
        cap = 7
    elif age <= 45:
        cap = 8
    else:
        cap = 9
    return cap + (2 if affinity else 0)


def spell_level_cap(*, technique: int, form: int, intelligence: int, magic_theory: int) -> int:
    return technique + form + intelligence + magic_theory + 3


def can_know_spell(
    level: int, *, technique: int, form: int, intelligence: int, magic_theory: int
) -> bool:
    return level <= spell_level_cap(
        technique=technique, form=form, intelligence=intelligence, magic_theory=magic_theory
    )


def childhood_ability_allowed(name: str, *, feral: bool = False) -> bool:
    folded = name.casefold()
    allowed = FERAL_CHILDHOOD_ABILITIES if feral else CHILDHOOD_ABILITIES
    if not feral and (folded.startswith("native language") or folded.endswith("lore")):
        return "Area Lore".casefold() in folded or folded.startswith("area lore")
    for item in allowed:
        if folded == item.casefold() or folded.startswith(item.casefold() + " "):
            return True
    return False


def _category_has(pick: VirtueFlaw, word: str) -> bool:
    return word.casefold() in pick.category.casefold()


def _named(pick: VirtueFlaw, names: frozenset[str]) -> bool:
    return pick.name.strip().casefold() in names


def check_virtues_and_flaws(character_type: str, picks: list[VirtueFlaw]) -> VirtueFlawTotals:
    budget = TYPE_BUDGETS.get(character_type)
    if budget is None:
        raise ValueError(f"Unknown character type: {character_type!r}")

    virtue_points = 0
    flaw_points = 0
    minor_flaws = 0
    has_gift = False
    has_hermetic_magus = False
    has_social_status = False
    wealthy = False
    poor = False
    privileged = False
    issues: list[Issue] = []

    for pick in picks:
        if pick.kind not in {"virtue", "flaw"}:
            raise ValueError(f"Pick {pick.name!r} must be virtue or flaw")
        points = 0 if pick.granted else vf_points(pick.magnitude)
        if pick.kind == "virtue":
            virtue_points += points
        else:
            flaw_points += points
            if pick.magnitude.title() == "Minor" and not pick.granted:
                minor_flaws += 1

        if _named(pick, GIFT_NAMES):
            has_gift = True
        if _named(pick, HERMETIC_MAGUS_NAMES):
            has_hermetic_magus = True
        if _named(pick, WEALTHY_NAMES):
            wealthy = True
        if _named(pick, POOR_NAMES):
            poor = True
        if _named(pick, PRIVILEGED_NAMES):
            privileged = True
        if _category_has(pick, "Social Status"):
            has_social_status = True

        if pick.magnitude.title() == "Major" and not budget.allow_major:
            issues.append(
                Issue(
                    "error",
                    "major_on_grog",
                    f"{pick.name} is Major. Grogs may only take Minor Virtues and Flaws.",
                    PATHS["grog"],
                )
            )
        if pick.kind == "flaw" and _category_has(pick, "Story") and not budget.allow_story:
            issues.append(
                Issue(
                    "error",
                    "story_on_grog",
                    f"{pick.name} is a Story Flaw. Grogs may not take Story Flaws.",
                    PATHS["grog"],
                )
            )

    hermetic_picks = [
        pick for pick in picks if _category_has(pick, "Hermetic") and not _named(pick, GIFT_NAMES)
    ]
    if hermetic_picks and not has_gift:
        issues.append(
            Issue(
                "error",
                "hermetic_without_gift",
                "Hermetic Virtues and Flaws need The Gift.",
                PATHS["the_gift"],
            )
        )
    if has_gift and not budget.allow_gift:
        issues.append(Issue("error", "gift_on_grog", "Grogs cannot have The Gift.", PATHS["grog"]))
    if has_gift and character_type == "companion":
        issues.append(
            Issue(
                "note",
                "gifted_companion",
                "A Gifted companion is legal. Core treats this as playing through apprenticeship.",
                PATHS["companion"],
            )
        )
    if character_type == "magus" and not has_gift:
        issues.append(
            Issue("error", "magus_needs_gift", "All magi must have The Gift.", PATHS["the_gift"])
        )
    if character_type == "magus" and not has_hermetic_magus:
        issues.append(
            Issue(
                "error",
                "magus_needs_status",
                "All magi must take the free Social Status Hermetic Magus.",
                PATHS["hermetic_magus"],
            )
        )
    if has_hermetic_magus and character_type != "magus":
        issues.append(
            Issue(
                "error",
                "hermetic_magus_only",
                "Only magi may take the Social Status Hermetic Magus.",
                PATHS["hermetic_magus"],
            )
        )
    if wealthy and poor:
        issues.append(
            Issue(
                "error",
                "wealthy_and_poor",
                "Wealthy and Poor cannot both apply.",
                PATHS["later_life"],
            )
        )
    if (wealthy or poor) and not budget.allow_wealthy_poor:
        issues.append(
            Issue(
                "error",
                "wealthy_poor_companions",
                "Wealthy and Poor are for companions, not magi or grogs.",
                PATHS["later_life"],
            )
        )
    if not has_social_status and not has_hermetic_magus:
        issues.append(
            Issue(
                "error",
                "need_social_status",
                "Every character must take a Social Status.",
                PATHS["virtues_flaws"],
            )
        )
    hermetic_flaws = [
        pick
        for pick in picks
        if pick.kind == "flaw" and _category_has(pick, "Hermetic")
    ]
    if character_type == "magus" and not hermetic_flaws:
        issues.append(
            Issue(
                "error",
                "magus_needs_hermetic_flaw",
                "All magi should have at least one Hermetic Flaw. "
                "Nobody fits perfectly into Hermetic theory.",
                PATHS["virtues_flaws"],
            )
        )

    personality_flaws = [
        pick
        for pick in picks
        if pick.kind == "flaw" and _category_has(pick, "Personality")
    ]
    major_personality = [
        pick for pick in personality_flaws if pick.magnitude.title() == "Major"
    ]
    if len(major_personality) > MAX_MAJOR_PERSONALITY_FLAWS:
        issues.append(
            Issue(
                "error",
                "two_major_personality",
                "A character may not have more than one Major Personality Flaw.",
                PATHS["vf_guidelines"],
            )
        )
    if len(personality_flaws) > MAX_PERSONALITY_FLAWS_GUIDELINE:
        issues.append(
            Issue(
                "note",
                "many_personality_flaws",
                "More than two Personality Flaws risks turning the character into a caricature.",
                PATHS["vf_guidelines"],
            )
        )
    story_flaws = [
        pick for pick in picks if pick.kind == "flaw" and _category_has(pick, "Story")
    ]
    if len(story_flaws) > MAX_STORY_FLAWS_GUIDELINE:
        issues.append(
            Issue(
                "note",
                "two_story_flaws",
                "A character should not have more than one Story Flaw.",
                PATHS["vf_guidelines"],
            )
        )

    if character_type != "grog" and minor_flaws > MAX_MINOR_FLAWS_CENTRAL:
        issues.append(
            Issue(
                "error",
                "too_many_minor_flaws",
                f"{minor_flaws} Minor Flaws; companions and magi may have at most "
                f"{MAX_MINOR_FLAWS_CENTRAL}.",
                PATHS["virtues_flaws"],
            )
        )
    if flaw_points > budget.max_flaw_points:
        issues.append(
            Issue(
                "error",
                "flaw_overspend",
                f"{flaw_points} Flaw points; this type may take up to {budget.max_flaw_points}.",
                budget.cite,
            )
        )
    if virtue_points > flaw_points:
        issues.append(
            Issue(
                "error",
                "virtue_overspend",
                f"{virtue_points} Virtue points bought with only {flaw_points} Flaw points.",
                PATHS["summary"],
            )
        )

    return VirtueFlawTotals(
        virtue_points=virtue_points,
        flaw_points=flaw_points,
        remaining=flaw_points - virtue_points,
        minor_flaws=minor_flaws,
        has_gift=has_gift,
        has_hermetic_magus=has_hermetic_magus,
        has_social_status=has_social_status or has_hermetic_magus,
        wealthy=wealthy,
        poor=poor,
        privileged_upbringing=privileged,
        issues=tuple(issues),
    )


def later_life_xp_rate(*, wealthy: bool = False, poor: bool = False) -> int:
    if wealthy and poor:
        raise ValueError("Wealthy and Poor cannot both apply")
    if wealthy:
        return WEALTHY_XP
    if poor:
        return POOR_XP
    return LATER_LIFE_XP


def simple_die(rng: random.Random | None = None) -> int:
    """A simple die. 10 counts as 10. It does not explode and it does not botch."""
    return (rng or random).randint(1, 10)


def add_aging_point(score: int, points: int) -> tuple[int, int]:
    """Add one Aging Point. The score falls by 1 only when points exceed its absolute value.

    Those points are then removed. A Communication of +2 falls on the third point.
    A Stamina of −3 falls on the fourth.
    """
    points += 1
    if points > abs(score):
        return score - 1, 0
    return score, points


def xp_to_next_ability_score(xp: int) -> int:
    """Experience still needed to reach the next Ability score, including from zero."""
    score, _leftover = ability_score_from_xp(xp)
    return ability_xp_for_score(score + 1) - xp


def crisis_label(total: int) -> str:
    """Short Crisis result. A Longevity Ritual replaces this with survival."""
    if total <= 8:
        return "Bedridden for a week"
    if total <= 14:
        return "Bedridden for a month"
    if total == 15:
        return "Minor illness (Stamina 3+ or CrCo 20)"
    if total == 16:
        return "Serious illness (Stamina 6+ or CrCo 25)"
    if total == 17:
        return "Major illness (Stamina 9+ or CrCo 30)"
    if total == 18:
        return "Critical illness (Stamina 12+ or CrCo 35)"
    return "Terminal illness (CrCo 40)"


def aging_year_ages(*, age: int, longevity: int = 0, since: int = 0) -> list[int]:
    """Winters that need a roll. A Longevity Ritual can include years before 36."""
    years = list(range(36, age + 1))
    if longevity > 0 and 0 < since < 36:
        years = list(range(since, min(age, 35) + 1)) + years
    return years


def _die_at(year: int, post35: list, early: dict) -> int | None:
    if year >= 36:
        index = year - 36
        if index >= len(post35):
            return None
        raw = post35[index]
    else:
        raw = early.get(str(year), early.get(year))
    if raw in (None, ""):
        return None
    return int(raw)


def _crisis_die_at(year: int, crisis_dice: dict) -> int | None:
    raw = crisis_dice.get(str(year), crisis_dice.get(year))
    if raw in (None, ""):
        return None
    return int(raw)


def resolve_aging(
    *,
    age: int,
    post35: list,
    early: dict,
    crisis_dice: dict,
    living: int,
    longevity: int,
    since: int,
    play: dict[str, int],
    assignments: list[str],
) -> dict:
    """Apply aging points in year order. A characteristic falls only past its absolute value."""
    scores = {key: int(play.get(key, 0)) for key in CHARACTERISTICS}
    stored = {key: 0 for key in CHARACTERISTICS}
    drops = {key: 0 for key in CHARACTERISTICS}
    queue = [key for key in assignments if key in scores]
    used: list[str] = []
    any_unassigned = 0
    any_total = 0
    decrepitude_xp = 0
    apparent = 0
    crises = 0
    ritual_active = longevity > 0
    ritual_spent_age: int | None = None
    years: dict[int, dict] = {}

    def claim() -> str:
        if not queue:
            return ""
        key = queue.pop(0)
        used.append(key)
        return key

    def land(key: str, notes: list[str]) -> None:
        before = scores[key]
        score, points = add_aging_point(before, stored[key])
        scores[key] = score
        stored[key] = points
        label = CHARACTERISTIC_LABELS[key]
        if score == before:
            notes.append(f"1 {label} aging point")
            return
        drops[key] += 1
        notes.append(f"{label} falls by 1")

    def gain(key: str, count: int, notes: list[str]) -> None:
        nonlocal decrepitude_xp, any_unassigned, any_total
        if key != "any":
            for _ in range(count):
                decrepitude_xp += 1
                land(key, notes)
            return
        pending = 0
        for _ in range(count):
            decrepitude_xp += 1
            any_total += 1
            chosen = claim()
            if not chosen:
                any_unassigned += 1
                pending += 1
                continue
            land(chosen, notes)
        if pending == 1:
            notes.append("1 aging point, any Characteristic")
        elif pending:
            notes.append(f"{pending} aging points, any Characteristic")

    for year in aging_year_ages(age=age, longevity=longevity, since=since):
        die = _die_at(year, post35, early)
        if die is None:
            continue
        bonus = longevity if ritual_active else 0
        die_used = die
        capped = ritual_active and year <= 35 and die >= 10
        if capped:
            die_used = 9
        total = aging_total(
            die=die_used, age=year, living_conditions=living, longevity=bonus
        )
        outcome = aging_outcome(total)
        notes: list[str] = []
        for key, amount in outcome.points:
            gain(key, amount, notes)
        apparent += outcome.apparent_age_increase
        crisis_die = None
        crisis_total = None
        crisis_text = ""
        spent = False
        if outcome.crisis:
            crises += 1
            gain("any", xp_to_next_ability_score(decrepitude_xp), notes)
            new_score, _left = ability_score_from_xp(decrepitude_xp)
            rolled = _crisis_die_at(year, crisis_dice)
            if rolled is None:
                crisis_text = "Crisis die not rolled"
            else:
                crisis_die = rolled
                crisis_total = rolled + ceil(year / 10) + new_score
                if ritual_active:
                    crisis_text = "Survived. The Longevity Ritual is spent."
                    ritual_active = False
                    ritual_spent_age = year
                    spent = True
                else:
                    crisis_text = crisis_label(crisis_total)
        years[year] = {
            "age": year,
            "die": die,
            "die_used": die_used,
            "total": total,
            "apparent": outcome.apparent_age_increase,
            "capped": capped,
            "crisis": outcome.crisis,
            "notes": notes,
            "crisis_die": crisis_die,
            "crisis_total": crisis_total,
            "crisis_label": crisis_text,
            "ritual_spent": spent,
            "botch": False,
        }

    dec_score, dec_left = ability_score_from_xp(decrepitude_xp)
    return {
        "penalties": drops,
        "points_left": stored,
        "any_points": any_unassigned,
        "any_total": any_total,
        "assignments": used,
        "apparent": apparent,
        "crises": crises,
        "decrepitude_xp": decrepitude_xp,
        "decrepitude_score": dec_score,
        "decrepitude_leftover": dec_left,
        "ritual_spent_age": ritual_spent_age,
        "years": years,
    }


def aging_years_required(age: int) -> int:
    """Winters after 35 that must be resolved before play."""
    return max(0, age - AGING_AGE)


def experience_pools(
    *,
    character_type: str,
    age: int,
    apprenticeship_start_age: int | None = None,
    wealthy: bool = False,
    poor: bool = False,
    privileged_upbringing: bool = False,
    extra_xp: int | None = None,
    apprenticeship_xp_delta: int = 0,
    apprenticeship_spell_delta: int = 0,
    feral_childhood: bool = False,
    later_life_xp_per_year: int | None = None,
) -> ExperiencePools:
    if character_type not in TYPE_BUDGETS:
        raise ValueError(f"Unknown character type: {character_type!r}")
    if age < 0:
        raise ValueError("Age cannot be negative")

    issues: list[Issue] = []
    childhood_years = min(CHILDHOOD_YEARS, age)
    if extra_xp is None:
        extra_xp = PRIVILEGED_UPBRINGING_XP if privileged_upbringing else 0

    apprenticeship_xp = 0
    apprenticeship_spells = 0
    post_years = 0
    if character_type == "magus":
        start = (
            apprenticeship_start_age
            if apprenticeship_start_age is not None
            else max(CHILDHOOD_YEARS, age - APPRENTICESHIP_YEARS)
        )
        if start < CHILDHOOD_YEARS:
            start = CHILDHOOD_YEARS
        later_years = max(0, start - CHILDHOOD_YEARS)
        gauntlet_age = start + APPRENTICESHIP_YEARS
        if age >= gauntlet_age:
            apprenticeship_xp = APPRENTICESHIP_XP + apprenticeship_xp_delta
            apprenticeship_spells = APPRENTICESHIP_SPELL_LEVELS + apprenticeship_spell_delta
            post_years = age - gauntlet_age
        else:
            issues.append(
                Issue(
                    "note",
                    "still_apprentice",
                    "This magus has not finished the fifteen years of apprenticeship.",
                    PATHS["apprenticeship"],
                )
            )
            later_years = max(0, min(later_years, age - CHILDHOOD_YEARS))
    else:
        later_years = max(0, age - CHILDHOOD_YEARS)

    rate = (
        later_life_xp_per_year
        if later_life_xp_per_year is not None
        else later_life_xp_rate(wealthy=wealthy, poor=poor)
    )
    later_xp = later_years * rate
    aging_years = aging_years_required(age)
    if aging_years:
        issues.append(
            Issue(
                "error",
                "aging",
                f"Age {age}: resolve {aging_years} aging roll(s) before play "
                f"(Winter after {AGING_AGE}).",
                PATHS["aging"],
            )
        )

    if feral_childhood and age >= CHILDHOOD_YEARS:
        native_xp = 0
        childhood_xp = FERAL_CHILDHOOD_XP
    else:
        native_xp = NATIVE_LANGUAGE_XP if age >= CHILDHOOD_YEARS else 0
        childhood_xp = CHILDHOOD_XP if age >= CHILDHOOD_YEARS else 0

    return ExperiencePools(
        childhood_years=childhood_years,
        native_language_xp=native_xp,
        childhood_xp=childhood_xp,
        later_life_years=later_years,
        later_life_xp_per_year=rate,
        later_life_xp=later_xp,
        extra_xp=extra_xp,
        apprenticeship_xp=apprenticeship_xp,
        apprenticeship_spell_levels=apprenticeship_spells,
        post_gauntlet_years=post_years,
        post_gauntlet_points=post_years * POST_GAUNTLET_POINTS,
        aging_years=aging_years,
        issues=tuple(issues),
    )


def childhood_package_xp(package: ChildhoodPackage) -> int:
    return sum(ability_xp_for_score(score) for _name, score in package.abilities)


def sample_childhood(name: str) -> ChildhoodPackage:
    folded = name.strip().casefold()
    for package in SAMPLE_CHILDHOODS:
        if package.name.casefold() == folded:
            return package
    raise ValueError(f"Unknown sample childhood: {name!r}")


def ability_learnable(
    *,
    category: str,
    phase: str,
    name: str = "",
    granted_categories: frozenset[str] = frozenset(),
    granted_abilities: frozenset[str] = frozenset(),
) -> bool:
    """Whether this Ability may receive XP in this life-path phase.

    Childhood uses the Early Childhood whitelist. Later life needs a Virtue
    (or Flaw) that grants Academic, Arcane, Martial, or Supernatural access.
    Apprenticeship unlocks Academic, Arcane, and Martial for magi; Supernatural
    still needs the relevant Virtue.
    """
    if name and name.casefold() in {item.casefold() for item in granted_abilities}:
        return True
    if phase == "childhood":
        return childhood_ability_allowed(name)
    cat = category.strip().casefold()
    if not cat or cat == "general":
        return True
    granted = {item.casefold() for item in granted_categories}
    if phase == "apprenticeship" and cat in APPRENTICESHIP_UNLOCKS:
        return True
    if cat in GATED_ABILITY_CATEGORIES:
        return cat in granted
    return True


def starting_confidence(character_type: str) -> tuple[int, int] | None:
    """Return (score, points), or None for grogs who have no Confidence."""
    if character_type not in TYPE_BUDGETS:
        raise ValueError(f"Unknown character type: {character_type!r}")
    if character_type == "grog":
        return None
    return (CONFIDENCE_SCORE, CONFIDENCE_POINTS)


def check_apprenticeship_minima(scores: dict[str, int]) -> tuple[Issue, ...]:
    """Order-admission errors and reading/laboratory notes for a gauntleted magus."""
    folded = {key.strip().casefold(): int(value) for key, value in scores.items()}
    issues: list[Issue] = []
    for name, minimum in APPRENTICESHIP_REQUIRED:
        if folded.get(name.casefold(), 0) < minimum:
            issues.append(
                Issue(
                    "error",
                    "apprenticeship_minimum",
                    f"Magi must have {name} {minimum} to be admitted to the Order.",
                    PATHS["apprenticeship"],
                )
            )
    latin = folded.get("latin", 0)
    artes = folded.get("artes liberales", 0)
    theory = folded.get("magic theory", 0)
    parma = folded.get("parma magica", 0)
    if latin < READING_LATIN or artes < READING_ARTES_LIBERALES:
        issues.append(
            Issue(
                "note",
                "cannot_read_order_books",
                "Latin 4 and Artes Liberales 1 are needed to read the books of the Order.",
                PATHS["minima"],
            )
        )
    if theory < WEAK_MAGIC_THEORY:
        issues.append(
            Issue(
                "note",
                "weak_magic_theory",
                "Magic Theory below 3 is weak; the magus cannot set up a laboratory.",
                PATHS["apprenticeship"],
            )
        )
    if parma > FRESH_PARMA_CAP:
        issues.append(
            Issue(
                "note",
                "high_parma_at_gauntlet",
                "Very few magi have Parma Magica above 1 immediately after apprenticeship.",
                PATHS["minima"],
            )
        )
    return tuple(issues)


def recommended_gauntlet_xp() -> int:
    return sum(ability_xp_for_score(score) for _name, score in RECOMMENDED_GAUNTLET_ABILITIES)


def child_modifiers(age: int) -> tuple[int, int]:
    """Return (characteristic modifier, size modifier) after the 7-point buy."""
    if age >= 14:
        return 0, 0
    for max_age, char_mod, size_mod in CHILD_AGE_MODIFIERS:
        if age <= max_age:
            return char_mod, size_mod
    return 0, 0


def characteristics_for_play(bought: dict[str, int], age: int) -> dict[str, int]:
    delta, _size = child_modifiers(age)
    return {key: int(bought.get(key, 0)) + delta for key in CHARACTERISTICS}


def size_for_play(*, age: int, virtue_size: int | None = None) -> int:
    _char, child_size = child_modifiers(age)
    base = DEFAULT_SIZE if virtue_size is None else virtue_size
    return base + child_size


def post_gauntlet_year_points(lab_seasons: int = 0) -> int:
    if lab_seasons < 0 or lab_seasons > 4:
        raise ValueError("A year has at most four seasons")
    return max(0, POST_GAUNTLET_POINTS - lab_seasons * POST_GAUNTLET_LAB_SEASON_COST)


def canonical_art(token: str) -> str:
    folded = token.strip().casefold()
    if folded in ART_ALIASES:
        return ART_ALIASES[folded]
    for name in (*HERMETIC_TECHNIQUES, *HERMETIC_FORMS):
        if folded == name.casefold():
            return name
    if folded in TECHNIQUE_ABBREV:
        return TECHNIQUE_ABBREV[folded]
    if folded in FORM_ABBREV:
        return FORM_ABBREV[folded]
    raise ValueError(f"Unknown Hermetic Art: {token!r}")


def spell_creation_cost(level: int) -> int:
    if level < 1:
        raise ValueError("Spell level must be at least 1")
    return level


@dataclass(frozen=True)
class KnownSpell:
    name: str
    technique: str
    form: str
    level: int
    catalog_stable_id: str = ""

    @property
    def cost(self) -> int:
        return spell_creation_cost(self.level)


def known_spell(
    name: str,
    technique: str,
    form: str,
    level: int,
    *,
    catalog_stable_id: str = "",
) -> KnownSpell:
    return KnownSpell(
        name=name.strip(),
        technique=canonical_art(technique),
        form=canonical_art(form),
        level=level,
        catalog_stable_id=catalog_stable_id,
    )


def stress_die(rng: random.Random | None = None) -> int:
    """Open stress die. A first 0 is a botch (0). A 1 rolls again and doubles."""
    roller = rng or random
    face = roller.randint(1, 10)
    if face == 10:
        return 0
    if face != 1:
        return face
    multiplier = 2
    while True:
        face = roller.randint(1, 10)
        if face != 1:
            shown = 10 if face == 10 else face
            return shown * multiplier
        multiplier *= 2


def aging_total(
    *,
    die: int,
    age: int,
    living_conditions: int = 0,
    longevity: int = 0,
) -> int:
    """Add a resolved stress die. Values above 10 are exploded 1s. 0 adds nothing."""
    if die < 0:
        raise ValueError(f"Aging die cannot be negative, got {die}")
    return die + ceil(age / 10) - living_conditions - longevity


@dataclass(frozen=True)
class AgingOutcome:
    apparent_age_increase: int
    points: tuple[tuple[str, int], ...]
    crisis: bool
    next_decrepitude: bool


def aging_outcome(total: int) -> AgingOutcome:
    apparent = 0 if total <= 2 else 1
    if total <= 2:
        return AgingOutcome(0, (), False, False)
    if total < 10:
        return AgingOutcome(apparent, (), False, False)
    if total <= 12:
        return AgingOutcome(apparent, (("any", 1),), False, False)
    if total == 13 or total >= 22:
        return AgingOutcome(apparent, (), True, True)
    mapping = {
        14: (("qik", 1),),
        15: (("sta", 1),),
        16: (("per", 1),),
        17: (("pre", 1),),
        18: (("str", 1), ("sta", 1)),
        19: (("dex", 1), ("qik", 1)),
        20: (("com", 1), ("pre", 1)),
        21: (("int", 1), ("per", 1)),
    }
    return AgingOutcome(apparent, mapping[total], False, False)


def experience_pools_from_picks(
    *,
    character_type: str,
    age: int,
    picks: list[VirtueFlaw],
    apprenticeship_start_age: int | None = None,
):
    from apps.chargen.vf_effects import apply_vf_effects

    applied = apply_vf_effects(picks)
    return experience_pools(
        character_type=character_type,
        age=age,
        apprenticeship_start_age=apprenticeship_start_age,
        extra_xp=applied.extra_xp,
        apprenticeship_xp_delta=applied.apprenticeship_xp_delta,
        apprenticeship_spell_delta=applied.apprenticeship_spell_delta,
        feral_childhood=applied.childhood == "feral",
        later_life_xp_per_year=applied.later_life_xp_per_year,
    ), applied
