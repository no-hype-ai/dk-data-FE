# Phase 0 Research — Silver Medallion Rebuild

## Topic 1: Hub bootstrap order

- **Decision**: Smallest-first within dependency tiers. Tier 0 → Tier 1 → Tier 2 → Tier 3 as enumerated in `plan.md`.
- **Rationale**: Validates the chunked PL/pgSQL pattern on small hubs (facilities = 6K, companies ≈ 10K, conditions ≈ 50K) before tackling the 10M-row providers hub. Respects FK constraints. Fails fast on small hubs without burning 15 minutes on a large bootstrap first.
- **Alternatives considered**: strict size order (would fail FKs); pure topological sort (wastes the validation opportunity); parallel bootstrap of independent tiers (harder to attribute WAL spikes during the run).

## Topic 2: Resolve function strictness markers

- **Decision**: Each `resolve_*()` is `STABLE PARALLEL SAFE`. Trigram fallback returns NULL below 0.85; matches at or above 0.85 return with computed `confidence`.
- **Rationale**: `STABLE` lets postgres cache results within a query plan. `PARALLEL SAFE` allows parallel hash joins to call the function. The 0.85 threshold matches the documented `pg_trgm` "probably the same word" boundary.
- **Alternatives considered**: `IMMUTABLE` (wrong — hub data can change between calls); always-return-best-fuzzy (pollutes gold layer); per-call confidence override (adds an unused parameter to every call site).

## Topic 3: Free-text source linking strategy

- **Decision**: Read structured sibling fields the source APIs already provide. No LLM in v1.
  - FAERS drugs: `patient.drug[].openfda.unii[]`, `openfda.rxcui[]`, `openfda.product_ndc[]`, `openfda.substance_name[]`
  - FAERS reactions: `patient.reaction[].reactionmeddrapt` (already MedDRA PT)
  - ClinicalTrials.gov: `protocolSection.derivedSection.interventionMeshList[]`, `conditionMeshList[]`
  - PubMed / EuropePMC: `MeshHeadingList`, `ChemicalList` + regex `NCT\d{8}` / DOI / PMID over title+abstract
  - Patents: Orange Book join on `(application_number, patent_number)` for FDA-approved drugs only
  - Medical news: precompiled regex against `mol_bronze.who_inn` (~10K WHO INN entries)
- **Rationale**: Source-API audit during the spec phase found ~80–90% coverage from structured fields alone. LLM cost analysis ($8K–30K one-time + $2.5K–10K/year) does not justify the marginal lift. Coverage targets in SC-013 are met via the structured-field strategy.
- **Alternatives considered**: LLM extraction via `litellm-server` (rejected on cost and the model-drift / re-extraction overhead); commercial pharma pipeline DB licensing (deferred until a product feature requires the marginal coverage).

## Topic 4: Column-retention contract test

- **Decision**: pytest test that loads a `sqlmesh.Context`, walks `context.dag.upstream(silver_model)` to discover bronze deps, then reads `context.get_model(name).columns_to_types` for both sides. Asserts every non-system bronze column appears in the silver column list.
- **Rationale**: SQLMesh is the single source of truth — it cannot drift from the actual model code. No live DB needed. No manifest file to maintain.
- **Alternatives considered**: maintained YAML manifest (drift risk); SQL comment headers (easy to forget); `information_schema.columns` query (needs live DB and produces stale results).

## Topic 5: Per-transaction WAL accounting

- **Decision**: Each chunked PL/pgSQL procedure brackets the chunk transaction with `pg_current_wal_lsn()` calls and writes a row to `meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)`. Operators grep the table to verify FR-021 compliance and feed prometheus metrics.
- **Rationale**: The cluster has no `pg_stat_statements` and `auto_explain` is not enabled — we need application-side WAL accounting to enforce the 2 GB ceiling.
- **Alternatives considered**: parse postgres logs for checkpoint events (fragile, high latency); enable `pg_stat_statements` (requires cluster change, out of scope).

## Topic 6: PL/pgSQL chunked-COMMIT pattern

- **Decision**: Each bootstrap procedure follows this template:

  ```
  CREATE PROCEDURE mol_silver.bootstrap_<hub>()
  LANGUAGE plpgsql AS $$
  DECLARE
      v_chunk_size constant int := 50000;
      v_last_id bigint := 0;
      v_chunk_count int := 0;
      v_wal_start pg_lsn;
      v_wal_end pg_lsn;
  BEGIN
      LOOP
          v_wal_start := pg_current_wal_lsn();
          INSERT INTO mol_silver.<hub> (...)
          SELECT ... FROM mol_bronze.<source>
          WHERE id > v_last_id ORDER BY id LIMIT v_chunk_size
          ON CONFLICT (...) DO NOTHING
          RETURNING id INTO v_last_id;

          GET DIAGNOSTICS v_chunk_count = ROW_COUNT;
          EXIT WHEN v_chunk_count = 0;

          v_wal_end := pg_current_wal_lsn();
          INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
          VALUES ('bootstrap_<hub>', v_last_id::text, ..., v_chunk_count, pg_wal_lsn_diff(v_wal_end, v_wal_start));

          UPDATE meta.refresh_state SET last_chunk_position = v_last_id::text, last_commit_at = NOW()
          WHERE procedure_name = 'bootstrap_<hub>';
          COMMIT;

          PERFORM pg_sleep(0.05);
      END LOOP;
      UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'bootstrap_<hub>';
  END;
  $$;
  ```

- **Rationale**: This is the only pattern that satisfies FR-021 (per-transaction WAL ceiling), FR-026 (resumability via `meta.refresh_state`), FR-028 (CPU yield via `pg_sleep`), and the `meta.transform_runs` accounting from Topic 5 above.
- **Alternatives considered**: Python-side row loops (either hold one transaction open — fails FR-021 — or commit per row — slow + lock thrashing); SQLMesh `INCREMENTAL_BY_UNIQUE_KEY` model with very small intervals (works for ongoing refresh but is too slow for the one-time bootstrap of 10M-row tables).

## Topic 7: Connection-string helper enforcement

- **Decision**: Single `dk_data.ingestion.utils.database.build_dsn()` helper. CI grep fails the build on any `psycopg2.connect(` call outside `database.py`. Helper sets all FR-022/FR-023 settings via the `options` query parameter.
- **Rationale**: A single chokepoint is the only practical way to enforce that timeouts, keepalives, and `application_name` are present on every connection. CI grep is cheap and unambiguous.
- **Alternatives considered**: a connection-string lint rule in pre-commit (more brittle); runtime validation in the connection itself (catches it too late, after the connection is open).

## Topic 8: PgBouncer routing strategy

- **Decision**: Two postgres host env vars per workload — `POSTGRES_HOST` (PgBouncer) and `POSTGRES_HOST_DIRECT` (CNPG primary). Fetcher pods, transform pods, and short-lived scripts use the pooled host. SQLMesh and PL/pgSQL procedure invocations use the direct host because they need session-level features (advisory locks, prepared statements, server-side procedures).
- **Rationale**: PgBouncer transaction mode breaks session-scoped features. Splitting the env vars is the cleanest way to route per-workload without runtime feature detection.
- **Alternatives considered**: detect-and-fall-back (slower, harder to test); single env with feature flag (couples the routing decision to the feature, which is fragile).
