-- SQLMesh Model: Silver EMA (European Medicines Agency authorised medicines)
-- Promotes bronze.ema to silver layer for the EMA authorized medicines vocabulary.
-- Feature: PR #415 Phase 1 (fix/415-phase1-db-first-router)
--
-- Grain: product_number (EMA authorisation number)
-- Source: bronze.ema (from raw.ema via EMAMolFetcher ingestion pipeline)
--
-- molecule_id is deferred to the entity-resolution pipeline (no inline fuzzy join).
-- See: AGENTS.md §"Silver Hub Architecture" antipatterns S1–S5.

MODEL (
    name mol_silver.ema,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (product_number, product_name))
    ),
    grain product_number
);

-- Deduplicate within the single source: keep the most recently ingested record
-- per product_number. DISTINCT ON over a single source (no UNION ALL) is permitted
-- by silver rules (S4 only bans DISTINCT ON over UNION ALL).
SELECT DISTINCT ON (b.product_number)
    gen_random_uuid() AS id,  -- surrogate id (regenerated each FULL rebuild — matches silver convention)
    b.product_number,
    b.product_name,
    b.active_substance,
    b.inn,
    b.atc_code,
    b.marketing_authorization_holder,
    b.authorization_status,
    b.authorization_date,
    b.revision_date,                -- retained for lineage; not consumed by ema.py _db_query
    b.medicine_type,
    b.therapeutic_area,
    b.pharmacotherapeutic_group,
    b.epar_url,
    b.summary_url,
    -- Entity resolution deferred: molecule_id linked by downstream resolve pipeline.
    -- Do NOT inline-fuzzy-join here (silver antipattern S1/S5).
    NULL::UUID AS molecule_id,  -- linked by entity resolution
    'ema'::TEXT                 AS source,
    b.ingested_at               AS source_updated_at,
    b.ingested_at,
    CURRENT_TIMESTAMP           AS _silver_updated_at
FROM bronze.ema AS b
WHERE b.product_number IS NOT NULL
  AND b.product_name IS NOT NULL
ORDER BY b.product_number, b.ingested_at DESC NULLS LAST

-- NOTE: kind FULL — this model is a COMPLETE snapshot of the current EMA
-- authorized-medicines vocabulary, rebuilt from all of bronze.ema each run.
-- It deliberately does NOT filter on bronze.processed_to_silver: under FULL,
-- that filter would drop every previously-promoted medicine on rebuild once
-- the external processed_to_silver marker is set (the flag is flipped outside
-- SQLMesh; cf. the trailing NOTE in silver/drug_labels.sql, which can filter
-- safely only because it is INCREMENTAL_BY_UNIQUE_KEY, not FULL).
