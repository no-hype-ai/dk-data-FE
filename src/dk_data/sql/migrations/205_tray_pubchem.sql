-- Migration 031/033: Tray procedure for mol_bronze.pubchem
-- Audit fix (2026-04-12): replaces the bronze→bronze stub with a real raw→bronze
-- rebuild that mirrors src/dk_data/sqlmesh/models/molecules/bronze/pubchem.sql.

CREATE OR REPLACE PROCEDURE mol_bronze.refresh_pubchem_via_tray()
LANGUAGE plpgsql
AS $$
DECLARE
    v_chunk_size CONSTANT BIGINT := 5000;
    v_proc_name  CONSTANT TEXT := 'mol_bronze.refresh_pubchem_via_tray';
    v_max_raw_id BIGINT;
    v_low_id     BIGINT := 0;
    v_high_id    BIGINT;
    v_chunk_pos  INT := 0;
    v_chunk_rows INT;
    v_total_rows BIGINT := 0;
    v_wal_start  pg_lsn;
    v_wal_end    pg_lsn;
    v_wal_bytes  BIGINT;
BEGIN
    CALL mol_bronze._tray_setup(v_proc_name, 'mol_bronze', 'pubchem', 'pubchem_tray');
    SET LOCAL work_mem = '128MB';

    SELECT COALESCE(MAX(id), 0) INTO v_max_raw_id FROM mol_raw.pubchem;

    WHILE v_low_id < v_max_raw_id LOOP
        v_high_id := v_low_id + v_chunk_size;
        v_wal_start := pg_current_wal_lsn();
        v_chunk_pos := v_chunk_pos + 1;

        WITH raw_slice AS (
            SELECT * FROM mol_raw.pubchem
            WHERE id > v_low_id AND id <= v_high_id
              AND response_status = 200
              AND response_body->>'cid' IS NOT NULL
        ),
        cid_xrefs AS (
            SELECT cid,
                MAX(CASE WHEN xref_type = 'CAS' THEN xref_id END) AS cas_number,
                jsonb_agg(xref_id) FILTER (WHERE xref_type = 'DrugBank') AS drugbank_ids,
                jsonb_agg(xref_id) FILTER (WHERE xref_type = 'ChEMBL')   AS chembl_ids,
                MAX(CASE WHEN xref_type IN ('UNII', 'FDA UNII') THEN xref_id END) AS unii
            FROM mol_bronze.pubchem_xrefs
            WHERE cid IN (SELECT (response_body->>'cid')::BIGINT FROM raw_slice)
            GROUP BY cid
        ),
        cid_bioassays AS (
            SELECT cid,
                jsonb_agg(DISTINCT aid ORDER BY aid) AS assay_ids,
                COUNT(DISTINCT aid)::INTEGER AS bioassay_count
            FROM mol_bronze.pubchem_bioassays
            WHERE cid IN (SELECT (response_body->>'cid')::BIGINT FROM raw_slice)
            GROUP BY cid
        ),
        cid_synonyms AS (
            SELECT cid, jsonb_agg(synonym_name ORDER BY synonym_name) AS synonym_names
            FROM mol_bronze.pubchem_synonyms
            WHERE cid IN (SELECT (response_body->>'cid')::BIGINT FROM raw_slice)
            GROUP BY cid
        )
        INSERT INTO mol_bronze.pubchem_tray (
            id, cid, canonical_smiles, isomeric_smiles, iupac_name, inchi, inchi_key,
            molecular_formula, molecular_weight, exact_mass,
            xlogp, tpsa, complexity, charge,
            h_bond_donor_count, h_bond_acceptor_count, rotatable_bond_count, heavy_atom_count,
            atom_stereo_count, bond_stereo_count, covalent_unit_count,
            synonyms, mesh_headings, pharmacological_actions,
            cas_number, drugbank_ids, chembl_ids, unii,
            taxonomy, patents, assay_ids, bioassay_count,
            raw_json, raw_source_id, source, request_timestamp, source_updated_at,
            processed_to_silver, created_at
        )
        SELECT
            gen_random_uuid(),
            (raw.response_body->>'cid')::BIGINT,
            raw.response_body->>'smiles',
            raw.response_body->>'isomericsmiles',
            raw.response_body->>'iupacname',
            raw.response_body->>'inchi',
            raw.response_body->>'inchikey',
            raw.response_body->>'mf',
            (raw.response_body->>'mw')::NUMERIC,
            (raw.response_body->>'exactmass')::NUMERIC,
            (raw.response_body->>'xlogp')::NUMERIC,
            (raw.response_body->>'polararea')::NUMERIC,
            (raw.response_body->>'complexity')::NUMERIC,
            (raw.response_body->>'charge')::INTEGER,
            (raw.response_body->>'hbonddonor')::INTEGER,
            (raw.response_body->>'hbondacc')::INTEGER,
            (raw.response_body->>'rotbonds')::INTEGER,
            (raw.response_body->>'heavycnt')::INTEGER,
            NULL::INTEGER, NULL::INTEGER, NULL::INTEGER,
            COALESCE(cs.synonym_names, '[]'::JSONB),
            NULL::JSONB, NULL::JSONB,
            cx.cas_number, cx.drugbank_ids, cx.chembl_ids, cx.unii,
            NULL::JSONB, NULL::JSONB, cb.assay_ids, cb.bioassay_count,
            raw.response_body, raw.id, 'pubchem',
            raw.request_timestamp, raw.request_timestamp, FALSE, NOW()
        FROM raw_slice raw
        LEFT JOIN cid_xrefs cx     ON cx.cid = (raw.response_body->>'cid')::BIGINT
        LEFT JOIN cid_bioassays cb ON cb.cid = (raw.response_body->>'cid')::BIGINT
        LEFT JOIN cid_synonyms cs  ON cs.cid = (raw.response_body->>'cid')::BIGINT;

        GET DIAGNOSTICS v_chunk_rows = ROW_COUNT;
        v_total_rows := v_total_rows + v_chunk_rows;

        v_wal_end := pg_current_wal_lsn();
        v_wal_bytes := pg_wal_lsn_diff(v_wal_end, v_wal_start);

        INSERT INTO meta.transform_runs (procedure_name, chunk_position, rows_processed, wal_bytes, started_at)
        VALUES (v_proc_name, v_chunk_pos, v_chunk_rows, v_wal_bytes, NOW());

        v_low_id := v_high_id;
        COMMIT;
        PERFORM pg_sleep(0.05);
    END LOOP;

    CALL mol_bronze._tray_finalize(v_proc_name, 'mol_bronze', 'pubchem', 'pubchem_tray');

    RAISE NOTICE 'refresh_pubchem_via_tray complete: % rows inserted', v_total_rows;
END;
$$;
