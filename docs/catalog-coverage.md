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

| Type | Detection sketch (from book survey) | Why |
|---|---|---|
| **Boon / Hook** | *Covenants* Ch.2: parent heading `Major/Minor … Boons/Hooks`; entries are bold lines `**Aura:**` / `**Immunity:**` in the body (not italic VF-style) | Covenant design |
| **Covenant / Place** | Tribunal books (e.g. *Against the Dark*): named sites / oppida; optional Aura in lead; many are narrative H3/H4 without a single template | Setting prep |
| **Organization** | *True Lineages*: House chapters + named offices (`Colentes Arcanorum`, `Seekers`, `Domus Magna`) | Politics / affiliation |
| **Enchanted item / Lab** | Named enchanted items appear as short H5 writeups (`Chest of Good Food`); *Covenants* lab chapter is mostly lab *virtues/rules*, not item catalog — pair with adventure/tribunal books for items | Long-term play |

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

### Book survey notes (Core + Covenants + Realms)

Pilots read: **Definitive Edition**, **Covenants**, **Through the Aegis** (wip),
**Realms of Power: Faerie / Magic**, **Mythic Locations**, plus earlier tribunal/
True Lineages notes. *Hooks* the supplement is **adventure scenarios**, not the
covenant Boon/Hook list — do not treat it as a Boon source.

**Existing rules on these books (spot-check):**
- Core: strong on spells / VF / abilities / guidelines; Might-creatures OK;
  mundane bestiary beasts correctly *not* creatures (no Might).
- Covenants book: almost no catalog yet (expected — Boons unused).
- RoP Faerie/Magic: virtues/flaws + creatures present; places/tethers not typed.
- Mythic Locations: place chapters mostly untyped; embedded Might callouts
  correctly become creatures (e.g. Anne / Minerva Sulis).

**Boon / Hook formats (three shapes):**
1. **Covenants** Ch.2 — parent `Major Site Boons` etc.; body `**Aura:**` blocks.
2. **Core** Ch.6 — shorter lists under `Major/Minor Boons|Hooks`; mostly same
   bold pattern, but some **Minor Hooks** start as plain `Contested Resource:`
   (no `**`).
3. **Through the Aegis** — applied picks:
   `**Mystical Allies (Major Surroundings Boon):**` (magnitude inside the name).

**Places / covenants:**
- Core Ch.6 example covenants by season (Vernus, Aestas, …) — short profiles.
- Mythic Locations — whole book is places, but narrative (no single Aura lead).
- RoP Magic — “Natural Tethers” (Caves, Forest, …) are aura *types*, not named sites.
- Tribunal / Aegis — named covenants as chapter roots (`Jardin: A Summer Covenant`).

**Organizations:**
- Core Ch.2 `House Bonisagus` … short blurbs (good stubs).
- True Lineages — deep offices under each House.

**Items / lab:**
- Core Ch.8 + Covenants Ch.9 = procedures / lab virtues, not item cards.
- Named enchanted items appear in Aegis/tribunals (`Joia's Trowel`, …).

### Mundane beasts ✅

Separate Lexicon type **beast** (GM-facing animals without Realm Might):
`Characteristics: … Cun …` + Size/Qualities. Core bestiary + matching writeups.

### WP4 — Boons & Hooks ✅

Pilot: **Covenants** (full list) + **Core** Ch.6 (short list; handle plain-text
Minor Hooks) + spot-check **Through the Aegis** applied lines.
- Detect definition sections by title Major/Minor + Boon/Hook (+ Site/…).
- Extract bold (and Core plain) name lines → one entry each.
- Fields: name, magnitude, category, summary, evidence.
- Do **not** use the *Hooks* adventure book as source.

### WP5 — Places / Covenants ✅ (narrow, high precision)

Named covenants/oppida (`The Covenant of…`, `Jardin: A Summer Covenant`,
Core Vernus/Aestas/…) — not every Mythic Locations chapter yet.

### WP6 — Organizations ✅

Core House blurbs + True Lineages offices under House organization paths.

### WP7 — Enchanted items ✅ (narrow)

`This enchanted item` writeups only; lab procedure chapters excluded.
Lab projects still deferred.

### WP8 — Optional enrichment pass ✅ (scaffold)

### WP8 — Optional enrichment pass ✅ (scaffold)

- Command `enrich_catalog` (default `--provider dry-run`, no network).
- `EnrichmentProposal` rows; accept promotes `CatalogEntry` with `extractor=llm`.
- Remote LLM provider stub refuses without a wired implementation / API key.
- Search UI stays keyword-only until a real embedding model exists.

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
- Generative RAG / chat answers (semantic/hybrid search is a separate shipped track)

## Decision checkpoints

After each WP, stop and check:

- False-positive rate on 20–50 spot checks
- Whether Coverage density moved for the intended books
- Whether table/filter UX still works with the new volume
