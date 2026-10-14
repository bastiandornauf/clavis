# Plan: Spontaneous spell calculator

Status: **planned, not implemented** (2026-10).

## Goal

A player describes an effect ("make my shadow look like a guard for the scene")
and Clavis helps answer three table questions, always with a link to the rule text:

1. Which Technique + Form and which **guideline** fit?
2. What **level** does the effect have at the chosen Range / Duration / Target?
3. Can this magus cast it **spontaneously**, and how likely is it?

Clavis proposes; the player and storyguide decide. The calculator never hides the
guideline text or the rules it applied.

## What the rules need (Definitive Edition core)

All of this is in the imported Core text and can be cited by `stable_id`:

| Piece | Rule | Source section |
|-------|------|----------------|
| Base level | Guideline level, assuming Personal / Momentary / Individual | Form guideline sections (`chapter-9-spells/*-guidelines`) |
| R / D / T | +1 magnitude per table step (Range: Personal 0, Touch/Eye 1, Voice 2, Sight 3, Arcane Connection 4; Duration: Momentary 0, Concentration/Diameter 1, Sun/Ring 2, Moon 3, Year 4; Target: Individual 0, Part 1, Group 2 … with Container and Sense columns) | `reference-guide/magic-rules/casting-spells/ranges-durations-and-targets` |
| Magnitude | Level / 5, rounded up; low levels (1–5) step differently | `chapter-9-spells/magnitudes` (refers to a table on p. 303) |
| Size | +1 magnitude per ×10 of the base Individual | `chapter-9-spells/targets-and-sizes` |
| Spontaneous total | Fatiguing: (Casting Score + stress die) / 2; non-fatiguing: Casting Score / 5 | `reference-guide/magic-rules/casting-spells/spontaneous-magic` |
| Sequence | Effect → fatigue choice → compare total → Penetration vs Magic Resistance | `…/spontaneous-spellcasting-sequence` |

Casting Score = Technique + Form + Stamina + aura (+ other bonuses the player
enters). The exact low-level stepping must be checked against the Core table
during implementation (see open questions).

## What Clavis already has

- **581 guidelines** in the Lexicon, all with Technique + Form, 561 with a base
  level (20 are "General"). 562 come from Core; the rest from Art & Academe,
  Houses of Hermes, Covenants, Legends of Hermes.
- **Spell workshop** grid: Technique × Form cell → guidelines + published spells.
- **1,883 published spells** with level and R/D/T. The R/D/T values are uniform:
  the 14 most common Range values cover 99 %, Duration 95 %, Target 89 % of spells
  (the rest are supplement values like Road, Bloodline, Cousin, Performance).
- **Local meaning index** (fastembed, offline): rank sections or Lexicon entries by
  a free-text description.

## Gap: guidelines share one section

Meaning ranking works on **section** vectors. Guidelines sit 10–30 per section
("Creo Ignem Guidelines"), so the current *Describe* filter cannot tell guidelines
in the same section apart — it would rank whole Form chapters, not single
guidelines. Published spells are mostly one per section, so ranking those works today.

Fix (local, no API key): embed each guideline's own text (the entry name already
holds the full guideline sentence) with the same local model. 581 short texts take
seconds. Store as entry vectors next to the section index.

## User flow (v1)

1. **Pick the guideline**, either:
   - *Browse*: choose Technique + Form → list of that cell's guidelines (reuses the
     workshop cell), or
   - *Describe*: free text → top guidelines across all cells, plus published
     spells that read similarly.
2. **Adjust**: Range / Duration / Target dropdowns from the Core table, size steps,
   and an "extra magnitudes" field for guideline-specific modifiers ("+1 per
   additional sense", requisites the storyguide adds). Supplement R/D/T go in as
   "Other (+N magnitudes)".
3. **Result**: level with a step-by-step breakdown ("Base 4 → Voice +2 → Sun +2 →
   Group +2 = 25"), magnitude, guideline text, links to the rule sections.
4. **Casting** (optional): Technique, Form, Stamina, aura, other → non-fatiguing
   total, fatiguing total needed on the die, and the chance of success with a
   stress die; Penetration Total against an entered Magic Resistance.
5. **Precedents**: published spells of the same Technique + Form near that level
   ("Pilum of Fire, CrIg 20, Voice/Mom/Ind") as a plausibility check.

Nothing is saved in v1. Later: "save to campaign" as a campaign note keyed by
the guideline's `stable_id`.

## Where the code goes

- `apps.catalog.spell_design` (service): R/D/T step tables with source
  `stable_id`s, `effect_level(base, steps, extra)`, `casting_totals(...)`,
  stress-die success probability. Pure functions, fully unit-tested.
- Guideline lookup by description: `apps.catalog.similarity` (extends the
  existing Describe logic with entry vectors).
- View + template under the Lexicon (`/lexicon/workshop/calculator/`), a
  "Calculate" link on every guideline detail page and workshop cell.
- No new parser, no second citation formatter: links use the existing reader URLs.

## How well this can work — realistic estimate

| Part | With current tech (offline) | Confidence |
|------|-----------------------------|------------|
| Level arithmetic, casting totals, probability | Deterministic | **Very high** — only risk is getting the low-level rule wrong, which tests against the Core table catch |
| Browse to guideline (Te + Fo chosen by player) | Existing data | **High** — 581 guidelines, workshop already shows them |
| Common R/D/T | Core table | **High** for ~95 % of real cases; supplement values via "Other" |
| Free text → right guideline in top 5 | Needs per-guideline vectors | **Medium**: good for concrete wording ("set a target on fire", "read surface thoughts"), weak when the effect needs Hermetic reasoning ("shadow looks like a guard" is Muto vs Creo Imaginem; "fly" is Rego Corpus, not Auram). Rough guess 60–75 % top-5 hit rate; to be measured |
| Guideline-specific modifiers (requisites, "+1 per sense", Form-specific base sizes) | Text only, not parsed | **Low** to automate; v1 shows the text plus a manual "extra magnitudes" field |
| Choosing R/D/T from the description ("for the scene" → Sun) | Not planned offline | Player picks; a small keyword hint table is possible later |

Before shipping *Describe*, build a test set of ~30 effect descriptions with the
expected guideline (taken from published spells: their description → their
Technique + Form + guideline). Ship *Describe* only if top-5 hits ≥ 70 %;
otherwise keep Browse as the main path and Describe as "suggestions".

## What an API key (LLM) would add

An LLM would help with the parts that need **Hermetic reasoning**: mapping a vague
description to Technique + Form, picking R/D/T from wording, spotting requisites
and guideline modifiers. Expected effect: Describe gets noticeably better
(likely 85–90 % top-5, still needs review), and the form could be pre-filled.

It should be strictly bounded:

- The model only **chooses from our guideline list** (by entry ID) and proposes
  R/D/T + extra magnitudes with a one-line reason each.
- **Clavis computes the level**, never the model; every number links to rule text.
- Optional and off by default; without `CLAVIS_LLM_API_KEY` the calculator works
  fully via Browse / local Describe.

This contradicts ADR 0002 ("networked LLM providers remain deferred"), so it
needs an explicit decision and a new ADR. Cost per request is tiny (one short
prompt with ≤ 30 candidate guidelines), but it breaks "fully offline" for that
feature and sends the player's description to a provider.

**Recommendation:** build v1 without an API key (Browse + arithmetic + casting +
precedents), then add local per-guideline Describe and measure it. Decide about
the LLM only if the measured Describe hit rate is not good enough in play.

## Milestones

1. **Arithmetic core** — `spell_design` service + tests (R/D/T table, low-level
   steps, size, totals, stress-die probability). No UI.
2. **Calculator page via Browse** — guideline picker from the workshop, R/D/T form,
   breakdown, rule links, "Calculate" links from guideline detail / workshop.
3. **Precedent spells** — same Te + Fo, nearby levels, similar description.
4. **Local Describe** — per-guideline vectors, evaluation set, ship gate ≥ 70 %.
5. *(Optional, needs ADR)* LLM suggestions bounded as above.

Milestones 1–3 need no new dependencies and no API key.

## Open questions

- Exact low-level stepping (levels 1–5) from the Core table on p. 303 — is that
  table in the imported Markdown? If not, encode it from the Core text and cite
  the Magnitudes section.
- How much of the Form-specific Target notes (Imaginem senses, Terram base
  volumes, Corpus/Animal sizes) to show inline vs. as links.
- Whether supplement R/D/T (Road, Bloodline, Performance …) get a hand-maintained
  table with citations, or stay as "Other (+N)".
- Ceremonial / fast casting modifiers in v1 or later.
