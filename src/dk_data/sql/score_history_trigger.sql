-- Score History Tracking Trigger
-- Automatically records score changes to scoring.score_history table
-- Usage: Run after init_database.sql

-- Function to record score changes to history
CREATE OR REPLACE FUNCTION scoring.record_score_history()
RETURNS TRIGGER AS $$
DECLARE
    change_desc VARCHAR(255);
BEGIN
    -- Determine change reason
    IF TG_OP = 'INSERT' THEN
        change_desc := 'Initial score calculation';
    ELSIF TG_OP = 'UPDATE' THEN
        -- Check what changed
        IF OLD.total_trs != NEW.total_trs THEN
            change_desc := 'Score changed from ' || OLD.total_trs || ' to ' || NEW.total_trs;
        ELSIF OLD.tier_classification != NEW.tier_classification THEN
            change_desc := 'Tier changed from ' || OLD.tier_classification || ' to ' || NEW.tier_classification;
        ELSE
            change_desc := 'Score recalculated (no change)';
        END IF;
    END IF;

    -- Insert into history table
    INSERT INTO scoring.score_history (
        hospital_key,
        score_date,
        total_trs,
        tier_classification,
        change_reason,
        _recorded_at
    ) VALUES (
        NEW.hospital_key,
        NEW.score_date,
        NEW.total_trs,
        NEW.tier_classification,
        change_desc,
        NOW()
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger on target_scores table
DROP TRIGGER IF EXISTS trg_score_history ON scoring.target_scores;

CREATE TRIGGER trg_score_history
    AFTER INSERT OR UPDATE ON scoring.target_scores
    FOR EACH ROW
    EXECUTE FUNCTION scoring.record_score_history();

-- Function to purge old score history (2-year retention)
CREATE OR REPLACE FUNCTION scoring.purge_old_history()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM scoring.score_history
    WHERE score_date < CURRENT_DATE - INTERVAL '2 years';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    RAISE NOTICE 'Purged % score history records older than 2 years', deleted_count;

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION scoring.record_score_history() TO PUBLIC;
GRANT EXECUTE ON FUNCTION scoring.purge_old_history() TO PUBLIC;

-- Notify completion
DO $$
BEGIN
    RAISE NOTICE 'Score history trigger created successfully';
END
$$;
