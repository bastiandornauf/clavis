# Architecture

Clavis is a local Django application that turns Ars Magica Open License Markdown
into a readable, searchable library with personal campaign overlays.

## Modules

| Module | Responsibility |
|---|---|
| `apps.sources` | Git sync, source snapshots, import orchestration, DB backup |
| `apps.library` | Books and sections, Markdown structural parse, stable IDs, released-image gallery, curated Guides links |
| `apps.reader` | TOC, section rendering, navigation |
| `apps.search` | SQLite FTS5 + optional section embeddings (keyword / semantic / hybrid) |
| `apps.annotations` | Bookmarks, notes, last-read position (lists live under Workspace) |
| `apps.campaigns` | Workspace hub (campaigns / bookmarks / notes tabs) + campaign detail |
| `apps.catalog` | Rule-based lexicon (incl. beasts, boons/hooks, orgs, places, items) + reviewable enrichment leftovers |

Shared library code lives under `src/clavis/`:

- `clavis.markdown` — parse sections + render safe HTML (title escape decode)
- `clavis.citations` — Book → Chapter → Section (+ commit)

The Library **Gallery** browses `released-images/` from the Open License checkout.
PNG/JPEG serve directly; TIFF/TIF are converted to cached PNG previews under
`data/cache/released-images/` (Pillow).

**Guides** (`/guides/`) is a curated external-link shelf driven by
`apps/library/guides.json`. It is not imported into the corpus, FTS, or Lexicon—
Library remains primary Open License sources only.

A session preference **Reviewed only** (header toggle) limits Library, Search, and
Lexicon lists/counts to `review_status=reviewed`. Direct URLs to WIP sections
still resolve.

## Data flow

1. User triggers import (UI or `import_sources` command).
2. Sources module clones/pulls the configured git repo (unless `--path` / `--no-sync`).
3. Library prefers `reviewed/` over `wip/` for the same filename; `3rd-party/` is separate.
4. Each Markdown file becomes a `Book` with a tree of `Section` rows.
5. Search rebuilds FTS5 rows for imported books.
6. Catalog rebuilds rule-based lexicon entries for those books.
7. Campaign excerpt integrity flags are refreshed.
8. Older snapshot books are removed; annotations remain keyed by `stable_id`.

## Identity

- `Section.stable_id = sha256(book_slug + ":" + section_path)`
- Bookmarks, notes, and campaign items store `stable_id` plus book slug/path hints.
- Source citations use Book → Chapter → Section and the import commit SHA. Page numbers are not used.

## Catalog coverage (Tier A shipped)

Rules currently recognize:

- **Spells** — section body with `R:/D:/T:` params; level from parent `LEVEL N` heading
- **Virtues / Flaws** — classic `*Major/Minor, Category*`, category-first italics (`*Social Status, Major*`), plain `Major/Minor … Virtue/Flaw`, and bold-packed blocks under Virtues/Flaws chapter headings
- **Story seeds** — `Story Seed:` headings and body lines
- **Creatures** — `Magic/Faerie/Infernal/Divine Might` within the lead window
- **Characters** — Age / Personality / Magus-style bold headers (with Hermetic house from title or body)
- **Guidelines** — `Creo Ignem Guidelines`-style tables with base levels
- **Abilities** — writeups with `*Specialties: … (Category)*`

Heading titles decode CommonMark escapes (`Ceremony\*` → `Ceremony*`) for display and catalog names. Unrecognized content remains available via full-text search.

## AI overlays (shipped scaffold)

- **Enrichment** — `uv run python manage.py enrich_catalog [--dry-run]` scans
  rule leftovers; default is **typed/signal only** (Might / Specialties misses),
  not a dump of every heading. `--include-untyped` is opt-in noise.
  Cleanup: `--clear-noise`. Accept: `--accept-pending` or admin.
- **Embeddings (meaning search)** — `rebuild_embeddings` runs the local ONNX model
  `BAAI/bge-small-en-v1.5` via fastembed (384 dims, title + first ~2000 chars per
  section; model cached in `CLAVIS_DATA_DIR/cache/models`, offline afterwards).
  Rows are saved per batch; reruns skip unchanged sections and re-imports copy
  vectors by `content_hash`. Search shows Keyword / Meaning / Keyword + meaning
  only once vectors for the active model exist (`semantic_search_available`).
  Scoring is a numpy matrix product over an in-process cache. `hashing-v1` is
  the dependency-free test backend and never enables the UI on its own.

## Deferred phases

5. Redistributable catalog packs; more entry types (lab projects, …)
6. Long-section chunking for embeddings (one vector per section today)
7. Later: grounded RAG assistant, campaign AI, saga profiles
