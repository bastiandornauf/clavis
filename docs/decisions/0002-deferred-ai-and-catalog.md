# ADR 0002: Defer catalog, LLM enrichment, and semantic search

## Status

Accepted

## Context

The product vision includes structured catalogs, import-time LLM enrichment, and
local semantic search. Those features add complexity before the reading/search/
campaign core is proven.

## Decision

Ship Phase 1 without catalog extraction, LLM calls, or embeddings.
Keep module boundaries and stable section IDs so later phases can attach cleanly.

## Consequences

- Users get value quickly from Reader + FTS + campaigns.
- Search quality for thematic queries may be weaker until semantic search lands.
- Structured filters for Technique/Form/Might wait for Phase 2+.
