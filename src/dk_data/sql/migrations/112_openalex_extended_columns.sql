-- Migration 112: OpenAlex extended columns
-- Adds additional fields to mol_raw.openalex_ci that the OpenAlexCIFetcher
-- now extracts from the API response. These fields were previously NULL in
-- the bronze model because they were not stored at the raw layer.
--
-- Fields added:
--   pmid, pmcid, mag_id     — cross-reference IDs from the ids object
--   work_type               — OpenAlex work type (journal-article, etc.)
--   language                — BCP-47 language code
--   volume, issue, first_page, last_page — bibliographic fields from biblio object
--   topics                  — OpenAlex topics JSONB array
--   keywords                — author-provided keywords JSONB array
--   mesh_terms              — MeSH terms JSONB array
--   cited_by_percentile     — citation percentile (0-100) NUMERIC
--   citation_counts_by_year — JSONB array of {year, cited_by_count}
--   grants                  — JSONB array of grant objects
--   referenced_works        — JSONB array of referenced work IDs
--   related_works           — JSONB array of related work IDs
--   sustainable_development_goals — JSONB array of UN SDG objects
--   best_oa_location        — JSONB object with best OA URL
--   is_retracted            — BOOLEAN retraction flag
--   is_paratext             — BOOLEAN paratext flag

ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS pmid                         TEXT;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS pmcid                        TEXT;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS mag_id                       TEXT;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS work_type                    TEXT;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS language                     TEXT;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS volume                       TEXT;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS issue                        TEXT;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS first_page                   TEXT;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS last_page                    TEXT;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS topics                       JSONB;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS keywords                     JSONB;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS mesh_terms                   JSONB;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS cited_by_percentile          NUMERIC;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS citation_counts_by_year      JSONB;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS grants                       JSONB;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS referenced_works             JSONB;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS related_works                JSONB;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS sustainable_development_goals JSONB;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS best_oa_location             JSONB;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS is_retracted                 BOOLEAN;
ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS is_paratext                  BOOLEAN;

-- Index on pmid for cross-reference joins
CREATE INDEX IF NOT EXISTS idx_mol_raw_openalex_ci_pmid
    ON mol_raw.openalex_ci (pmid)
    WHERE pmid IS NOT NULL;
