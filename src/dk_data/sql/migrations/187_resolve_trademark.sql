-- Migration: 013_resolve_trademark.sql
-- Feature: 001-silver-medallion-rebuild
-- T058: ip_silver.resolve_trademark — entity-resolution function for trademarks.
--
-- Priority tree (most-specific → least-specific):
--   1. (jurisdiction, registration_number) — canonical granted trademark hub columns
--   2. (jurisdiction, serial_number)       — pre-registration application hub columns
--   3. WIPO Madrid number                  — international registration (via identifiers)
--   4. Mark text + nice_classes + jurisdiction fuzzy (pg_trgm similarity ≥ 0.85)
--
-- jurisdiction + registration_number / serial_number are canonical hub columns.
-- WIPO Madrid number is stored in trademark_identifiers.
-- nice_classes is int[] — sorted before comparison to ensure class-order independence.
--
-- Returns NULL when no match is found at any tier.
-- STABLE PARALLEL SAFE: no writes; reads are deterministic within a transaction.

BEGIN;

CREATE OR REPLACE FUNCTION ip_silver.resolve_trademark(
    p_jurisdiction        text    DEFAULT NULL,
    p_registration_number text    DEFAULT NULL,
    p_serial_number       text    DEFAULT NULL,
    p_wipo_madrid_number  text    DEFAULT NULL,
    p_mark_text           text    DEFAULT NULL,
    p_nice_classes        int[]   DEFAULT NULL,
    p_owner               text    DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id bigint;
BEGIN
    -- 1. (jurisdiction, registration_number) — canonical hub columns
    IF p_jurisdiction IS NOT NULL AND p_registration_number IS NOT NULL THEN
        SELECT trademark_id INTO v_id
        FROM ip_silver.trademarks
        WHERE jurisdiction = p_jurisdiction
          AND registration_number = p_registration_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. (jurisdiction, serial_number) — pre-registration hub columns
    IF p_jurisdiction IS NOT NULL AND p_serial_number IS NOT NULL THEN
        SELECT trademark_id INTO v_id
        FROM ip_silver.trademarks
        WHERE jurisdiction = p_jurisdiction
          AND serial_number = p_serial_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. WIPO Madrid international registration number — via trademark_identifiers
    IF p_wipo_madrid_number IS NOT NULL THEN
        SELECT trademark_id INTO v_id
        FROM ip_silver.trademark_identifiers
        WHERE source = 'wipo_madrid' AND identifier = p_wipo_madrid_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 4. Mark text fuzzy + optional nice_classes + jurisdiction filter (pg_trgm ≥ 0.85)
    --    Sort nice_classes array to ensure class-order independence
    IF p_mark_text IS NOT NULL THEN
        SELECT tn.trademark_id INTO v_id
        FROM ip_silver.trademark_names tn
        JOIN ip_silver.trademarks tm ON tm.trademark_id = tn.trademark_id
        WHERE tn.name_kind = 'mark_text'
          AND similarity(LOWER(tn.normalized_name), LOWER(TRIM(p_mark_text))) >= 0.85
          AND LENGTH(tn.normalized_name) >= 4 AND LENGTH(TRIM(p_mark_text)) >= 4
          AND (p_jurisdiction IS NULL OR tm.jurisdiction = p_jurisdiction)
          AND (p_nice_classes IS NULL OR
               (SELECT ARRAY(SELECT unnest(tm.nice_classes) ORDER BY 1)) =
               (SELECT ARRAY(SELECT unnest(p_nice_classes) ORDER BY 1)))
        ORDER BY similarity(LOWER(tn.normalized_name), LOWER(TRIM(p_mark_text))) DESC, tn.trademark_id ASC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION ip_silver.resolve_trademark IS
    'T058: Resolve a trademark hub ID from jurisdiction+number, serial, WIPO Madrid, '
    'or mark_text+nice_classes+jurisdiction. '
    'Priority: (jurisdiction,registration_number) → (jurisdiction,serial_number) → '
    'WIPO Madrid → mark_text+nice_classes+jurisdiction fuzzy(≥0.85). Returns NULL on no match.';

COMMIT;
