-- staging.certifications - ACC TVC Certifications with active status
-- Source: hcs_raw.acc_tvc_certification
-- Model type: FULL refresh

MODEL (
    name staging.certifications,
    kind FULL,
    cron '@daily',
    description 'Transcatheter Valve Certifications from ACC/NCDR'
);

-- acc_tvc_certification is a legacy file source loaded manually.
-- When not yet loaded, return empty result set with the correct schema.
WITH acc_tvc AS (
    SELECT
        NULL::TEXT  AS id,
        NULL::TEXT  AS facility_name,
        NULL::TEXT  AS certification_type,
        NULL::DATE  AS certification_date,
        NULL::DATE  AS expiration_date,
        NULL::TEXT  AS state,
        NULL::TEXT  AS city,
        NULL::TEXT  AS zip_code
    WHERE FALSE  -- empty until acc_tvc file is loaded
),
matched_hospitals AS (
    SELECT DISTINCT
        h.facility_id AS hospital_id,
        c.facility_name,
        c.certification_type,
        c.certification_date,
        c.expiration_date,
        ROW_NUMBER() OVER (
            PARTITION BY c.id
            ORDER BY
                CASE WHEN UPPER(c.state) = UPPER(h.state) THEN 0 ELSE 1 END,
                CASE WHEN UPPER(c.city) = UPPER(h.city_town) THEN 0 ELSE 1 END,
                h._loaded_at DESC
        ) AS match_rank
    FROM acc_tvc c
    JOIN hcs_bronze.cms_hospital_general_info h ON (
        UPPER(c.state) = UPPER(h.state)
        AND (
            UPPER(c.city) = UPPER(h.city_town)
            OR LEFT(c.zip_code, 5) = LEFT(h.zip_code, 5)
        )
        AND (
            UPPER(h.facility_name) LIKE '%' || UPPER(SPLIT_PART(c.facility_name, ' ', 1)) || '%'
            OR UPPER(c.facility_name) LIKE '%' || UPPER(SPLIT_PART(h.facility_name, ' ', 1)) || '%'
        )
    )
    WHERE c.facility_name IS NOT NULL
)
SELECT
    hospital_id,
    certification_type,
    'ACC' AS certifying_body,
    certification_date,
    expiration_date,
    -- Active if no expiration or expiration is in the future
    CASE
        WHEN expiration_date IS NULL THEN TRUE
        WHEN expiration_date >= CURRENT_DATE THEN TRUE
        ELSE FALSE
    END AS is_active,
    NOW() AS _updated_at
FROM matched_hospitals
WHERE match_rank = 1
-- Deduplicate by hospital and certification type
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY hospital_id, certification_type
    ORDER BY certification_date DESC NULLS LAST
) = 1;
