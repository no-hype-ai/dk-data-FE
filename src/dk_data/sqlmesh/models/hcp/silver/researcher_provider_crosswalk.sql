-- T039a: hcp_silver.researcher_provider_crosswalk
-- Links hcp_silver.researchers (ORCID-keyed) to hcs_silver.providers (NPI-keyed).
-- Match confidence is computed from name + institution + state agreement.
-- Gold consumers MUST filter confidence >= 0.95 per FR-013.

MODEL (
    name hcp_silver.researcher_provider_crosswalk,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (researcher_id, provider_id)
    ),
    grain (researcher_id, provider_id),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

-- Link via shared NPI in ORCID records that include an NPI reference
WITH orcid_npi_links AS (
    SELECT
        ('x' || substr(md5(COALESCE(o.orcid_id, 'scopus:' || o.scopus_author_id, 'pubmed:' || o.pubmed_author_signature, LOWER(o.full_name || '|' || COALESCE(o.institution, '')))), 1, 16))::bit(64)::bigint AS researcher_id,
        ('x' || substr(md5(COALESCE(p.npi, 'pecos:' || p.pecos_id)), 1, 16))::bit(64)::bigint AS provider_id,
        1.0                                                                      AS confidence,
        'npi_exact'                                                              AS matched_via,
        GREATEST(o.ingested_at, p.ingested_at)                                  AS first_seen_at
    FROM mol_bronze.orcid o
    JOIN hcs_bronze.cms_pecos p ON o.npi = p.npi
    WHERE o.npi IS NOT NULL
      AND p.npi IS NOT NULL
)

SELECT DISTINCT ON (researcher_id, provider_id)
    researcher_id,
    provider_id,
    confidence,
    matched_via,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM orcid_npi_links
WHERE researcher_id IS NOT NULL
  AND provider_id IS NOT NULL
  AND confidence >= 0.85
ORDER BY researcher_id, provider_id, confidence DESC;

-- CREATE INDEX IF NOT EXISTS hcp_silver_res_prov_xwalk_prov_idx ON hcp_silver.researcher_provider_crosswalk (provider_id);
-- Gold consumers: WHERE confidence >= 0.95 per FR-013.
