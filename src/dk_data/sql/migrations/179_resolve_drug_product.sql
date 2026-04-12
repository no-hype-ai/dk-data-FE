-- Migration: 005_resolve_drug_product.sql
-- Feature: 001-silver-medallion-rebuild
-- T051: mol_silver.resolve_drug_product — entity-resolution function for drug products.
--
-- Priority tree (most-specific → least-specific):
--   1. NDC                      (national drug code — product-level canonical)
--   2. RxCUI SCD/SBD/GPCK/BPCK (clinical/branded/pack RxNorm concepts only)
--   3. BLA + product name        (biologics license application)
--   4. Application + product     (NDA / ANDA application number)
--   5. EMA product number        (European Medicines Agency)
--   6. CVX code                  (vaccines)
--   7. Ingredients hash          (canonical ingredient fingerprint)
--   8. Brand + form + strength   (composite lookup)
--   9. Generic + form + strength (composite lookup)
--  10. Brand fuzzy               (pg_trgm similarity ≥ 0.85)
--
-- RxCUI IN/PIN/BN types are intentionally excluded — those map to molecules,
-- not to drug products.
--
-- Returns NULL when no match is found at any tier.
-- STABLE PARALLEL SAFE: no writes; reads are deterministic within a transaction.

BEGIN;

CREATE OR REPLACE FUNCTION mol_silver.resolve_drug_product(
    p_ndc               text    DEFAULT NULL,
    p_rxcui             text    DEFAULT NULL,
    p_bla               text    DEFAULT NULL,
    p_application_number text   DEFAULT NULL,
    p_ema_product_number text   DEFAULT NULL,
    p_cvx               text    DEFAULT NULL,
    p_ingredients_hash  text    DEFAULT NULL,
    p_brand             text    DEFAULT NULL,
    p_generic           text    DEFAULT NULL,
    p_dosage_form       text    DEFAULT NULL,
    p_strength_mg       numeric DEFAULT NULL,
    p_route             text    DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id bigint;
BEGIN
    -- 1. NDC (national drug code — canonical product-level identifier)
    IF p_ndc IS NOT NULL THEN
        SELECT product_id INTO v_id
        FROM mol_silver.drug_product_identifiers
        WHERE source = 'ndc' AND identifier = p_ndc;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. RxCUI — only SCD/SBD/GPCK/BPCK (clinical/branded/pack), not IN/PIN/BN
    IF p_rxcui IS NOT NULL THEN
        SELECT product_id INTO v_id
        FROM mol_silver.drug_product_identifiers
        WHERE source = 'rxcui_scd_sbd' AND identifier = p_rxcui;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. BLA number + product name (biologics)
    IF p_bla IS NOT NULL AND p_brand IS NOT NULL THEN
        SELECT dp.product_id INTO v_id
        FROM mol_silver.drug_products dp
        WHERE dp.bla_number = p_bla
          AND LOWER(TRIM(dp.brand_name)) = LOWER(TRIM(p_brand));
        IF FOUND THEN RETURN v_id; END IF;
    END IF;
    -- BLA alone (without product name) — still useful
    IF p_bla IS NOT NULL THEN
        SELECT dp.product_id INTO v_id
        FROM mol_silver.drug_products dp
        WHERE dp.bla_number = p_bla
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 4. Application number (NDA/ANDA) + product name
    IF p_application_number IS NOT NULL AND p_brand IS NOT NULL THEN
        SELECT dp.product_id INTO v_id
        FROM mol_silver.drug_products dp
        WHERE dp.application_number = p_application_number
          AND LOWER(TRIM(dp.brand_name)) = LOWER(TRIM(p_brand));
        IF FOUND THEN RETURN v_id; END IF;
    END IF;
    -- Application number alone
    IF p_application_number IS NOT NULL THEN
        SELECT dp.product_id INTO v_id
        FROM mol_silver.drug_products dp
        WHERE dp.application_number = p_application_number
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 5. EMA product number
    IF p_ema_product_number IS NOT NULL THEN
        SELECT product_id INTO v_id
        FROM mol_silver.drug_product_identifiers
        WHERE source = 'ema_product' AND identifier = p_ema_product_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 6. CVX vaccine code
    IF p_cvx IS NOT NULL THEN
        SELECT product_id INTO v_id
        FROM mol_silver.drug_product_identifiers
        WHERE source = 'cvx' AND identifier = p_cvx;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 7. Ingredients hash (canonical fingerprint of active ingredient set)
    IF p_ingredients_hash IS NOT NULL THEN
        SELECT product_id INTO v_id
        FROM mol_silver.drug_product_identifiers
        WHERE source = 'ingredients_hash' AND identifier = p_ingredients_hash;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 8. Brand name + dosage form + strength composite lookup
    IF p_brand IS NOT NULL AND p_dosage_form IS NOT NULL AND p_strength_mg IS NOT NULL THEN
        SELECT dp.product_id INTO v_id
        FROM mol_silver.drug_products dp
        WHERE LOWER(TRIM(dp.brand_name))  = LOWER(TRIM(p_brand))
          AND LOWER(TRIM(dp.dosage_form)) = LOWER(TRIM(p_dosage_form))
          AND dp.strength_mg              = p_strength_mg
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 9. Generic name + dosage form + strength composite lookup
    IF p_generic IS NOT NULL AND p_dosage_form IS NOT NULL AND p_strength_mg IS NOT NULL THEN
        SELECT dp.product_id INTO v_id
        FROM mol_silver.drug_products dp
        WHERE LOWER(TRIM(dp.generic_name)) = LOWER(TRIM(p_generic))
          AND LOWER(TRIM(dp.dosage_form))  = LOWER(TRIM(p_dosage_form))
          AND dp.strength_mg               = p_strength_mg
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 10. Fuzzy brand name fallback via pg_trgm (threshold ≥ 0.85)
    IF p_brand IS NOT NULL THEN
        SELECT product_id INTO v_id
        FROM mol_silver.drug_product_names
        WHERE name_kind = 'brand'
          AND similarity(LOWER(normalized_name), LOWER(p_brand)) >= 0.85
          AND LENGTH(normalized_name) >= 4 AND LENGTH(p_brand) >= 4
        ORDER BY similarity(LOWER(normalized_name), LOWER(p_brand)) DESC, product_id ASC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION mol_silver.resolve_drug_product IS
    'T051: Resolve a drug product hub ID from any combination of external identifiers. '
    'Priority: NDC → RxCUI(SCD/SBD/GPCK/BPCK) → BLA+product → application+product → '
    'EMA → CVX → ingredients_hash → brand+form+strength → generic+form+strength → '
    'brand fuzzy(≥0.85). RxCUI IN/PIN/BN intentionally excluded. Returns NULL on no match.';

COMMIT;
