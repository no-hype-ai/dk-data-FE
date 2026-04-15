-- SQLMesh Model: Silver Conference Abstracts
-- Molecule crosswalk via text matching on title + abstract_text against
-- mol_silver.molecules.canonical_name. Embargo filter ensures embargoed
-- abstracts do not appear until publication_date.
-- Feature: 006-claims-engine-data-gaps (T080)

MODEL (
    name mol_silver.conference_abstracts,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (abstract_id, conference_body))
    ),
    grain (abstract_id)
);

SELECT
    b.abstract_id,
    b.conference_name,
    b.conference_body,
    b.conference_date,
    b.presentation_date,
    b.presentation_type,
    b.title,
    b.authors,
    b.affiliations,
    b.abstract_text,
    b.embargo_date,
    b.publication_date,
    b.session_title,
    b.track,
    b.source_url,
    -- Molecule crosswalk: match canonical_name appearing in title or abstract_text
    m.id                                AS molecule_id,
    b.source_updated_at,
    NOW()                               AS created_at
FROM mol_bronze.conference_abstracts b
LEFT JOIN mol_silver.molecules m
    ON (
        LOWER(b.title) LIKE '%' || LOWER(TRIM(m.name)) || '%'
        OR LOWER(b.abstract_text) LIKE '%' || LOWER(TRIM(m.name)) || '%'
    )
    AND LENGTH(TRIM(m.name)) >= 4  -- avoid spurious short-name matches
WHERE b.publication_date <= CURRENT_DATE
   OR b.publication_date IS NULL;
