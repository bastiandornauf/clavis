# Lexicon coverage plan

Goal: make the lexicon as complete as is **reliably possible with rules**,
without pretending uncatalogued text does not exist. Full-text search remains
the fallback; Coverage must stay honest.

Corpus surveyed: 54 Markdown books (`reviewed` + `wip`). Current install still
has the three pilot books imported.

## Current state (Tier A extractors shipped)

| Type | Status | Notes |
|---|---|---|
| Spells | shipped | R/D/T near top; creature powers largely excluded |
| Virtues / Flaws | shipped | Italic both orders, plain lines, bold blocks, chapter path |
| Story seeds | shipped | Headings + blockquote/body lines; short prose labels |
| Creatures | shipped | Might lead within ~400 chars |
| Characters | shipped | Age / Magus headers; house from title or body |
| Guidelines | shipped | Tech+Form guideline tables |
| Abilities | shipped | Specialties + category line |

Rough corpus signal (all 54 files, pattern hits ≠ unique entries):

| Signal | Hits | Interpret as |
|---|---:|---|
| Spell R/D/T lines | ~1486 | Spell writeups (+ some powers) |
| Virtue/Flaw italic leads | ~1282 | Character options |
| Story Seed lines | ~1012 | Adventure hooks |
| Characteristics blocks | ~748 | Creatures / NSC / beasts |
| Magic/Faerie/Infernal/Divine Might | ~434 | Realm creatures |
| Age: lines | ~414 | Named characters / magi |
| LEVEL headings | ~423 | Spell level bands |
| Covenant-ish headings | ~195 | Places / covenants |
| Guidelines headings | ~169 | Spell guidelines |
| Magus/Maga headers | ~50 | Named magi (strict pattern) |

## Design principles

1. **Definition first** — full writeups before loose mentions.
2. **Evidence required** — every field ties back to source text.
3. **Unknown is allowed** — missing Aura/Might stays empty, never guessed.
4. **Coverage UI tells truth** — thin/search-only books are expected early.
5. **Rules before LLM** — LLM only for leftovers after rules plateau.
6. **One extractor family per type** — extend `apps.catalog.extractors`, no
   parallel parsers.

## Proposed entry types (priority order)

### Tier A — high value, strong patterns (do next)

| Type | Detection sketch | Why |
|---|---|---|
| **Creature** | `Magic/Faerie/Infernal/Divine Might` near start + often Characteristics | Spieltisch-Gegner/NSC-Werte |
| **Character** | `**Name, Magus/Maga…**` or `**Age:**` + Personality Traits; not Might-led | Named magi / companions in tribunal books |
| **Guideline** | Heading contains Guideline / Base … under Technique·Form parents | Spell design companion to Spells |
| **Ability** | Chapter-5 style headings + category line (General/Academic/…) | Character creation |

### Tier B — strong saga value, messier structure

| Type | Detection sketch | Why |
|---|---|---|
| **Covenant / Place** | Tribunal book chapter structure; named site headings; optional Aura | Setting prep |
| **Organization** | House X, Mystery Cult, League, Tribunal institutions | Politics / affiliation |
| **Boon / Hook** | `*Major/Minor Boon/Hook*` (Covenants economy) | Covenant design |
| **Enchanted item / Lab project** | Lab chapter patterns, effect levels | Long-term play |

### Tier C — useful later / needs LLM or heavy editorial tags

| Type | Notes |
|---|---|
| **Rule topic** | Cross-cutting rules without fixed template |
| **Region / Tribunal overview** | Often long narrative chapters |
| **Creature role tags** | Guardian / tempter / patron — editorial, not RAW fields |
| **Mentions graph** | Same name elsewhere; link after definitions are stable |

## Completeness model (what “complete” means)

Not “every paragraph is an entry.” Complete means:

1. **All books imported** (reviewed preferred over wip).
2. **Tier A types** extracted with acceptable precision on Core + one tribunal +
   one Realms book, then measured on full corpus.
3. **Coverage page** shows per book × type counts + density.
4. **Precision gate**: sample audit (e.g. 50 random hits/type) before expanding.
5. Leftovers stay searchable; optional LLM enrichment is Tier D.

Suggested quality targets (rules phase):

| Type | Precision | Recall (vs pattern hits) |
|---|---|---|
| Spell | ≥ 90% | ≥ 70% of true spell writeups |
| Virtue/Flaw | ≥ 90% | ≥ 80% of italic writeups |
| Story seed | ≥ 85% | ≥ 70% of Seed lines |
| Creature | ≥ 85% | ≥ 75% of Might-led blocks |
| Character | ≥ 80% | Best-effort on Age/Magus headers |
| Guideline | ≥ 85% | ≥ 70% of Guideline headings |

## Work packages

### WP0 — Foundation (short)

- Import **full corpus** (not only pilot).
- Extend Coverage table for every entry type.
- Add per-type “pattern estimate vs extracted” on Coverage (optional debug).
- Keep result counts on filtered lexicon lists (done).

### WP1 — Creatures ✅

- Lead: Might line within first ~400 chars of section body.
- Fields: realm, might, size (if present), season, summary sentence.

### WP2 — Characters (named people) ✅

- Distinct from Creature: no Might lead, or explicit Magus/Maga header.
- Fields: name, house/tradition if present, age band, one-line role summary.
- One section may yield **multiple** characters from bold name lines.

### WP3 — Guidelines + Abilities ✅

- Guidelines: `Creo Ignem Guidelines` tables → base-level entries.
- Abilities: `*Specialties: … (Category)*` writeups.

### WP4 — Places / Covenants / Organizations

- Start with named covenants in tribunal books; Aura when explicit.
- Houses as organizations from Core “Houses of Hermes” sections.

### WP5 — Boons/Hooks + Lab/Items

- After covenant model exists so links make sense.

### WP6 — Optional LLM pass

- Only unclassified “interesting” headings / leftover Might failures.
- Store as `extractor=llm`, always reviewable, app works offline without key.

## Suggested sequence for you

1. **Full import now** — unlocks search everywhere; Coverage becomes meaningful.
2. **WP1 Creatures** — biggest gap vs pattern volume after current four types.
3. **WP2 Characters** — matches how you already read tribunal books.
4. **WP3 Guidelines** — pairs with Spells for play utility.
5. Then Places/Covenants as saga prep deepens.

## Out of scope for “complete coverage”

- Replacing reading with chat answers
- Perfect OCR/structure fixes in upstream Markdown
- Guaranteed extraction of every narrative NPC without a template
- Semantic search (separate track; helps find uncatalogued text)

## Decision checkpoints

After each WP, stop and check:

- False-positive rate on 20–50 spot checks
- Whether Coverage density moved for the intended books
- Whether table/filter UX still works with the new volume
