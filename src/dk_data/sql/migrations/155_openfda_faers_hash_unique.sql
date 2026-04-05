-- Migration 155: Add unique index on mol_raw.openfda_faers.response_body_hash
-- The loader uses ON CONFLICT (response_body_hash) DO NOTHING for dedup but
-- no unique constraint existed on the column. NULL values are permitted and
-- PostgreSQL unique indexes allow multiple NULLs, so this is safe.

CREATE UNIQUE INDEX IF NOT EXISTS mol_raw_openfda_faers_hash_uniq
    ON mol_raw.openfda_faers (response_body_hash);
