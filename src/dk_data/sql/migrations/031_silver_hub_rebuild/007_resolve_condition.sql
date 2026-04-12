-- Migration: 007_resolve_condition.sql
-- Feature: 001-silver-medallion-rebuild
-- T053: ind_silver.resolve_condition — entity-resolution function for conditions/diseases.
--
-- Priority tree (most-specific → least-specific):
--   1. ICD-11 code      (current global disease classification)
--   2. ICD-10 code      (widely used clinical coding standard)
--   3. MeSH descriptor  (NIH Medical Subject Headings)
--   4. MedDRA PT        (pharmaceutical adverse event terminology)
--   5. Name fuzzy       (pg_trgm similarity ≥ 0.85 on normalized_name)
--
-- Returns NULL when no match is found at any tier.
-- STABLE PARALLEL SAFE: no writes; reads are deterministic within a transaction.

BEGIN;

CREATE OR REPLACE FUNCTION ind_silver.resolve_condition(
    p_icd11    text DEFAULT NULL,
    p_icd10    text DEFAULT NULL,
    p_mesh     text DEFAULT NULL,
    p_meddra_pt text DEFAULT NULL,
    p_name     text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id bigint;
BEGIN
    -- 1. ICD-11 code (current WHO disease classification — most authoritative)
    IF p_icd11 IS NOT NULL THEN
        SELECT condition_id INTO v_id
        FROM ind_silver.conditions
        WHERE icd11_code = p_icd11;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. ICD-10 code (legacy but widely used clinical coding)
    IF p_icd10 IS NOT NULL THEN
        SELECT condition_id INTO v_id
        FROM ind_silver.conditions
        WHERE icd10_code = p_icd10;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. MeSH descriptor ID (NIH controlled vocabulary)
    IF p_mesh IS NOT NULL THEN
        SELECT condition_id INTO v_id
        FROM ind_silver.conditions
        WHERE mesh_descriptor_id = p_mesh;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 4. MedDRA preferred term (pharmaceutical safety/regulatory terminology)
    IF p_meddra_pt IS NOT NULL THEN
        SELECT condition_id INTO v_id
        FROM ind_silver.conditions
        WHERE meddra_pt = p_meddra_pt;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 5. Fuzzy name fallback via pg_trgm (threshold ≥ 0.85)
    IF p_name IS NOT NULL THEN
        SELECT condition_id INTO v_id
        FROM ind_silver.condition_names
        WHERE similarity(LOWER(normalized_name), LOWER(p_name)) >= 0.85
        ORDER BY similarity(LOWER(normalized_name), LOWER(p_name)) DESC, condition_id ASC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION ind_silver.resolve_condition IS
    'T053: Resolve a condition/disease hub ID from any combination of external identifiers. '
    'Priority: ICD-11 → ICD-10 → MeSH → MedDRA PT → name fuzzy(≥0.85). '
    'Returns NULL on no match.';

COMMIT;
