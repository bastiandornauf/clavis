# Clavis

Local Ars Magica source archive: readable books, full-text search, a rule-based
lexicon, bookmarks, notes, and campaign collections.

**Repository:** <https://github.com/bastiandornauf/clavis>

Clavis runs on your machine (for example a Mac mini). You do not need to host it
for other people. Others can install the same software themselves.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Git (to sync the Open License Markdown repository)

## Quick start

```bash
git clone https://github.com/bastiandornauf/clavis.git
cd clavis
uv sync
uv run python manage.py migrate
uv run python manage.py import_sources
uv run python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

### Import options

```bash
# Full corpus from GitHub (recommended)
uv run python manage.py import_sources

# Re-import without pulling
uv run python manage.py import_sources --no-sync

# Import Markdown from a local folder (tests / offline fixtures)
uv run python manage.py import_sources --path tests/fixtures/markdown

# Optional: three Phase-1 pilot books only
uv run python manage.py import_sources --pilot
```

Reviewed source files are preferred over work-in-progress when both exist for
the same work (for example Definitive Edition replaces the old Core Rules WIP).

## What you get

| Area | Features |
|---|---|
| **Library / Reader** | Nested TOC, breadcrumbs, single section or include subsections, similar passages, gallery, guides |
| **Search** | Full-text (FTS5) across imported books; optional local meaning search |
| **Lexicon** | Rule-extracted spells (Hermetic / non-Hermetic), virtues, flaws, story seeds, creatures, beasts, characters, guidelines, abilities, boons, hooks, organizations, places, items; spell workshop; "mentioned in" links |
| **Saved / Campaigns** | Bookmarks, notes, campaign excerpts (local overlays) |
| **Sources** | Sync from the Open License repo, update check, import history |

Personal notes, bookmarks, and campaigns live in SQLite under `CLAVIS_DATA_DIR`
and never modify imported Markdown.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CLAVIS_DATA_DIR` | `./data` | Database, source clone, backups, collected static |
| `CLAVIS_SOURCE_REPO_URL` | Ars Magica Open License GitHub URL | Source repository |
| `CLAVIS_APP_REPO_URL` | `https://github.com/bastiandornauf/clavis` | Link shown in the app footer |
| `DJANGO_SECRET_KEY` | dev default | Set a real secret for non-dev use |
| `DJANGO_DEBUG` | `1` | Set `0` to disable debug |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated hosts |

## Backup

Copy the entire `CLAVIS_DATA_DIR` directory. Before each import Clavis also writes
a SQLite backup under `CLAVIS_DATA_DIR/backups/`.

## Optional Docker

```bash
docker compose up --build
```

Native `uv` install remains the primary path; Compose is a convenience wrapper.

## Development

```bash
uv run pytest
uv run ruff check .
```

Coding standards: **[docs/coding-standards.md](docs/coding-standards.md)**  
Architecture: **[docs/architecture.md](docs/architecture.md)**  
Lexicon plan: **[docs/catalog-coverage.md](docs/catalog-coverage.md)**  
Contributing: **[CONTRIBUTING.md](CONTRIBUTING.md)**

## License

| Part | License |
|---|---|
| **Clavis application code** | [MIT](LICENSE) — free to use, modify, and share; keep the copyright notice |
| **Ars Magica texts** | CC BY-SA 4.0 via the separate Open License corpus — see [NOTICE.md](NOTICE.md) |

Clavis does not ship book text in this repository. Import pulls Markdown from the
[Ars Magica Open License](https://github.com/OriginalMadman/Ars-Magica-Open-License)
project. Clavis is independent and not affiliated with Atlas Games.

## Meaning search (optional, local)

Search can also match by meaning ("faerie queen marries a baby heir" finds
*Birth Right* in *Hooks*). It runs a small model on your machine — no API key.
Build the index once (downloads ~65 MB on first run, ≈30 min for all books):

```bash
uv run python manage.py rebuild_embeddings
```

Afterwards Search offers Keyword / Meaning / Keyword + meaning, and imports keep
the index current. Interrupted runs resume.

## Deferred features

Remote LLM enrichment and generative chat/RAG stay out of scope until explicitly
requested. See `docs/architecture.md`.
