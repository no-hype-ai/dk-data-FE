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
                source_priority * 1000000000000000::bigint + src_id::bigint AS union_id,
                rxcui,
                bla_number,
                bla_product_number,
                application_number,
                brand_name,
                generic_name,
                dosage_form,
                route,
                is_biologic,
                is_biosimilar,
                reference_product_name,
                reference_product_brand,
                ndc_code,
                source_name
            FROM (
                -- RxNorm SCD/SBD (SCD=clinical drugs, SBD=branded drugs)
                SELECT 1::bigint AS source_priority, id::bigint AS src_id,
                    rxcui, NULL AS bla_number, NULL AS bla_product_number, NULL AS application_number,
                    brand_name, generic_name, dose_form AS dosage_form, route,
                    false AS is_biologic, false AS is_biosimilar,
                    NULL AS reference_product_name, NULL AS reference_product_brand,
                    ndc AS ndc_code,
                    'rxnorm_scd' AS source_name
                FROM mol_bronze.rxnorm_scd
                WHERE tty IN ('SCD', 'SBD', 'GPCK', 'BPCK')

                UNION ALL

                -- FDA Drugs@FDA (NDA applications)
                SELECT 2, id,
                    NULL, NULL, NULL, application_number,
                    brand_name, generic_name, dosage_form, route,
                    false, false,
                    NULL, NULL,
                    NULL,
                    'fda_drugs'
                FROM mol_bronze.fda_drugs

                UNION ALL

                -- Purple Book (biologics BLA — biosimilar status preserved from source)
                SELECT 3, id,
                    NULL, bla_number, product_number, NULL,
                    brand_name,
                    generic_name,
                    dosage_form, route,
                    true,
                    COALESCE(is_biosimilar, false),
                    reference_product_name,
                    reference_product_brand,
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
                bla_product_number,
                application_number,
                brand_name,
                generic_name,
                dosage_form,
                route,
                is_biologic,
                is_biosimilar
            )
            SELECT
                c.rxcui,
                c.bla_number,
                c.bla_product_number,
                c.application_number,
                c.brand_name,
                c.generic_name,
                c.dosage_form,
                c.route,
                COALESCE(c.is_biologic, false),
                COALESCE(c.is_biosimilar, false)
            FROM chunked c
            ON CONFLICT (rxcui) WHERE rxcui IS NOT NULL DO UPDATE SET
                brand_name      = COALESCE(EXCLUDED.brand_name, mol_silver.drug_products.brand_name),
                generic_name    = COALESCE(EXCLUDED.generic_name, mol_silver.drug_products.generic_name),
                is_biosimilar   = mol_silver.drug_products.is_biosimilar OR EXCLUDED.is_biosimilar,
                last_updated_at = NOW()
            RETURNING product_id, rxcui, bla_number, bla_product_number, application_number
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
        bla_crosswalk AS (
            -- BLA crosswalk: bla_number:product_number composite identifier
            INSERT INTO mol_silver.drug_product_identifiers (source, identifier, product_id, is_primary)
            SELECT
                'bla',
                c.bla_number || ':' || COALESCE(c.bla_product_number, '0'),
                i.product_id,
                true
            FROM chunked c
            JOIN inserted i ON i.bla_number = c.bla_number
                AND COALESCE(i.bla_product_number, '0') = COALESCE(c.bla_product_number, '0')
            WHERE c.bla_number IS NOT NULL
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
            SELECT source_priority * 1000000000000000::bigint + src_id::bigint AS union_id
            FROM (
                SELECT 1::bigint AS source_priority, id::bigint AS src_id FROM mol_bronze.rxnorm_scd WHERE tty IN ('SCD', 'SBD', 'GPCK', 'BPCK')
                UNION ALL
                SELECT 2::bigint, id::bigint FROM mol_bronze.fda_drugs
                UNION ALL
                SELECT 3::bigint, id::bigint FROM mol_bronze.purple_book
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

    -- 3b. Resolve biosimilar→reference product linkage (FR-012a, Gap 9).
    -- Run after the chunked load so all originator and biosimilar rows exist in the hub.
    -- Equality-only join on lowercased brand_name; no LIKE/similarity (S2/S5 banned).
    WITH originator AS (
        SELECT DISTINCT ON (LOWER(brand_name))
            LOWER(brand_name) AS norm_brand,
            product_id        AS reference_product_id
        FROM mol_silver.drug_products
        WHERE brand_name IS NOT NULL
          AND is_biologic = true
          AND COALESCE(is_biosimilar, false) = false
        ORDER BY LOWER(brand_name), product_id
    ),
    biosim AS (
        SELECT DISTINCT
            dp.product_id,
            COALESCE(o1.reference_product_id, o2.reference_product_id) AS reference_product_id
        FROM mol_silver.drug_products dp
        JOIN mol_bronze.purple_book pb
          ON pb.bla_number = dp.bla_number
         AND COALESCE(pb.product_number, '0') = COALESCE(dp.bla_product_number, '0')
        LEFT JOIN originator o1 ON o1.norm_brand = LOWER(NULLIF(pb.reference_product_brand, ''))
        LEFT JOIN originator o2 ON o2.norm_brand = LOWER(NULLIF(pb.reference_product_name, ''))
        WHERE COALESCE(dp.is_biosimilar, false) = true
          AND dp.reference_product_id IS NULL
    )
    UPDATE mol_silver.drug_products dp
    SET reference_product_id = b.reference_product_id,
        last_updated_at      = NOW()
    FROM biosim b
    WHERE dp.product_id = b.product_id
      AND b.reference_product_id IS NOT NULL;

    COMMIT;

    -- 4. Mark completed
    UPDATE meta.refresh_state
    SET status = 'completed', last_commit_at = NOW()
    WHERE procedure_name = v_proc_name;

    -- 5. Release lock
    DELETE FROM meta.job_locks WHERE name = v_proc_name;

    COMMIT;
END;
$$;
