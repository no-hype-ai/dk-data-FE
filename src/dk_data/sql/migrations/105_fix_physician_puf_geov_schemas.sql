-- Migration 105: Fix physician PUF default partition and geographic variation PK
-- Applied: 2026-03-14

-- Create a default partition for cms_physician_puf to handle records without year
CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf_default
    PARTITION OF hcs_raw.cms_physician_puf DEFAULT;

-- Fix geographic_variation PK to (state, year) — state alone causes
-- ON CONFLICT collisions when multiple years share the same state
ALTER TABLE hcs_raw.cms_geographic_variation DROP CONSTRAINT IF EXISTS cms_geographic_variation_pkey;
ALTER TABLE hcs_raw.cms_geographic_variation ADD PRIMARY KEY (state, year);
