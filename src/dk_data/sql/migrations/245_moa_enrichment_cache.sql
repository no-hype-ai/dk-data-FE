-- 245: MOA enrichment cache.
--
-- Caches free-text mechanism-of-action lookups against external sources
-- (OpenFDA, ChEMBL) so the competitor-search graph service doesn't hit
-- those APIs on every request for the same novel MOA.
--
-- Lookup precedence (in code, not SQL):
--   1. static dict in services/.../moa_enrichment.py (~97 common MOAs)
--   2. this cache table
--   3. external API resolver → INSERT here on miss (negative or positive)
--
-- Cache is forever by default. To refresh a row, DELETE it manually and
-- the next lookup will re-resolve from APIs.

CREATE TABLE IF NOT EXISTS mol_silver.moa_enrichment_cache (
    moa_key              TEXT PRIMARY KEY,
    fda_pharm_class_moa  TEXT,
    fda_pharm_class_epc  TEXT,
    targets              TEXT[] NOT NULL DEFAULT '{}',
    atc_prefix           TEXT,
    source               TEXT NOT NULL,
    confidence           SMALLINT NOT NULL DEFAULT 50,
    is_negative          BOOLEAN NOT NULL DEFAULT FALSE,
    hit_count            INTEGER NOT NULL DEFAULT 0,
    cached_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT moa_enrichment_cache_source_chk
        CHECK (source IN ('openfda', 'chembl', 'manual', 'negative'))
);

CREATE INDEX IF NOT EXISTS idx_moa_cache_last_used
    ON mol_silver.moa_enrichment_cache (last_used_at);

CREATE INDEX IF NOT EXISTS idx_moa_cache_source
    ON mol_silver.moa_enrichment_cache (source);

COMMENT ON TABLE mol_silver.moa_enrichment_cache IS
    'API-resolved MOA → pharm_class/targets/ATC cache. Filled lazily on cache miss in CompetitorSearchService graph build.';
COMMENT ON COLUMN mol_silver.moa_enrichment_cache.is_negative IS
    'TRUE = APIs returned nothing; cached so we do not re-query the same unknown MOA forever.';
COMMENT ON COLUMN mol_silver.moa_enrichment_cache.confidence IS
    '0-100. Higher when multiple sources agree. Used as tiebreak; not a strict filter.';
