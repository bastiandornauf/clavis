# ADR 0001: Application stack

## Status

Accepted

## Context

Clavis needs a locally hosted, maintainable archive for Markdown rules texts with
full-text search, personal overlays, and eventual optional enrichment pipelines.

## Decision

Use Django + SQLite (including FTS5) + server-rendered HTML with HTMX.
Package and run primarily with `uv`; provide optional Docker Compose.

## Consequences

- One process and one database file keep self-hosting simple.
- FTS5 covers Phase-1 search without an external search engine.
- HTMX allows progressive enhancement without a SPA.
- Future catalog/LLM/embedding work can attach as management commands and services
  without changing the reader core.
