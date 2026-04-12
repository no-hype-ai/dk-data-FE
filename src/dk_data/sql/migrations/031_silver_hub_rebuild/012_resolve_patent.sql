-- Migration: 012_resolve_patent.sql
-- Feature: 001-silver-medallion-rebuild
-- T057: ip_silver.resolve_patent — entity-resolution function for patents.
--
-- Priority tree (most-specific → least-specific):
--   1. (jurisdiction, patent_number)      — canonical granted patent
--   2. (jurisdiction, application_number) — pre-grant application
--   3. (jurisdiction, publication_number) — via patent_identifiers crosswalk
--   4. PCT application number             — international filing (via identifiers)
--   5. Title + assignee + filing_year fuzzy (pg_trgm similarity ≥ 0.85)
--
-- jurisdiction + patent_number / application_number are canonical hub columns.
-- publication_number and PCT number are stored in patent_identifiers.
--
-- Returns NULL when no match is found at any tier.
-- STABLE PARALLEL SAFE: no writes; reads are deterministic within a transaction.

BEGIN;

CREATE OR REPLACE FUNCTION ip_silver.resolve_patent(
    p_jurisdiction       text    DEFAULT NULL,
    p_patent_number      text    DEFAULT NULL,
    p_application_number text    DEFAULT NULL,
    p_publication_number text    DEFAULT NULL,
    p_pct_application    text    DEFAULT NULL,
    p_title              text    DEFAULT NULL,
    p_first_assignee     text    DEFAULT NULL,
    p_filing_year        integer DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    v_id bigint;
BEGIN
    -- 1. (jurisdiction, patent_number) — canonical granted patent hub columns
    IF p_jurisdiction IS NOT NULL AND p_patent_number IS NOT NULL THEN
        SELECT patent_id INTO v_id
        FROM ip_silver.patents
        WHERE jurisdiction = p_jurisdiction
          AND patent_number = p_patent_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 2. (jurisdiction, application_number) — pre-grant application hub columns
    IF p_jurisdiction IS NOT NULL AND p_application_number IS NOT NULL THEN
        SELECT patent_id INTO v_id
        FROM ip_silver.patents
        WHERE jurisdiction = p_jurisdiction
          AND application_number = p_application_number;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 3. (jurisdiction, publication_number) — via patent_identifiers crosswalk
    IF p_jurisdiction IS NOT NULL AND p_publication_number IS NOT NULL THEN
        SELECT pi.patent_id INTO v_id
        FROM ip_silver.patent_identifiers pi
        JOIN ip_silver.patents p ON p.patent_id = pi.patent_id
        WHERE pi.source = 'publication_number'
          AND pi.identifier = p_publication_number
          AND p.jurisdiction = p_jurisdiction;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 4. PCT application number — via patent_identifiers (jurisdiction-independent)
    IF p_pct_application IS NOT NULL THEN
        SELECT patent_id INTO v_id
        FROM ip_silver.patent_identifiers
        WHERE source = 'pct_application' AND identifier = p_pct_application;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    -- 5. Title + assignee + year fuzzy (pg_trgm ≥ 0.85 on normalized title)
    IF p_title IS NOT NULL THEN
        SELECT pn.patent_id INTO v_id
        FROM ip_silver.patent_names pn
        JOIN ip_silver.patents pt ON pt.patent_id = pn.patent_id
        WHERE pn.name_kind = 'title'
          AND similarity(LOWER(pn.normalized_name), LOWER(TRIM(p_title))) >= 0.85
          AND (p_first_assignee IS NULL OR
               similarity(LOWER(COALESCE(pt.first_assignee, '')),
                          LOWER(TRIM(p_first_assignee))) >= 0.75)
          AND (p_filing_year IS NULL OR
               EXTRACT(YEAR FROM pt.filing_date) = p_filing_year)
        ORDER BY similarity(LOWER(pn.normalized_name), LOWER(TRIM(p_title))) DESC, pn.patent_id ASC
        LIMIT 1;
        IF FOUND THEN RETURN v_id; END IF;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION ip_silver.resolve_patent IS
    'T057: Resolve a patent hub ID from jurisdiction+number, application, publication, '
    'PCT, or title+assignee+year. '
    'Priority: (jurisdiction,patent_number) → (jurisdiction,application_number) → '
    '(jurisdiction,publication_number) → PCT → title+assignee+year fuzzy(≥0.85). '
    'Returns NULL on no match.';

COMMIT;
