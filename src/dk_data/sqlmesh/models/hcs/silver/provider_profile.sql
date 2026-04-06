-- SQLMesh Model: Silver HCS Provider Profile
-- NPI-centric consolidated provider view — entity linking equivalent for providers.
-- Analogous to mol_silver.molecules: one canonical row per provider per year.
--
-- Entity linking key: NPI (National Provider Identifier)
-- Source precedence: NPPES (1) > Physician PUF (2) > specialty-specific tables (3)
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_silver.provider_profile,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (npi, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (npi, _source_year))
    ),
    grain (npi, _source_year)
);

-- Source 1: NPPES — authoritative identity registry (entity type 1 = individual, 2 = org)
WITH nppes AS (
    SELECT
        npi,
        _source_year,
        entity_type_code,
        provider_last_name,
        provider_first_name,
        provider_organization_name,
        provider_credential_text,
        provider_first_line_business_mailing_address     AS mailing_address_1,
        provider_second_line_business_mailing_address    AS mailing_address_2,
        provider_business_mailing_address_city_name      AS mailing_city,
        provider_business_mailing_address_state_name     AS mailing_state,
        provider_business_mailing_address_postal_code    AS mailing_zip,
        provider_business_mailing_address_telephone_number AS mailing_phone,
        provider_first_line_business_practice_location_address  AS practice_address_1,
        provider_second_line_business_practice_location_address AS practice_address_2,
        provider_business_practice_location_address_city_name   AS practice_city,
        provider_business_practice_location_address_state_name  AS practice_state,
        provider_business_practice_location_address_postal_code AS practice_zip,
        provider_business_practice_location_address_telephone_number AS phone,
        provider_business_practice_location_address_fax_number AS fax,
        provider_business_practice_location_address_country_code AS country_code,
        healthcare_provider_taxonomy_code_1             AS taxonomy_code_1,
        healthcare_provider_taxonomy_code_2             AS taxonomy_code_2,
        npi_deactivation_date,
        npi_reactivation_date,
        1 AS source_precedence
    FROM hcs_bronze.cms_nppes
    WHERE npi IS NOT NULL
),

-- Source 2: Physician PUF — Medicare utilization and billing summary
physician_puf AS (
    SELECT
        npi,
        _source_year,
        nppes_provider_last_org_name,
        nppes_provider_first_name,
        nppes_provider_mi,
        nppes_credentials,
        nppes_provider_gender,
        nppes_entity_code,
        nppes_provider_street1,
        nppes_provider_street2,
        nppes_provider_city,
        nppes_provider_state,
        nppes_provider_state_fips,
        nppes_provider_zip,
        nppes_provider_ruca,
        nppes_provider_country,
        provider_type,
        medicare_participation_indicator,
        number_of_hcpcs,
        total_services,
        total_unique_benes,
        total_submitted_chrg_amt,
        total_medicare_allowed_amt,
        total_medicare_payment_amt,
        total_medicare_stnd_amt
    FROM hcs_bronze.cms_physician_puf
    WHERE npi IS NOT NULL
),

-- Source 3: DME PUF — Durable Medical Equipment billing (avg per-claim amounts × claim counts)
dme_agg AS (
    SELECT
        npi,
        _source_year,
        SUM(tot_suplr_clms * avg_suplr_sbmtd_chrg)     AS dme_total_chrg_amt,
        SUM(tot_suplr_clms * avg_suplr_mdcr_pymt_amt)  AS dme_total_payment_amt,
        COUNT(DISTINCT hcpcs_cd)                        AS dme_hcpcs_count
    FROM hcs_bronze.cms_dme_puf
    WHERE npi IS NOT NULL
    GROUP BY npi, _source_year
),

-- Source 4: Mental Health PUF — Behavioral health services
mh_agg AS (
    SELECT
        npi,
        _source_year,
        SUM(tot_srvcs)                  AS mh_total_services,
        SUM(tot_benes)                  AS mh_total_benes,
        SUM(avg_mdcr_pymt_amt)          AS mh_total_payment_amt,
        COUNT(DISTINCT hcpcs_cd)        AS mh_hcpcs_count
    FROM hcs_bronze.cms_mental_health_puf
    WHERE npi IS NOT NULL
    GROUP BY npi, _source_year
),

-- Source 5: Telehealth PUF — Telehealth service delivery (NPI × HCPCS grain → aggregate per NPI)
telehealth AS (
    SELECT
        npi,
        _source_year,
        SUM(tot_srvcs)                  AS telehealth_services,
        SUM(tot_benes)                  AS telehealth_benes,
        SUM(avg_mdcr_pymt_amt)          AS total_telehealth_payment
    FROM hcs_bronze.cms_telehealth_puf
    WHERE npi IS NOT NULL
    GROUP BY npi, _source_year
),

-- Source 6: Referring Providers — referral network activity (rndrng_npi = rendering provider)
-- Aggregates: how many unique referring partners, total referred services/benes/payments
referring AS (
    SELECT
        rndrng_npi                      AS npi,
        _source_year,
        COUNT(DISTINCT rfrd_npi)        AS referral_partner_count,
        SUM(tot_srvcs)                  AS referral_total_srvcs,
        SUM(tot_benes)                  AS referral_total_benes,
        SUM(tot_mdcr_alowd_amt)         AS referral_total_alowd_amt,
        SUM(tot_mdcr_pymt_amt)          AS referral_total_pymt_amt
    FROM hcs_bronze.cms_referring_providers
    WHERE rndrng_npi IS NOT NULL
    GROUP BY rndrng_npi, _source_year
),

-- Source 7: Ordering Providers — ordering activity (rndrng_npi = ordering/rendering provider)
ordering AS (
    SELECT
        rndrng_npi                      AS npi,
        _source_year,
        COUNT(DISTINCT rfrd_npi)        AS ordering_partner_count,
        SUM(tot_srvcs)                  AS ordering_total_srvcs,
        SUM(tot_benes)                  AS ordering_total_benes,
        SUM(tot_mdcr_alowd_amt)         AS ordering_total_alowd_amt,
        SUM(tot_mdcr_pymt_amt)          AS ordering_total_pymt_amt
    FROM hcs_bronze.cms_ordering_providers
    WHERE rndrng_npi IS NOT NULL
    GROUP BY rndrng_npi, _source_year
),

-- Canonical NPI set from all sources
-- Note: Hospice PUF uses CCN (provider_id), not NPI — hospice joins via facility_profile
all_npis AS (
    SELECT npi, _source_year FROM nppes
    UNION
    SELECT npi, _source_year FROM physician_puf
    UNION
    SELECT npi, _source_year FROM dme_agg
    UNION
    SELECT npi, _source_year FROM mh_agg
    UNION
    SELECT npi, _source_year FROM telehealth
    UNION
    SELECT npi, _source_year FROM referring
    UNION
    SELECT npi, _source_year FROM ordering
),

-- Determine provider type: individual vs. organization
provider_type_resolved AS (
    SELECT
        a.npi,
        a._source_year,
        CASE
            WHEN n.entity_type_code = '1' THEN 'individual'
            WHEN n.entity_type_code = '2' THEN 'organization'
            ELSE 'individual'
        END AS provider_entity_type,
        -- Canonical name: NPPES org name for orgs, last+first for individuals
        CASE
            WHEN n.entity_type_code = '2' THEN n.provider_organization_name
            WHEN n.entity_type_code = '1' THEN
                TRIM(COALESCE(n.provider_last_name, '') || ' ' || COALESCE(n.provider_first_name, ''))
            ELSE COALESCE(
                n.provider_organization_name,
                p.nppes_provider_last_org_name
            )
        END AS canonical_name,
        -- Location: prefer practice address, fall back to mailing
        COALESCE(n.practice_address_1, p.nppes_provider_street1)            AS address_line_1,
        COALESCE(n.practice_address_2, p.nppes_provider_street2)            AS address_line_2,
        COALESCE(n.practice_city, n.mailing_city, p.nppes_provider_city)    AS city,
        COALESCE(n.practice_state, n.mailing_state, p.nppes_provider_state) AS state,
        COALESCE(n.practice_zip, n.mailing_zip, p.nppes_provider_zip)       AS zip_code,
        COALESCE(p.nppes_provider_state_fips)                               AS state_fips,
        COALESCE(p.nppes_provider_ruca)                                     AS ruca,
        COALESCE(p.nppes_provider_country, n.country_code)                  AS country,
        n.phone,
        n.fax,
        -- Credential/name detail
        COALESCE(n.provider_credential_text, p.nppes_credentials)           AS credentials,
        p.nppes_provider_mi                                                 AS middle_initial,
        p.nppes_provider_gender                                             AS gender,
        -- Taxonomy
        n.taxonomy_code_1,
        n.taxonomy_code_2,
        -- Provider specialty (from physician PUF if available)
        p.provider_type                  AS specialty,
        p.medicare_participation_indicator,
        -- Deactivation status
        n.npi_deactivation_date,
        n.npi_reactivation_date,
        CASE WHEN n.npi_deactivation_date IS NOT NULL
              AND (n.npi_reactivation_date IS NULL OR n.npi_reactivation_date < NOW())
             THEN TRUE ELSE FALSE END    AS is_deactivated
    FROM all_npis a
    LEFT JOIN nppes n         ON a.npi = n.npi AND a._source_year = n._source_year
    LEFT JOIN physician_puf p ON a.npi = p.npi AND a._source_year = p._source_year
)

SELECT
    gen_random_uuid()                   AS id,
    pt.npi,
    pt._source_year,
    pt.provider_entity_type,
    pt.canonical_name,
    pt.address_line_1,
    pt.address_line_2,
    pt.city,
    pt.state,
    pt.zip_code,
    pt.state_fips,
    pt.ruca,
    pt.country,
    pt.phone,
    pt.fax,
    pt.credentials,
    pt.middle_initial,
    pt.gender,
    pt.taxonomy_code_1,
    pt.taxonomy_code_2,
    pt.specialty,
    pt.medicare_participation_indicator,
    pt.is_deactivated,
    pt.npi_deactivation_date,
    pt.npi_reactivation_date,
    -- Medicare utilization (from Physician PUF)
    p.number_of_hcpcs,
    p.total_services,
    p.total_unique_benes,
    p.total_submitted_chrg_amt,
    p.total_medicare_allowed_amt,
    p.total_medicare_payment_amt,
    p.total_medicare_stnd_amt,
    -- DME billing
    d.dme_total_chrg_amt,
    d.dme_total_payment_amt,
    d.dme_hcpcs_count,
    -- Mental health services
    mh.mh_total_services,
    mh.mh_total_benes,
    mh.mh_total_payment_amt,
    mh.mh_hcpcs_count,
    -- Telehealth delivery
    t.telehealth_services,
    t.telehealth_benes,
    t.total_telehealth_payment,
    -- Referral network
    r.referral_partner_count,
    r.referral_total_srvcs,
    r.referral_total_benes,
    r.referral_total_alowd_amt,
    r.referral_total_pymt_amt,
    -- Ordering activity
    o.ordering_partner_count,
    o.ordering_total_srvcs,
    o.ordering_total_benes,
    o.ordering_total_alowd_amt,
    o.ordering_total_pymt_amt,
    -- Data quality
    CASE
        WHEN p.npi IS NOT NULL AND pt.taxonomy_code_1 IS NOT NULL THEN 1.0
        WHEN p.npi IS NOT NULL OR pt.taxonomy_code_1 IS NOT NULL THEN 0.8
        ELSE 0.5
    END AS data_completeness_score,
    -- Data sources present for this provider
    ARRAY_REMOVE(ARRAY[
        CASE WHEN pt.taxonomy_code_1 IS NOT NULL THEN 'nppes' END,
        CASE WHEN p.npi IS NOT NULL  THEN 'physician_puf' END,
        CASE WHEN d.npi IS NOT NULL  THEN 'dme_puf' END,
        CASE WHEN mh.npi IS NOT NULL THEN 'mental_health_puf' END,
        CASE WHEN t.npi IS NOT NULL  THEN 'telehealth_puf' END,
        CASE WHEN r.npi IS NOT NULL  THEN 'referring_providers' END,
        CASE WHEN o.npi IS NOT NULL  THEN 'ordering_providers' END
    ], NULL)                            AS data_sources,
    NOW()                               AS created_at,
    NOW()                               AS updated_at
FROM provider_type_resolved pt
LEFT JOIN physician_puf p ON pt.npi = p.npi AND pt._source_year = p._source_year
LEFT JOIN dme_agg d       ON pt.npi = d.npi AND pt._source_year = d._source_year
LEFT JOIN mh_agg mh       ON pt.npi = mh.npi AND pt._source_year = mh._source_year
LEFT JOIN telehealth t    ON pt.npi = t.npi AND pt._source_year = t._source_year
LEFT JOIN referring r     ON pt.npi = r.npi AND pt._source_year = r._source_year
LEFT JOIN ordering o      ON pt.npi = o.npi AND pt._source_year = o._source_year
WHERE pt.canonical_name IS NOT NULL
  AND LENGTH(TRIM(pt.canonical_name)) > 0;
