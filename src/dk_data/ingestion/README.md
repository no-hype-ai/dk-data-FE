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

## Wave B: HCP / research sources

Three new sources onboarded in `wave-b/hcp-research-sources`:

| Source key | Schema.Table | Origin | Fetcher | Schedule |
|---|---|---|---|---|
| `ema_epar` | `mol_raw.ema_epar` | EMA EPAR assessment reports (bulk CSV) | `EMAEparFetcher` | Monthly |
| `health_canada_dpd` | `mol_raw.health_canada_dpd` | Health Canada Drug Product Database (ZIP of pipe-delimited TXT) | `HealthCanadaDPDFetcher` | Monthly |
| `research_orgs_ror` | `hcp_raw.research_orgs_ror` | Research Organization Registry via Zenodo JSON dump (~110k orgs) | `ResearchOrgsRORFetcher` | Monthly |

`hcp_raw` schema created by migration 235. The ROR source is the first
to land in the HCP domain raw layer.

## International health data sources (wave-b)

| Source | Schema.Table | Fetcher | Loader | Schedule |
|--------|-------------|---------|--------|----------|
| WHO GHED | `hcs_raw.who_ghed` | `fetchers/who_ghed.py` | `sources/who_ghed.py` | Annual (Jan 15) |
| World Bank Health | `hcs_raw.worldbank_health` | `fetchers/worldbank_health.py` | `sources/worldbank_health.py` | Annual (Feb 1) |
| OECD Health | `hcs_raw.oecd_health` | `fetchers/oecd_health.py` | `sources/oecd_health.py` | Annual (Jul 15) |
| PBS Australia | `mol_raw.pbs_australia` | `fetchers/pbs_australia.py` | `sources/pbs_australia.py` | Monthly (3rd) |

All four are T1 free/open sources with no authentication required.

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
