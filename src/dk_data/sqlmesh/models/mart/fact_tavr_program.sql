-- mart.fact_tavr_program - TAVR program metrics by hospital and year
-- Source: staging.tavr_volumes, staging.certifications, mart.dim_hospital
-- Model type: INCREMENTAL by fiscal_year

MODEL (
    name mart.fact_tavr_program,
    kind FULL,
    cron '@daily',
    description 'TAVR program metrics including volumes and YoY changes'
);

WITH volume_aggregates AS (
    -- Aggregate TAVR volumes across DRG codes for each hospital/year
    SELECT
        hospital_id,
        fiscal_year,
        SUM(medicare_discharges) AS medicare_tavr_volume,
        SUM(estimated_total_discharges) AS estimated_total_volume
    FROM staging.tavr_volumes
    GROUP BY hospital_id, fiscal_year
),
volume_with_yoy AS (
    -- Calculate year-over-year change
    SELECT
        v.hospital_id,
        v.fiscal_year,
        v.medicare_tavr_volume,
        v.estimated_total_volume,
        -- YoY change as percentage
        CASE
            WHEN LAG(v.estimated_total_volume) OVER (
                PARTITION BY v.hospital_id
                ORDER BY v.fiscal_year
            ) > 0 THEN
                (v.estimated_total_volume - LAG(v.estimated_total_volume) OVER (
                    PARTITION BY v.hospital_id
                    ORDER BY v.fiscal_year
                ))::DECIMAL / LAG(v.estimated_total_volume) OVER (
                    PARTITION BY v.hospital_id
                    ORDER BY v.fiscal_year
                )
            ELSE NULL
        END AS yoy_volume_change
    FROM volume_aggregates v
)
SELECT
    h.hospital_key,
    v.fiscal_year,
    v.medicare_tavr_volume,
    v.estimated_total_volume,
    v.yoy_volume_change,
    -- TVT star rating placeholder (would come from TVT registry data)
    NULL::INTEGER AS tvt_star_rating,
    -- Check for active certification in that year
    CASE
        WHEN c.is_active = TRUE
             AND (c.certification_date IS NULL OR EXTRACT(YEAR FROM c.certification_date) <= v.fiscal_year)
             AND (c.expiration_date IS NULL OR EXTRACT(YEAR FROM c.expiration_date) >= v.fiscal_year)
        THEN TRUE
        ELSE FALSE
    END AS has_active_certification,
    NOW() AS _updated_at
FROM volume_with_yoy v
JOIN mart.dim_hospital h ON v.hospital_id = h.hospital_id
LEFT JOIN staging.certifications c ON v.hospital_id = c.hospital_id
    AND c.certification_type LIKE '%Transcatheter%';
