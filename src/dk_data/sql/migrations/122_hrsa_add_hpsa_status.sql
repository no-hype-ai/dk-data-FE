-- Migration 122: Add hpsa_status column to hcs_raw.hrsa_shortage_areas
-- The HRSA loader inserts hpsa_status (Designated, Proposed Withdrawal, etc.)
-- but the column was missing from the original table definition.

ALTER TABLE hcs_raw.hrsa_shortage_areas
    ADD COLUMN IF NOT EXISTS hpsa_status VARCHAR(100);
