-- Migration: 004_resolve_molecule.sql
-- Feature: 001-silver-medallion-rebuild
-- T050: mol_silver.resolve_molecule — entity-resolution function for molecules.
--
-- Priority tree (most-specific → least-specific):
--   1. InChIKey        (globally unique structural key)
--   2. ChEMBL ID       (authoritative chemical database)
--   3. DrugBank ID     (clinical drug resource)
--   4. PubChem CID     (large-scale compound database)
--   5. UNII            (FDA unique ingredient identifier)
--   6. CAS Number      (Chemical Abstracts registry)
--   7. RxCUI IN/PIN    (RxNorm ingredient / precise ingredient)
--   8. NDC             (national drug code — less specific, product-level)
--   9. INN             (international nonproprietary name)
--  10. Name fuzzy      (pg_trgm similarity ≥ 0.85 on normalized_name)
--
-- Returns NULL when no match is found at any tier.
-- STABLE PARALLEL SAFE: no writes; reads are deterministic within a transaction.

BEGIN;

CREATE OR REPLACE FUNCTION mol_silver.resolve_molecule(
    p_inchi_key   text DEFAULT NULL,
    p_chembl_id   text DEFAULT NULL,
    p_drugbank_id text DEFAULT NULL,
    p_pubchem_cid text DEFAULT NULL,
    p_unii        text DEFAULT NULL,
    p_cas_number  text DEFAULT NULL,
    p_rxcui       text DEFAULT NULL,
    p_ndc         text DEFAULT NULL,
    p_inn         text DEFAULT NULL,
    p_name        text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id bigint;
BEGIN
    -- 1. InChIKey (most specific — structural hash, globally unique)
    IF p_inchi_key IS NOT NULL THEN
        SELECT molecule_id INTO v_id
        FROM mol_silver.molecule_identifiers
        WHERE source = 'inchi_key' AND identifier = p_inchi_key;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. ChEMBL ID
    IF p_chembl_id IS NOT NULL THEN
        SELECT molecule_id INTO v_id
        FROM mol_silver.molecule_identifiers
        WHERE source = 'chembl' AND identifier = p_chembl_id;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. DrugBank ID
    IF p_drugbank_id IS NOT NULL THEN
        SELECT molecule_id INTO v_id
        FROM mol_silver.molecule_identifiers
        WHERE source = 'drugbank' AND identifier = p_drugbank_id;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 4. PubChem CID
    IF p_pubchem_cid IS NOT NULL THEN
        SELECT molecule_id INTO v_id
        FROM mol_silver.molecule_identifiers
        WHERE source = 'pubchem' AND identifier = p_pubchem_cid;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 5. UNII (FDA Unique Ingredient Identifier)
    IF p_unii IS NOT NULL THEN
        SELECT molecule_id INTO v_id
        FROM mol_silver.molecule_identifiers
        WHERE source = 'unii' AND identifier = p_unii;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 6. CAS Number
    IF p_cas_number IS NOT NULL THEN
        SELECT molecule_id INTO v_id
        FROM mol_silver.molecule_identifiers
        WHERE source = 'cas' AND identifier = p_cas_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 7. RxCUI — only IN (ingredient) and PIN (precise ingredient) types
    IF p_rxcui IS NOT NULL THEN
        SELECT molecule_id INTO v_id
        FROM mol_silver.molecule_identifiers
        WHERE source = 'rxcui_in_pin' AND identifier = p_rxcui;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 8. NDC (national drug code — less specific; maps to product first, then molecule)
    IF p_ndc IS NOT NULL THEN
        SELECT molecule_id INTO v_id
        FROM mol_silver.molecule_identifiers
        WHERE source = 'ndc' AND identifier = p_ndc;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 9. INN (International Nonproprietary Name)
    IF p_inn IS NOT NULL THEN
        SELECT molecule_id INTO v_id
        FROM mol_silver.molecule_identifiers
        WHERE source = 'inn' AND identifier = p_inn;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 10. Fuzzy name fallback via pg_trgm (threshold ≥ 0.85)
    --     NOTE: for Gold-tier confidence (≥ 0.95) callers should apply an
    --     additional filter; this function returns the best match ≥ 0.85.
    IF p_name IS NOT NULL THEN
        SELECT molecule_id INTO v_id
        FROM mol_silver.molecule_names
        WHERE similarity(LOWER(normalized_name), LOWER(p_name)) >= 0.85
        ORDER BY similarity(LOWER(normalized_name), LOWER(p_name)) DESC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION mol_silver.resolve_molecule IS
    'T050: Resolve a molecule hub ID from any combination of external identifiers. '
    'Priority: InChIKey → ChEMBL → DrugBank → PubChem → UNII → CAS → '
    'RxCUI(IN/PIN) → NDC → INN → name fuzzy(≥0.85). Returns NULL on no match.';

COMMIT;
