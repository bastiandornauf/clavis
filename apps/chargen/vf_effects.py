"""Cited Core Virtue/Flaw effects that change character generation.

Keyed by catalog slug. Markdown repairs should not require edits here; add a
row when a new Core V/F actually changes XP, gates, size, or scores.
Social Status variants reuse the same tags.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.chargen.core_tables import (
    ARCANE_LORE_XP,
    EDUCATED_XP,
    FERAL_CHILDHOOD_XP,
    PATHS,
    POOR_XP,
    PRIVILEGED_UPBRINGING_XP,
    SKILLED_PARENS_SPELLS,
    SKILLED_PARENS_XP,
    WARRIOR_XP,
    WEALTHY_XP,
    WELL_TRAVELED_XP,
)
from apps.chargen.types import Issue, VirtueFlaw


def vf_slug(name: str) -> str:
    """Match CatalogEntry.slug without pulling Django into the arithmetic."""
    folded = name.strip().casefold()
    chars: list[str] = []
    for char in folded:
        if char.isalnum():
            chars.append(char)
        elif chars and chars[-1] != "-":
            chars.append("-")
    return "".join(chars).strip("-")


def _cite(kind: str, slug: str) -> str:
    folder = "virtues" if kind == "virtue" else "flaws"
    return f"chapter-4-virtues-and-flaws/{folder}/{slug}"


@dataclass(frozen=True)
class VFTag:
    """One mechanical chargen consequence of a Virtue or Flaw."""

    kind: str
    amount: int = 0
    target: str = ""
    restrict: tuple[str, ...] = ()


@dataclass(frozen=True)
class VFEffect:
    slug: str
    name: str
    kind: str
    cite: str
    tags: tuple[VFTag, ...]


@dataclass(frozen=True)
class XpGrant:
    amount: int
    restrict: tuple[str, ...] = ()
    privileged_exception: bool = False


@dataclass(frozen=True)
class PendingPick:
    slug: str
    kind: str
    restrict: tuple[str, ...] = ()


@dataclass(frozen=True)
class AppliedEffects:
    later_life_xp_per_year: int | None
    xp_grants: tuple[XpGrant, ...]
    granted_categories: frozenset[str]
    granted_abilities: frozenset[str]
    free_abilities: tuple[tuple[str, int], ...]
    characteristic_points_delta: int
    size: int | None
    str_sta_bonus: int
    apprenticeship_xp_delta: int
    apprenticeship_spell_delta: int
    childhood: str
    forbid_wealthy_poor: bool
    affinities: tuple[str, ...]
    puissants: tuple[tuple[str, int], ...]
    age_cap_bonus: int
    pending_picks: tuple[PendingPick, ...]
    issues: tuple[Issue, ...]

    @property
    def extra_xp(self) -> int:
        return sum(grant.amount for grant in self.xp_grants)


def boost_xp(xp: int, *, extra_per: int) -> int:
    """Increase XP by 1/extra_per, rounded up. extra_per=2 is +half; 4 is +quarter."""
    if xp < 0:
        raise ValueError("Experience points cannot be negative")
    if extra_per < 1:
        raise ValueError("Affinity divisor must be at least 1")
    return xp + (xp + extra_per - 1) // extra_per


def _t(kind: str, amount: int = 0, target: str = "", *restrict: str) -> VFTag:
    return VFTag(kind, amount=amount, target=target, restrict=restrict)


def _row(kind: str, slug: str, name: str, *tags: VFTag) -> tuple[str, VFEffect]:
    return slug, VFEffect(slug, name, kind, _cite(kind, slug), tags)


def _ability_one(slug: str, name: str, ability: str) -> tuple[str, VFEffect]:
    return _row("virtue", slug, name, _t("free_ability", 1, ability))


_SIZE_SET = ("giant-blood", "large", "small-frame", "dwarf")

_ABILITY_ONE = (
    _ability_one("premonitions", "Premonitions", "Premonitions"),
    _ability_one("second-sight", "Second Sight", "Second Sight"),
    _ability_one("animal-ken", "Animal Ken", "Animal Ken"),
    _ability_one("dowsing", "Dowsing", "Dowsing"),
    _ability_one("enchanting-ability", "Enchanting (Ability)", "Enchanting (Ability)"),
    _ability_one("entrancement", "Entrancement", "Entrancement"),
    _ability_one("hex", "Hex", "Hex"),
    _ability_one("magic-sensitivity", "Magic Sensitivity", "Magic Sensitivity"),
    _ability_one(
        "sense-holiness-and-unholiness",
        "Sense Holiness and Unholiness",
        "Sense Holiness and Unholiness",
    ),
    _ability_one("shapeshifter", "Shapeshifter", "Shapeshifter"),
    _ability_one("wilderness-sense", "Wilderness Sense", "Wilderness Sense"),
    _ability_one("heartbeast", "Heartbeast", "Heartbeast"),
    _ability_one("the-enigma", "The Enigma", "Enigmatic Wisdom"),
    _ability_one("faerie-magic", "Faerie Magic", "Faerie Magic"),
)

EFFECTS: dict[str, VFEffect] = dict(
    (
        _row("virtue", "wealthy", "Wealthy", _t("later_life_xp", WEALTHY_XP)),
        _row("flaw", "poor", "Poor", _t("later_life_xp", POOR_XP)),
        _row(
            "virtue",
            "privileged-upbringing",
            "Privileged Upbringing",
            _t("extra_xp", PRIVILEGED_UPBRINGING_XP, "", "general", "academic", "martial"),
            _t("privileged_exception"),
        ),
        _row(
            "flaw",
            "feral-upbringing",
            "Feral Upbringing",
            _t("childhood", FERAL_CHILDHOOD_XP, "feral"),
        ),
        _row(
            "virtue",
            "educated",
            "Educated",
            _t("grants_category", 0, "academic"),
            _t("extra_xp", EDUCATED_XP, "", "Latin", "Artes Liberales"),
        ),
        _row(
            "virtue",
            "arcane-lore",
            "Arcane Lore",
            _t("grants_category", 0, "arcane"),
            _t("extra_xp", ARCANE_LORE_XP, "", "arcane"),
        ),
        _row(
            "virtue",
            "warrior",
            "Warrior",
            _t("grants_category", 0, "martial"),
            _t("extra_xp", WARRIOR_XP, "", "martial"),
        ),
        _row(
            "virtue",
            "well-traveled",
            "Well-Traveled",
            _t(
                "extra_xp",
                WELL_TRAVELED_XP,
                "",
                "Living Language",
                "Area Lore",
                "Bargain",
                "Carouse",
                "Charm",
                "Etiquette",
                "Folk Ken",
                "Guile",
            ),
        ),
        _row(
            "virtue",
            "skilled-parens",
            "Skilled Parens",
            _t("apprenticeship_xp", SKILLED_PARENS_XP),
            _t("apprenticeship_spells", SKILLED_PARENS_SPELLS),
        ),
        _row(
            "flaw",
            "weak-parens",
            "Weak Parens",
            _t("apprenticeship_xp", -SKILLED_PARENS_XP),
            _t("apprenticeship_spells", -SKILLED_PARENS_SPELLS),
        ),
        _row(
            "virtue",
            "improved-characteristics",
            "Improved Characteristics",
            _t("characteristic_points", 3),
            _t("repeatable"),
        ),
        _row(
            "virtue",
            "great-characteristic",
            "Great (Characteristic)",
            _t("great_characteristic"),
            _t("pick", 0, "characteristic"),
            _t("repeatable"),
        ),
        _row(
            "flaw",
            "weak-characteristics",
            "Weak Characteristics",
            _t("characteristic_points", -3),
            _t("repeatable"),
        ),
        _row(
            "flaw",
            "poor-characteristic",
            "Poor (Characteristic)",
            _t("poor_characteristic"),
            _t("pick", 0, "characteristic"),
            _t("repeatable"),
        ),
        _row(
            "virtue",
            "giant-blood",
            "Giant Blood",
            _t("size", 2),
            _t("str_sta", 1),
            *(_t("incompatible", 0, other) for other in _SIZE_SET if other != "giant-blood"),
        ),
        _row(
            "virtue",
            "large",
            "Large",
            _t("size", 1),
            *(_t("incompatible", 0, other) for other in _SIZE_SET if other != "large"),
        ),
        _row(
            "flaw",
            "small-frame",
            "Small Frame",
            _t("size", -1),
            *(_t("incompatible", 0, other) for other in _SIZE_SET if other != "small-frame"),
        ),
        _row(
            "flaw",
            "dwarf",
            "Dwarf",
            _t("size", -2),
            _t("str_sta", -1),
            *(_t("incompatible", 0, other) for other in _SIZE_SET if other != "dwarf"),
        ),
        _row(
            "virtue",
            "affinity-with-ability",
            "Affinity with Ability",
            _t("affinity", 2, "ability"),
            _t("age_cap", 2),
            _t("pick", 0, "ability"),
            _t("repeatable"),
        ),
        _row(
            "virtue",
            "affinity-with-art",
            "Affinity with Art",
            _t("affinity", 2, "art"),
            _t("pick", 0, "art"),
            _t("repeatable"),
        ),
        _row(
            "virtue",
            "puissant-ability",
            "Puissant Ability",
            _t("puissant", 2, "ability"),
            _t("pick", 0, "ability"),
            _t("repeatable"),
        ),
        _row(
            "virtue",
            "puissant-art",
            "Puissant Art",
            _t("puissant", 3, "art"),
            _t("pick", 0, "art"),
            _t("repeatable"),
        ),
        _row("virtue", "linguist", "Linguist", _t("affinity", 4, "language")),
        _row("virtue", "covenfolk", "Covenfolk", _t("forbid_wealthy_poor")),
        _row(
            "virtue",
            "custos",
            "Custos",
            _t("forbid_wealthy_poor"),
            _t("pick", 0, "category", "academic", "arcane", "martial"),
        ),
        _row("virtue", "knight", "Knight", _t("grants_category", 0, "martial")),
        _row(
            "virtue",
            "failed-apprentice",
            "Failed Apprentice",
            _t("grants_category", 0, "academic"),
            _t("grants_category", 0, "arcane"),
            _t("grants_category", 0, "martial"),
        ),
        _row("virtue", "berserk", "Berserk", _t("grants_category", 0, "martial")),
        _row(
            "virtue",
            "faerie-blood",
            "Faerie Blood",
            _t("grants_ability", 0, "Faerie Lore"),
        ),
        _row(
            "virtue",
            "student-of-realm",
            "Student of (Realm)",
            _t("pick", 0, "realm", "divine", "faerie", "infernal", "magic"),
            _t("repeatable"),
        ),
        _row(
            "flaw",
            "covenant-upbringing",
            "Covenant Upbringing",
            _t("grants_ability", 0, "Latin"),
        ),
        _row(
            "flaw",
            "faerie-upbringing",
            "Faerie Upbringing",
            _t("grants_ability", 0, "Faerie Lore"),
        ),
        _row("flaw", "deficient-form", "Deficient Form", _t("pick", 0, "form")),
        _row(
            "flaw",
            "deficient-technique",
            "Deficient Technique",
            _t("pick", 0, "technique"),
        ),
        *_ABILITY_ONE,
    )
)


def lookup_effect(pick: VirtueFlaw) -> VFEffect | None:
    slug = pick.slug.strip() or vf_slug(pick.name)
    return EFFECTS.get(slug)


def target_spec(slug: str) -> tuple[str, tuple[str, ...]] | None:
    """Return (kind, allowed values) when this Virtue or Flaw must name a target."""
    effect = EFFECTS.get(slug)
    if effect is None:
        return None
    for tag in effect.tags:
        if tag.kind == "pick":
            return tag.target, tag.restrict
    return None


def apply_vf_effects(picks: list[VirtueFlaw]) -> AppliedEffects:
    later_life: int | None = None
    grants: list[XpGrant] = []
    categories: set[str] = set()
    abilities: set[str] = set()
    free: list[tuple[str, int]] = []
    char_delta = 0
    size: int | None = None
    str_sta = 0
    appr_xp = 0
    appr_spells = 0
    childhood = ""
    forbid_wp = False
    affinities: list[str] = []
    puissants: list[tuple[str, int]] = []
    age_cap = 0
    pending: list[PendingPick] = []
    issues: list[Issue] = []
    slugs = {pick.slug.strip() or vf_slug(pick.name) for pick in picks}

    for pick in picks:
        effect = lookup_effect(pick)
        if effect is None:
            continue
        privileged = any(tag.kind == "privileged_exception" for tag in effect.tags)
        for tag in effect.tags:
            if tag.kind == "later_life_xp":
                later_life = tag.amount
            elif tag.kind == "extra_xp":
                grants.append(
                    XpGrant(
                        tag.amount,
                        restrict=tag.restrict,
                        privileged_exception=privileged,
                    )
                )
            elif tag.kind == "grants_category":
                categories.add(tag.target)
            elif tag.kind == "grants_ability":
                abilities.add(tag.target)
            elif tag.kind == "free_ability":
                free.append((tag.target, tag.amount or 1))
            elif tag.kind == "characteristic_points":
                char_delta += tag.amount
            elif tag.kind == "size":
                size = tag.amount
            elif tag.kind == "str_sta":
                str_sta += tag.amount
            elif tag.kind == "apprenticeship_xp":
                appr_xp += tag.amount
            elif tag.kind == "apprenticeship_spells":
                appr_spells += tag.amount
            elif tag.kind == "childhood":
                childhood = tag.target
            elif tag.kind == "forbid_wealthy_poor":
                forbid_wp = True
            elif tag.kind == "affinity":
                affinities.append(tag.target)
            elif tag.kind == "puissant":
                puissants.append((tag.target, tag.amount))
            elif tag.kind == "age_cap":
                age_cap += tag.amount
            elif tag.kind == "pick":
                pending.append(PendingPick(effect.slug, tag.target, tag.restrict))
            elif tag.kind == "incompatible" and tag.target in slugs:
                issues.append(
                    Issue(
                        "error",
                        "vf_incompatible",
                        f"{effect.name} cannot be combined with {tag.target}.",
                        effect.cite,
                    )
                )

    if forbid_wp and later_life is not None:
        issues.append(
            Issue(
                "error",
                "wealthy_poor_status",
                "This Social Status is supported by the covenant; "
                "Wealthy and Poor do not apply.",
                PATHS["later_life"],
            )
        )

    return AppliedEffects(
        later_life_xp_per_year=later_life,
        xp_grants=tuple(grants),
        granted_categories=frozenset(categories),
        granted_abilities=frozenset(abilities),
        free_abilities=tuple(free),
        characteristic_points_delta=char_delta,
        size=size,
        str_sta_bonus=str_sta,
        apprenticeship_xp_delta=appr_xp,
        apprenticeship_spell_delta=appr_spells,
        childhood=childhood,
        forbid_wealthy_poor=forbid_wp,
        affinities=tuple(affinities),
        puissants=tuple(puissants),
        age_cap_bonus=age_cap,
        pending_picks=tuple(pending),
        issues=tuple(issues),
    )
