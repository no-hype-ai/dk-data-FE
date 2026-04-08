-- SQLMesh Model: Bronze CMS Medicare Part B Drug Spending
-- Transforms raw CMS data.cms.gov Part B spending API responses to Bronze typed columns.
-- API: https://data.cms.gov/data-api/v1/dataset/{id}/data
-- Response shape: JSON array of spending records (one per drug per year)
-- Silver reads: mol_silver.drug_spending via mol_bronze.cms_medicare

MODEL (
    name mol_bronze.cms_medicare,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (generic_name, program, year)
    ),
    cron '@monthly',
    grain (generic_name, program, year)
);

WITH expanded AS (
    SELECT
        r.id              AS raw_source_id,
        r.ingested_at,
        rec.value         AS row
    FROM mol_raw.cms_medicare r,
         LATERAL jsonb_array_elements(
             CASE
                 WHEN jsonb_typeof(r.response_body) = 'array' THEN r.response_body
                 WHEN r.response_body ? 'data'                THEN r.response_body->'data'
                 WHEN r.response_body ? 'results'             THEN r.response_body->'results'
                 ELSE '[]'::jsonb
             END
         ) AS rec(value)
    WHERE r.ingested_at BETWEEN @start_dt AND @end_dt
)

SELECT DISTINCT ON (
    COALESCE(row->>'hcpcs_desc', row->>'generic_name', row->>'drug_name'),
    COALESCE(row->>'program', 'Part B'),
    COALESCE(row->>'year', row->>'cal_year', row->>'srvc_yr')
)
    gen_random_uuid()                                                           AS id,

    -- Drug name: CMS Part B uses hcpcs_desc; Part D uses generic_name
    COALESCE(row->>'hcpcs_desc', row->>'generic_name', row->>'drug_name')      AS generic_name,
    COALESCE(row->>'brand_name', row->>'brdname')                              AS brand_name,
    COALESCE(row->>'hcpcs_cd', row->>'ndc')                                   AS drug_code,
    COALESCE(row->>'program', 'Part B')                                        AS program,
    COALESCE(
        (row->>'year')::INTEGER,
        (row->>'cal_year')::INTEGER,
        (row->>'srvc_yr')::INTEGER
    )                                                                           AS year,

    -- Spending fields — CMS Part B field names vary by dataset version
    COALESCE(
        (row->>'tot_suplcnt')::NUMERIC,
        (row->>'total_supply_days')::NUMERIC
    )                                                                           AS total_supply_days,

    COALESCE(
        (row->>'tot_clms')::INTEGER,
        (row->>'total_claims')::INTEGER,
        (row->>'clm_cnt')::INTEGER
    )                                                                           AS total_claims,

    COALESCE(
        (row->>'bene_count')::INTEGER,
        (row->>'tot_benes')::INTEGER,
        (row->>'total_beneficiaries')::INTEGER
    )                                                                           AS total_beneficiaries,

    COALESCE(
        (row->>'tot_drug_cst')::NUMERIC,
        (row->>'total_spending')::NUMERIC
    )                                                                           AS total_spending,

    COALESCE(
        (row->>'avg_drug_cst')::NUMERIC,
        (row->>'avg_cost_per_claim')::NUMERIC
    )                                                                           AS avg_cost_per_claim,

    -- avg_cost_per_day: not available in CMS Part B/D API fields;
    -- would require total_spending / total_supply_days but supply days is Part D only
    NULL::NUMERIC                                                               AS avg_cost_per_day,

    COALESCE(
        (row->>'avg_mdcr_pymt_amt')::NUMERIC,
        (row->>'avg_cost_per_beneficiary')::NUMERIC
    )                                                                           AS avg_cost_per_beneficiary,

    -- Raw source tracking
    row                                                                         AS raw_json,
    raw_source_id,
    'cms_medicare'                                                              AS source,
    ingested_at,
    ingested_at                                                           AS source_updated_at,
    FALSE                                                                       AS processed_to_silver,
    NOW()                                                                       AS created_at

FROM expanded
WHERE COALESCE(row->>'hcpcs_desc', row->>'generic_name', row->>'drug_name') IS NOT NULL
ORDER BY
    COALESCE(row->>'hcpcs_desc', row->>'generic_name', row->>'drug_name'),
    COALESCE(row->>'program', 'Part B'),
    COALESCE(row->>'year', row->>'cal_year', row->>'srvc_yr'),
    ingested_at DESC NULLS LAST;
