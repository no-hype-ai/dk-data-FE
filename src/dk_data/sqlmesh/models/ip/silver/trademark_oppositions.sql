-- T071: ip_silver.trademark_oppositions — FULL model
-- One row per opposition from USPTO tta_proceedings and EUIPO oppositions.
-- Sources: ip_bronze.uspto_trademarks.tta_proceedings (T063 expansion),
--          ip_bronze.euipo_trademarks.oppositions (T066 expansion).
-- Part of: 006-claims-engine-data-gaps (Item 28)

MODEL (
    name ip_silver.trademark_oppositions,
    kind FULL,
    cron '@weekly',
    grain (trademark_id, opponent, filing_date, jurisdiction)
);

WITH uspto_oppositions AS (
    -- Unnest USPTO TTA (Trademark Trial and Appeal) proceedings
    SELECT
        ('x' || substr(md5('US:' || COALESCE(u.registration_number, u.serial_number)), 1, 16))::bit(64)::bigint AS trademark_id,
        proc.value->>'opponent' AS opponent,
        (proc.value->>'filing_date')::DATE AS filing_date,
        proc.value->>'decision' AS decision,
        (proc.value->>'decision_date')::DATE AS decision_date,
        'US' AS jurisdiction
    FROM ip_bronze.uspto_trademarks u,
         jsonb_array_elements(u.tta_proceedings) AS proc(value)
    WHERE u.tta_proceedings IS NOT NULL
      AND jsonb_typeof(u.tta_proceedings) = 'array'
),

euipo_oppositions AS (
    -- Unnest EUIPO oppositions
    SELECT
        ('x' || substr(md5('EU:' || u.application_number), 1, 16))::bit(64)::bigint AS trademark_id,
        opp.value->>'opponent' AS opponent,
        (opp.value->>'filing_date')::DATE AS filing_date,
        opp.value->>'decision' AS decision,
        (opp.value->>'decision_date')::DATE AS decision_date,
        'EU' AS jurisdiction
    FROM ip_bronze.euipo_trademarks u,
         jsonb_array_elements(u.oppositions) AS opp(value)
    WHERE u.oppositions IS NOT NULL
      AND jsonb_typeof(u.oppositions) = 'array'
)

SELECT
    trademark_id,
    opponent,
    filing_date,
    decision,
    decision_date,
    jurisdiction,
    NOW() AS last_updated_at
FROM (
    SELECT * FROM uspto_oppositions
    UNION ALL
    SELECT * FROM euipo_oppositions
) combined
