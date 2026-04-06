# Research: Silver Column Retention

**Date**: 2026-04-06  
**Status**: Complete — no unknowns

## Decision: Column Exclusion List

**Decision**: Exclude only these system/ETL columns from silver:
- `raw_json`, `raw_source_id` — raw API response blobs
- `processed_to_bronze`, `processed_to_silver` — ETL flags
- `_bronze_loaded_at` — internal ETL timestamp
- `id` — bronze surrogate key (silver generates its own)

**Rationale**: These are internal pipeline mechanics, not consumer-facing data. Everything else is a domain column that consumers may need.

**Alternatives considered**: 
- Exclude all metadata (`source`, `_source_year`, `_source_hash`) — rejected because lineage tracking is valuable for consumers debugging data quality.
- Exclude JSONB array columns — rejected because consumers need structured data like `drug_interactions`, `pathways`, `targets`.

## Decision: Column Collision Strategy

**Decision**: Prefix with source name when columns from different bronze tables share the same name in a multi-source silver model.

**Rationale**: Avoids ambiguity. If chembl and drugbank both have `max_phase`, the silver model has `chembl_max_phase` and `drugbank_max_phase`.

**Alternatives considered**:
- COALESCE into single column — rejected because it loses source attribution and may hide data quality issues.
- Suffix with source — rejected; prefix is more readable in column listings.

## Decision: Aggregation Model Handling

**Decision**: Add missing columns directly into existing aggregation models. No companion detail tables.

**Rationale**: Simpler scope — 95 models to modify, 0 new models to create. Consumers get everything from one table per entity.

**Alternatives considered**:
- Companion detail tables alongside aggregation — rejected by stakeholder (option C selected over A).
- Replace aggregation with full pass-through — rejected; loses valuable pre-computed aggregates.
