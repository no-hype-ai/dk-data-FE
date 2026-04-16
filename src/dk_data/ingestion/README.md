# dk_data.ingestion

Ingestion modules for the dk-data platform. Two parallel paths land
data in `dk_data_*` schemas:

## 1. Live fetchers (default)

Entry point: `main.run_ingestion(source: str, **kwargs) -> dict`

Per-source fetchers live in `fetchers/` and `sources/`; `main.py`
dispatches by name from the `SOURCES` registry. SQLMesh then promotes
`raw` → `bronze` → `silver` → `gold`.

CronJobs in `dk-data-prod` invoke this path on a schedule.

## 2. Pre-staged dumps (feature 005-prestaged-hydration)

Entry point: `python -m dk_data.ingestion.prestaged`

Walks `${PRESTAGED_ROOT}` for `pg_dump -Fc` files (two layouts
supported), dispatches `pg_restore` per `(schema, table)` in declared
hub → spoke order (`load_order.py:SOURCE_LOAD_ORDER`). Falls through to
path 1 for any source without a pre-staged artifact. Throttled by
`meta.wal_usage`; idempotent reruns via the deterministic `run_label`
hash stored in `meta.transform_runs.details`.

See:
- `.dk/specs/005-prestaged-hydration/spec.md` — feature spec
- `.dk/specs/005-prestaged-hydration/quickstart.md` — local-dev walkthrough
- `.dk/specs/005-prestaged-hydration/contracts/cli.md` — CLI contract
- `deploy/jobs/prestaged-hydrate.yaml` — k8s Job manifest

## Module map (5 new files for feature 005)

| Module | Purpose |
|--------|---------|
| `prestaged.py` | CLI + walk/validate/dispatch + run_step orchestration |
| `prestaged_types.py` | Pydantic `LoadPlan`/`LoadStep`/`PrestagedArtifact` + `compute_run_id()` |
| `prestaged_safety.py` | `is_restorable_target()` view-safety filter (`pg_class.relkind='r'`) |
| `transform_runs_writer.py` | Append-only writer for `meta.transform_runs` post-migration-229 |
| `load_order.py` | `SOURCE_LOAD_ORDER`, `WAL_MODE_TABLES`, `plan_load()`, `propagate_blocked()` |
| `wal_throttle.py` | `WalThrottle` gate against `meta.wal_usage` |

## Tests

| Path | Speed | What |
|------|-------|------|
| `tests/ingestion/test_load_order.py` | unit (~10ms) | tier ordering, blocked propagation, tier precedence |
| `tests/ingestion/test_wal_throttle.py` | unit (~10ms) | pause loop, downshift, budget exhaustion |
| `tests/ingestion/test_prestaged_discovery.py` | unit (~10ms) | walker for both layouts |
| `tests/ingestion/test_prestaged_validate.py` | unit (~10ms) | PGDMP magic-byte check |
| `tests/ingestion/test_prestaged_fallback.py` | unit (~10ms) | live-fetch dispatch, suspended fetchers, out-of-scope |
| `tests/ingestion/test_prestaged_idempotency.py` | unit (~10ms) | SC-006 (rerun-noop), SC-007 (one terminal row), OTLP swallow |
| `tests/load/test_prestaged_e2e.py` | integration | requires `cnpg_conn` + `pg_restore` binary |
