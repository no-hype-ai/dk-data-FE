-- Migration 031/034: Tray procedure for mol_bronze.chembl_molecules
-- Audit fix (2026-04-12): replaces the bronze→bronze stub with a real raw→bronze
-- rebuild that mirrors src/dk_data/sqlmesh/models/molecules/bronze/chembl_molecules.sql.

CREATE OR REPLACE PROCEDURE mol_bronze.refresh_chembl_molecules_via_tray()
LANGUAGE plpgsql
AS $$
DECLARE
    v_chunk_size CONSTANT BIGINT := 5000;
    v_proc_name  CONSTANT TEXT := 'mol_bronze.refresh_chembl_molecules_via_tray';
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
    CALL mol_bronze._tray_setup(v_proc_name, 'mol_bronze', 'chembl_molecules', 'chembl_molecules_tray');
    SET LOCAL work_mem = '128MB';

    SELECT COALESCE(MAX(id), 0) INTO v_max_raw_id FROM mol_raw.chembl;

    WHILE v_low_id < v_max_raw_id LOOP
        v_high_id := v_low_id + v_chunk_size;
        v_wal_start := pg_current_wal_lsn();
        v_chunk_pos := v_chunk_pos + 1;

        WITH molecules AS (
            SELECT
                raw.id          AS raw_source_id,
                raw.request_timestamp,
                mol.value       AS mol
            FROM mol_raw.chembl AS raw
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN raw.response_body ? 'molecules'
                    THEN raw.response_body->'molecules'
                    ELSE jsonb_build_array(raw.response_body)
                END
            ) AS mol(value)
            WHERE raw.id > v_low_id AND raw.id <= v_high_id
              AND raw.response_status = 200
        ),
        deduped AS (
            SELECT DISTINCT ON (mol->>'molecule_chembl_id')
                raw_source_id, request_timestamp, mol
            FROM molecules
            WHERE mol->>'molecule_chembl_id' IS NOT NULL
            ORDER BY mol->>'molecule_chembl_id', request_timestamp DESC
        )
        INSERT INTO mol_bronze.chembl_molecules_tray (
            id, chembl_id, pref_name, molecule_type, max_phase,
            molecular_formula, molecular_weight, canonical_smiles, inchi, inchi_key,
            alogp, hba, hbd, psa, num_ro5_violations, aromatic_rings, heavy_atoms,
            first_approval, indication_class, usan_stem,
            therapeutic_flag, prodrug, natural_product,
            synonyms, cross_references,
            raw_json, raw_source_id, source, request_timestamp, source_updated_at,
            processed_to_silver, created_at
        )
        SELECT
            gen_random_uuid(),
            mol->>'molecule_chembl_id',
            REGEXP_REPLACE(mol->>'pref_name', '_v\d+$', ''),
            mol->>'molecule_type',
            (mol->>'max_phase')::NUMERIC::INTEGER,
            mol->'molecule_properties'->>'full_molformula',
            (mol->'molecule_properties'->>'full_mwt')::NUMERIC,
            mol->'molecule_structures'->>'canonical_smiles',
            mol->'molecule_structures'->>'standard_inchi',
            mol->'molecule_structures'->>'standard_inchi_key',
            (mol->'molecule_properties'->>'alogp')::NUMERIC,
            (mol->'molecule_properties'->>'hba')::NUMERIC::INTEGER,
            (mol->'molecule_properties'->>'hbd')::NUMERIC::INTEGER,
            (mol->'molecule_properties'->>'psa')::NUMERIC,
            (mol->'molecule_properties'->>'num_ro5_violations')::NUMERIC::INTEGER,
            (mol->'molecule_properties'->>'aromatic_rings')::NUMERIC::INTEGER,
            (mol->'molecule_properties'->>'heavy_atoms')::NUMERIC::INTEGER,
            (mol->>'first_approval')::NUMERIC::INTEGER,
            mol->>'indication_class',
            mol->>'usan_stem',
            CASE mol->>'therapeutic_flag' WHEN 'true' THEN TRUE WHEN '1' THEN TRUE WHEN '-1' THEN TRUE WHEN 'false' THEN FALSE WHEN '0' THEN FALSE ELSE NULL END,
            CASE mol->>'prodrug' WHEN 'true' THEN TRUE WHEN '1' THEN TRUE WHEN '-1' THEN TRUE WHEN 'false' THEN FALSE WHEN '0' THEN FALSE ELSE NULL END,
            CASE mol->>'natural_product' WHEN 'true' THEN TRUE WHEN '1' THEN TRUE WHEN '-1' THEN TRUE WHEN 'false' THEN FALSE WHEN '0' THEN FALSE ELSE NULL END,
            mol->'molecule_synonyms',
            mol->'cross_references',
            mol, raw_source_id, 'chembl',
            request_timestamp, request_timestamp, FALSE, NOW()
        FROM deduped;

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

    CALL mol_bronze._tray_finalize(v_proc_name, 'mol_bronze', 'chembl_molecules', 'chembl_molecules_tray');

    RAISE NOTICE 'refresh_chembl_molecules_via_tray complete: % rows inserted', v_total_rows;
END;
$$;
