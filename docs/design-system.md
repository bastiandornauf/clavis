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


## Tokens

CSS custom properties define color, type, spacing, radius, and content width.
Pages should compose those tokens rather than inventing one-off values.

## Components

| Component | Template / CSS |
|---|---|
| Shell / nav / footer | `templates/base.html` |
| Citation | `templates/components/citation.html` |
| Filters / forms | `.filter-bar`, `.stack-form` |
| Result lists | `.result-list` |
| Reader TOC | `.toc` |
| Empty / warning | `.empty-state`, `.warning` |
| Gallery grid | `.gallery-jump`, `.gallery-album`, `.gallery-grid` |

Accessibility target: WCAG 2.2 AA.
