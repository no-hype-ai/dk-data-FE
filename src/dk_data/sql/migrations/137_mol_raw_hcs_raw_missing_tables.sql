-- Migration 137: Create all missing mol_raw and hcs_raw tables
-- Feature: fix/mol-raw-bindingdb-missing-table
--
-- Root cause: when the codebase was refactored from raw.* → mol_raw.*/hcs_raw.*,
-- the Python source loaders were updated to target the new schema but DDL migrations
-- were never written for the mol_raw/hcs_raw versions of these tables.
-- Additionally, migrations 020-126 were baselined on the cluster (SQL never ran),
-- so any mol_raw CREATE TABLEs in those migrations were skipped.
--
-- All 49 missing tables are created here (32 mol_raw + 17 hcs_raw).
-- DDL derived directly from INSERT column lists in each source loader.

-- ============================================================================
-- mol_raw: envelope-pattern tables (request_id, response_body JSONB, etc.)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_raw.bindingdb (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        TEXT,
    api_version         TEXT,
    request_params      JSONB,
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    response_size_bytes INTEGER,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           TEXT,
    UNIQUE (request_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_bindingdb_processed ON mol_raw.bindingdb (processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_mol_raw_bindingdb_ingested ON mol_raw.bindingdb (ingested_at);

CREATE TABLE IF NOT EXISTS mol_raw.chembl_activities (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT,
    api_version         TEXT,
    request_params      JSONB,
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    source_id           TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_chembl_activities_processed ON mol_raw.chembl_activities (ingested_at);

CREATE TABLE IF NOT EXISTS mol_raw.fda_ndc (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT,
    api_version         TEXT,
    request_params      JSONB,
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    source_id           TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id)
);

CREATE TABLE IF NOT EXISTS mol_raw.fda_rems (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT,
    api_version         TEXT,
    request_params      JSONB,
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    source_id           TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id)
);

CREATE TABLE IF NOT EXISTS mol_raw.pharmgkb (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT,
    api_version         TEXT,
    request_params      JSONB,
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    source_id           TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id)
);

CREATE TABLE IF NOT EXISTS mol_raw.kegg_drug (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_kegg_drug_processed ON mol_raw.kegg_drug (processed_to_bronze);

CREATE TABLE IF NOT EXISTS mol_raw.rxnorm (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id)
);

CREATE TABLE IF NOT EXISTS mol_raw.who_icd (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        TEXT,
    api_version         TEXT,
    request_params      JSONB,
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    source_id           TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_who_icd_processed ON mol_raw.who_icd (processed_to_bronze);

CREATE TABLE IF NOT EXISTS mol_raw.who_inn (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    source_id           TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id)
);

CREATE TABLE IF NOT EXISTS mol_raw.tdc_admet (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    request_params      JSONB,
    api_endpoint        TEXT,
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    source_id           TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tdc_admet_processed ON mol_raw.tdc_admet (processed_to_bronze);

-- mol_raw: minimal envelope (response_body + source_id only)
CREATE TABLE IF NOT EXISTS mol_raw.cms_medicare (
    id            BIGSERIAL PRIMARY KEY,
    response_body JSONB NOT NULL,
    source_id     TEXT,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_raw.nice_hta (
    id            BIGSERIAL PRIMARY KEY,
    response_body JSONB NOT NULL,
    source_id     TEXT,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Loader uses: ON CONFLICT ((response_body->>'Id')) WHERE response_body->>'Id' IS NOT NULL
CREATE UNIQUE INDEX IF NOT EXISTS idx_mol_raw_nice_hta_id
    ON mol_raw.nice_hta ((response_body->>'Id'))
    WHERE response_body->>'Id' IS NOT NULL;

CREATE TABLE IF NOT EXISTS mol_raw.npi_registry (
    id            BIGSERIAL PRIMARY KEY,
    response_body JSONB NOT NULL,
    source_id     TEXT,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Loader uses: ON CONFLICT ((response_body->>'number')) WHERE response_body->>'number' IS NOT NULL
CREATE UNIQUE INDEX IF NOT EXISTS idx_mol_raw_npi_registry_number
    ON mol_raw.npi_registry ((response_body->>'number'))
    WHERE response_body->>'number' IS NOT NULL;

CREATE TABLE IF NOT EXISTS mol_raw.purple_book (
    id            BIGSERIAL PRIMARY KEY,
    response_body JSONB NOT NULL,
    source_id     TEXT,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Loader uses: ON CONFLICT ((response_body->>'application_number')) WHERE ... IS NOT NULL
CREATE UNIQUE INDEX IF NOT EXISTS idx_mol_raw_purple_book_app_number
    ON mol_raw.purple_book ((response_body->>'application_number'))
    WHERE response_body->>'application_number' IS NOT NULL;

CREATE TABLE IF NOT EXISTS mol_raw.reactome (
    id            BIGSERIAL PRIMARY KEY,
    response_body JSONB NOT NULL,
    source_id     TEXT,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Loader uses: ON CONFLICT ((response_body->>'stId')) WHERE response_body->>'stId' IS NOT NULL
CREATE UNIQUE INDEX IF NOT EXISTS idx_mol_raw_reactome_stid
    ON mol_raw.reactome ((response_body->>'stId'))
    WHERE response_body->>'stId' IS NOT NULL;

CREATE TABLE IF NOT EXISTS mol_raw.who_gho (
    id            BIGSERIAL PRIMARY KEY,
    response_body JSONB NOT NULL,
    source_id     TEXT,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Loader uses: ON CONFLICT ((response_body->>'IndicatorCode')) WHERE ... IS NOT NULL
CREATE UNIQUE INDEX IF NOT EXISTS idx_mol_raw_who_gho_indicator_code
    ON mol_raw.who_gho ((response_body->>'IndicatorCode'))
    WHERE response_body->>'IndicatorCode' IS NOT NULL;

-- ============================================================================
-- mol_raw: domain-column tables (specific fields, not envelope)
-- ============================================================================

-- Drop the orphaned raw.cochrane_reviews table (superseded by mol_raw.cochrane_reviews).
-- Created in migration 060; mol_raw version is the canonical target since the
-- codebase migrated from raw.* → mol_raw.*
DROP TABLE IF EXISTS raw.cochrane_reviews;

CREATE TABLE IF NOT EXISTS mol_raw.cochrane_reviews (
    id               BIGSERIAL PRIMARY KEY,
    review_id        TEXT NOT NULL,
    pmid             TEXT,
    title            TEXT,
    authors          JSONB,
    abstract         TEXT,
    publication_date DATE,
    review_type      TEXT,
    interventions    TEXT[],
    conditions       TEXT[],
    conclusions      TEXT,
    doi              TEXT,
    _source_file     TEXT,
    _source_hash     TEXT,
    _loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (review_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_cochrane_doi  ON mol_raw.cochrane_reviews (doi);
CREATE INDEX IF NOT EXISTS idx_mol_raw_cochrane_pmid ON mol_raw.cochrane_reviews (pmid);

CREATE TABLE IF NOT EXISTS mol_raw.ema_regulatory (
    id                 BIGSERIAL PRIMARY KEY,
    document_id        TEXT NOT NULL,
    document_type      TEXT,
    product_name       TEXT,
    active_substance   TEXT,
    therapeutic_area   TEXT,
    decision_date      DATE,
    decision_type      TEXT,
    document_url       TEXT,
    summary            TEXT,
    _source_file       TEXT,
    _source_hash       TEXT,
    _loaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ema_reg_product ON mol_raw.ema_regulatory (product_name);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ema_reg_date ON mol_raw.ema_regulatory (decision_date);

CREATE TABLE IF NOT EXISTS mol_raw.epo_patents (
    id               BIGSERIAL PRIMARY KEY,
    publication_id   TEXT NOT NULL,
    title            TEXT,
    abstract         TEXT,
    applicants       JSONB,
    inventors        JSONB,
    filing_date      DATE,
    publication_date DATE,
    ipc_codes        JSONB,
    family_id        TEXT,
    _source_file     TEXT,
    _source_hash     TEXT,
    _loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (publication_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_epo_family ON mol_raw.epo_patents (family_id);

CREATE TABLE IF NOT EXISTS mol_raw.euipo_designs (
    id                 BIGSERIAL PRIMARY KEY,
    application_number TEXT NOT NULL,
    design_title       TEXT,
    applicant_name     TEXT,
    applicant_country  TEXT,
    representative_name TEXT,
    designer_name      TEXT,
    status             TEXT,
    filing_date        DATE,
    registration_date  DATE,
    expiry_date        DATE,
    publication_date   DATE,
    locarno_classes    JSONB,
    product_indication TEXT,
    image_url          TEXT,
    number_of_designs  INTEGER,
    _source_file       TEXT,
    _source_hash       TEXT,
    _loaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (application_number)
);

CREATE TABLE IF NOT EXISTS mol_raw.euipo_trademarks (
    id                 BIGSERIAL PRIMARY KEY,
    application_number TEXT NOT NULL,
    mark_name          TEXT,
    mark_kind          TEXT,
    mark_feature       TEXT,
    mark_basis         TEXT,
    applicant_name     TEXT,
    applicant_country  TEXT,
    representative_name TEXT,
    status             TEXT,
    filing_date        DATE,
    registration_date  DATE,
    expiry_date        DATE,
    nice_classes       JSONB,
    goods_and_services TEXT,
    image_url          TEXT,
    _source_file       TEXT,
    _source_hash       TEXT,
    _loaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (application_number)
);

CREATE TABLE IF NOT EXISTS mol_raw.hta_decisions (
    id            BIGSERIAL PRIMARY KEY,
    decision_id   TEXT NOT NULL,
    agency        TEXT,
    drug_name     TEXT,
    indication    TEXT,
    decision_type TEXT,
    decision_date DATE,
    document_url  TEXT,
    summary       TEXT,
    _source_file  TEXT,
    _source_hash  TEXT,
    _loaded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (decision_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_hta_drug ON mol_raw.hta_decisions (drug_name);

CREATE TABLE IF NOT EXISTS mol_raw.journal_rss (
    id               BIGSERIAL PRIMARY KEY,
    article_id       TEXT NOT NULL,
    feed_source      TEXT,
    title            TEXT,
    authors          JSONB,
    abstract         TEXT,
    publication_date DATE,
    link             TEXT,
    doi              TEXT,
    categories       JSONB,
    _source_file     TEXT,
    _source_hash     TEXT,
    _loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (article_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_journal_rss_doi ON mol_raw.journal_rss (doi);

CREATE TABLE IF NOT EXISTS mol_raw.medical_news (
    id                BIGSERIAL PRIMARY KEY,
    article_id        TEXT NOT NULL,
    source_name       TEXT,
    title             TEXT,
    summary           TEXT,
    publication_date  DATE,
    url               TEXT,
    drug_mentions     JSONB,
    therapeutic_areas JSONB,
    _source_file      TEXT,
    _source_hash      TEXT,
    _loaded_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (article_id)
);

CREATE TABLE IF NOT EXISTS mol_raw.openalex_ci (
    id                          BIGSERIAL PRIMARY KEY,
    work_id                     TEXT NOT NULL,
    doi                         TEXT,
    title                       TEXT,
    abstract                    TEXT,
    publication_date            DATE,
    cited_by_count              INTEGER,
    concepts                    JSONB,
    authorships                 JSONB,
    primary_location            JSONB,
    open_access                 JSONB,
    pmid                        TEXT,
    pmcid                       TEXT,
    mag_id                      TEXT,
    work_type                   TEXT,
    language                    TEXT,
    volume                      TEXT,
    issue                       TEXT,
    first_page                  TEXT,
    last_page                   TEXT,
    topics                      JSONB,
    keywords                    JSONB,
    mesh_terms                  JSONB,
    cited_by_percentile         JSONB,
    citation_counts_by_year     JSONB,
    grants                      JSONB,
    referenced_works            JSONB,
    related_works               JSONB,
    sustainable_development_goals JSONB,
    best_oa_location            JSONB,
    is_retracted                BOOLEAN,
    is_paratext                 BOOLEAN,
    _source_file                TEXT,
    _source_hash                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (work_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_openalex_ci_doi  ON mol_raw.openalex_ci (doi);
CREATE INDEX IF NOT EXISTS idx_mol_raw_openalex_ci_pmid ON mol_raw.openalex_ci (pmid);

CREATE TABLE IF NOT EXISTS mol_raw.orcid (
    id                   BIGSERIAL PRIMARY KEY,
    orcid_id             TEXT NOT NULL,
    given_names          TEXT,
    family_name          TEXT,
    credit_name          TEXT,
    biography            TEXT,
    keywords             JSONB,
    current_affiliations JSONB,
    works_count          INTEGER,
    external_ids         JSONB,
    raw_response         JSONB,
    fetched_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (orcid_id)
);

CREATE TABLE IF NOT EXISTS mol_raw.pubmed (
    id               BIGSERIAL PRIMARY KEY,
    pmid             TEXT NOT NULL,
    title            TEXT,
    abstract         TEXT,
    authors          JSONB,
    journal          TEXT,
    publication_date DATE,
    mesh_terms       JSONB,
    doi              TEXT,
    publication_types JSONB,
    keywords         JSONB,
    _source_file     TEXT,
    _source_hash     TEXT,
    _loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (pmid)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_pubmed_doi ON mol_raw.pubmed (doi);

CREATE TABLE IF NOT EXISTS mol_raw.sec_edgar (
    id               BIGSERIAL PRIMARY KEY,
    accession_number TEXT NOT NULL,
    company_name     TEXT,
    cik              TEXT,
    filing_type      TEXT,
    filing_date      DATE,
    document_url     TEXT,
    description      TEXT,
    _source_file     TEXT,
    _source_hash     TEXT,
    _loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (accession_number)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_sec_edgar_cik ON mol_raw.sec_edgar (cik);

CREATE TABLE IF NOT EXISTS mol_raw.uspto_ci (
    id            BIGSERIAL PRIMARY KEY,
    patent_id     TEXT NOT NULL,
    title         TEXT,
    abstract      TEXT,
    inventors     JSONB,
    assignees     JSONB,
    filing_date   DATE,
    grant_date    DATE,
    cpc_codes     JSONB,
    claims_count  INTEGER,
    _source_file  TEXT,
    _source_hash  TEXT,
    _loaded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (patent_id)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_uspto_ci_grant ON mol_raw.uspto_ci (grant_date);

CREATE TABLE IF NOT EXISTS mol_raw.uspto_patents (
    id             BIGSERIAL PRIMARY KEY,
    patent_number  TEXT NOT NULL,
    title          TEXT,
    abstract       TEXT,
    inventors      JSONB,
    assignees      JSONB,
    filing_date    DATE,
    grant_date     DATE,
    cpc_codes      JSONB,
    claims_count   INTEGER,
    patent_type    TEXT,
    _source_file   TEXT,
    _source_hash   TEXT,
    _loaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (patent_number)
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_uspto_patents_grant ON mol_raw.uspto_patents (grant_date);

CREATE TABLE IF NOT EXISTS mol_raw.uspto_trademarks (
    id                   BIGSERIAL PRIMARY KEY,
    serial_number        TEXT NOT NULL,
    mark_element         TEXT,
    mark_type            TEXT,
    status               TEXT,
    status_code          TEXT,
    status_date          DATE,
    filing_date          DATE,
    registration_number  TEXT,
    registration_date    DATE,
    nice_classes         JSONB,
    us_classes           JSONB,
    owner_name           TEXT,
    owner_entity_type    TEXT,
    goods_and_services   TEXT,
    description_of_mark  TEXT,
    _source_file         TEXT,
    _source_hash         TEXT,
    _loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (serial_number)
);

CREATE TABLE IF NOT EXISTS mol_raw.trademark_status_history (
    id                   BIGSERIAL PRIMARY KEY,
    trademark_identifier TEXT NOT NULL,
    source               TEXT NOT NULL,
    old_status           TEXT,
    new_status           TEXT,
    changed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tm_status_hist ON mol_raw.trademark_status_history (trademark_identifier, source);

-- ============================================================================
-- hcs_raw: envelope-pattern tables (17 CMS facility/provider sources)
-- DDL matches migration 097_hcs_raw_facility_tables.sql exactly.
-- ON CONFLICT in all loaders: (response_body_hash) WHERE response_body_hash IS NOT NULL
-- Requires: UNIQUE NULLS NOT DISTINCT (response_body_hash)  — NOT UNIQUE (request_id)
-- ============================================================================

CREATE TABLE IF NOT EXISTS hcs_raw.cms_care_compare (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_care_compare',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_care_compare',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_care_compare_ingested ON hcs_raw.cms_care_compare (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_chow (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_chow',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_chow',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_chow_ingested ON hcs_raw.cms_chow (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_ddinter (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_ddinter',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_ddinter',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_ddinter_ingested ON hcs_raw.cms_ddinter (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_dmepos (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_dmepos',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_dmepos',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_dmepos_ingested ON hcs_raw.cms_dmepos (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_formulary (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_formulary',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_formulary',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_formulary_ingested ON hcs_raw.cms_formulary (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hcris (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_hcris',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_hcris',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_hcris_ingested ON hcs_raw.cms_hcris (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospital_affiliation (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_hospital_affiliation',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_hospital_affiliation',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_hospital_affil_ingested ON hcs_raw.cms_hospital_affiliation (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospital_quality (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_hospital_quality',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_hospital_quality',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_hospital_qual_ingested ON hcs_raw.cms_hospital_quality (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_magnet (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_magnet',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_magnet',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_magnet_ingested ON hcs_raw.cms_magnet (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_ndc (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_ndc',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_ndc',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_ndc_ingested ON hcs_raw.cms_ndc (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_nucc (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_nucc',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_nucc',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_nucc_ingested ON hcs_raw.cms_nucc (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_pecos (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_pecos',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_pecos',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_pecos_ingested ON hcs_raw.cms_pecos (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_pos (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_pos',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_pos',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_pos_ingested ON hcs_raw.cms_pos (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_post_acute (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_post_acute',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_post_acute',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_post_acute_ingested ON hcs_raw.cms_post_acute (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_rbcs (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_rbcs',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_rbcs',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_rbcs_ingested ON hcs_raw.cms_rbcs (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_stabilis (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_stabilis',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_stabilis',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_stabilis_ingested ON hcs_raw.cms_stabilis (ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_usp (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_usp',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_usp',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (response_body_hash)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_usp_ingested ON hcs_raw.cms_usp (ingested_at);

DO $$
BEGIN
    RAISE NOTICE 'Migration 137 complete: created 49 missing mol_raw/hcs_raw tables (32 mol_raw + 17 hcs_raw).';
END $$;
