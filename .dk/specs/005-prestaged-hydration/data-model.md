# Data Model

All entities are either in-memory Python dataclasses (Pydantic models) or existing PostgreSQL tables/views. No new tables are created; we write to existing `meta.transform_runs` and read from existing `meta.wal_usage` and `meta.job_locks`.

## Entities

### PrestagedArtifact (Python / Pydantic)

| Field | Type | Notes |
|-------|------|-------|
| `path` | `Path` | Absolute path to `.dump` file |
| `target_schema` | `str` | Inferred from parent dir |
| `target_table` | `str` | Inferred from grandparent dir (raw) or dir-name parse (bronze/silver) |
| `tier` | `Literal["raw","bronze","silver"]` | Derived from `target_schema` suffix |
| `chunk_index` | `str` | File prefix: `"1"`, `"3"`, `"retry"`, or `""` for single-file |
| `size_bytes` | `int` | `stat().st_size` |
| `sha256` | `str` \| `None` | Computed on demand; cached in memory |
| `magic_ok` | `bool` | First 5 bytes == `b"PGDMP"` |

**Invariants**:
- `magic_ok == True` before dispatch (FR-002).
- A `(target_schema, target_table, chunk_index)` triple is unique within a run.

### LoadPlan (Python / dataclass)

| Field | Type | Notes |
|-------|------|-------|
| `run_id` | `str` | Deterministic sha256 per R4 |
| `sources` | `list[LoadStep]` | Ordered per `SOURCE_LOAD_ORDER` |
| `wal_mode_tables` | `set[tuple[str,str]]` | The 5 >5 GB tables |

### LoadStep (Python / dataclass)

| Field | Type | Notes |
|-------|------|-------|
| `source_id` | `str` | e.g. `mol_raw.chembl` |
| `schema` | `str` | |
| `table` | `str` | |
| `tier` | `Literal["raw","bronze","silver"]` | Highest tier available |
| `kind` | `Literal["pg_dump","bronze_ready","raw_csv","live_fetch"]` | Dispatch branch |
| `artifacts` | `list[PrestagedArtifact]` | Empty iff kind=`live_fetch` |
| `depends_on` | `list[str]` | Other `source_id` that must be terminal before this one runs |
| `wal_mode` | `bool` | True if `(schema, table) in wal_mode_tables` |

**State machine** (recorded per `LoadStep` in `meta.transform_runs`):

```
           +-----------+
pending -->| running   |--+-- completed
           +-----------+  |
                ^         +-- failed
                |         |
           blocked <------+-- skipped_view
                          |
                          +-- no_source_available
```

### Transform Run (existing table `meta.transform_runs`)

Columns used by writer:

| Column | Write responsibility |
|--------|----------------------|
| `run_id` | Deterministic key (R4) |
| `schema` | From LoadStep |
| `table` | From LoadStep |
| `source_kind` | pg_dump / bronze_ready / raw_csv / live_fetch |
| `status` | State-machine value above |
| `row_count` | `COUNT(*)` post-restore; `NULL` on failure |
| `started_at` | UTC timestamp |
| `finished_at` | UTC timestamp on terminal transition |
| `artifact_sha256` | Comma-joined sha256s of all chunks; `NULL` for live_fetch |
| `error_detail` | Truncated stderr on failure |

**Note on schema drift**: This feature assumes the column is named `status` in prod. If the post-restore meta dump reveals a different column name (e.g. `state`), the writer reads the column list at connection time via `information_schema.columns` and maps to whatever is present. The list above is the canonical names this module uses internally.

### WAL Observation (existing view `meta.wal_usage`)

Read-only. Columns the throttle logic uses:

| Column | Use |
|--------|-----|
| `observed_at` | Most-recent ordering |
| `current_wal_bytes` | Numerator |
| `max_wal_size` | Denominator |
| `pct_used` | Convenience |

### Source Dependency (Python / dataclass)

| Field | Type |
|-------|------|
| `source_id` | `str` |
| `depends_on` | `list[str]` |
| `parallelizable` | `bool` (declared; ignored in v1 — serial always) |

Stored as entries in the extended `SOURCE_TO_BRONZE_MODELS` dict in `source_backfill.py:57`.

## Advisory lock

Not an entity per se, but part of the data contract:

| Lock key | Hold duration |
|----------|---------------|
| `hashtext('prestaged:' || schema || '.' || table)` | From first chunk dispatch until last chunk completes for that table |

## Ordering contract

`SOURCE_LOAD_ORDER` (in `load_order.py`) is a list of 8 tiers:

1. Metadata/lineage: `meta.fetch_checkpoints`, `sqlmesh._snapshots`
2. Molecule hub raw (8 sources)
3. Molecule bronze (7 sources — skip-transform)
4. Molecule silver hubs (3 sources — skip-transform)
5. Clinical/activity spokes (~23 sources)
6. HCS raw + HCS bronze (34 + 34 sources, both tiers before tier 7)
7. HCS silver aggregates (5 sources)
8. Gold (SQLMesh, no dumps): 4 models

Within a tier, steps run serially in declared order (v1). No step in tier N starts until every step in tier <N has reached a terminal state.
