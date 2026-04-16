-- Custom SQLMesh audits for silver/gold layer boundaries (horizon-2 C.7).
-- These complement the built-in audits (not_null, unique_values, number_of_rows,
-- accepted_values, forall, etc.) that ship with SQLMesh 0.230.
--
-- Usage — declare on a model's MODEL (...) block:
--
--   audits (
--     not_null(columns := (molecule_id)),
--     unique_values(columns := (molecule_id)),
--     referential_integrity(
--       parent_model := mol_silver.molecules,
--       parent_key := molecule_id,
--       child_key := molecule_id
--     ),
--     freshness_threshold(time_column := last_updated_at, max_age_seconds := 86400),
--     row_count_above(min_rows := 1000)
--   )
--
-- SQLMesh audit semantics: an audit PASSES when its SELECT returns zero rows
-- and FAILS otherwise. Every audit below therefore returns rows only on violation.
-- See docs/sqlmesh/audits.md for the audit taxonomy and when to tighten tolerances.

-- ---------------------------------------------------------------------------
-- referential_integrity — FR-014 hub crosswalk enforcement (feature 001).
--
-- Fails when child rows reference a @child_key that does not exist in the
-- parent hub's @parent_key. Silver spoke tables use this against their hub
-- (e.g. mol_silver.molecule_identifiers -> mol_silver.molecules on molecule_id).
--
-- Uses NOT EXISTS over a LEFT JOIN to stay planner-friendly (no OR-joins /
-- S1 antipattern). @child_key IS NOT NULL guard allows nullable FKs.
-- ---------------------------------------------------------------------------
AUDIT (
  name referential_integrity
);
SELECT c.@child_key AS missing_parent
FROM @this_model AS c
WHERE c.@child_key IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM @parent_model p
    WHERE p.@parent_key = c.@child_key
  );

-- ---------------------------------------------------------------------------
-- freshness_threshold — staleness budget for gold models.
--
-- Fails when MAX(@time_column) is older than @max_age_seconds. Default budget
-- in docs/sqlmesh/audits.md is 86400s (daily refresh). Tighten to 3600s for
-- hot models, loosen to 604800s for monthly crons (@monthly).
--
-- NB: we check MAX, not row-level timestamps — a single fresh row is enough
-- to prove the model ran; per-row staleness is a different audit (not added
-- here to avoid false-positive thrash on slowly-changing dimensions).
-- ---------------------------------------------------------------------------
AUDIT (
  name freshness_threshold
);
SELECT 1 AS stale
FROM (SELECT MAX(@time_column) AS max_ts FROM @this_model) t
WHERE t.max_ts IS NULL
   OR t.max_ts < NOW() - MAKE_INTERVAL(secs => @max_age_seconds);

-- ---------------------------------------------------------------------------
-- row_count_above — lower-bound row count audit.
--
-- Fails when the model has fewer than @min_rows rows. Catches silent drops
-- where a join goes wrong and the model materializes empty or near-empty.
-- Prefer this to percentage-based audits for incremental models whose prior-
-- run baseline is not recorded in SQLMesh state.
--
-- When a model has a known minimum floor (e.g. mol_silver.molecules > 50k),
-- set min_rows to ~80% of the observed steady-state count. Too tight and
-- you page on legitimate shrinkage; too loose and a silent-drop slips.
-- ---------------------------------------------------------------------------
AUDIT (
  name row_count_above
);
SELECT 1 AS below_threshold
FROM (SELECT COUNT(*) AS n FROM @this_model) c
WHERE c.n < @min_rows;

-- ---------------------------------------------------------------------------
-- row_count_within_pct — drift-vs-baseline audit (parameterized template).
--
-- Compares current row count to a recorded baseline in
-- meta.sqlmesh_row_count_baseline (populated out-of-band by a separate job —
-- see docs/sqlmesh/audits.md §"Baseline maintenance"). Fails when the
-- absolute delta exceeds @tolerance_pct of the baseline.
--
-- Intentionally NOT declared `standalone true` — the baseline table is not
-- populated yet (follow-up work, see docs/sqlmesh/audits.md §"Percentage
-- drift audits"). Declaring it standalone would force SQLMesh to resolve
-- @tolerance_pct / @target_model / @model_name at plan time with no binding,
-- which fails compilation. Leaving it as a parameterized audit keeps the
-- definition dormant until a model opts in by invoking it with concrete args:
--
--   audits (
--     row_count_within_pct(
--       target_model := mol_gold.molecule_profile,
--       model_name := 'mol_gold.molecule_profile',
--       tolerance_pct := 10
--     )
--   )
--
-- Once activated, @model_name must match baseline.model_name exactly.
-- ---------------------------------------------------------------------------
AUDIT (
  name row_count_within_pct
);
SELECT curr.n AS current_count,
       base.row_count AS baseline_count,
       @tolerance_pct AS tolerance_pct
FROM (SELECT COUNT(*) AS n FROM @target_model) curr
CROSS JOIN (
  SELECT row_count
  FROM meta.sqlmesh_row_count_baseline
  WHERE model_name = @model_name
  ORDER BY recorded_at DESC
  LIMIT 1
) base
WHERE ABS(curr.n - base.row_count)::numeric / GREATEST(base.row_count, 1)
      > (@tolerance_pct / 100.0);
