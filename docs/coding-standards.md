# Coding standards and code design

This document is the authoritative programming-style and code-design policy for
Clavis. It captures the rules agreed during project planning. Keep them here;
link from elsewhere instead of copying.

Related documents:

- [CONTRIBUTING.md](../CONTRIBUTING.md) — workflow and definition of done
- [AGENTS.md](../AGENTS.md) — hard rules for coding agents
- [architecture.md](architecture.md) — module boundaries and data flow
- [design-system.md](design-system.md) — UI tokens and shared components
- [decisions/](decisions/) — Architecture Decision Records

## Established foundations

We adopt proven guidelines and only add Clavis-specific rules on top:

| Foundation | What we take from it |
|---|---|
| [Google Engineering Practices](https://google.github.io/eng-practices/) | Small changes; readable code; review for design, complexity, tests, naming, docs |
| [Django design philosophies](https://docs.djangoproject.com/en/stable/misc/design-philosophies/) | Loose coupling, DRY, explicit is better than implicit, shared templates |
| [PEP 8](https://peps.python.org/pep-0008/) | Python style and naming — enforced with Ruff |
| [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow) | Short-lived branches, review, merge |
| [Architecture Decision Records](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) | Short records of important technical choices |
| [WCAG 2.2](https://www.w3.org/TR/WCAG22/) Level AA | Keyboard use, contrast, focus, understandable forms |
| [GOV.UK Design System](https://design-system.service.gov.uk/components/) approach | Documented, reusable UI components with clear usage rules |
| [Kevin Powell — smart / breakpoint-free layouts](https://www.kevinpowell.co/talks/smart-layout-patterns/) | Intrinsic CSS: container queries, auto-fit grids, `clamp()`, subgrid, cascade layers — as implementation references only |

Two standing principles:

- **KISS** — choose the simplest solution that meets the real requirement.
- **YAGNI** — do not build extensions until they are needed. “Scalable” alone does
  not justify extra services, queues, or plugin frameworks.

### DRY, correctly understood

A business rule or shared concern has **one authoritative implementation**.
Reader, search, and campaigns must not invent their own citation links, section
identity, or Markdown interpretation.

That does **not** mean every similar-looking snippet must be abstracted.
A forced shared helper that does not fit both call sites is worse than a little
honest duplication. Prefer reuse of existing named functions and components;
avoid a dumping-ground `utils` module.

---

## 1. Clarify requirements before implementation

Every task states purpose, scope, and verifiable acceptance criteria.

- Too vague: “Improve search.”
- Usable: “Hits show book and section; opening a hit keeps the current filters.”

New ideas go on a task list. They expand an in-progress task only by deliberate
decision, not by silent scope creep.

## 2. Develop in small, working steps

Each change delivers a bounded, usable increment. Do not combine large refactors
with new features and redesigns in one change.

The application must remain startable after every completed step. Incomplete
side features must not block existing ones.

## 3. Modular application with clear responsibilities

Clavis is one application with bounded modules:

| Module | Responsibility |
|---|---|
| **sources** | Repository sync and source snapshot |
| **library** | Books, chapters, sections, source metadata |
| **reader** | Presentation and navigation of book text |
| **search** | Indexing, queries, hit presentation |
| **catalog** | Structured entries and evidence (deferred) |
| **campaigns** | Campaigns and collected sources |
| **annotations** | Bookmarks and personal notes |

Modules talk through defined interfaces. Example: search knows the library
section model; it does not know git-sync details.

Prefer extending these apps and `src/clavis/` shared packages over new top-level
utility trees.

## 4. Search for and reuse existing functions first

Before writing something new, check for an existing function, service, template,
or component.

Shared once (never reimplemented per feature):

- Source citations and section deep-links
- Markdown parse and HTML render
- Excerpt / stable-id handling
- Search filters and result rows
- Bookmark, note, and campaign actions
- Dialogs, forms, empty/error/loading states

Shared functions get concrete names and a clear owner module.

## 5. Define data and domain logic centrally

Models, validation, and normalization live in models/services — not in templates.

Keep these layers distinct:

1. **Raw source** — imported Markdown, untouched by personal overlays
2. **Structural content** — books/sections produced by the shared parser
3. **Derived data** — search index (and later catalog); must be reproducible
   from stored sources

Templates present. Domain logic belongs in services (or equivalent).

**One Markdown parser** (`clavis.markdown`) defines what a section is for import,
reader, and search alike.

## 6. Keep sources and personal content separate

Imported files are never modified by notes, bookmarks, or campaign edits.

Books, sections, and (later) catalog entries use **stable internal IDs**.
Filenames and headings are not durable identities by themselves.

Source updates must be repeatable:

- The same import does not create duplicates
- A failed update leaves the last working library available
- Removed or unresolvable content is marked visibly
- Annotations and campaign links keyed by `stable_id` survive re-import when
  structure still matches
- Broken excerpts show “Source changed — check excerpt” rather than silently
  moving to another passage

## 7. Reuse markup and layout as components

Recurring UI is shared templates/partials, especially:

- Navigation and page shell
- Citations and status badges
- Search hits and filters
- Table of contents and section navigation
- Bookmark, note, and campaign actions
- Forms, dialogs, and error messages

The same citation looks the same in reader, search, and campaigns, and is
produced by the same component.

## 8. Use one small, binding design system

Colors, spacing, type sizes, content width, and related values are CSS design
tokens in `static/css/clavis.css`.

Components use shared rules. Individual pages do not copy styles or scatter
inline one-offs.

States — selected, disabled, loading, empty, error — are styled consistently.
Meaning is never conveyed by color alone.

Prefer **intrinsic layouts** and reusable, container-responsive components.
Write a component once and let it adapt to available width (container queries,
`auto-fit` / `auto-fill` grids, `min`/`max`/`clamp`) instead of maintaining
per-page layout variants. Use Kevin Powell’s examples as implementation
references; verify browser support and accessibility before adopting a
technique. Cascade layers (`tokens` → `reset` → `base` → `layout` →
`components` → `utilities`) keep override priority predictable.

Tokens, shared components, and WCAG obligations remain authoritative over any
external example.

See [design-system.md](design-system.md).

## 9. Write semantic, accessible HTML

- Links navigate; buttons perform actions
- Headings form a coherent hierarchy
- Landmarks distinguish navigation, main content, and complementary regions
- Forms have visible labels; tables have proper headers
- Keyboard use, visible focus, and clear error text are normal requirements
- Imported Markdown is rendered safely; foreign HTML must not execute scripts
- UI language is English

Target: WCAG 2.2 Level AA.

## 10. Prioritize readability over decorative design

Book text gets a comfortable measure (`clamp` / `min` against `--content-width`),
clear typography, and enough spacing. Wide tables may scroll horizontally in a
controlled way.

Check desktop and tablet; small screens must still reach content and navigation.
Prefer container-based adaptation so the same reader/result components remain
usable in narrower chrome without a separate “mobile stylesheet.”

Research comfort matters: reading position, search filters, and open context
should survive appropriate navigation steps.

## 11. Enable scale with concrete measures

- Large books: load/navigate by section
- Result lists: paginate when volumes grow
- Queries: use indexes; avoid N+1 queries for hit lists
- Import and analysis run outside ordinary page requests
- Prefer targeted reprocessing of changed content

Introduce an extra search engine, cache, or service only when measurement or a
clear requirement justifies it. Interfaces should allow later replacement.

## 12. Test important behavior deliberately

Prioritize tests for:

- Markdown structure, tables, and internal links
- Repeated imports and source changes
- Stable references and preserved notes/bookmarks
- Search filters and correct hit locations
- Campaign associations and broken-excerpt flags
- Access control if multi-user support is ever added

Representative Markdown excerpts are fixed fixtures under `tests/fixtures/`.
Formatting and lint run on every change. UI checks supplement when presentation
changes.

## 13. Document decisions and operations

Document setup, start, import, update, backup, and restore in the README (and
related docs). Schema changes use versioned migrations.

Important architecture decisions get a short ADR: context, decision, status,
consequences.

Choose dependencies deliberately and pin them reproducibly (`uv.lock`).

Logs explain which import or processing step failed. Personal notes and secrets
do not belong in logs.

## 14. Shared definition of done

A task is done when:

- Acceptance criteria are met
- Existing functions and components were reused where appropriate
- Relevant checks pass (`pytest`, `ruff`)
- Affected documentation is updated
- Error, empty, and loading states work for UI changes
- The change contains no unintentional extras

---

## Language, tooling, and assets

| Topic | Rule |
|---|---|
| UI and project docs | English |
| Python style | PEP 8 via Ruff |
| Package/run | `uv` primary; optional Docker Compose |
| Front-end assets | Local only under `static/` — no CDN CSS/JS/fonts |
| Markdown | Only `clavis.markdown` |
| Citations | Only `clavis.citations` + shared citation template |

## AI features (keep optional)

Enrichment lives under `apps.catalog`; local-model meaning search under
`apps.search` (`embeddings.py`, `semantic.py`). Do **not** add generative
chat/RAG, remote LLM calls, or a second citation/Markdown stack unless explicitly
asked. Enrichment must stay reviewable; the app must run fully offline without API
keys. Import ML libraries lazily, and keep tests on the `hashing-v1` backend (set
in `tests/conftest.py`) so they never download a model.

