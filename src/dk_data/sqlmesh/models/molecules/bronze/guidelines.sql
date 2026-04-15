-- SQLMesh Model: Bronze Treatment Guidelines
-- Passthrough from mol_raw.guidelines with dedup on (body, title, version)
-- Part of: 006-claims-engine-data-gaps (Item 8, T049)

MODEL (
    name mol_bronze.guidelines,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (body, title, version)
    ),
    cron '@weekly',
    grain (body, title, version)
);

SELECT
    r.id                AS raw_source_id,
    r.body,
    r.title,
    r.publication_date,
    r.version,
    r.indication_icd11,
    r.indication_name,
    r.source_url,
    r.full_text,
    r.sections,
    r.recommendations,
    r.ingested_at,
    'guidelines' AS source,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.guidelines r
WHERE r.body IS NOT NULL
  AND r.title IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt
