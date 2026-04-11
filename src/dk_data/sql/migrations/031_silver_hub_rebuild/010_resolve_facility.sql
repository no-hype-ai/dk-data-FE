-- Migration: 010_resolve_facility.sql
-- Feature: 001-silver-medallion-rebuild
-- T056: hcs_silver.resolve_facility — entity-resolution function for healthcare facilities.
--
-- Priority tree (most-specific → least-specific):
--   1. CCN              (CMS Certification Number — canonical US facility ID)
--   2. NPI type-2       (organizational NPI — canonical hub column)
--   3. NCDR ID          (National Cardiovascular Data Registry)
--   4. Name+city+state+zip fuzzy (pg_trgm similarity ≥ 0.85 on facility_name)
--
-- CCN and npi_type2 are direct canonical hub columns, not routed through identifiers.
-- NCDR ID is stored in facility_identifiers crosswalk.
--
-- Returns NULL when no match is found at any tier.
-- STABLE PARALLEL SAFE: no writes; reads are deterministic within a transaction.

BEGIN;

CREATE OR REPLACE FUNCTION hcs_silver.resolve_facility(
    p_ccn           text DEFAULT NULL,
    p_npi_type2     text DEFAULT NULL,
    p_ncdr_id       text DEFAULT NULL,
    p_facility_name text DEFAULT NULL,
    p_city          text DEFAULT NULL,
    p_state         text DEFAULT NULL,
    p_zip           text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id bigint;
BEGIN
    -- 1. CCN — canonical hub column (direct lookup)
    IF p_ccn IS NOT NULL THEN
        SELECT facility_id INTO v_id
        FROM hcs_silver.facilities
        WHERE ccn = p_ccn;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. NPI type-2 — canonical hub column (direct lookup)
    IF p_npi_type2 IS NOT NULL THEN
        SELECT facility_id INTO v_id
        FROM hcs_silver.facilities
        WHERE npi_type2 = p_npi_type2;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. NCDR ID — stored in facility_identifiers crosswalk
    IF p_ncdr_id IS NOT NULL THEN
        SELECT facility_id INTO v_id
        FROM hcs_silver.facility_identifiers
        WHERE source = 'ncdr' AND identifier = p_ncdr_id;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 4. Composite fuzzy: name + geographic filters (city, state, zip)
    IF p_facility_name IS NOT NULL THEN
        SELECT fn.facility_id INTO v_id
        FROM hcs_silver.facility_names fn
        JOIN hcs_silver.facilities fac ON fac.facility_id = fn.facility_id
        WHERE similarity(LOWER(fn.normalized_name), LOWER(TRIM(p_facility_name))) >= 0.85
          AND (p_city  IS NULL OR LOWER(TRIM(fac.city))  = LOWER(TRIM(p_city)))
          AND (p_state IS NULL OR UPPER(TRIM(fac.state)) = UPPER(TRIM(p_state)))
          AND (p_zip   IS NULL OR LEFT(TRIM(fac.zip), 5) = LEFT(TRIM(p_zip), 5))
        ORDER BY similarity(LOWER(fn.normalized_name), LOWER(TRIM(p_facility_name))) DESC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION hcs_silver.resolve_facility IS
    'T056: Resolve a healthcare facility hub ID from CCN, NPI type-2, NCDR ID, or '
    'name+city+state+zip. Priority: CCN (hub column) → NPI type-2 (hub column) → '
    'NCDR ID (identifiers) → fuzzy(name+city+state+zip, ≥0.85). Returns NULL on no match.';

COMMIT;
