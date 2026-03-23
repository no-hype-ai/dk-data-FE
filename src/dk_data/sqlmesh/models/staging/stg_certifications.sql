-- staging.certifications - ACC TVC Certifications with active status
-- Source: raw.acc_tvc_certification
-- Model type: FULL refresh

MODEL (
    name hcs_silver.certifications,
    kind FULL,
    cron '@daily',
    description 'Transcatheter Valve Certifications from ACC/NCDR'
);

WITH matched_hospitals AS (
    -- Match ACC TVC facilities to CMS hospital IDs by name and location
    SELECT DISTINCT
        h.provider_id AS hospital_id,
        c.response_body->>'facility_name'    AS facility_name,
        c.response_body->>'certification_type' AS certification_type,
        CASE WHEN c.response_body->>'certification_date' ~ '^\d{4}-\d{2}-\d{2}'
             THEN (c.response_body->>'certification_date')::DATE ELSE NULL END AS certification_date,
        CASE WHEN c.response_body->>'expiration_date' ~ '^\d{4}-\d{2}-\d{2}'
             THEN (c.response_body->>'expiration_date')::DATE ELSE NULL END AS expiration_date,
        -- Calculate similarity for matching
        ROW_NUMBER() OVER (
            PARTITION BY c.id
            ORDER BY
                -- Prioritize exact state match
                CASE WHEN UPPER(c.response_body->>'state') = UPPER(h.state) THEN 0 ELSE 1 END,
                -- Then city match
                CASE WHEN UPPER(c.response_body->>'city') = UPPER(h.city) THEN 0 ELSE 1 END,
                h._loaded_at DESC
        ) AS match_rank
    FROM mol_raw.acc_tvc_certification c
    JOIN hcs_raw.cms_hospital_info h ON (
        -- Match by state (required)
        UPPER(c.response_body->>'state') = UPPER(h.state)
        -- And either city match or zip match
        AND (
            UPPER(c.response_body->>'city') = UPPER(h.city)
            OR LEFT(c.response_body->>'zip_code', 5) = LEFT(h.zip_code, 5)
        )
        -- And fuzzy name match (contains check)
        AND (
            UPPER(h.hospital_name) LIKE '%' || UPPER(SPLIT_PART(c.response_body->>'facility_name', ' ', 1)) || '%'
            OR UPPER(c.response_body->>'facility_name') LIKE '%' || UPPER(SPLIT_PART(h.hospital_name, ' ', 1)) || '%'
        )
    )
    WHERE (c.response_body->>'facility_name') IS NOT NULL
      AND c.response_status = 200
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
