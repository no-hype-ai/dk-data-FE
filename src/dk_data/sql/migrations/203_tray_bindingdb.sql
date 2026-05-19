-- Migration 031/031: Tray procedure for mol_bronze.bindingdb
-- Audit fix (2026-04-12): replaces the bronze→bronze stub with a real
-- raw→bronze rebuild that mirrors src/dk_data/sqlmesh/models/molecules/bronze/bindingdb.sql.

CREATE OR REPLACE PROCEDURE mol_bronze.refresh_bindingdb_via_tray()
LANGUAGE plpgsql
AS $$
DECLARE
    v_chunk_size CONSTANT BIGINT := 5000;
    v_proc_name  CONSTANT TEXT := 'mol_bronze.refresh_bindingdb_via_tray';
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
    CALL mol_bronze._tray_setup(v_proc_name, 'mol_bronze', 'bindingdb', 'bindingdb_tray');
    SET LOCAL work_mem = '128MB';

    SELECT COALESCE(MAX(id), 0) INTO v_max_raw_id FROM mol_raw.bindingdb;

    WHILE v_low_id < v_max_raw_id LOOP
        v_high_id := v_low_id + v_chunk_size;
        v_wal_start := pg_current_wal_lsn();
        v_chunk_pos := v_chunk_pos + 1;

        INSERT INTO mol_bronze.bindingdb_tray (
            id, raw_id, bindingdb_id, inchi_key, smiles, pubchem_cid, chembl_id,
            target_name, target_organism, uniprot_id,
            ki_nm, ic50_nm, kd_nm, ec50_nm, kon, koff, assay_ph, assay_temp_c,
            activity_type, activity_value, activity_unit,
            pmid, doi, data_source, pdb_ids,
            processed_to_silver, ingested_at
        )
        SELECT
            uuid_generate_v4(),
            r.id,
            r.response_body->>'BindingDB Reactant_set_id',
            r.response_body->>'Ligand InChIKey',
            r.response_body->>'Ligand SMILES',
            (r.response_body->>'PubChem CID')::BIGINT,
            r.response_body->>'ChEMBL ID of Ligand',
            r.response_body->>'Target Name Assigned by Curator or DataSource',
            r.response_body->>'Target Source Organism According to Curator or DataSource',
            r.response_body->>'UniProt (SwissProt) Primary ID of Target Chain',
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Ki (nM)', ''),    '[^0-9.]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'IC50 (nM)', ''),  '[^0-9.]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Kd (nM)', ''),    '[^0-9.]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'EC50 (nM)', ''),  '[^0-9.]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'kon (M-1-s-1)', ''), '[^0-9.eE+-]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'koff (s-1)', ''),    '[^0-9.eE+-]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'pH', ''),       '[^0-9.]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Temp (C)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC,
            CASE
                WHEN REGEXP_REPLACE(COALESCE(r.response_body->>'Ki (nM)', ''),   '[^0-9.]', '', 'g') != '' THEN 'Ki'
                WHEN REGEXP_REPLACE(COALESCE(r.response_body->>'Kd (nM)', ''),   '[^0-9.]', '', 'g') != '' THEN 'Kd'
                WHEN REGEXP_REPLACE(COALESCE(r.response_body->>'IC50 (nM)', ''), '[^0-9.]', '', 'g') != '' THEN 'IC50'
                WHEN REGEXP_REPLACE(COALESCE(r.response_body->>'EC50 (nM)', ''), '[^0-9.]', '', 'g') != '' THEN 'EC50'
                ELSE NULL
            END,
            COALESCE(
                NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Ki (nM)', ''),   '[^0-9.]', '', 'g'), '')::NUMERIC,
                NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Kd (nM)', ''),   '[^0-9.]', '', 'g'), '')::NUMERIC,
                NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'IC50 (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC,
                NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'EC50 (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC
            ),
            'nM',
            r.response_body->>'PMID',
            r.response_body->>'Article DOI',
            r.response_body->>'Curation/DataSource',
            r.response_body->>'PDB ID(s) for Ligand-Target Complex',
            FALSE,
            r.ingested_at
        FROM mol_raw.bindingdb r
        WHERE r.id > v_low_id AND r.id <= v_high_id
          AND r.response_status = 200
          AND r.response_body IS NOT NULL
          AND r.response_body->>'BindingDB Reactant_set_id' IS NOT NULL;

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

    CALL mol_bronze._tray_finalize(v_proc_name, 'mol_bronze', 'bindingdb', 'bindingdb_tray');

    RAISE NOTICE 'refresh_bindingdb_via_tray complete: % rows inserted', v_total_rows;
END;
$$;
