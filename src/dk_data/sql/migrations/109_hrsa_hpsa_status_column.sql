-- Migration 109: Add hpsa_status to hcs_raw.hrsa_shortage_areas
-- HRSA bulk CSV includes "HPSA Status" column (e.g. "Designated", "Proposed Withdrawal").
-- Previously not extracted; loader and bronze model updated to capture it.

ALTER TABLE hcs_raw.hrsa_shortage_areas
    ADD COLUMN IF NOT EXISTS hpsa_status TEXT;
