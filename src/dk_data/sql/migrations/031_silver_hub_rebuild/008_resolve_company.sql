-- Migration: 008_resolve_company.sql
-- Feature: 001-silver-medallion-rebuild
-- T054: mol_silver.resolve_company — entity-resolution function for companies/sponsors.
--
-- Priority tree (most-specific → least-specific):
--   1. CIK                  (SEC EDGAR Central Index Key — authoritative for US public cos)
--   2. Ticker symbol        (exchange ticker — ambiguous across jurisdictions, lower priority)
--   3. Normalized name      (strip legal suffixes: Inc./Corp./Ltd./LLC/AG/SA/GmbH/plc)
--   4. Name fuzzy           (pg_trgm similarity ≥ 0.85 on normalized_name after stripping)
--
-- Legal suffix stripping: removes common suffixes before exact match so that
-- "Pfizer Inc." matches "Pfizer" already in the hub.
--
-- Returns NULL when no match is found at any tier.
-- STABLE PARALLEL SAFE: no writes; reads are deterministic within a transaction.

BEGIN;

CREATE OR REPLACE FUNCTION mol_silver.resolve_company(
    p_cik     text DEFAULT NULL,
    p_ticker  text DEFAULT NULL,
    p_name    text DEFAULT NULL,
    p_country text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id           bigint;
    v_stripped_name text;
BEGIN
    -- 1. SEC CIK (most specific — canonical for US public companies)
    IF p_cik IS NOT NULL THEN
        SELECT company_id INTO v_id
        FROM mol_silver.company_identifiers
        WHERE source = 'cik' AND identifier = p_cik;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. Ticker symbol
    IF p_ticker IS NOT NULL THEN
        SELECT company_id INTO v_id
        FROM mol_silver.company_identifiers
        WHERE source = 'ticker'
          AND LOWER(identifier) = LOWER(p_ticker);
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. Normalized name — strip common legal suffixes then exact match
    IF p_name IS NOT NULL THEN
        v_stripped_name := LOWER(TRIM(
            REGEXP_REPLACE(
                p_name,
                '\s*(,\s*)?(Inc\.?|Corp\.?|Ltd\.?|LLC\.?|AG|SA|S\.A\.|GmbH|plc|PLC|N\.V\.|NV|B\.V\.|BV|S\.p\.A\.|SpA)\.?\s*$',
                '',
                'i'
            )
        ));

        SELECT company_id INTO v_id
        FROM mol_silver.company_names
        WHERE LOWER(normalized_name) = v_stripped_name
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;

        -- Also try exact match on original name (in case it's already clean)
        SELECT company_id INTO v_id
        FROM mol_silver.company_names
        WHERE LOWER(normalized_name) = LOWER(TRIM(p_name))
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;

        -- 4. Fuzzy name fallback via pg_trgm — try stripped name first, then original
        SELECT company_id INTO v_id
        FROM mol_silver.company_names
        WHERE similarity(LOWER(normalized_name), v_stripped_name) >= 0.85
        ORDER BY similarity(LOWER(normalized_name), v_stripped_name) DESC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;

        SELECT company_id INTO v_id
        FROM mol_silver.company_names
        WHERE similarity(LOWER(normalized_name), LOWER(p_name)) >= 0.85
        ORDER BY similarity(LOWER(normalized_name), LOWER(p_name)) DESC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION mol_silver.resolve_company IS
    'T054: Resolve a company/sponsor hub ID from any combination of external identifiers. '
    'Priority: CIK → ticker → normalized name (strips Inc./Corp./Ltd./AG/SA/GmbH/plc) → '
    'name fuzzy(≥0.85). Returns NULL on no match.';

COMMIT;
