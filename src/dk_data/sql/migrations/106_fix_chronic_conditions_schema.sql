-- Migration 106: Fix chronic conditions year column
-- Applied: 2026-03-14
--
-- The CMS Chronic Conditions CSV does not include a year column.
-- Make year nullable so the loader can insert without it.

ALTER TABLE raw.cms_chronic_conditions ALTER COLUMN year DROP NOT NULL;
