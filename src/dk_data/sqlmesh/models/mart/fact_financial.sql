-- mart.fact_financial_metrics - Financial metrics by hospital and year
-- Source: raw.cms_cost_reports, mart.dim_hospital
-- Model type: FULL refresh with quartile calculation

MODEL (
    name mart.fact_financial_metrics,
    kind FULL,
    cron '@daily',
    description 'Hospital financial metrics with operating margin quartiles'
);

WITH cost_report_latest AS (
    -- Get most recent cost report per provider/fiscal year
    SELECT
        provider_id,
        EXTRACT(YEAR FROM fiscal_year_end) AS fiscal_year,
        total_beds,
        total_discharges,
        net_patient_revenue,
        total_operating_expenses,
        operating_margin
    FROM raw.cms_cost_reports
    WHERE fiscal_year_end IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY provider_id, EXTRACT(YEAR FROM fiscal_year_end)
        ORDER BY _loaded_at DESC
    ) = 1
),
with_quartiles AS (
    -- Calculate margin quartiles nationally
    SELECT
        provider_id,
        fiscal_year,
        operating_margin,
        NTILE(4) OVER (
            PARTITION BY fiscal_year
            ORDER BY operating_margin DESC NULLS LAST
        ) AS margin_quartile
    FROM cost_report_latest
    WHERE operating_margin IS NOT NULL
)
SELECT
    h.hospital_key,
    q.fiscal_year::INTEGER,
    q.operating_margin,
    q.margin_quartile,
    NOW() AS _updated_at
FROM with_quartiles q
JOIN mart.dim_hospital h ON q.provider_id = h.hospital_id;
