"""Cited Core tables for character creation. No book prose — numbers and paths only.

Each constant names the Definitive Edition section it comes from. The generator
never copies rule text into this repository; the Reader opens the cited path.
"""

from __future__ import annotations

from dataclasses import dataclass

CORE_BOOK_SLUG = "definitive-edition-core-rules"

# section.path values under the Core book (Reader: reader:section, CORE_BOOK_SLUG, path).
PATHS = {
    "summary": (
        "chapter-3-characters/detailed-character-creation/detailed-character-creation-summary"
    ),
    "virtues_flaws": "chapter-3-characters/detailed-character-creation/virtues-and-flaws",
    "characteristics": "chapter-3-characters/detailed-character-creation/characteristics",
    "abilities": "chapter-3-characters/detailed-character-creation/abilities",
    "childhood": "chapter-3-characters/detailed-character-creation/abilities/early-childhood",
    "later_life": "chapter-3-characters/detailed-character-creation/abilities/later-life",
    "apprenticeship": (
        "chapter-3-characters/detailed-character-creation/abilities/magus-only-apprenticeship"
    ),
    "after_apprenticeship": (
        "chapter-3-characters/detailed-character-creation/abilities/magus-only-after-apprenticeship"
    ),
    "house": "chapter-3-characters/detailed-character-creation/magi-only-hermetic-house",
    "houses_table": (
        "chapter-3-characters/detailed-character-creation/magi-only-hermetic-house/"
        "hermetic-houses-summary"
    ),
    "experience": "chapter-10-long-term-events/using-experience-points",
    "the_gift": "chapter-4-virtues-and-flaws/types-of-virtue-and-flaw/the-gift",
    "hermetic_magus": "chapter-4-virtues-and-flaws/virtues/hermetic-magus",
    "wealthy": "chapter-4-virtues-and-flaws/virtues/wealthy",
    "poor": "chapter-4-virtues-and-flaws/flaws/poor",
    "privileged_upbringing": "chapter-4-virtues-and-flaws/virtues/privileged-upbringing",
    "grog": "chapter-3-characters/character-types/grogs",
    "companion": "chapter-3-characters/character-types/companions",
    "magus": "chapter-3-characters/character-types/magi",
    "starting_age": "chapter-3-characters/detailed-character-creation/starting-character-age",
    "templates": "chapter-3-characters/character-templates",
    "template_format": "chapter-3-characters/character-templates/format",
    "sample_childhoods": (
        "chapter-3-characters/detailed-character-creation/abilities/sample-childhoods"
    ),
    "choosing_vf": (
        "chapter-3-characters/detailed-character-creation/virtues-and-flaws/"
        "choosing-virtues-and-flaws"
    ),
    "quick_vf": (
        "chapter-3-characters/detailed-character-creation/virtues-and-flaws/"
        "quick-and-easy-virtues-and-flaws"
    ),
    "vf_guidelines": "chapter-4-virtues-and-flaws/virtues-and-flaws-rules-and-guidelines",
    "personality": "chapter-3-characters/detailed-character-creation/personality",
    "confidence": "chapter-3-characters/detailed-character-creation/confidence",
    "equipment": "chapter-3-characters/detailed-character-creation/equipment",
    "minima": (
        "chapter-3-characters/detailed-character-creation/abilities/"
        "hermetic-magi-recommended-minimum-abilities"
    ),
    "aging": "chapter-10-long-term-events/aging",
    "child_characters": "chapter-3-characters/detailed-character-creation/child-characters",
    "arts": "chapter-7-hermetic-magic/the-hermetic-arts",
    "combat": "chapter-6-combat",
    "wounds": "chapter-6-combat/wounds",
    "fatigue": "chapter-6-combat/fatigue",
    "casting": "chapter-7-hermetic-magic/casting-spells",
    "laboratory": "chapter-8-laboratory",
}

CHARACTER_TYPES = ("grog", "companion", "magus")

CHARACTERISTICS = ("int", "per", "str", "sta", "pre", "com", "dex", "qik")
CHARACTERISTIC_LABELS = {
    "int": "Intelligence",
    "per": "Perception",
    "str": "Strength",
    "sta": "Stamina",
    "pre": "Presence",
    "com": "Communication",
    "dex": "Dexterity",
    "qik": "Quickness",
}
CHARACTERISTIC_POINTS = 7
# Score → point cost. Negative scores grant points (negative cost).
CHARACTERISTIC_COST = {3: 6, 2: 3, 1: 1, 0: 0, -1: -1, -2: -3, -3: -6}

CHILDHOOD_YEARS = 5
NATIVE_LANGUAGE_XP = 75  # normally Language 5
CHILDHOOD_XP = 45
CHILDHOOD_TOTAL_XP = NATIVE_LANGUAGE_XP + CHILDHOOD_XP
CHILDHOOD_ABILITIES = (
    "Area Lore",
    "Athletics",
    "Awareness",
    "Brawl",
    "Charm",
    "Folk Ken",
    "Guile",
    "Living Language",
    "Stealth",
    "Survival",
    "Swim",
)

# Optional 120-XP packages (Native Language 5 + the 45 childhood XP).
# The player may still spend the 45 XP freely instead.
@dataclass(frozen=True)
class ChildhoodPackage:
    name: str
    abilities: tuple[tuple[str, int], ...]
    cite: str = PATHS["sample_childhoods"]


SAMPLE_CHILDHOODS = (
    ChildhoodPackage(
        "Athletic",
        (("Athletics", 2), ("Brawl", 2), ("Native Language", 5), ("Swim", 2)),
    ),
    ChildhoodPackage(
        "Exploring",
        (
            ("Area Lore", 2),
            ("Athletics", 1),
            ("Awareness", 1),
            ("Native Language", 5),
            ("Stealth", 1),
            ("Survival", 2),
        ),
    ),
    ChildhoodPackage(
        "Mischievous",
        (("Brawl", 2), ("Guile", 2), ("Native Language", 5), ("Stealth", 2)),
    ),
    ChildhoodPackage(
        "Social",
        (("Charm", 2), ("Folk Ken", 2), ("Guile", 2), ("Native Language", 5)),
    ),
    ChildhoodPackage(
        "Traveling",
        (
            ("Area Lore (place A)", 1),
            ("Area Lore (place B)", 1),
            ("Folk Ken", 2),
            ("Living Language", 1),
            ("Native Language", 5),
            ("Survival", 2),
        ),
    ),
)

# Later-life / apprenticeship Ability gates (Choosing Virtues and Flaws).
GATED_ABILITY_CATEGORIES = frozenset({"academic", "arcane", "martial", "supernatural"})
APPRENTICESHIP_UNLOCKS = frozenset({"academic", "arcane", "martial"})
# Fallback when the Lexicon row is missing; catalog category still wins.
GATED_ABILITY_NAMES = {
    "artes liberales": "academic",
    "civil and canon law": "academic",
    "common law": "academic",
    "dead language": "academic",
    "latin": "academic",
    "medicine": "academic",
    "philosophiae": "academic",
    "theology": "academic",
    "code of hermes": "arcane",
    "dominion lore": "arcane",
    "faerie lore": "arcane",
    "finesse": "arcane",
    "infernal lore": "arcane",
    "magic lore": "arcane",
    "magic theory": "arcane",
    "parma magica": "arcane",
    "penetration": "arcane",
    "bows": "martial",
    "great weapon": "martial",
    "single weapon": "martial",
    "thrown weapon": "martial",
}

LATER_LIFE_XP = 15
WEALTHY_XP = 20
POOR_XP = 10
PRIVILEGED_UPBRINGING_XP = 50
WELL_TRAVELED_XP = 50
EDUCATED_XP = 50
ARCANE_LORE_XP = 50
WARRIOR_XP = 50

# Feral Upbringing replaces the 75+45 childhood split (no Native Language).
FERAL_CHILDHOOD_XP = 120
FERAL_CHILDHOOD_ABILITIES = (
    "Area Lore",
    "Animal Handling",
    "Athletics",
    "Awareness",
    "Brawl",
    "Hunt",
    "Stealth",
    "Survival",
    "Swim",
)

# Optional magus package: 90 XP of the 240 apprenticeship Ability budget.
RECOMMENDED_GAUNTLET_ABILITIES = (
    ("Artes Liberales", 1),
    ("Latin", 4),
    ("Magic Theory", 3),
    ("Parma Magica", 1),
)

HERMETIC_TECHNIQUES = ("Creo", "Intellego", "Muto", "Perdo", "Rego")
HERMETIC_FORMS = (
    "Animal",
    "Aquam",
    "Auram",
    "Corpus",
    "Herbam",
    "Ignem",
    "Imaginem",
    "Mentem",
    "Terram",
    "Vim",
)
TECHNIQUE_ABBREV = {"cr": "Creo", "in": "Intellego", "mu": "Muto", "pe": "Perdo", "re": "Rego"}
FORM_ABBREV = {
    "an": "Animal",
    "aq": "Aquam",
    "au": "Auram",
    "co": "Corpus",
    "he": "Herbam",
    "ig": "Ignem",
    "im": "Imaginem",
    "me": "Mentem",
    "te": "Terram",
    "vi": "Vim",
}
ART_ALIASES = {"corporem": "Corpus", "imagonem": "Imaginem", "intelligo": "Intellego"}

DEFAULT_SIZE = 0
# Buy Characteristics as an adult, then apply (characteristic_mod, size_mod).
# Ages under 6 use the 6–7 row.
CHILD_AGE_MODIFIERS = (
    (7, -4, -2),
    (9, -3, -2),
    (11, -2, -2),
    (13, -1, -1),
)

# After-apprenticeship example: typical Spring/Winter covenant (magus) = +1.
LIVING_CONDITIONS_TYPICAL_MAGUS = 1
SKILLED_PARENS_XP = 60
SKILLED_PARENS_SPELLS = 30

APPRENTICESHIP_YEARS = 15
APPRENTICESHIP_XP = 240
APPRENTICESHIP_SPELL_LEVELS = 120
# Must have these scores or the character is not admitted to the Order.
APPRENTICESHIP_REQUIRED = (("Parma Magica", 1), ("Magic Theory", 1), ("Latin", 1))
READING_LATIN = 4
READING_ARTES_LIBERALES = 1
WEAK_MAGIC_THEORY = 3  # below this the magus cannot set up a laboratory
FRESH_PARMA_CAP = 1  # just out of apprenticeship; rarely higher

POST_GAUNTLET_POINTS = 30  # per year: 1 point = 1 Art/Ability XP or 1 spell level
POST_GAUNTLET_LAB_SEASON_COST = 10  # of the 30 yearly points
AGING_AGE = 35

VF_POINTS = {"Minor": 1, "Major": 3, "Free": 0}
MAX_MINOR_FLAWS_CENTRAL = 5  # companions and magi
MAX_MAJOR_PERSONALITY_FLAWS = 1  # "may not"
MAX_STORY_FLAWS_GUIDELINE = 1  # "should not"; troupe may agree to more
MAX_PERSONALITY_FLAWS_GUIDELINE = 2

CONFIDENCE_SCORE = 1
CONFIDENCE_POINTS = 3
PERSONALITY_TRAIT_RANGE = (-3, 3)
PERSONALITY_MINOR_SCORE = 3  # ±3 for a Minor Personality Flaw
PERSONALITY_MAJOR_SCORE = 6  # ±6 for a Major Personality Flaw


@dataclass(frozen=True)
class TypeBudget:
    """Virtue/Flaw caps for a character type (Core creation summary)."""

    max_flaw_points: int
    allow_major: bool
    allow_story: bool
    allow_gift: bool
    allow_wealthy_poor: bool
    cite: str


TYPE_BUDGETS = {
    "grog": TypeBudget(3, False, False, False, False, PATHS["grog"]),
    "companion": TypeBudget(10, True, True, True, True, PATHS["companion"]),
    "magus": TypeBudget(10, True, True, True, False, PATHS["magus"]),
}


@dataclass(frozen=True)
class HousePick:
    """One Virtue or Flaw a House grants. Magnitude stays real; the points are not spent."""

    slug: str
    name: str
    kind: str
    magnitude: str
    category: str
    target: str = ""


@dataclass(frozen=True)
class HouseBenefit:
    name: str
    kind: str
    benefit: str
    cite: str = PATHS["houses_table"]
    picks: tuple[HousePick, ...] = ()
    choices: tuple[HousePick, ...] = ()
    # Open slots the player designates. A compulsory slot must be filled.
    open_slots: tuple[str, ...] = ()
    required_slots: tuple[str, ...] = ()
    # First-move Virtues or Flaws the player can add from the House block.
    suggestions: tuple[HousePick, ...] = ()


def _art(target: str) -> HousePick:
    return HousePick("puissant-art", "Puissant Art", "virtue", "Minor", "Hermetic", target)


def _ability(target: str) -> HousePick:
    return HousePick(
        "puissant-ability", "Puissant Ability", "virtue", "Minor", "General", target
    )


HOUSES = (
    HouseBenefit(
        "Bjornaer",
        "Mystery Cult",
        "Heartbeast Ability 1",
        picks=(HousePick("heartbeast", "Heartbeast", "virtue", "Minor", "Hermetic"),),
    ),
    HouseBenefit(
        "Bonisagus",
        "True Lineage",
        "Puissant Magic Theory or Puissant Intrigue",
        choices=(_ability("Magic Theory"), _ability("Intrigue")),
    ),
    HouseBenefit(
        "Criamon",
        "Mystery Cult",
        "The Enigma; Enigmatic Wisdom 1",
        picks=(HousePick("the-enigma", "The Enigma", "virtue", "Minor", "Hermetic"),),
    ),
    HouseBenefit(
        "Ex Miscellanea",
        "Societas",
        "Free Minor Hermetic Virtue, free Major non-Hermetic Virtue, "
        "compulsory Major Hermetic Flaw (beyond the normal allowance)",
        open_slots=("minor-hermetic", "major-nonhermetic", "major-hermetic-flaw"),
        required_slots=("major-hermetic-flaw",),
    ),
    HouseBenefit(
        "Flambeau",
        "Societas",
        "Puissant Perdo or Puissant Ignem",
        choices=(_art("Perdo"), _art("Ignem")),
    ),
    HouseBenefit(
        "Guernicus",
        "True Lineage",
        "Hermetic Prestige",
        picks=(
            HousePick("hermetic-prestige", "Hermetic Prestige", "virtue", "Minor", "General"),
        ),
    ),
    HouseBenefit(
        "Jerbiton",
        "Societas",
        "A Minor Virtue of scholarship, arts, or mundane interaction",
        open_slots=("minor-mundane",),
        suggestions=(
            HousePick("educated", "Educated", "virtue", "Minor", "General"),
            HousePick("free-expression", "Free Expression", "virtue", "Minor", "General"),
            HousePick(
                "venus-s-blessing", "Venus's Blessing", "virtue", "Minor", "General"
            ),
        ),
    ),
    HouseBenefit(
        "Mercere",
        "True Lineage",
        "Puissant Creo or Puissant Muto",
        choices=(_art("Creo"), _art("Muto")),
    ),
    HouseBenefit(
        "Merinita",
        "Mystery Cult",
        "Faerie Magic Ability 1",
        picks=(HousePick("faerie-magic", "Faerie Magic", "virtue", "Minor", "Hermetic"),),
    ),
    HouseBenefit(
        "Tremere",
        "True Lineage",
        "Minor Magical Focus (certamen)",
        picks=(
            HousePick(
                "minor-magical-focus",
                "Minor Magical Focus",
                "virtue",
                "Minor",
                "Hermetic",
                "certamen",
            ),
        ),
    ),
    HouseBenefit(
        "Tytalus",
        "Societas",
        "Self-Confident",
        picks=(HousePick("self-confident", "Self-Confident", "virtue", "Minor", "General"),),
    ),
    HouseBenefit(
        "Verditius",
        "Mystery Cult",
        "Verditius Magic",
        picks=(HousePick("verditius-magic", "Verditius Magic", "virtue", "Minor", "Hermetic"),),
    ),
)

# Living Conditions modifier from the Aging table. The value is what the roll subtracts.
LIVING_CONDITIONS = (
    (2, "Wealthy, or a healthy location"),
    (2, "Typical Summer or Autumn covenant (magus)"),
    (1, "Typical Summer or Autumn covenant (mundane)"),
    (1, "Typical Spring or Winter covenant (magus)"),
    (0, "Average"),
    (-2, "Poor, an unhealthy location, or a typical town"),
)
