# CLI Contract: `python -m dk_data.ingestion.prestaged`

## Invocation

```
python -m dk_data.ingestion.prestaged [--dry-run] [--source-list <all|SOURCE[,SOURCE...]>] [--only-tier <N>]
```

## Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dry-run` | bool | false | Emit ordered plan + validation results; no writes (FR-012) |
| `--source-list` | string | `all` | Comma-separated source_ids OR `all`; filters `SOURCE_LOAD_ORDER` |
| `--only-tier` | int | none | Run a single tier (1–8) for rehearsal |
| `--verbose` / `-v` | bool | false | Debug-level logging |

## Environment

| Var | Required | Default | Description |
|-----|----------|---------|-------------|
| `PRESTAGED_ROOT` | yes | (none) | Absolute path to artifact root (FR-016) |
| `PG_URL` | yes | (none) | PostgreSQL connection URL |
| `WAL_PAUSE_HIGH_PCT` | no | 70 | FR-007 |
| `WAL_PAUSE_LOW_PCT` | no | 40 | FR-007 |
| `WAL_PAUSE_DOWNSHIFT_THRESHOLD` | no | 2 | FR-008 |
| `WAL_PAUSE_BUDGET_SECONDS` | no | 600 | Max cumulative pause per run |
| `FETCHERS_SUSPENDED` | no | `patentsview,epo_ops,euipo,fda_ndc` | Comma-separated; live_fetch fallback skipped for these |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Run completed; all terminal states recorded |
| 1 | Configuration error (bad `PRESTAGED_ROOT`, missing `PG_URL`) |
| 2 | One or more steps failed; at least one completed |
| 3 | All steps failed (e.g. bad Postgres connection from step 1) |

Exit 0 even if individual sources are `failed`/`blocked`/`skipped_view`/`no_source_available` — the run as a whole succeeded in processing what it could. Exit 2 is reserved for unexpected terminations (uncaught exception, container OOM).

## Stdout contract (non-`--dry-run`)

One JSON line per terminal transition:

```json
{"run_id":"abc...","source_id":"mol_raw.chembl","status":"completed","row_count":1234567,"duration_s":42.1}
```

## Stdout contract (`--dry-run`)

One JSON line per planned step:

```json
{"tier":2,"source_id":"mol_raw.chembl","kind":"pg_dump","artifacts":["/data/prestaged/.../chembl_1_chunk.dump"],"artifact_count":3,"total_bytes":1470000000,"magic_ok":true,"wal_mode":false}
```

Followed by a summary line:

```json
{"summary":true,"total_steps":120,"total_bytes":42500000000,"wal_mode_steps":5,"missing_sources":[]}
```
