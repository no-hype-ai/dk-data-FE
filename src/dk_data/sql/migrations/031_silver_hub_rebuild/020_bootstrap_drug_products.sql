-- T076: Bootstrap mol_silver.drug_products from RxNorm SCD, FDA Drugs, Purple Book
-- Expected: Tier 1/2 (moderate volume)
-- Chunk: ≤50K rows, ≤200 MB WAL per chunk, pg_sleep(0.05) between chunks

CREATE OR REPLACE PROCEDURE mol_silver.bootstrap_drug_products()
LANGUAGE plpgsql
AS $$
DECLARE
    v_proc_name  text := 'mol_silver.bootstrap_drug_products';
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
                rxcui,
                bla_number,
                application_number,
                brand_name,
                generic_name,
                dosage_form,
                route,
                is_biologic,
                ndc_code,
                source_name
            FROM (
                -- RxNorm SCD/SBD (SCD=clinical drugs, SBD=branded drugs)
                SELECT 1 AS source_priority, id AS src_id,
                    rxcui, NULL AS bla_number, NULL AS application_number,
                    brand_name, generic_name, dose_form AS dosage_form, route,
                    false AS is_biologic,
                    ndc AS ndc_code,
                    'rxnorm_scd' AS source_name
                FROM mol_bronze.rxnorm_scd
                WHERE tty IN ('SCD', 'SBD', 'GPCK', 'BPCK')

                UNION ALL

                -- FDA Drugs@FDA (NDA applications)
                SELECT 2, id,
                    NULL, NULL, application_number,
                    brand_name, generic_name, dosage_form, route,
                    false,
                    NULL,
                    'fda_drugs'
                FROM mol_bronze.fda_drugs

                UNION ALL

                -- Purple Book (biologics BLA)
                SELECT 3, id,
                    NULL, bla_number, NULL,
                    proprietary_name AS brand_name,
                    nonproprietary_name AS generic_name,
                    dosage_form, route,
                    true,
                    NULL,
                    'purple_book'
                FROM mol_bronze.purple_book
            ) sub
        ),
        chunked AS (
            SELECT *
            FROM source_union
            WHERE union_id > v_resume_pos
            ORDER BY union_id
            LIMIT v_chunk_size
        ),
        inserted AS (
            INSERT INTO mol_silver.drug_products (
                rxcui,
                bla_number,
                application_number,
                brand_name,
                generic_name,
                dosage_form,
                route,
                is_biologic
            )
            SELECT
                c.rxcui,
                c.bla_number,
                c.application_number,
                c.brand_name,
                c.generic_name,
                c.dosage_form,
                c.route,
                COALESCE(c.is_biologic, false)
            FROM chunked c
            ON CONFLICT (rxcui) WHERE rxcui IS NOT NULL DO UPDATE SET
                brand_name      = COALESCE(EXCLUDED.brand_name, mol_silver.drug_products.brand_name),
                generic_name    = COALESCE(EXCLUDED.generic_name, mol_silver.drug_products.generic_name),
                last_updated_at = NOW()
            RETURNING product_id, rxcui, bla_number, application_number
        ),
        ndc_insert AS (
            -- NDC goes into drug_product_identifiers, NOT the hub column
            INSERT INTO mol_silver.drug_product_identifiers (source, identifier, product_id, is_primary)
            SELECT
                'ndc',
                c.ndc_code,
                i.product_id,
                false
            FROM chunked c
            JOIN inserted i ON
                (c.rxcui IS NOT NULL AND i.rxcui = c.rxcui)
                OR (c.bla_number IS NOT NULL AND i.bla_number = c.bla_number)
                OR (c.application_number IS NOT NULL AND i.application_number = c.application_number)
            WHERE c.ndc_code IS NOT NULL
            ON CONFLICT (source, identifier) DO NOTHING
        ),
        name_insert AS (
            INSERT INTO mol_silver.drug_product_names (normalized_name, product_id, name_kind, source, display_name)
            SELECT DISTINCT
                LOWER(TRIM(name_val)),
                i.product_id,
                name_kind,
                c.source_name,
                name_val
            FROM chunked c
            JOIN inserted i ON
                (c.rxcui IS NOT NULL AND i.rxcui = c.rxcui)
                OR (c.bla_number IS NOT NULL AND i.bla_number = c.bla_number)
                OR (c.application_number IS NOT NULL AND i.application_number = c.application_number),
            LATERAL (
                VALUES
                    (c.brand_name, 'brand'),
                    (c.generic_name, 'generic')
            ) AS names(name_val, name_kind)
            WHERE name_val IS NOT NULL
            ON CONFLICT (normalized_name, product_id, source) DO NOTHING
        )
        SELECT COUNT(*) INTO v_rows FROM inserted;

        v_end_lsn := pg_current_wal_lsn();

        SELECT COALESCE(MAX(union_id), v_resume_pos) INTO v_new_pos
        FROM (
            SELECT ROW_NUMBER() OVER (ORDER BY source_priority, src_id) AS union_id
            FROM (
                SELECT 1 AS source_priority, id AS src_id FROM mol_bronze.rxnorm_scd WHERE tty IN ('SCD', 'SBD', 'GPCK', 'BPCK')
                UNION ALL
                SELECT 2, id FROM mol_bronze.fda_drugs
                UNION ALL
                SELECT 3, id FROM mol_bronze.purple_book
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
