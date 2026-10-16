# Plan: Character generator

Status: **milestone 7** (2026-10) — worksheet, print, Markdown, JSON,
Workspace save, optional play numbers, and PDF fill of a user-supplied
ArMD fillable sheet. Optional play numbers stay off the posted HTML/Markdown.

## Goal

A player builds a legal Ars Magica 5e character in Clavis, starting with the
Definitive Edition Core Rules: grog, companion, or magus.

**The player decides. The tool leads, records, and calculates.** There is no
automatic character generation. Every Virtue, score, Ability, Art, and spell is
a human choice. ClavisGen walks the Core creation sequence, writes the sheet
down, keeps the running totals, and **blocks anything the rules forbid**.

Legality is the **rulebook**, not the troupe. House-rule exceptions are out of
scope: a grog with a Story Flaw is illegal here even if a saga would allow it.
Notes (aging rolls, a Gifted companion) flag further rules that still apply to a
legal sheet. Every number and block cites the Core section in the Reader.

It is a **guided worksheet with a live total**, not a one-click random magus.
Core templates (The Knight, house sample magi, …) are optional starting points
the player then edits.

## License

The Open License (CC BY-SA 4.0) covers the Core rules fully, so a generator
that applies those rules is allowed. Constraints that already apply to Clavis:

- Do **not** copy book prose into this software repository. Tables and catalogs
  are derived at import from the user's Open License checkout.
- Structured derived data (point tables, house benefits, catalog picks) is
  CC BY-SA 4.0 if ever redistributed; keep Atlas attribution (see `NOTICE.md`).
- Saved characters are **user overlays**, like notes and campaigns — not source
  text.
- Clavis stays an independent fan project, not affiliated with Atlas Games.

ShareAlike would bite if we shipped a packaged "character pack" of Core text.
It does not bite a local tool that reads the imported books.

## Attach to Clavis, do not fork

A separate generator would re-parse virtues, abilities, and spells. Clavis
already has them, plus citations and campaign storage.

| Clavis already has | Character creation needs |
|--------------------|--------------------------|
| 317 Core virtues / 281 Core flaws (magnitude + category) | Point budgets, Social Status, Gift / Hermetic / Story / grog limits |
| 45 Core abilities (category: General / Academic / Arcane / Martial / Supernatural) | XP triangular cost, early-childhood whitelist, age caps, Virtue gates |
| 350 Core spells (Te / Fo / level, not device effects) | 120 levels in apprenticeship; max level = Te + Fo + Int + Magic Theory + 3 |
| House sample magi + grog/companion templates as characters | Prefill a sheet |
| Spell workshop + (planned) spontaneous calculator | Later: "can this magus cast this?" |
| Campaigns keyed by `stable_id` | Save the sheet as overlay JSON, not as a library section |

New Django app: `apps.chargen`. Domain logic in its services; Lexicon stays
the picker; Reader stays the citation target; `apps.campaigns` stores the
saved sheet. Do not grow `apps.catalog` into a character engine.

## Two ways in (Chapter 3)

Core offers three speeds. ClavisGen must support the first and the third;
customizing a template is the first plus the worksheet.

1. **Take a template** — 6 grogs, 5 companions, 12 house magi. Fully generated;
   the player adds a name and a bit of background. Combat, soak, leftover XP
   in parentheses, and `X+Y` Puissant bonuses are already on the sheet.
2. **Customize a template** — follow that template's *Customization Notes*.
   Personality Flaws and similar are cheap to swap. Virtues that change the
   XP rate (Wealthy) cannot be changed without rebuilding the life path.
3. **Detailed character creation** — from scratch, walk the life path below.

A first magus is told to start from a template. Templates are not a different
ruleset; they are finished sheets that still have to stay legal if edited.

## Core creation sequence (Definitive Edition)

Cited from `chapter-3-characters/detailed-character-creation/detailed-character-creation-summary`
and the following subsections.

1. **Concept** — free text.
2. **Type** — grog / companion / magus (Mythic Companion later).
3. **House** (magi) — one of twelve; grants a listed starting benefit (often a
   free Virtue, or a free Ability at 1). Ex Miscellanea's extra V/F are *beyond
   the normal allowance*.
4. **Virtues and Flaws** (before childhood XP — they gate Abilities and XP)
   - Minor = 1 point, Major = 3. Start from 0; Flaws buy Virtues. You do not
     have to take the maximum.
   - Grog: up to 3 Minor Flaws, same number of Minor Virtues; no Major, no
     Story, no Gift.
   - Companion / magus: up to 10 Flaw points, matching Virtue points; no more
     than five Minor Flaws.
   - All characters need a Social Status. Hermetic Magus is free and magus-only.
   - The Gift is free; unusual on companions.
   - No Hermetic V/F without The Gift.
   - Magi must have The Gift and **at least one Hermetic Flaw**.
   - At most one Major Personality Flaw. Two Story Flaws / more than two
     Personality Flaws are notes (Core calls them guidelines).
   - Academic, Arcane, Martial, and Supernatural Abilities each need a Virtue
     (or some Flaws) that grants access. Educated / Arcane Lore / Warrior are
     the easy options; each Supernatural Ability is usually its own Virtue.
   - Record free Ability scores from Virtues *before* spending childhood XP
     (Darius: Premonitions 1, Second Sight 1).
5. **Characteristics** — 7 points, table +3=6 … −3 grants 6. Eight scores
   (Int, Per, Str, Sta, Pre, Com, Dex, Qik).
6. **Early childhood** (years 0–5, a lump, **not** 15 XP/year)
   - 75 XP Native Language (normally score 5) + 45 XP from a closed list:
     Area Lore, Athletics, Awareness, Brawl, Charm, Folk Ken, Guile, Living
     Language (not the native one), Stealth, Survival, Swim.
   - Optional shortcuts: five sample childhoods (Athletic, Exploring,
     Mischievous, Social, Traveling), each spending exactly 120 XP. The player
     may still spend the 45 XP freely.
7. **Later life** — 15 XP/year (Wealthy 20, Poor 10; companions only) from age
   5 until apprenticeship starts (magi) or current age (others). Only Abilities
   the V/F allow. Future magi still need a Virtue for Academic/Arcane/Martial
   *before* apprenticeship.
8. **Apprenticeship** (magi, 15 years) — 240 XP (Arts + Abilities) and 120
   spell levels. Academic, Arcane, and Martial are open; Supernatural still
   needs the Virtue. Spell cap = Te + Fo + Int + Magic Theory + 3, requisites
   count, V/F that affect lab totals apply, aura assumed +3. **Must** have
   Parma Magica 1, Magic Theory 1, Latin 1. Notes: Latin 4 + Artes Liberales 1
   to read; Magic Theory 3 to open a lab; Parma rarely above 1 at Gauntlet.
   Affinity increases spent XP by half, rounded up; Linguist by a quarter.
   Puissant Ability is +2 on the displayed score (`X+Y`), Puissant Art +3 —
   not extra XP.
9. **Optional years after Gauntlet** — 30 points/year split across Art XP,
   Ability XP, and extra spell levels. Each lab season costs 10 of those 30
   (min 0 if three or four seasons). Aging rolls from the Winter after 35
   (player supplies the die; the engine applies the table).
   Optional 90-XP package: Artes Liberales 1, Latin 4, Magic Theory 3,
   Parma Magica 1.
10. **Spells** — pick from the Core catalog, or a free name plus Technique,
    Form, and level (cost = level, still capped).
11. **Personality** — a few traits at −3…+3. Grogs need Loyal; warriors need
    Brave. A Minor Personality Flaw is represented at ±3, a Major at ±6.
12. **Reputation** — only if a V/F grants one.
13. **Confidence** — grogs none; companions/magi start at Score 1 / 3 points
    unless a V/F says otherwise.
14. **Equipment** — anything reasonably acquired and kept.

Child characteristic/size modifiers apply after the 7-point buy when age < 14.
**Extremely Complex Character Generation** (season-by-season lab and
Long-Term Events) is out of scope — not a later milestone. Might-score
characters stay a later type.

XP formulas (`chapter-10-long-term-events/using-experience-points`):

- Ability +1 costs `(score + 1) × 5` XP. Total to reach *n* is `5 × n(n+1)/2`.
- Art +1 costs `score + 1` XP. Total to reach *n* is `n(n+1)/2`.

Age cap on Ability scores at creation: under 30 → 5, then +1 per five years
to 9 at 46+ (some Virtues raise this).

## What the Lexicon does *not* yet give us

The generator can **list** Core virtues, flaws, abilities, and spells today.
It cannot **interpret their effects** from the catalog row. Missing structure:

| Need | In Core text | In Lexicon today |
|------|----------------|------------------|
| Characteristic cost table | yes | no (encode + cite) |
| Ability / Art XP tables | yes | no (encode + cite) |
| Early-childhood Ability list | yes | no (encode + cite) |
| House starting benefits | table on the House page | no (encode 12 rows + cite) |
| Social Status by culture | yes | category `Social Status` only |
| V/F incompatibilities, prerequisites | in each writeup | not parsed |
| V/F that change XP / age cap / Ability access | in writeup (Wealthy, Poor, Privileged Upbringing, …) | not parsed |
| Affinity / Puissant targets | player choice | not modelled |
| Spell requisites, ritual vs formulaic | sometimes in text | not reliable |

Classic Core chargen V/F are a slug-keyed **effect table** in
`apps.chargen.vf_effects` (Wealthy/Poor/Feral, Educated/Arcane Lore/Warrior,
Parens, Characteristics/Size, Affinity/Puissant/Linguist, Ability-1
Supernaturals, plus the few Core Social Status tags the life path needs).
Social Status variants from later books reuse those tags. Play-only V/F stay
text + Reader link.

## How well this can run — realistic estimate

| Part | With current tech (offline, Core only) | Confidence |
|------|----------------------------------------|------------|
| Point / XP / spell-level arithmetic | Deterministic tables | **Very high** |
| Type rules (grog vs companion vs magus) | Core summary | **High** |
| Picking V/F/Abilities/spells from Lexicon | Existing catalog | **High** for Core lists |
| Template → editable sheet | 23 Core templates already extracted | **High** as a starting snapshot, not a full parse of every stat |
| V/F combination legality beyond type/Gift/Hermetic/Story | Prose in each entry | **Low** to automate; v1 shows text + a few encoded modifiers |
| "Build me a Flambeau hunter" from a description | Needs Hermetic taste | **Low** offline; templates + filters instead |
| Supplement virtues (Houses of Hermes, …) | 634 virtues / 467 flaws in the whole corpus | **Medium** as extra pickers once Core is solid; their extra rules are even more prose-heavy |
| Aging at creation (die + table) | Core aging chapter | **High** for the table; Longevity/crisis are player-supplied |
| Combat totals, full lab simulation | Later chapters | **Out of scope** (not Extremely Complex generation) |

No API key is required for v1–v3. An LLM would help only at "suggest a concept"
and "read this Virtue and apply its modifiers". That stays deferred (ADR 0002).
If we ever add it, the model may only choose from Lexicon IDs; Clavis still
computes points.

## User flow (v1)

ClavisGen home stays at `/gen/`. Saved sheets later sit under Workspace.

1. **How to start** — *From scratch* or *From a Core template* (the 23 Chapter 3
   templates). Template copies the catalog snapshot, then the same worksheet
   re-validates every edit.
2. **Type, name, age, (magus) House.** Magus: apprenticeship start age (default
   such that Gauntlet is at 25).
3. **Virtues & Flaws** — Lexicon picker. Running total vs the type cap. Optional
   "Quick and Easy" packages as pre-checked suggestions the player still
   confirms. Illegal picks explained in one sentence with a Reader link.
4. **Characteristics** — eight scores, remaining points, cost table cited.
5. **Abilities, life path**
   - Childhood: Native Language locked at 5; 45 XP whitelist *or* one of the
     five sample childhoods.
   - Later life: years × 15 (or 20/10); category gates from V/F.
   - Magi: 240 apprenticeship XP + 120 spell levels, then optional Gauntlet
     years.
6. **Arts & spells** (magi) — Art scores from apprenticeship XP; spell picker
   with the level cap shown.
7. **Personality, confidence, equipment** — Loyal/Brave prompts; Confidence
   1 (3) for non-grogs; free-text equipment.
8. **Sheet** — printable HTML. Every heading links to the Core section.

Nothing is generated without the imported Core book. If Core is missing, the
page says so and points at Sources.

## Data model (overlays)

User characters are **not** `CatalogEntry` rows.

```
Character  (apps.chargen)
  campaign FK (nullable) — unassigned allowed
  name, character_type, house, age
  state JSON            — full worksheet dict (the editor is /gen/new/)
  updated_at
```

The worksheet is the editor: opening a Workspace row loads `state` into the
session. Print HTML and Markdown are views of `_character_sheet`, not a second
layout. Optional play numbers (combat, TeFo grid, lab) stay off this document.

References to Lexicon entries inside `state` keep slug/name so a reimport that
loses an extractor still shows what was chosen.

## Where the code goes

- `apps.chargen` — models, `creation` service (pure functions: point spend,
  XP totals, type rules, spell cap), views, templates.
- Cited constants (cost tables, childhood list, house benefits) live in
  `apps.chargen.core_tables` with a `stable_id` per table, loaded from Core
  where it is already a Markdown table, otherwise encoded and cited.
- Picker queries reuse `apps.catalog` querysets (Core book slug filter in v1).
- Save / list under Workspace; optional "add to campaign".
- No second Markdown parser. No CDN. English UI.

## Milestones

1. **Arithmetic core** ✅ — `apps.chargen.creation` + tests against the Core tables
   (V/F budgets by type, Hermetic Flaw, characteristic costs, Ability/Art XP,
   spell cap, childhood 75+45 and sample packages, later-life 15/20/10,
   apprenticeship gates and minima, Wealthy/Poor). ClavisGen home at `/gen/`
   shows type budgets and House benefits; worksheet UI is milestone 2.
2. **Worksheet UI** ✅ — `/gen/new/` walks detailed creation (type → V/F →
   characteristics → childhood → later life → magus apprenticeship/spells/
   post-Gauntlet → aging if needed → personality → sheet). Session only;
   illegal Continue stays on the step with a Reader link.
3. **Magi** — House benefit as a free extra, apprenticeship XP, Arts, spell
   picker, Gauntlet years. Affinity/Puissant as encoded modifiers on the
   handful of creation-time effects.
4. **Templates** — start from the 23 Core catalog templates; user edits from
   there (best-effort prefills from the stat block, not a full reverse parse).
   Changing Wealthy/Poor/age/House recomputes the pools.
5. **Save / print / Markdown / JSON** — Workspace `Character` overlay, print-only
   HTML, Markdown (posted sheet), JSON (`clavis.character/1`: identity, scores,
   slugs, play totals, plus `worksheet` for a later import). Opening a saved row
   loads it back into `/gen/new/` (the worksheet is the editor).
6. **Play numbers** ✅ — optional toggle on the sheet, off by default so a posted
   character stays compact. Always present in JSON. Soak, fatigue, wound
   brackets, Dodge/Brawl, magus TeFo grid (formulaic / fatigue spont / no
   fatigue / quiet+subtle / thought), lab base, Fast Cast, Concentration, MR,
   Ceremonial, aura note. Weapons/armor rows stay empty until catalog items feed
   them.
7. **PDF fill** ✅ — user uploads their own ArMD B&W/COLOR FILLABLE sheet;
   Clavis fingerprints AcroForm names and fills from the worksheet. See below.
8. *(Later)* Mythic Companions; remaining Social Status tags; supplement V/F
   as an opt-in book filter; hook into the planned spontaneous calculator;
   Might-score characters.

Milestones 1–5 need no new dependencies and no API key.

## Open questions

- Whether house benefits are a free extra Virtue or an applied modifier —
  encode the Core table literally, do not guess.
- Extremely Complex Character Generation stays out of scope.
- A Gifted companion is legal (toggle + note), not a separate type.
- Print CSS vs. a downloaded markdown sheet — both: print-only HTML and `.md`.
- UI name: ClavisGen for the product; page title **New character**.

## PDF fill (do not ship Atlas PDFs)

Do **not** fetch a URL the player pastes (SSRF, Google Drive auth, we would
mirror Atlas files). The player **uploads** their copy; we fill and return it.

Sheets:

| File | Fillable? | Notes |
|------|-----------|--------|
| Classic B&W `arm5charactersheet.pdf` (the layout many troupes prefer) | No | Print-only. Browser print-to-PDF remains the path. |
| Classic color `arm5charactersheetnew.pdf` | No | Same. |
| **ArMD Character Sheet B&W FILLABLE** (Atlas AG0215 Drive) | Yes | Semantic fields: `Creo`, `ABILITY 1`…`30`, `SPELL`…, `Virtues 1`…, `Soak`, `Str`… |
| **ArMD Character Sheet COLOR FILLABLE** | Yes | Same names plus `Weapons 1`…`6`, wound labels. |
| Germanitas `arm5char_fillable.pdf` | Yes, but `Text1`…`Text46z` | Fragile index map. Ignore unless someone only has that file. |

Shipped (2026-10): fingerprint by AcroForm field *names* (not filename or
bytes). `pypdf` writes `/V` and sets NeedAppearances — some viewers need a
click or a save to show the values. Clavis never fetches a URL and never
vendors the Atlas blank.

This file’s ArMD B&W FILLABLE fingerprint (632 fields) includes `Creo`,
`ABILITY 1`–`30`, `Virtues 1`, `SPELL` / `SPELL_2`…, `Intelligence Score`.
Identity uses `Text140` (Character), `Text6`–`Text9` (House / Age / Size /
Confidence). Characteristic scores besides Int sit in colliding
`undefined_*` boxes and are filled by page-1 position. Named `Str` / `Per`
/ `Soak` / `Size` on this sheet are the familiar block — left alone.
Germanitas (`Text1`… without those markers) is recognized and refused.
Classic print (no AcroForm) is refused. Extra abilities past 30 and spells
past 12 are truncated. Tests use a synthetic AcroForm only.

## Atlas manuscript styles vs Clavis

The ArM5 Word template and Style Guide are **author instructions for Atlas
layout**, not CSS for this app. Clavis already renders imported Markdown; do
not invent ArM5 Word styles in the Reader.

Use the **character-insert rules** as the target for ClavisGen's *posted*
sheet and JSON, where they do not fight an existing ClavisGen choice:

Do now or next (sheet / JSON):

- [x] Compact posted sheet without play numbers
- [x] Optional play: Combat, Soak, Fatigue, Wounds
- [ ] Sort Virtues/Flaws: The Gift; Social Status; Major Virtues A–Z; Minor
      Virtues A–Z; Major Flaws A–Z; Minor Flaws A–Z (semicolons between groups)
- [ ] Personality and Reputation: high score first, then A–Z
- [ ] Abilities already alphabetical; leftover XP already in parentheses;
      Puissant as `x+2`
- [x] Official insert puts specialty after the score (`Athletics 3 (running)`)
- [x] Positive Characteristics use `+` (`Int +2`); 0 stays `0`; negatives
      keep `−`. Play/JSON keep integers
- [ ] Spell line already `Name (TeFo level/+casting)` without aura/cyclic
- [ ] Casting bonus includes Stamina; not aura
- [ ] Omit empty blocks (no Arts on grogs)
- [ ] `Area Lore: Place` when we collect that Ability
- [ ] Encumbrance and weapon lines once Load/weapons exist
- [ ] Appearance paragraph is troupe text, not generator arithmetic

Ignore for Clavis (manuscript process):

- ArM5 Word styles, ODT, heading hierarchy for chapters, no tables, art
  guidelines, author lists, playtest process, US spell-check, that/which,
  Diedne/future-history/human-sacrifice, hedge-magic design for *writing*
  supplements, "you" = player in running text

Ease Factors as multiples of 3 only if ClavisGen starts showing contest EFs.
