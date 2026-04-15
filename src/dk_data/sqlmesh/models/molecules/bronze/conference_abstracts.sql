-- SQLMesh Model: Bronze Conference Abstracts
-- Passthrough from mol_raw.conference_abstracts to typed bronze layer.
-- Feature: 006-claims-engine-data-gaps (T079)

MODEL (
    name mol_bronze.conference_abstracts,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key abstract_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (abstract_id))
    ),
    grain (abstract_id)
);

SELECT
    r.abstract_id::TEXT                 AS abstract_id,
    r.conference_name::TEXT             AS conference_name,
    r.conference_body::TEXT             AS conference_body,
    r.conference_date                   AS conference_date,
    r.presentation_date                 AS presentation_date,
    r.presentation_type::TEXT           AS presentation_type,
    r.title::TEXT                       AS title,
    r.authors::JSONB                    AS authors,
    r.affiliations::JSONB               AS affiliations,
    r.abstract_text::TEXT               AS abstract_text,
    r.embargo_date                      AS embargo_date,
    r.publication_date                  AS publication_date,
    r.session_title::TEXT               AS session_title,
    r.track::TEXT                       AS track,
    r.source_url::TEXT                  AS source_url,

    -- Source tracking
    'conference_abstracts'              AS source,
    r.ingested_at                       AS source_updated_at,
    FALSE                               AS processed_to_silver,
    r.ingested_at                       AS ingested_at

FROM mol_raw.conference_abstracts r
WHERE r.abstract_id IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt;
