# SQLMesh audit runbook

Audits run automatically after each model refresh. A failing audit marks the snapshot as failed in SQLMesh state and blocks promotion. This document covers the audit taxonomy in this repo, when to tighten thresholds, and how to interpret failures.

Related code:
- Custom audit definitions: `src/dk_data/sqlmesh/audits/custom_audits.sql`
- Model-level audit declarations: `src/dk_data/sqlmesh/models/*/silver/*.sql`, `*/gold/*.sql`
- Integration test: `tests/sqlmesh/test_audits.py`
- Horizon plan: plan.md §C.7 (horizon-2 observability)

## Audit taxonomy

| Audit | Source | Fails when | Use on |
|-------|--------|------------|--------|
| `not_null` | built-in | Any row in `columns` is NULL | Silver hub ER keys, gold dimension keys |
| `unique_values` | built-in | A value in `columns` appears >1 time | Silver hub natural keys, gold grain |
| `unique_combination_of_columns` | built-in | A combination appears >1 time | Composite grains in gold |
| `number_of_rows` | built-in | Row count ≤ `threshold` | Hard minima only; prefer `row_count_above` |
| `accepted_values` / `not_accepted_values` | built-in | Value outside allow/deny list | Enum-like columns (status, tier, type) |
| `forall` | built-in | Any row fails `criteria` predicate | Ad-hoc sanity checks |
| **`referential_integrity`** | custom | A child FK does not resolve in the parent hub | Silver hub crosswalks — enforces FR-014 |
| **`freshness_threshold`** | custom | `MAX(time_column)` older than `max_age_seconds` | Gold models with known crons |
| **`row_count_above`** | custom | `COUNT(*)` < `min_rows` | Gold models (silent-drop guard) |
| **`row_count_within_pct`** | custom (standalone) | |current − baseline| > `tolerance_pct` of `meta.sqlmesh_row_count_baseline.row_count` | Gold models with a recorded baseline |

The four custom audits are defined in `src/dk_data/sqlmesh/audits/custom_audits.sql`. SQLMesh auto-discovers any `.sql` file in that directory.

## Per-layer baseline

### Silver hub tables (the 10 canonical hubs)

Every hub table has three minimum audits:

```
audits (
    not_null(columns := (<hub_id>)),
    unique_values(columns := (<hub_id>)),
    -- only when the table crosswalks to a parent hub
    referential_integrity(parent_model := <parent_hub>, parent_key := <pk>, child_key := <fk>)
)
```

The `<hub_id>` is always the deterministic hash key: `molecule_id`, `product_id`, `company_id`, `target_id`, `provider_id`, `facility_id`, `condition_id`, `researcher_id`, `patent_id`, or `trademark_id`. See `.claude/CLAUDE.md` §"Silver Hub Architecture" for the full hub matrix.

`referential_integrity` is wired up today for the two IP hubs:
- `ip_silver.patents.molecule_id` → `mol_silver.molecules.molecule_id` (FR-034, Orange Book crosswalk)
- `ip_silver.trademarks.owner_company_id` → `mol_silver.companies.company_id`

Both FK columns are nullable; the audit skips NULLs intentionally (most patents are not drug-linked).

### Gold tables

Gold models add two audits on top of the silver-style not_null / unique_values:

```
audits (
    ...,
    row_count_above(min_rows := <floor>),
    freshness_threshold(time_column := <ts>, max_age_seconds := <budget>)
)
```

Default freshness budgets, derived from the model's `cron`:

| `cron` | `max_age_seconds` | Rationale |
|---|---|---|
| `@daily` | `172800` (2 days) | 1 skipped run + slack |
| `@weekly` | `1209600` (14 days) | 1 skipped run + slack |
| `@monthly` | `5184000` (60 days) | 1 skipped run + slack |

Tighten the freshness budget once the cron is reliably completing for 30+ days; the default is loose on purpose so a one-off cron hiccup doesn't fire an audit alarm.

`row_count_above(min_rows := N)` is a lower-bound guard, not a "within X%" drift alarm — see §"Percentage drift audits" below. Set `min_rows` to roughly 80% of the observed steady-state count.

## Percentage drift audits

`row_count_within_pct` is a **standalone audit** (declared with `standalone true` in `custom_audits.sql`). It compares the current `COUNT(*)` of `@target_model` against `meta.sqlmesh_row_count_baseline.row_count` for the matching `model_name`.

The baseline table is **not populated by this PR**. To activate these audits:

1. Create `meta.sqlmesh_row_count_baseline (model_name text, row_count bigint, recorded_at timestamptz)`.
2. Populate from the last 7 runs of `meta.transform_runs` with a helper job: for each gold model, insert the 90th-percentile row count as the baseline.
3. Declare the standalone audit in a top-level audit file or a `standalone_audit.sql` block.
4. Re-record the baseline monthly to track legitimate growth.

Until that infrastructure lands, prefer `row_count_above(min_rows := N)` — it catches the same silent-drop failure class (~empty model) without requiring external state.

## Interpreting audit failures

SQLMesh 0.230 surfaces audit failures in three places:

1. **CLI**: `sqlmesh run` exits non-zero and prints the failing model + audit name + the count of offending rows.
2. **UI**: the model snapshot turns red with a link to the failing audit. Click through to see the exact rendered SQL and the first ~100 offending rows.
3. **`sqlmesh_state.audits`** table in the state DB: each audit execution is logged with `model_name`, `audit_name`, `count`, `passed`, `executed_at`.

When an audit fails:

- **`not_null` on hub ER key** — bronze data changed shape or a silver UNION introduced a NULL-producing branch. Check the final `SELECT` of the model and the upstream bronze sources.
- **`unique_values` on hub ER key** — the deterministic hash collided or the `DISTINCT ON` dedup was removed. Confirm the hash derivation (FR-014 rule: both source CTEs must hash on the same canonical key expression).
- **`referential_integrity`** — a child record references a parent hub row that was deleted or never existed. For ip_silver this usually means the Orange Book crosswalk found a patent_no with no matching NDA in molecule_identifiers. Check `meta.linkage_conflicts` first.
- **`row_count_above`** — the model went empty or near-empty. Compare `COUNT(*)` before/after in `meta.transform_runs.row_count` to confirm; then walk the upstream silver dependencies.
- **`freshness_threshold`** — the model's cron has been skipping. Check the SQLMesh scheduler logs and the `meta.transform_runs.finished_at` for that model.

## When to tighten tolerances

Start loose, tighten over time. A hair-trigger audit that pages on every legitimate shrinkage erodes trust faster than no audit at all.

Rule of thumb:
- After 30 days of green runs, halve the freshness budget (2x → 1x the cron).
- After 90 days of stable counts, raise `min_rows` to 80% of the p10 observed count.
- Never tighten past the point where a legitimate bronze-source hiccup would fail the audit — those are upstream issues, not gold-layer issues.

## Adding audits to a new model

1. Pick the minimums from §"Per-layer baseline" above.
2. Declare them in the model's `MODEL (...)` block after `kind` / `cron` / before `grain`.
3. `uv run pytest tests/sqlmesh/test_audits.py` to confirm the audit renders.
4. For gold models, run `sqlmesh plan` and verify the audit appears in the snapshot plan.

## Banned antipattern reminder

Audits must not contradict the Silver Hub Architecture banned antipatterns (see CLAUDE.md):

- S1 (OR-join hub IDs): `referential_integrity` uses `NOT EXISTS` over a single key, not OR-joins.
- S2 (leading-wildcard LIKE): no audits use LIKE at all.
- S3 (correlated scalar subquery): `NOT EXISTS` is a semi-join, not a correlated scalar.
- S4 (DISTINCT ON over UNION ALL): audits read `@this_model` directly, no UNION.
- S5 (similarity + = in OR): no fuzzy matching in audits.

If you need an audit that does fuzzy matching or multi-key lookups, surface that as an explicit standalone audit — do not embed it into a silver hub model's audit block.
