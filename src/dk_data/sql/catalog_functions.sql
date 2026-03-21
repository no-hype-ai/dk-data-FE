-- TAVR Data Platform - Catalog Functions and Triggers
-- Feature: 001-data-layer-postgrest-gitops
-- Tasks: T017-T018
--
-- Functions for calculating and maintaining table health status

-- ============================================================================
-- T017: calculate_health_status() function
-- Determines health status based on freshness and data quality metrics
-- ============================================================================

CREATE OR REPLACE FUNCTION meta.calculate_health_status(p_source_id INTEGER)
RETURNS VARCHAR(20) AS $$
DECLARE
    v_freshness_hours INTEGER;
    v_threshold INTEGER;
    v_null_rate DECIMAL(5,4);
    v_error_count INTEGER;
    v_last_refresh TIMESTAMP;
BEGIN
    -- Get source configuration and last refresh time
    SELECT
        staleness_threshold_hours,
        last_successful_refresh
    INTO v_threshold, v_last_refresh
    FROM meta.ops_data_sources
    WHERE source_id = p_source_id;

    -- Calculate freshness in hours
    IF v_last_refresh IS NOT NULL THEN
        v_freshness_hours := EXTRACT(EPOCH FROM (NOW() - v_last_refresh)) / 3600;
    ELSE
        v_freshness_hours := NULL;
    END IF;

    -- Use default threshold if not set
    v_threshold := COALESCE(v_threshold, 24);

    -- Get latest quality metrics
    SELECT null_rate, validation_error_count
    INTO v_null_rate, v_error_count
    FROM meta.ops_table_health
    WHERE source_id = p_source_id
    ORDER BY check_timestamp DESC
    LIMIT 1;

    -- Default quality metrics if no health check yet
    v_null_rate := COALESCE(v_null_rate, 0);
    v_error_count := COALESCE(v_error_count, 0);

    -- Determine status based on rules from data-model.md:
    -- unhealthy: freshness_hours > threshold × 2 OR validation_error_count > 100
    -- stale: freshness_hours > threshold OR null_rate >= 0.10 (but not critical)
    -- healthy: freshness_hours ≤ threshold AND null_rate < 0.10 AND validation_error_count = 0

    IF v_freshness_hours IS NULL THEN
        RETURN 'unhealthy';  -- Never refreshed
    ELSIF v_freshness_hours > v_threshold * 2 OR v_error_count > 100 THEN
        RETURN 'unhealthy';
    ELSIF v_freshness_hours > v_threshold OR v_null_rate >= 0.10 THEN
        RETURN 'stale';
    ELSE
        RETURN 'healthy';
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION meta.calculate_health_status(INTEGER) IS
    'Calculate health status for a data source based on freshness and quality metrics';

-- ============================================================================
-- Helper function: Insert health check record
-- ============================================================================

CREATE OR REPLACE FUNCTION meta.record_health_check(
    p_source_id INTEGER,
    p_null_rate DECIMAL(5,4) DEFAULT 0,
    p_error_count INTEGER DEFAULT 0,
    p_details JSONB DEFAULT NULL
)
RETURNS INTEGER AS $$
DECLARE
    v_health_status VARCHAR(20);
    v_freshness_hours INTEGER;
    v_row_count INTEGER;
    v_prev_row_count INTEGER;
    v_health_id INTEGER;
    v_last_refresh TIMESTAMP;
BEGIN
    -- Get current source data
    SELECT last_successful_refresh, record_count
    INTO v_last_refresh, v_row_count
    FROM meta.ops_data_sources
    WHERE source_id = p_source_id;

    -- Calculate freshness
    IF v_last_refresh IS NOT NULL THEN
        v_freshness_hours := EXTRACT(EPOCH FROM (NOW() - v_last_refresh)) / 3600;
    END IF;

    -- Get previous row count for change calculation
    SELECT row_count INTO v_prev_row_count
    FROM meta.ops_table_health
    WHERE source_id = p_source_id
    ORDER BY check_timestamp DESC
    LIMIT 1;

    -- Calculate health status
    v_health_status := meta.calculate_health_status(p_source_id);

    -- Insert health record
    INSERT INTO meta.ops_table_health (
        source_id,
        health_status,
        freshness_hours,
        null_rate,
        validation_error_count,
        row_count,
        row_count_change,
        details
    ) VALUES (
        p_source_id,
        v_health_status,
        v_freshness_hours,
        p_null_rate,
        p_error_count,
        v_row_count,
        v_row_count - COALESCE(v_prev_row_count, v_row_count),
        p_details
    )
    RETURNING health_id INTO v_health_id;

    RETURN v_health_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION meta.record_health_check(INTEGER, DECIMAL, INTEGER, JSONB) IS
    'Record a health check for a data source with optional quality metrics';

-- ============================================================================
-- T018: Trigger to update health on refresh_log inserts
-- Automatically record health status when data is refreshed
-- ============================================================================

CREATE OR REPLACE FUNCTION meta.update_health_on_refresh()
RETURNS TRIGGER AS $$
BEGIN
    -- Only process successful refreshes
    IF NEW.status = 'success' THEN
        -- Update last_successful_refresh on data_sources
        UPDATE meta.ops_data_sources
        SET
            last_successful_refresh = COALESCE(NEW.refresh_completed_at, NOW()),
            last_refresh_attempt = COALESCE(NEW.refresh_started_at, NOW()),
            last_refresh_status = NEW.status,
            record_count = COALESCE(NEW.records_inserted + NEW.records_updated, record_count)
        WHERE source_id = NEW.source_id;

        -- Record health check with default quality metrics
        -- (actual quality metrics would be calculated separately)
        PERFORM meta.record_health_check(
            NEW.source_id,
            0,  -- null_rate to be calculated separately
            0,  -- error_count to be calculated separately
            jsonb_build_object(
                'refresh_log_id', NEW.log_id,
                'records_fetched', NEW.records_fetched,
                'records_inserted', NEW.records_inserted,
                'records_updated', NEW.records_updated
            )
        );
    ELSE
        -- Update attempt info for failed refreshes
        UPDATE meta.ops_data_sources
        SET
            last_refresh_attempt = COALESCE(NEW.refresh_started_at, NOW()),
            last_refresh_status = NEW.status
        WHERE source_id = NEW.source_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger on refresh_log
DROP TRIGGER IF EXISTS trg_update_health_on_refresh ON meta.ops_refresh_log;
CREATE TRIGGER trg_update_health_on_refresh
    AFTER INSERT ON meta.ops_refresh_log
    FOR EACH ROW
    EXECUTE FUNCTION meta.update_health_on_refresh();

COMMENT ON TRIGGER trg_update_health_on_refresh ON meta.ops_refresh_log IS
    'Automatically update health status when new refresh log entries are added';

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Catalog functions created successfully:';
    RAISE NOTICE '  - meta.calculate_health_status(source_id)';
    RAISE NOTICE '  - meta.record_health_check(source_id, null_rate, error_count, details)';
    RAISE NOTICE '  - Trigger: trg_update_health_on_refresh on meta.ops_refresh_log';
END $$;
