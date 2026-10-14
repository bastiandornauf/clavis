# ADR 0002: Catalog first; AI as optional overlays

## Status

Superseded in part (2026-10) — rule-based catalog shipped; enrichment scaffold and
local-model meaning search are in-tree. Generative RAG/chat remains deferred.

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
3. **Local embeddings** — `SectionEmbedding` filled by a small local ONNX model
   (fastembed, `BAAI/bge-small-en-v1.5`); no PyTorch, no API key, one-time model
   download. Built explicitly with `rebuild_embeddings`; afterwards kept current on
   import (`CLAVIS_REBUILD_EMBEDDINGS_ON_IMPORT=auto`). Search modes appear only
   when that index exists. `hashing-v1` (stdlib) is kept for tests only — its
   relevance was too weak to ship.
4. **Still deferred** — networked LLM providers, generative chat, saga RAG.

## Consequences

- Meaning search works offline without an API key; full build ≈30 min on an
  Apple Silicon laptop, incremental afterwards.
- Keyword search never depends on the model; embedding failures on import are
  logged, not raised.
- False enrichment cannot land silently; accept is explicit.
- Section vectors are the retrieval layer a later cited RAG feature would reuse.
