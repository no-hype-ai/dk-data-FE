-- Migration 142: Add unique index for cms_dual_eligible deduplication
-- Required by ON CONFLICT (state_cd, dual_elgbl_lvl, _source_year) in the loader.
-- Now that cms_dual_eligible has a real fetcher (Excel parser), this index
-- enables idempotent upserts on re-runs.

CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_dual_eligible_key
    ON hcs_raw.cms_dual_eligible (state_cd, dual_elgbl_lvl, _source_year);
