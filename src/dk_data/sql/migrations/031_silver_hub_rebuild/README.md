# Migration 031: Silver Hub Rebuild

**Feature**: 001-silver-medallion-rebuild
**Branch**: feature/001-silver-medallion-rebuild

Builds the 10-hub silver entity-resolution architecture across `mol_silver`, `hcs_silver`,
`ind_silver`, `hcp_silver`, `ip_silver`. Adds the `ip_*` schema family. Wires `meta.*`
observability tables.

## Execution order

Run files in numeric prefix order. Every PL/pgSQL bootstrap procedure is designed to be
restarted mid-run via `meta.refresh_state.last_chunk_position`.

## Files added by this migration

| File | Description |
|------|-------------|
| 001_meta_job_locks.sql | `meta.job_locks` concurrency lock table (FR-025) |
| 002_meta_refresh_state.sql | `meta.refresh_state` resumability table (FR-026) |
| 003_meta_linkage_conflicts.sql | `meta.linkage_conflicts` crosswalk audit table (FR-026a) |
| 003a_meta_transform_runs.sql | `meta.transform_runs` WAL accounting table (FR-021) |
| 004–013 | `resolve_*()` PL/pgSQL functions for all 10 entity types |
| 014–023b | Bootstrap procedures (smallest-first by dependency tier) |
| 050_create_ip_schemas.sql | `ip_raw`, `ip_bronze`, `ip_silver`, `ip_gold` schema registration |
| 051–054 | IP domain data migrations and PostgREST grants |
