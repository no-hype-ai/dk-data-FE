-- Migration 151: Create mol_raw.websearch table for web/news search API responses
-- Feature: 026-fetcher-checkpoint-resume
--
-- Stores raw web and news search API responses (e.g. from SerpAPI, NewsAPI, etc.)
-- The bronze model mol_bronze.websearch reads from this table.

CREATE TABLE IF NOT EXISTS mol_raw.websearch (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        TEXT,
    api_version         TEXT,
    request_params      JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           TEXT NOT NULL DEFAULT 'websearch'
);

CREATE UNIQUE INDEX IF NOT EXISTS mol_raw_websearch_request_id_uq
    ON mol_raw.websearch (request_id)
    WHERE request_id IS NOT NULL;
