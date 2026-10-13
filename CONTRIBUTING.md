# Contributing to Clavis

## Coding standards (read first)

**[docs/coding-standards.md](docs/coding-standards.md)** is the binding policy for
programming style, code design, reuse, testing, and the definition of done.

It is based on Google Engineering Practices, Django design philosophies, PEP 8,
GitHub Flow, ADRs, WCAG 2.2 AA, and Clavis-specific rules (one Markdown parser,
stable IDs, sources vs. personal overlays, shared UI components).

Also see:

- [docs/architecture.md](docs/architecture.md)
- [docs/design-system.md](docs/design-system.md)
- [AGENTS.md](AGENTS.md) for coding-agent hard rules

## Workflow

1. Clarify purpose, scope, and acceptance criteria before coding.
2. Work on a short-lived branch (GitHub Flow).
3. Prefer small, runnable increments.
4. Reuse existing services and templates before adding new ones.
5. Open a reviewable change; keep unrelated work out.

## Checks before you finish

```bash
uv sync
uv run python manage.py migrate
uv run pytest
uv run ruff check .
```

## Definition of done (summary)

Full criteria: [docs/coding-standards.md](docs/coding-standards.md#14-shared-definition-of-done).

- Acceptance criteria met
- Existing helpers/components reused where appropriate
- `pytest` and `ruff` clean
- Docs updated when behavior or setup changes
- Empty/error/loading states handled for UI work
