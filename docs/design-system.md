# Design system

Clavis uses a small token-based design system in `static/css/clavis.css`.
UI design obligations that affect code structure are also in
[coding-standards.md](coding-standards.md) (§7–§10).

## Principles

- Reading comfort first: comfortable measure, serif body text, clear hierarchy.
- Semantic HTML: landmarks, heading order, labeled forms, keyboard focus styles.
- One shell for Library, Reader, Search, Campaigns, Sources.
- Shared components for citation, filters, result lists, empty states, messages.
- No CDN assets; HTMX and CSS are local.
- Meaning is not conveyed by color alone (badges + text).
- States (selected, disabled, loading, empty, error) are consistent across pages.
- Prefer intrinsic layouts and reusable, container-responsive components over
  page-specific layout variants.

## Layout references (Kevin Powell)

Kevin Powell’s modern CSS layout patterns are an **implementation reference**
for Clavis. His talk
[Smart layout patterns with modern CSS](https://www.kevinpowell.co/talks/smart-layout-patterns/)
covers container queries, subgrid, `clamp()`, and cascade layers. For
breakpoint-light grids see
[Breakpoint-Free CSS Grid Layouts](https://frontendmasters.com/tutorials/kevin-powell/breakpoint-free-grid-layouts/)
(`auto-fit` / `auto-fill`, with linked CodePen).

Project rule:

> Prefer intrinsic layouts and reusable, container-responsive components. Use
> Kevin Powell’s examples as implementation references; verify browser support
> and accessibility before adopting a technique.

His examples supply ideas. Shared components, design tokens, and accessibility
rules remain binding.

| Technique | Use in Clavis |
|---|---|
| **Container Queries** | A search hit / result card adapts to its actual width—main column or a narrow campaign strip—without a second component variant. |
| **Auto-wrapping grids** | Book lists, lexicon cards, and gallery tiles distribute by available space (`auto-fit` / `auto-fill` + `minmax(min(100%, …), 1fr)`). Prefer fewer bespoke viewport breakpoints. |
| **Subgrid** | Align repeated fields across cards (e.g. title + meta on book cards) even when titles wrap to different lengths. |
| **`clamp()`, `min()`, `max()`** | Spacing and content width stay within fixed bounds; the reader keeps a comfortable measure. |
| **Cascade Layers** | Fixed priority: `tokens` → `reset` → `base` → `layout` → `components` → `utilities`. Reduces accidental override fights. |

### Adoption notes

- Styles live under `@layer` in `static/css/clavis.css`. New page-shell rules
  belong in `@layer layout` when split out; component chrome stays in
  `@layer components`.
- `.shell` is a named containment context (`shell`) so nested layouts (reader)
  can react to shell width, not only the viewport.
- `.result-list` and `.gallery-album` are also containment contexts for local
  density / tile sizing.
- Always keep a sensible `@supports` / `@media` fallback when a technique is
  load-bearing for navigation or reading.
- Do not adopt a pattern that harms keyboard focus, contrast, or reflow.

## Tokens

CSS custom properties define color, type, spacing, radius, and content width.
Prefer fluid tokens (`clamp` / `min`) for measure and gutters. Pages should
compose those tokens rather than inventing one-off values.

`--content-width` is the reading measure for a book chapter and for a found
passage in search, the lexicon, or a campaign. The default (Book) is about
80 characters. Narrow is about 70 and Wide about 90. On a narrow screen the
column uses the available width. Chapter text is a regular-weight serif at
1.125rem (about 20px) with a line-height of 1.5. The interface stays at the
root size. Reading options — face and line width — sit in a collapsed
disclosure on the chapter. A chapter can switch the reading face to Literata,
Inter (with its disambiguation set), Verdana, Atkinson Hyperlegible, Andika,
ABeeZee, or OpenDyslexic. Each face nudges size, line spacing, and measure
for that face. The choice is kept in the browser. The book serif remains the
default.

## Components

| Component | Template / CSS |
|---|---|
| Shell / nav / footer | `templates/base.html` |
| Citation | `templates/components/citation.html` |
| Filters / forms | `.filter-bar`, `.stack-form` |
| Result lists | `.result-list` (container-responsive) |
| Reader TOC | `.toc` |
| Reader header switches | `.reader-heading__controls`, `.view-toggle__label` |
| Reading options | `.reading-prefs` (collapsed face and line width) |
| Raw Markdown view (Reader toggle) | `.markdown-source` |
| Empty / warning | `.empty-state`, `.warning` |
| Book / lexicon grids | `.book-grid`, `.book-card` (subgrid-aligned) |
| Gallery grid | `.gallery-jump`, `.gallery-album`, `.gallery-grid` |
| Guides list | `.guides-stack`, `.guides-category`, `.guides-list` |

Accessibility target: WCAG 2.2 AA.
