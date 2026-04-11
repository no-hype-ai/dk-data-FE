-- Migration: 014_resolve_design.sql
-- Feature: 001-silver-medallion-rebuild
-- T059: ip_silver.resolve_design — entity-resolution function for industrial designs.
--
-- Priority tree (most-specific → least-specific):
--   1. (jurisdiction, design_number)  — canonical hub columns
--   2. WIPO Hague number              — international registration (via identifiers)
--   3. Locarno classes + holder + year fuzzy (pg_trgm similarity ≥ 0.85 on holder name)
--
-- jurisdiction + design_number are canonical hub columns.
-- WIPO Hague number is stored in design_identifiers.
-- locarno_classes is int[] — sorted before comparison for class-order independence.
--
-- Returns NULL when no match is found at any tier.
-- STABLE PARALLEL SAFE: no writes; reads are deterministic within a transaction.

BEGIN;

CREATE OR REPLACE FUNCTION ip_silver.resolve_design(
    p_jurisdiction    text    DEFAULT NULL,
    p_design_number   text    DEFAULT NULL,
    p_wipo_hague_number text  DEFAULT NULL,
    p_locarno_classes int[]   DEFAULT NULL,
    p_holder          text    DEFAULT NULL,
    p_filing_year     integer DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id bigint;
BEGIN
    -- 1. (jurisdiction, design_number) — canonical hub columns
    IF p_jurisdiction IS NOT NULL AND p_design_number IS NOT NULL THEN
        SELECT design_id INTO v_id
        FROM ip_silver.designs
        WHERE jurisdiction = p_jurisdiction
          AND design_number = p_design_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. WIPO Hague international registration — via design_identifiers
    IF p_wipo_hague_number IS NOT NULL THEN
        SELECT design_id INTO v_id
        FROM ip_silver.design_identifiers
        WHERE source = 'wipo_hague' AND identifier = p_wipo_hague_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. Locarno classes + holder + year composite fuzzy
    --    Uses pg_trgm on holder name from design_names; filters by classes and year.
    --    Sort locarno_classes for class-order independence.
    IF p_holder IS NOT NULL THEN
        SELECT dn.design_id INTO v_id
        FROM ip_silver.design_names dn
        JOIN ip_silver.designs d ON d.design_id = dn.design_id
        WHERE similarity(LOWER(dn.normalized_name), LOWER(TRIM(p_holder))) >= 0.85
          AND (p_locarno_classes IS NULL OR
               (SELECT ARRAY(SELECT unnest(d.locarno_classes) ORDER BY 1)) =
               (SELECT ARRAY(SELECT unnest(p_locarno_classes) ORDER BY 1)))
          AND (p_filing_year IS NULL OR
               EXTRACT(YEAR FROM d.filing_date) = p_filing_year)
        ORDER BY similarity(LOWER(dn.normalized_name), LOWER(TRIM(p_holder))) DESC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION ip_silver.resolve_design IS
    'T059: Resolve an industrial design hub ID from jurisdiction+number, WIPO Hague, '
    'or locarno_classes+holder+year. '
    'Priority: (jurisdiction,design_number) → WIPO Hague → '
    'locarno+holder+year fuzzy(≥0.85). Returns NULL on no match.';

COMMIT;
