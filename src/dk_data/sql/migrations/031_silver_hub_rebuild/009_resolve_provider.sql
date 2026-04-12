-- Migration: 009_resolve_provider.sql
-- Feature: 001-silver-medallion-rebuild
-- T055: hcs_silver.resolve_provider — entity-resolution function for healthcare providers.
--
-- Priority tree (most-specific → least-specific):
--   1. NPI              (National Provider Identifier — canonical US provider ID)
--   2. PECOS ID         (Medicare enrollment ID)
--   3. Name+state+taxonomy fuzzy (pg_trgm similarity ≥ 0.85 on canonical name)
--
-- NPI is a direct canonical hub column, not routed through provider_identifiers.
-- PECOS ID is stored in provider_identifiers.
-- The composite fuzzy match normalizes full name as "last, first".
--
-- Returns NULL when no match is found at any tier.
-- STABLE PARALLEL SAFE: no writes; reads are deterministic within a transaction.

BEGIN;

CREATE OR REPLACE FUNCTION hcs_silver.resolve_provider(
    p_npi       text DEFAULT NULL,
    p_pecos_id  text DEFAULT NULL,
    p_first_name text DEFAULT NULL,
    p_last_name  text DEFAULT NULL,
    p_state      text DEFAULT NULL,
    p_taxonomy   text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id            bigint;
    v_canonical_name text;
BEGIN
    -- 1. NPI — canonical hub column (direct lookup)
    IF p_npi IS NOT NULL THEN
        SELECT provider_id INTO v_id
        FROM hcs_silver.providers
        WHERE npi = p_npi;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. PECOS ID — stored in provider_identifiers crosswalk
    IF p_pecos_id IS NOT NULL THEN
        SELECT provider_id INTO v_id
        FROM hcs_silver.provider_identifiers
        WHERE source = 'pecos' AND identifier = p_pecos_id;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. Composite fuzzy: normalized "last, first" name + state filter + taxonomy filter
    --    Build canonical name format matching bootstrap_providers: "last_name, first_name"
    IF p_first_name IS NOT NULL AND p_last_name IS NOT NULL THEN
        v_canonical_name := LOWER(TRIM(p_last_name)) || ', ' || LOWER(TRIM(p_first_name));

        SELECT pn.provider_id INTO v_id
        FROM hcs_silver.provider_names pn
        JOIN hcs_silver.providers pr ON pr.provider_id = pn.provider_id
        WHERE similarity(LOWER(pn.normalized_name), v_canonical_name) >= 0.85
          AND (p_state    IS NULL OR UPPER(TRIM(pr.state))    = UPPER(TRIM(p_state)))
          AND (p_taxonomy IS NULL OR LOWER(TRIM(pr.taxonomy)) = LOWER(TRIM(p_taxonomy)))
        ORDER BY similarity(LOWER(pn.normalized_name), v_canonical_name) DESC, pn.provider_id ASC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION hcs_silver.resolve_provider IS
    'T055: Resolve a healthcare provider hub ID from NPI, PECOS ID, or name+state+taxonomy. '
    'Priority: NPI (canonical hub column) → PECOS ID (identifiers crosswalk) → '
    'fuzzy(last+first+state+taxonomy, ≥0.85). Returns NULL on no match.';

COMMIT;
