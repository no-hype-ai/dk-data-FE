-- Migration: 006_resolve_target.sql
-- Feature: 001-silver-medallion-rebuild
-- T052: mol_silver.resolve_target — entity-resolution function for molecular targets.
--
-- Priority tree (most-specific → least-specific):
--   1. UniProt ID       (canonical protein sequence accession)
--   2. ChEMBL target ID (authoritative bioactivity database)
--   3. HUGO gene symbol (human genome nomenclature)
--   4. Entrez gene ID   (NCBI gene identifier)
--   5. Ensembl ID       (Ensembl genome database)
--   6. Sequence hash    (canonical digest of protein sequence)
--   7. PDB ID           (Protein Data Bank structure identifier)
--   8. Name fuzzy       (pg_trgm similarity ≥ 0.85 on normalized_name)
--
-- Returns NULL when no match is found at any tier.
-- STABLE PARALLEL SAFE: no writes; reads are deterministic within a transaction.

BEGIN;

CREATE OR REPLACE FUNCTION mol_silver.resolve_target(
    p_uniprot_id      text DEFAULT NULL,
    p_chembl_target_id text DEFAULT NULL,
    p_gene_symbol     text DEFAULT NULL,
    p_entrez_id       text DEFAULT NULL,
    p_ensembl_id      text DEFAULT NULL,
    p_sequence_hash   text DEFAULT NULL,
    p_pdb_id          text DEFAULT NULL,
    p_name            text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id bigint;
BEGIN
    -- 1. UniProt ID (primary canonical protein accession)
    IF p_uniprot_id IS NOT NULL THEN
        SELECT target_id INTO v_id
        FROM mol_silver.target_identifiers
        WHERE source = 'uniprot' AND identifier = p_uniprot_id;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. ChEMBL target ID
    IF p_chembl_target_id IS NOT NULL THEN
        SELECT target_id INTO v_id
        FROM mol_silver.target_identifiers
        WHERE source = 'chembl_target' AND identifier = p_chembl_target_id;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. HUGO gene symbol (case-insensitive for robustness)
    IF p_gene_symbol IS NOT NULL THEN
        SELECT target_id INTO v_id
        FROM mol_silver.target_identifiers
        WHERE source = 'gene_symbol'
          AND LOWER(identifier) = LOWER(p_gene_symbol);
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 4. Entrez gene ID
    IF p_entrez_id IS NOT NULL THEN
        SELECT target_id INTO v_id
        FROM mol_silver.target_identifiers
        WHERE source = 'entrez' AND identifier = p_entrez_id;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 5. Ensembl gene/protein ID
    IF p_ensembl_id IS NOT NULL THEN
        SELECT target_id INTO v_id
        FROM mol_silver.target_identifiers
        WHERE source = 'ensembl' AND identifier = p_ensembl_id;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 6. Sequence hash (canonical digest of the primary protein sequence)
    IF p_sequence_hash IS NOT NULL THEN
        SELECT target_id INTO v_id
        FROM mol_silver.targets
        WHERE sequence_hash = p_sequence_hash;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 7. PDB structure ID
    IF p_pdb_id IS NOT NULL THEN
        SELECT target_id INTO v_id
        FROM mol_silver.target_identifiers
        WHERE source = 'pdb' AND identifier = UPPER(p_pdb_id);
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 8. Fuzzy name fallback via pg_trgm (threshold ≥ 0.85)
    IF p_name IS NOT NULL THEN
        SELECT target_id INTO v_id
        FROM mol_silver.target_names
        WHERE similarity(LOWER(normalized_name), LOWER(p_name)) >= 0.85
        ORDER BY similarity(LOWER(normalized_name), LOWER(p_name)) DESC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION mol_silver.resolve_target IS
    'T052: Resolve a molecular target hub ID from any combination of external identifiers. '
    'Priority: UniProt → ChEMBL target → HUGO gene → Entrez → Ensembl → sequence_hash → '
    'PDB → name fuzzy(≥0.85). Returns NULL on no match.';

COMMIT;
