-- TAVR Targeting Summary Model
-- Feature: 002-tavr-targeting-tool
-- Tasks: T043-T045

MODEL (
    name targeting.targeting_summary,
    kind VIEW,
    cron '@daily',
    description 'Aggregated targeting summary by segment and priority'
);

-- ============================================================================
-- T043: Segment calculation (Acceleration vs Optimization)
-- T044: DNQ flagging
-- T045: Summary aggregations
-- ============================================================================

WITH targeting_with_segment AS (
    SELECT
        *,
        -- T043: Segment calculation
        CASE
            WHEN is_current_client THEN 'Optimization'
            ELSE 'Acceleration'
        END AS segment
    FROM targeting.targeting_scores
)

SELECT
    segment,
    priority,
    COUNT(*) AS hospital_count,
    SUM(total_tavr_volume) AS total_volume,
    AVG(total_tavr_volume)::INTEGER AS avg_volume,
    ROUND(AVG(yoy_growth_pct)::NUMERIC, 2) AS avg_growth,
    SUM(CASE WHEN expressed_interest THEN 1 ELSE 0 END) AS interested_count,
    SUM(COALESCE(phase_2_tokens_needed, 0)) AS total_tokens_needed
FROM targeting_with_segment
GROUP BY segment, priority
ORDER BY
    segment,
    CASE priority
        WHEN 'High' THEN 1
        WHEN 'Medium' THEN 2
        WHEN 'Low' THEN 3
        ELSE 4
    END;
