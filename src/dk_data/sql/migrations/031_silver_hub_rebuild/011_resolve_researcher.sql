-- Migration: 011_resolve_researcher.sql
-- Feature: 001-silver-medallion-rebuild
-- T056a: hcp_silver.resolve_researcher — entity-resolution function for researchers/authors.
--
-- Priority tree (most-specific → least-specific):
--   1. ORCID               (Open Researcher and Contributor ID — globally unique)
--   2. Scopus author ID    (Elsevier bibliometric identifier)
--   3. PubMed signature    (normalized: lower(lastname) || '_' || lower(firstinitial))
--   4. ResearchGate ID     (social research platform ID)
--   5. Google Scholar ID   (Google Scholar profile ID)
--   6. Full name + institution fuzzy (pg_trgm similarity ≥ 0.85)
--
-- ORCID, Scopus, ResearchGate, Google Scholar → researcher_identifiers crosswalk.
-- PubMed signature → canonical hub column pubmed_author_signature.
-- Fuzzy match on researcher_names with optional institution filter.
--
-- Returns NULL when no match is found at any tier.
-- STABLE PARALLEL SAFE: no writes; reads are deterministic within a transaction.

BEGIN;

CREATE OR REPLACE FUNCTION hcp_silver.resolve_researcher(
    p_orcid              text DEFAULT NULL,
    p_scopus_author_id   text DEFAULT NULL,
    p_pubmed_signature   text DEFAULT NULL,
    p_researchgate_id    text DEFAULT NULL,
    p_google_scholar_id  text DEFAULT NULL,
    p_full_name          text DEFAULT NULL,
    p_institution        text DEFAULT NULL,
    p_country            text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id bigint;
BEGIN
    -- 1. ORCID (globally unique researcher identifier)
    IF p_orcid IS NOT NULL THEN
        SELECT researcher_id INTO v_id
        FROM hcp_silver.researcher_identifiers
        WHERE source = 'orcid' AND identifier = p_orcid;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. Scopus author ID
    IF p_scopus_author_id IS NOT NULL THEN
        SELECT researcher_id INTO v_id
        FROM hcp_silver.researcher_identifiers
        WHERE source = 'scopus_author' AND identifier = p_scopus_author_id;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. PubMed author signature — canonical hub column
    --    Format: lower(lastname) || '_' || lower(firstinitial)
    IF p_pubmed_signature IS NOT NULL THEN
        SELECT researcher_id INTO v_id
        FROM hcp_silver.researchers
        WHERE pubmed_author_signature = LOWER(TRIM(p_pubmed_signature));
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 4. ResearchGate ID
    IF p_researchgate_id IS NOT NULL THEN
        SELECT researcher_id INTO v_id
        FROM hcp_silver.researcher_identifiers
        WHERE source = 'researchgate' AND identifier = p_researchgate_id;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 5. Google Scholar ID
    IF p_google_scholar_id IS NOT NULL THEN
        SELECT researcher_id INTO v_id
        FROM hcp_silver.researcher_identifiers
        WHERE source = 'google_scholar' AND identifier = p_google_scholar_id;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 6. Full name fuzzy + optional institution filter (pg_trgm ≥ 0.85)
    IF p_full_name IS NOT NULL THEN
        SELECT rn.researcher_id INTO v_id
        FROM hcp_silver.researcher_names rn
        JOIN hcp_silver.researchers r ON r.researcher_id = rn.researcher_id
        WHERE similarity(LOWER(rn.normalized_name), LOWER(TRIM(p_full_name))) >= 0.85
          AND (p_institution IS NULL OR
               similarity(LOWER(COALESCE(r.primary_affiliation_institution, '')),
                          LOWER(TRIM(p_institution))) >= 0.75)
        ORDER BY similarity(LOWER(rn.normalized_name), LOWER(TRIM(p_full_name))) DESC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION hcp_silver.resolve_researcher IS
    'T056a: Resolve a researcher/author hub ID from any combination of identifiers. '
    'Priority: ORCID → Scopus author ID → PubMed signature → ResearchGate → '
    'Google Scholar → full_name+institution fuzzy(≥0.85). Returns NULL on no match.';

COMMIT;
