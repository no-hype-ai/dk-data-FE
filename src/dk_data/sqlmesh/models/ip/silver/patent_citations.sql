-- T070: ip_silver.patent_citations — FULL model
-- Edge list from cited_patents arrays. One row per citation relationship.
-- Sources: USPTO cited_patents (T055 expansion), EPO cited_documents (T059 expansion).
-- Part of: 006-claims-engine-data-gaps (Item 28)

MODEL (
    name ip_silver.patent_citations,
    kind FULL,
    cron '@weekly',
    grain (citing_patent, cited_patent, jurisdiction)
);

WITH uspto_citations AS (
    -- Unnest USPTO cited_patents JSONB array
    SELECT
        u.patent_number AS citing_patent,
        cite.value::TEXT AS cited_patent,
        'patent' AS citation_type,
        'US' AS jurisdiction
    FROM ip_bronze.uspto_patents u,
         jsonb_array_elements_text(u.cited_patents) AS cite(value)
    WHERE u.cited_patents IS NOT NULL
      AND jsonb_typeof(u.cited_patents) = 'array'
),

epo_citations AS (
    -- Unnest EPO cited_documents JSONB array (objects with doc_number field)
    SELECT
        e.patent_number AS citing_patent,
        COALESCE(
            cite.value->>'doc_number',
            cite.value->>'text'
        ) AS cited_patent,
        CASE
            WHEN cite.value->>'type' = 'npl' THEN 'npl'
            ELSE 'patent'
        END AS citation_type,
        'EP' AS jurisdiction
    FROM ip_bronze.epo_patents e,
         jsonb_array_elements(e.cited_documents) AS cite(value)
    WHERE e.cited_documents IS NOT NULL
      AND jsonb_typeof(e.cited_documents) = 'array'
)

SELECT
    citing_patent,
    cited_patent,
    citation_type,
    jurisdiction,
    NOW() AS last_updated_at
FROM (
    SELECT * FROM uspto_citations
    UNION ALL
    SELECT * FROM epo_citations
) combined
WHERE cited_patent IS NOT NULL
  AND cited_patent != ''
