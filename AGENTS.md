# Agent instructions for Clavis

Coding agents must follow:

1. **[docs/coding-standards.md](docs/coding-standards.md)** — programming style and code design (authoritative)
2. [CONTRIBUTING.md](CONTRIBUTING.md) — workflow and done criteria
3. [docs/architecture.md](docs/architecture.md) — module boundaries
4. [docs/design-system.md](docs/design-system.md) — UI tokens and shared components

Do not invent a parallel set of rules. If guidance conflicts, coding-standards wins
for style/design; architecture wins for module ownership.

## Hard rules

- Do not edit imported Ars Magica Markdown in place.
- Do not add CDN dependencies for CSS/JS/fonts — vendor under `static/`.
- Do not introduce a second Markdown parser or a second citation formatter.
- Catalog rule extractors live in `apps.catalog.extractors` — extend there, do not
  duplicate parsing in templates.
- Do not implement LLM enrichment, generative chat, or semantic search unless
  explicitly asked; those remain deferred.

- Keep the UI language English.
- Prefer extending existing Django apps and `src/clavis/` packages over new
  top-level utilities.
- Store user overlays (bookmarks, notes, campaigns) by `stable_id`, not by
  transient DB PKs alone.
- Templates present; domain logic lives in services.
- Reuse before inventing; no dumping-ground `utils` modules.
- When changing import behavior, update tests under `tests/` and fixtures if needed.
- Ship small, runnable increments with clear acceptance criteria.

## Preferred commands

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py import_sources --path tests/fixtures/markdown
uv run pytest
uv run ruff check .
```
