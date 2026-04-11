-- T079a: Bootstrap hcp_silver.researchers from PubMed + OpenAlex
-- Expected: ~2M rows
-- Also populates researcher_publications and researcher_affiliations
-- Chunk: ≤50K rows, ≤200 MB WAL per chunk, pg_sleep(0.05) between chunks

CREATE OR REPLACE PROCEDURE hcp_silver.bootstrap_researchers()
LANGUAGE plpgsql
AS $$
DECLARE
    v_proc_name  text := 'hcp_silver.bootstrap_researchers';
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
    VALUES (v_proc_name, pg_backend_pid()::text, NOW(), NOW() + INTERVAL '6 hours')
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
    --    Source 1: PubMed AuthorList with ORCID identifier
    --    Source 2: OpenAlex authorships with orcid + scopus_id
    LOOP
        v_started_at := clock_timestamp();
        v_start_lsn  := pg_current_wal_lsn();

        WITH source_union AS (
            SELECT
                ROW_NUMBER() OVER (ORDER BY source_priority, src_id) AS union_id,
                orcid_id,
                scopus_author_id,
                pubmed_author_signature,
                canonical_full_name,
                primary_affiliation_institution,
                pmid,
                pub_title,
                pub_year,
                institution_name,
                ror_id
            FROM (
                -- PubMed: extract from AuthorList JSONB (orcid in Identifier[@Source='ORCID'])
                SELECT 1 AS source_priority, id AS src_id,
                    -- ORCID extracted from author identifiers JSON
                    jsonb_path_query_first(
                        author_data,
                        '$.Identifier[*] ? (@.Source == "ORCID").value'
                    )::text                    AS orcid_id,
                    NULL                       AS scopus_author_id,
                    -- PubMed author signature: lower(LastName) || '_' || lower(left(ForeName, 1))
                    LOWER(author_data->>'LastName') || '_' ||
                        LOWER(LEFT(author_data->>'ForeName', 1)) AS pubmed_author_signature,
                    -- canonical_full_name: "LastName, ForeName"
                    (author_data->>'LastName') || ', ' || (author_data->>'ForeName') AS canonical_full_name,
                    -- Primary affiliation from AffiliationInfo
                    author_data->'AffiliationInfo'->0->>'Affiliation' AS primary_affiliation_institution,
                    pmid,
                    title AS pub_title,
                    pub_year,
                    NULL  AS institution_name,
                    NULL  AS ror_id
                FROM mol_bronze.pubmed,
                    jsonb_array_elements(author_list) AS author_data
                WHERE author_list IS NOT NULL
                  AND author_data->>'LastName' IS NOT NULL

                UNION ALL

                -- OpenAlex: authorships array with orcid + scopus_id
                SELECT 2, id,
                    -- strip leading https://orcid.org/ prefix
                    REPLACE(authorship->>'orcid', 'https://orcid.org/', '') AS orcid_id,
                    authorship->>'scopus_id'      AS scopus_author_id,
                    NULL                          AS pubmed_author_signature,
                    authorship->'author'->>'display_name' AS canonical_full_name,
                    authorship->'institutions'->0->>'display_name' AS primary_affiliation_institution,
                    NULL AS pmid,
                    NULL AS pub_title,
                    pub_year,
                    authorship->'institutions'->0->>'display_name' AS institution_name,
                    authorship->'institutions'->0->>'ror'          AS ror_id
                FROM mol_bronze.openalex,
                    jsonb_array_elements(authorships) AS authorship
                WHERE authorships IS NOT NULL
                  AND authorship->'author'->>'display_name' IS NOT NULL
            ) sub
        ),
        chunked AS (
            SELECT DISTINCT ON (COALESCE(orcid_id, canonical_full_name))
                union_id, orcid_id, scopus_author_id, pubmed_author_signature,
                canonical_full_name, primary_affiliation_institution,
                pmid, pub_title, pub_year, institution_name, ror_id
            FROM source_union
            WHERE union_id > v_resume_pos
            ORDER BY COALESCE(orcid_id, canonical_full_name), union_id
        ),
        inserted AS (
            INSERT INTO hcp_silver.researchers (
                orcid_id,
                scopus_author_id,
                pubmed_author_signature,
                canonical_full_name,
                primary_affiliation_institution
            )
            SELECT
                c.orcid_id,
                c.scopus_author_id,
                c.pubmed_author_signature,
                c.canonical_full_name,
                c.primary_affiliation_institution
            FROM chunked c
            WHERE c.canonical_full_name IS NOT NULL
            ON CONFLICT (orcid_id) WHERE orcid_id IS NOT NULL DO UPDATE SET
                scopus_author_id              = COALESCE(EXCLUDED.scopus_author_id, hcp_silver.researchers.scopus_author_id),
                pubmed_author_signature       = COALESCE(EXCLUDED.pubmed_author_signature, hcp_silver.researchers.pubmed_author_signature),
                primary_affiliation_institution = COALESCE(EXCLUDED.primary_affiliation_institution, hcp_silver.researchers.primary_affiliation_institution),
                last_updated_at               = NOW()
            RETURNING researcher_id, orcid_id, canonical_full_name
        ),
        pub_insert AS (
            INSERT INTO hcp_silver.researcher_publications (
                researcher_id,
                pmid,
                publication_year,
                journal_name
            )
            SELECT
                i.researcher_id,
                c.pmid,
                c.pub_year,
                NULL
            FROM chunked c
            JOIN inserted i ON
                (c.orcid_id IS NOT NULL AND i.orcid_id = c.orcid_id)
                OR (c.orcid_id IS NULL AND i.canonical_full_name = c.canonical_full_name)
            WHERE c.pmid IS NOT NULL
            ON CONFLICT DO NOTHING
        ),
        aff_insert AS (
            INSERT INTO hcp_silver.researcher_affiliations (
                researcher_id,
                institution_name,
                first_year
            )
            SELECT
                i.researcher_id,
                c.institution_name,
                c.pub_year
            FROM chunked c
            JOIN inserted i ON
                (c.orcid_id IS NOT NULL AND i.orcid_id = c.orcid_id)
                OR (c.orcid_id IS NULL AND i.canonical_full_name = c.canonical_full_name)
            WHERE c.institution_name IS NOT NULL
            ON CONFLICT DO NOTHING
        )
        SELECT COUNT(*) INTO v_rows FROM inserted;

        v_end_lsn := pg_current_wal_lsn();

        SELECT COALESCE(MAX(union_id), v_resume_pos) INTO v_new_pos
        FROM (
            SELECT ROW_NUMBER() OVER (ORDER BY source_priority, src_id) AS union_id
            FROM (
                SELECT 1 AS source_priority, id AS src_id
                FROM mol_bronze.pubmed, jsonb_array_elements(author_list) AS a
                WHERE author_list IS NOT NULL AND a->>'LastName' IS NOT NULL
                UNION ALL
                SELECT 2, id
                FROM mol_bronze.openalex, jsonb_array_elements(authorships) AS a
                WHERE authorships IS NOT NULL AND a->'author'->>'display_name' IS NOT NULL
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
