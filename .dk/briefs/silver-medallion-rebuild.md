# Silver Medallion Rebuild

## Goal

Rebuild the dk-data silver layer on top of canonical entity-resolution hub tables so silver becomes a complete, indexed, single source of truth for downstream apps — and so every silver and transform activity stays inside the fixed CNPG cluster's hard ceilings on WAL, CPU, memory, and connections.

## Why now

External applications and gold/mart models read **only** from silver and gold. Today silver has three structural problems:

1. **Silver models drop bronze columns.** ~95 silver SQLMesh models across `mol_silver` / `hcs_silver` / `ind_silver` are dropping non-system columns that exist in their upstream bronze sources. Consumers can't see fields that the data platform actually has — the medallion contract is broken.
2. **Silver models re-derive entity linkage inline using bad SQL patterns.** OR-joins between hub-eligible identifiers; leading-wildcard `LIKE`; correlated scalar subqueries; global `DISTINCT ON` over multi-way `UNION ALL`; trigram similarity combined with equality in OR clauses. The worst offenders (`adverse_events`, `bioactivity`, `molecule_publications`, `pubmed_articles`) are slow or never complete.
3. **Transformations exceed the cluster's WAL ceiling.** On 2026-04-10 a single transaction generated ~100 GB of WAL on a cluster that can only buffer 4 GB, contributing to a postgres crash and disk I/O exhaustion. This is the recurring failure mode the rebuild has to prevent.

## Source documents (authoritative)

The full design rationale, the 6 reliability principles, the 5 banned silver antipatterns, the 4 entity-linking patterns, the source × identifier matrix, the hub + crosswalk + name-index architecture, and the bootstrap budget math all live in two companion documents in the Cross-Project-Planning repo:

- `/Users/pschloz/Desktop/DataKinetic/Cross-Project-Planning/dk data fe/01-architecture-and-reliability/transformation-reliability-low-tech-solutions.md`
- `/Users/pschloz/Desktop/DataKinetic/Cross-Project-Planning/dk data fe/01-architecture-and-reliability/silver-linkage-reference.md`

These are the inputs to the spec. Read them in full before generating user stories or requirements.

## What "done" means

- Every silver model carries forward every non-system column from its upstream bronze source(s), verified by a CI contract test.
- Entity resolution lives in canonical hub tables (one per top-level entity type) with per-entity-type identifier crosswalks, normalized name indexes, and `resolve_*()` functions. No silver model re-derives linkage inline.
- The 5 banned antipatterns are absent from every silver model after rewrite.
- The full hub bootstrap, the silver rewrites, and every other transformation fit inside the cluster's documented WAL / CPU / memory / connection budgets and can be killed and resumed without duplicating work.
- Free-text sources (FAERS, ClinicalTrials, DailyMed, PubMed, EuropePMC, patents, news) are linked via the structured sibling fields the source APIs already provide — no LLM extraction in v1.

## Scope: what's in, what's out

**In:**
- Hub tables, identifier crosswalks, name indexes, and `resolve_*()` functions for the top-level entity types identified in the linkage doc
- Bootstrap procedures that read from existing bronze data only (no re-ingestion)
- Silver model rewrites in priority order (worst antipattern + largest blast radius first)
- Connection-string fixes, idempotence/resumability, PgBouncer routing, stampede staggering, and the rest of the 6 reliability principles
- Structured-field linking for free-text sources via the source APIs' harmonized fields and pre-indexed concept lists
- Deletion of legacy silver models that the new hubs supersede (currently empty in the cluster)

**Out:**
- Any change to the postgres pod, the CNPG cluster, the K3s topology, the connection pooler config, or the WAL archiver
- Bronze schema migrations on tables larger than ~1M rows
- Re-ingestion of bronze data
- LLM-based entity extraction from prose (deferred — the structured-field strategy covers ~80–90% of the cases originally assumed to need LLM)
- Indication-prose parsing of DailyMed labels, non-FDA-approved compounds in patent claims, SEC EDGAR 10-K Business section pipeline mentions
- Licensed sources not currently ingested (SNOMED CT, MONDO, OMIM, MedDRA hierarchy, JapicCTI, DUNS/LEI/ROR)
- Bronze stamping with `molecule_id` columns (this is the failure mode the feature exists to prevent)
