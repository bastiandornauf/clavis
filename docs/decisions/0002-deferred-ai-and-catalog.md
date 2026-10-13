# ADR 0002: Catalog first; AI as optional overlays

## Status

Superseded in part (2026-10) — rule-based catalog shipped; enrichment + local
semantic search scaffolds are in-tree. Generative RAG/chat remains deferred.

## Context

The product vision includes structured catalogs, import-time LLM enrichment, and
local semantic search. Phase 1 deferred those until Reader / FTS / campaigns were
proven. Catalog Tier A is now rule-based. AI work must stay optional and offline-safe.

## Decision

1. **Rules before LLM** — extractors in `apps.catalog.extractors` remain source of
   structured truth. LLM/heuristic enrichment only proposes leftovers.
2. **Enrichment is reviewable** — `EnrichmentProposal` rows with `extractor=llm`
   (or dry-run heuristics). Accept promotes to `CatalogEntry`; app works without
   `CLAVIS_LLM_API_KEY`. Command: `enrich_catalog`.
3. **Local embeddings** — `SectionEmbedding` + `hashing-v1` backend (stdlib).
   Semantic / Hybrid modes on Search. Rebuild: `rebuild_embeddings`. Optional on
   import via `CLAVIS_REBUILD_EMBEDDINGS_ON_IMPORT`.
4. **Still deferred** — networked LLM providers, generative chat, saga RAG.

## Consequences

- Thematic search works without an API key (hashing vectors; upgradeable later).
- False enrichment cannot land silently; accept is explicit.
- Real model backends (MLX / sentence-transformers) can replace `hashing-v1`
  behind `CLAVIS_EMBEDDINGS_BACKEND` without UI changes.
