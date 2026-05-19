# SQLMesh Transformation Pipeline — Status Investigation

**Date:** 2026-04-05  
**Cluster:** k3s prod (`dk-data-prod`)  
**SQLMesh state:** `prod` environment initialized at 17:04 UTC with 238 models / 265 snapshots  

---

## Executive Summary

The SQLMesh transformation pipeline has **two distinct failure modes** that have been active simultaneously:

1. **Initialization loop (now resolved):** Until 17:04 UTC today, the `prod` SQLMesh environment had never been successfully initialized. Every transform CronJob tried to bootstrap 237+ models via `sqlmesh plan --auto-apply`, failed partway through, and exited with code 1. This was a **blocking prerequisite** — no transforms could run at all.

2. **Model execution errors (current blocker):** Now that the `prod` environment exists, `sqlmesh run` can execute but individual models fail with data-level errors (integer overflow, type mismatches). Since models are batched per layer, one failing model marks the entire layer as failed.

---

## Finding 1: SQLMesh Initialization Was Broken Until Today

### Symptom
Every transform CronJob (15 jobs) logged the same pattern:
```
**`prod` environment will be initialized**
**Added Models:** hcs_bronze.acc_tvc .... 236 more ....
Updating physical layer  0.0% • pending
**Skipped models** (long list)
SQLMesh plan failed: Exit code: 1
Error: SQLMesh initialization failed
```

### Root Cause
The `ensure_sqlmesh_initialized()` function (transform_molecules.py:456-481) checks for `_snapshots` table existence. When not found, it runs `sqlmesh plan --auto-apply --forward-only` with a 600-second timeout. This plan compiles all 238 models, creates physical tables, and registers snapshots. On prior runs, this process failed partway through — likely due to:

- **Timeout**: 600 seconds may not be enough for 238 models on first init
- **Memory**: Previous CronJob memory limits were 2Gi (now bumped to 4Gi in commit `311111c`)
- **Cache directory**: SQLMesh tried to write cache to read-only package directory (`/usr/local/lib/python3.11/site-packages/dk_data/sqlmesh/.cache/`) instead of the configured `/tmp/sqlmesh-cache`

### Current State
The `prod` environment was successfully initialized at 17:04 UTC today (plan_id: `1780c830b041430db059000394334b81`). The `sqlmesh._environments` table has 1 row, `sqlmesh._snapshots` has 265 rows covering 238 distinct model names. Two intervals exist (for `mol_bronze.openfda_labels` and `mol_bronze.chembl_molecules` from a test run).

### Residual Risk
The `ensure_sqlmesh_initialized()` function only checks for `_snapshots` table existence — it does NOT check if the `prod` environment entry exists. If the table exists but the environment doesn't (e.g., after a partial init), the function returns `True` but `sqlmesh run` would fail with "Environment 'prod' was not found". This is now moot since the environment exists, but it's a fragile check.

---

## Finding 2: Bronze Layer Has One Confirmed Model Error

### Test Run Results (mol-transform-bronze-test, 17:03 UTC)

This was the first successful `sqlmesh run` after initialization. It ran the `bronze` layer (2 models):

| Model | Status | Details |
|-------|--------|---------|
| `mol_bronze.chembl_molecules` | **Succeeded** | 2.88M rows inserted in 2 batches (34s + 727s = ~12 min), audits passed |
| `mol_bronze.openfda_labels` | **Failed** | `NumericValueOutOfRange: value "4571261921" is out of range for type integer` |

### openfda_labels Integer Overflow

**File:** `src/dk_data/sqlmesh/models/molecules/bronze/openfda_labels.sql:23`
```sql
(label->>'version')::INTEGER AS spl_version,
```

**Problem:** The `version` field in OpenFDA label JSON can exceed PostgreSQL INTEGER max (2,147,483,647). Value `4571261921` is a valid SPL version number but overflows a 4-byte integer.

**Fix needed:** Change `::INTEGER` to `::BIGINT`.

### Impact
Because both models are batched in a single `sqlmesh run`, the `openfda_labels` failure causes the entire bronze layer to report as failed (exit code 1), even though `chembl_molecules` succeeded. The transform_molecules.py code marks all models in the layer as failed when the `sqlmesh run` exits non-zero.

---

## Finding 3: Potential INTEGER Overflow in Other Models

The same `::INTEGER` cast pattern exists across many models. Most are safe (year numbers, small counts), but these could be risky with large datasets:

| File | Line | Cast | Risk |
|------|------|------|------|
| `openfda_labels.sql` | 23 | `(label->>'version')::INTEGER` | **Confirmed failure** — values exceed 2.1B |
| `dailymed.sql` | 25 | `(spl->>'spl_version')::INTEGER` | Same field type as openfda_labels — may overflow |
| `uniprot.sql` | 48 | `(response_body->'sequence'->>'molWeight')::INTEGER` | Molecular weight — protein masses can exceed 2.1B daltons for large complexes |
| `cms_dme_puf.sql` | 33-34 | `tot_suplr_clms::INTEGER`, `tot_suplr_srvcs::INTEGER` | CMS aggregate counts — 9.6M+ rows, individual values likely safe |
| `europepmc.sql` | 66 | `(r.response_body->>'citedByCount')::INTEGER` | Citation counts — unlikely to exceed 2.1B but not impossible for mega-papers |

---

## Finding 4: CronJob Schedule and Dependency Chain

The transform CronJobs form a strict dependency chain. If an earlier layer fails, downstream layers still run on schedule but operate on stale/empty data.

### Scheduled Execution Order (UTC)

```
06:00  mol-transform-bronze          →  bronze (2 models: chembl_molecules, openfda_labels)
06:30  mol-transform-ip-bronze       →  ip_bronze (19 models: patents, IP, clinical, pdb, who_icd)
07:00  mol-transform-bronze-ext      →  mol_bronze_ext (35 models: rxnorm, pharmgkb, pubchem...)
07:00  hcs-transform-bronze          →  hcs_bronze (53 models: all CMS sources)
07:30  ind-transform                 →  ind_bronze + ind_silver (2 models)
08:00  mol-transform-silver          →  silver (7 models: molecules_from_bronze, targets, drug_labels...)
09:00  hcs-transform-silver          →  hcs_silver (10 models)
09:00  ind-gold-transform            →  ind_gold (1 model)
10:30  mol-transform-ip-silver       →  ip_silver (12 models: patents, trademarks, bridges...)
11:00  mol-transform-silver-ext      →  mol_silver_ext (44 models)
12:00  mol-transform-gold            →  gold (9 models)
13:00  mol-transform-ip-gold         →  ip_gold (3 models)
14:00  mol-transform-gold-ext        →  mol_gold_ext (6 models)
14:30  cms-gold-refresh              →  (shell script, checks SQLMesh init state)
15:30  mart-transform                →  mart (7 models: dim_hospital, score_factors, targeting...)
```

### Dependency Issues

1. **No retry on failure:** If bronze fails at 06:00, silver at 08:00 still runs but reads empty bronze tables. There's no retry mechanism or dependency gate between CronJobs.

2. **All-or-nothing batching:** `transform_layer()` batches all models in one `sqlmesh run`. If 1 of 53 hcs_bronze models fails, all 53 are reported as failed.

3. **No partial success handling:** The code (line 533-534) sets `success_count = len(models)` on success or `fail_count = len(models)` on failure — there's no parsing of SQLMesh output to determine which specific models succeeded vs failed.

---

## Finding 5: Missing Layer in Argparse Choices (Fixed)

**Issue:** `ind-gold-transform` CronJob passes `--layer ind_gold`, but the argparse choices list did not include `ind_gold`.

**Error:**
```
transform_molecules.py: error: argument --layer/-l: invalid choice: 'ind_gold' 
(choose from 'bronze', 'silver', 'gold', 'ip_bronze', 'ip_silver', 'ip_gold', 
'hcs_bronze', 'hcs_silver', 'mol_bronze_ext', 'mol_silver_ext', 'mol_gold_ext', 
'ind_bronze', 'ind_silver', 'mart', 'all')
```

**Status:** Fixed in commit `6820b3c` — `ind_gold` added to argparse choices and `transform_all_layers()` sequence.

---

## Finding 6: Models Not in Any LAYER_MODELS (Unrunnable)

238 SQL model files exist, and the LAYER_MODELS dictionary lists models across 15 layers. Cross-referencing reveals some models exist in SQL but may not be assigned to any layer:

| Model | Has SQL File | Notes |
|-------|-------------|-------|
| `mol_gold.molecule_profiles_agg` | Unknown | Referenced in `gold` layer but may be a view/alias |
| `mol_gold.safety_signals_agg` | Unknown | Same |
| `mol_gold.trial_analytics_agg` | Unknown | Same |
| `mol_silver.molecules_from_bronze` | Unknown | Referenced as "entity hub — must be first" in `silver` layer |
| `mol_silver.indication_epidemiology` | Unknown | In `mol_silver_ext` but may not have SQL file |
| `scoring.*` | 2 SQL files | Not in any LAYER_MODELS entry |
| `targeting.*` | 2 SQL files | Not in any LAYER_MODELS entry |
| `staging.*` | 4 SQL files | Not in any LAYER_MODELS entry (but registered in SQLMesh snapshots) |

The `staging`, `scoring`, and `targeting` models (8 total) have SQL files but are not assigned to any layer in `LAYER_MODELS`, meaning `transform_all_layers()` would never run them. They may be implicitly pulled in by SQLMesh dependency resolution when downstream models reference them.

---

## Finding 7: cms-gold-refresh Uses Shell Script, Not transform_molecules.py

The `cms-gold-refresh` CronJob uses an inline shell script (not `python -m dk_data.ingestion.transform_molecules`). It:

1. Checks if SQLMesh is initialized by querying `sqlmesh._snapshots`
2. If not initialized, runs `sqlmesh plan --auto-apply --skip-backfill`
3. Then runs `sqlmesh run` with individual `--select-model` flags for HCS gold models

This is a separate initialization path from `transform_molecules.py`, which means:
- It has its own initialization timeout and error handling
- It may succeed or fail independently of the Python-based transforms
- The shell script's initialization check is different from the Python one

---

## Finding 8: "Skipped Models" During Plan

When `sqlmesh plan` runs, it reports "Skipped models" — these are models that cannot be updated because their upstream dependencies haven't changed or don't exist yet. The skipped model list changes between runs (different random order) but consistently includes:

- All `mol_silver.*` models (depend on `mol_bronze.*` which hasn't been backfilled)
- All `hcs_silver.*` models (depend on `hcs_bronze.*`)
- All `*_gold.*` models (depend on `*_silver.*`)
- `staging.*` models

This is expected behavior — SQLMesh correctly identifies that these models can't be populated yet because their source data doesn't exist in the bronze tables.

---

## Summary: Would Transforms Run Cleanly?

### Bronze Layer
- **chembl_molecules**: YES — successfully processed 2.88M rows in test run
- **openfda_labels**: NO — integer overflow on `spl_version` column
- **All other bronze models** (87 remaining): UNTESTED — the `prod` environment was just initialized and no other layers have been run yet. They would likely encounter similar data-type issues since none have been validated against real production data.

### Silver / Gold / Mart Layers
- **Cannot be tested** until bronze completes successfully. All silver models read from bronze tables which are currently empty (0 rows). Running silver now would produce empty results, not errors.

### Blocking Issues (in priority order)

| # | Issue | Impact | Fix Complexity |
|---|-------|--------|----------------|
| 1 | `openfda_labels` INTEGER overflow | Blocks entire `bronze` layer | Trivial — change `::INTEGER` to `::BIGINT` |
| 2 | No partial-success handling | One model failure fails entire layer batch | Medium — parse SQLMesh output for per-model status |
| 3 | No inter-CronJob dependency gates | Downstream layers run on empty data | Medium — add init check or job completion gate |
| 4 | Potential INTEGER overflows in other models | Unknown until real data flows | Low — audit all `::INTEGER` casts |
| 5 | `staging`/`scoring`/`targeting` models not in LAYER_MODELS | These 8 models never run directly | Low — add to appropriate layer or verify implicit execution |
| 6 | `dailymed.sql` spl_version same pattern as openfda_labels | May fail when dailymed bronze runs | Trivial — same fix as #1 |

### Recommended Test Sequence

To validate the full pipeline without fixing code:

1. Fix `openfda_labels` INTEGER → BIGINT (single line change)
2. Manually trigger `bronze` layer and verify
3. Trigger `mol_bronze_ext` + `hcs_bronze` + `ip_bronze` and verify
4. Trigger `silver` → `hcs_silver` → `ip_silver` → `mol_silver_ext`
5. Trigger `gold` → `ip_gold` → `mol_gold_ext` → `mart`
6. At each step, check for new data-level errors in the SQLMesh output
