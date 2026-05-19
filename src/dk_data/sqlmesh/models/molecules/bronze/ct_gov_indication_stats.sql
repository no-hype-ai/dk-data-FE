-- SQLMesh Model: Bronze ClinicalTrials.gov Indication Statistics
-- Aggregates trial counts per condition from mol_raw.clinicaltrials raw data.
-- Derived from: mol_raw.clinicaltrials (populated by ClinicalTrialsFetcher).
-- No separate raw table needed — this is a derived bronze aggregation.
-- Part of: 003-molecule-assessment-dashboard

MODEL (
    name mol_bronze.ct_gov_indication_stats,
    kind FULL,
    cron '@weekly'
);

SELECT
    gen_random_uuid()::text                                            AS id,
    NOW()                                                              AS request_timestamp,
    lower(trim(cond_name.value #>> '{}'))                              AS condition_query,
    COUNT(DISTINCT study.value #>> '{protocolSection,identificationModule,nctId}')
                                                                       AS total_count,
    COUNT(DISTINCT study.value #>> '{protocolSection,identificationModule,nctId}')
        FILTER (
            WHERE (study.value #>> '{protocolSection,statusModule,overallStatus}')
              IN ('RECRUITING', 'ACTIVE_NOT_RECRUITING', 'ENROLLING_BY_INVITATION')
        )                                                              AS active_count,
    NOW()                                                              AS fetched_at

FROM mol_raw.clinicaltrials r,
     LATERAL jsonb_array_elements(
         COALESCE(r.response_body -> 'studies', '[]'::jsonb)
     ) AS study(value),
     LATERAL jsonb_array_elements(
         COALESCE(
             study.value #> '{protocolSection,conditionsModule,conditions}',
             '[]'::jsonb
         )
     ) AS cond_name(value)

WHERE
    cond_name.value #>> '{}' IS NOT NULL
    AND cond_name.value #>> '{}' != ''

GROUP BY lower(trim(cond_name.value #>> '{}'))
HAVING COUNT(DISTINCT study.value #>> '{protocolSection,identificationModule,nctId}') > 0
