-- T074: Bootstrap mol_silver.molecules from ChEMBL, DrugBank, PubChem
-- Expected: ~500K rows (Tier 1)
-- Uses INSERT ON CONFLICT (inchi_key) DO UPDATE SET last_updated_at = NOW()
-- Chunk: ≤50K rows, ≤200 MB WAL per chunk, pg_sleep(0.05) between chunks

CREATE OR REPLACE PROCEDURE mol_silver.bootstrap_molecules()
LANGUAGE plpgsql
AS $$
DECLARE
    v_proc_name  text := 'mol_silver.bootstrap_molecules';
    v_chunk_size int  := 50000;
    v_resume_pos bigint := 0;
    v_new_pos    bigint;
    v_rows       bigint;
    v_start_lsn  pg_lsn;
    v_end_lsn    pg_lsn;
    v_started_at timestamptz;
BEGIN
    -- 1. Acquire job lock (delete stale first, then insert)
    DELETE FROM meta.job_locks WHERE name = v_proc_name AND expires_at < NOW();
    INSERT INTO meta.job_locks (name, locked_by, locked_at, expires_at)
    VALUES (v_proc_name, pg_backend_pid()::text, NOW(), NOW() + INTERVAL '4 hours')
    ON CONFLICT (name) DO NOTHING;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Could not acquire job lock for %; another instance may be running', v_proc_name;
    END IF;

    -- 2. Initialize or resume meta.refresh_state
    INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, last_commit_at, status)
    VALUES (v_proc_name, '0', NOW(), 'in_progress')
    ON CONFLICT (procedure_name) DO UPDATE
        SET status = 'in_progress', last_commit_at = NOW()
        WHERE meta.refresh_state.status <> 'in_progress';

    SELECT last_chunk_position::bigint INTO v_resume_pos
    FROM meta.refresh_state
    WHERE procedure_name = v_proc_name;

    v_resume_pos := COALESCE(v_resume_pos, 0);

    -- 3. Chunked load loop — union ordered by synthetic sequential id
    LOOP
        v_started_at := clock_timestamp();
        v_start_lsn  := pg_current_wal_lsn();

        WITH source_union AS (
            SELECT
                ROW_NUMBER() OVER (ORDER BY source_priority, src_id) AS union_id,
                inchi_key,
                canonical_smiles,
                sequence_hash,
                is_biologic,
                canonical_name,
                source_name,
                source_identifier
            FROM (
                -- ChEMBL molecules (highest priority)
                SELECT 1 AS source_priority, id AS src_id,
                    standard_inchi_key AS inchi_key,
                    canonical_smiles,
                    NULL               AS sequence_hash,
                    (biotherapeutic IS NOT NULL AND biotherapeutic <> 'f') AS is_biologic,
                    pref_name          AS canonical_name,
                    'chembl'           AS source_name,
                    chembl_id          AS source_identifier
                FROM mol_bronze.chembl_molecules
                WHERE standard_inchi_key IS NOT NULL

                UNION ALL

                -- DrugBank drugs
                SELECT 2, id,
                    inchikey, canonical_smiles, NULL,
                    (biotech = 'yes')::boolean,
                    name,
                    'drugbank',
                    drugbank_id
                FROM mol_bronze.drugbank_drugs
                WHERE inchikey IS NOT NULL

                UNION ALL

                -- PubChem compounds
                SELECT 3, id,
                    inchikey, isomeric_smiles AS canonical_smiles, NULL,
                    false,
                    iupac_name AS canonical_name,
                    'pubchem',
                    cid::text
                FROM mol_bronze.pubchem
                WHERE inchikey IS NOT NULL
            ) sub
        ),
        chunked AS (
            SELECT DISTINCT ON (inchi_key)
                union_id, inchi_key, canonical_smiles, sequence_hash,
                is_biologic, canonical_name, source_name, source_identifier
            FROM source_union
            WHERE union_id > v_resume_pos
            ORDER BY inchi_key, union_id   -- lowest union_id wins (highest priority source)
        ),
        inserted AS (
            INSERT INTO mol_silver.molecules (
                inchi_key,
                canonical_smiles,
                sequence_hash,
                is_biologic,
                canonical_name
            )
            SELECT
                c.inchi_key,
                c.canonical_smiles,
                c.sequence_hash,
                COALESCE(c.is_biologic, false),
                c.canonical_name
            FROM chunked c
            ON CONFLICT (inchi_key) DO UPDATE SET
                canonical_smiles = COALESCE(EXCLUDED.canonical_smiles, mol_silver.molecules.canonical_smiles),
                canonical_name   = COALESCE(EXCLUDED.canonical_name, mol_silver.molecules.canonical_name),
                last_updated_at  = NOW()
            RETURNING molecule_id, inchi_key
        ),
        id_insert AS (
            INSERT INTO mol_silver.molecule_identifiers (source, identifier, molecule_id, is_primary)
            SELECT
                c.source_name,
                c.source_identifier,
                i.molecule_id,
                (c.source_name = 'chembl')
            FROM chunked c
            JOIN inserted i ON i.inchi_key = c.inchi_key
            WHERE c.source_identifier IS NOT NULL
            ON CONFLICT (source, identifier) DO NOTHING
        ),
        name_insert AS (
            INSERT INTO mol_silver.molecule_names (normalized_name, molecule_id, name_kind, source, display_name)
            SELECT
                LOWER(TRIM(c.canonical_name)),
                i.molecule_id,
                'canonical',
                c.source_name,
                c.canonical_name
            FROM chunked c
            JOIN inserted i ON i.inchi_key = c.inchi_key
            WHERE c.canonical_name IS NOT NULL
            ON CONFLICT (normalized_name, molecule_id, source) DO NOTHING
        )
        SELECT COUNT(*) INTO v_rows FROM inserted;

        v_end_lsn := pg_current_wal_lsn();

        SELECT COALESCE(MAX(union_id), v_resume_pos) INTO v_new_pos
        FROM (
            SELECT ROW_NUMBER() OVER (ORDER BY source_priority, src_id) AS union_id
            FROM (
                SELECT 1 AS source_priority, id AS src_id FROM mol_bronze.chembl_molecules WHERE standard_inchi_key IS NOT NULL
                UNION ALL
                SELECT 2, id FROM mol_bronze.drugbank_drugs WHERE inchikey IS NOT NULL
                UNION ALL
                SELECT 3, id FROM mol_bronze.pubchem WHERE inchikey IS NOT NULL
            ) sub
        ) numbered
        WHERE union_id > v_resume_pos
        ORDER BY union_id
        LIMIT v_chunk_size;

        INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
        VALUES (
            v_proc_name,
            v_new_pos::text,
            v_started_at,
            clock_timestamp(),
            v_rows,
            pg_wal_lsn_diff(v_end_lsn, v_start_lsn)
        );

        UPDATE meta.refresh_state
        SET last_chunk_position = v_new_pos::text,
            last_commit_at      = NOW()
        WHERE procedure_name = v_proc_name;

        COMMIT;

        EXIT WHEN v_rows = 0 OR v_new_pos = v_resume_pos;
        v_resume_pos := v_new_pos;

        PERFORM pg_sleep(0.05);
    END LOOP;

    -- 4. Mark completed
    UPDATE meta.refresh_state
    SET status = 'completed', last_commit_at = NOW()
    WHERE procedure_name = v_proc_name;

    -- 5. Release lock
    DELETE FROM meta.job_locks WHERE name = v_proc_name;

    COMMIT;
END;
$$;
