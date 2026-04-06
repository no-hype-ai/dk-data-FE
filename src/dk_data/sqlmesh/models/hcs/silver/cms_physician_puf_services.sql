-- SQLMesh Model: Silver CMS Physician PUF by Provider and Service
-- NPI-by-HCPCS utilization data with provider identity and molecule linkage.
-- Grain: (npi, hcpcs_code, place_of_service, _source_year)
--
-- Linkage strategy:
--   Provider: NPI → hcs_bronze.cms_nppes (most recent year, DISTINCT ON prevents fan-out)
--   Drug:     hcpcs_code → mol_silver.hcpcs_molecule_bridge (when hcpcs_drug_ind = 'Y')
--             confidence-ranked; LIMIT 1 prevents fan-out

MODEL (
    name hcs_silver.cms_physician_puf_services,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (npi, hcpcs_code, _source_year))
    ),
    grain (npi, hcpcs_code, place_of_service, _source_year)
);

SELECT DISTINCT ON (b.npi, b.hcpcs_code, b.place_of_service, b._source_year)
    gen_random_uuid()                                       AS id,
    b.npi,
    b.hcpcs_code,
    b.hcpcs_description,
    b.hcpcs_drug_ind,
    b.place_of_service,
    b.line_srvc_cnt,
    b.bene_unique_cnt,
    b.bene_day_srvc_cnt,
    b.average_submitted_chrg_amt,
    b.average_medicare_allowed_amt,
    b.average_medicare_payment_amt,
    b.average_medicare_stnd_amt,
    b._source_year,
    b._source_hash,
    b._source_file,

    -- Provider identity from NPPES (most recent year)
    COALESCE(n.provider_organization_name,
             n.provider_last_name || ', ' || n.provider_first_name) AS provider_name,
    n.entity_type_code                                              AS provider_entity_type,
    n.provider_credential_text                                      AS provider_credentials,
    n.healthcare_provider_taxonomy_code_1                           AS provider_specialty,
    n.healthcare_provider_taxonomy_code_2                           AS provider_specialty_2,
    n.provider_business_practice_location_address_city_name         AS provider_city,
    n.provider_business_practice_location_address_state_name        AS provider_state,
    n.provider_business_practice_location_address_postal_code       AS provider_zip,
    n.provider_business_practice_location_address_telephone_number  AS provider_phone,
    n.npi_deactivation_date,
    n.npi_reactivation_date,

    -- Molecule linkage for drug HCPCS codes
    hb.molecule_id,
    hb.confidence                                           AS molecule_link_confidence,

    'cms_physician_puf_services'                            AS source,
    b._loaded_at                                            AS source_updated_at,
    NOW()                                                   AS created_at

FROM hcs_bronze.cms_physician_puf_services b

-- Provider identity: join cms_nppes on npi; grain (npi, _source_year) → DISTINCT ON dedups
LEFT JOIN hcs_bronze.cms_nppes n
       ON b.npi = n.npi

-- Molecule linkage: only for drug-flagged HCPCS codes
LEFT JOIN LATERAL (
    SELECT hb2.molecule_id, hb2.confidence
    FROM mol_silver.hcpcs_molecule_bridge hb2
    WHERE b.hcpcs_drug_ind = 'Y'
      AND LOWER(hb2.hcpcs_code) = LOWER(b.hcpcs_code)
    ORDER BY hb2.confidence DESC
    LIMIT 1
) hb ON TRUE

WHERE b.npi IS NOT NULL
  AND b.hcpcs_code IS NOT NULL
ORDER BY b.npi, b.hcpcs_code, b.place_of_service, b._source_year,
         n._source_year DESC NULLS LAST
