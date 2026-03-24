-- Migration 126: mol_raw + mol_bronze tables for Python-only sources
-- These sources existed in the old raw.*/bronze.* schemas (dropped in migration 121).
-- Re-creates them under mol_raw.*/mol_bronze.* and registers in ops.sync_schedules.
-- Sources: bindingdb, who_inn, rxnorm, tdc_admet, pharmgkb, kegg_drug, websearch
BEGIN;

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw tables
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS mol_raw.bindingdb (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name           TEXT,
    molecule_id         UUID,
    request_url         TEXT,
    request_params      JSONB,
    response_status     INTEGER NOT NULL,
    response_body       JSONB,
    response_hash       TEXT,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    request_timestamp   TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bindingdb_raw_drug    ON mol_raw.bindingdb(drug_name);
CREATE INDEX IF NOT EXISTS idx_bindingdb_raw_ts      ON mol_raw.bindingdb(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_bindingdb_raw_flag    ON mol_raw.bindingdb(processed_to_bronze) WHERE processed_to_bronze = FALSE;

CREATE TABLE IF NOT EXISTS mol_raw.who_inn (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name           TEXT,
    molecule_id         UUID,
    request_url         TEXT,
    request_params      JSONB,
    response_status     INTEGER NOT NULL,
    response_body       JSONB,
    response_hash       TEXT,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    request_timestamp   TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_who_inn_raw_drug  ON mol_raw.who_inn(drug_name);
CREATE INDEX IF NOT EXISTS idx_who_inn_raw_ts    ON mol_raw.who_inn(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_who_inn_raw_flag  ON mol_raw.who_inn(processed_to_bronze) WHERE processed_to_bronze = FALSE;

CREATE TABLE IF NOT EXISTS mol_raw.rxnorm (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name           TEXT,
    molecule_id         UUID,
    request_url         TEXT,
    request_params      JSONB,
    response_status     INTEGER NOT NULL,
    response_body       JSONB,
    response_hash       TEXT,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    request_timestamp   TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rxnorm_raw_drug  ON mol_raw.rxnorm(drug_name);
CREATE INDEX IF NOT EXISTS idx_rxnorm_raw_ts    ON mol_raw.rxnorm(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_rxnorm_raw_flag  ON mol_raw.rxnorm(processed_to_bronze) WHERE processed_to_bronze = FALSE;

CREATE TABLE IF NOT EXISTS mol_raw.tdc_admet (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name           TEXT,
    molecule_id         UUID,
    request_url         TEXT,
    request_params      JSONB,
    response_status     INTEGER NOT NULL,
    response_body       JSONB,
    response_hash       TEXT,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    request_timestamp   TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tdc_admet_raw_drug  ON mol_raw.tdc_admet(drug_name);
CREATE INDEX IF NOT EXISTS idx_tdc_admet_raw_ts    ON mol_raw.tdc_admet(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_tdc_admet_raw_flag  ON mol_raw.tdc_admet(processed_to_bronze) WHERE processed_to_bronze = FALSE;

CREATE TABLE IF NOT EXISTS mol_raw.pharmgkb (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name           TEXT,
    molecule_id         UUID,
    request_url         TEXT,
    request_params      JSONB,
    response_status     INTEGER NOT NULL,
    response_body       JSONB,
    response_hash       TEXT,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    request_timestamp   TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pharmgkb_raw_drug  ON mol_raw.pharmgkb(drug_name);
CREATE INDEX IF NOT EXISTS idx_pharmgkb_raw_ts    ON mol_raw.pharmgkb(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_pharmgkb_raw_flag  ON mol_raw.pharmgkb(processed_to_bronze) WHERE processed_to_bronze = FALSE;

CREATE TABLE IF NOT EXISTS mol_raw.kegg_drug (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name           TEXT,
    molecule_id         UUID,
    request_url         TEXT,
    request_params      JSONB,
    response_status     INTEGER NOT NULL,
    response_body       JSONB,
    response_hash       TEXT,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    request_timestamp   TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kegg_drug_raw_drug  ON mol_raw.kegg_drug(drug_name);
CREATE INDEX IF NOT EXISTS idx_kegg_drug_raw_ts    ON mol_raw.kegg_drug(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_kegg_drug_raw_flag  ON mol_raw.kegg_drug(processed_to_bronze) WHERE processed_to_bronze = FALSE;

CREATE TABLE IF NOT EXISTS mol_raw.websearch (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name           TEXT,
    molecule_id         UUID,
    request_url         TEXT,
    request_params      JSONB,
    response_status     INTEGER NOT NULL,
    response_body       JSONB,
    response_hash       TEXT,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    request_timestamp   TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_websearch_raw_drug  ON mol_raw.websearch(drug_name);
CREATE INDEX IF NOT EXISTS idx_websearch_raw_ts    ON mol_raw.websearch(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_websearch_raw_flag  ON mol_raw.websearch(processed_to_bronze) WHERE processed_to_bronze = FALSE;

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_bronze tables
-- ══════════════════════════════════════════════════════════════════════════════

-- BindingDB Bronze — binding affinity data per ligand-target pair
-- Note: mol_bronze.bindingdb may already exist if SQLMesh was previously run.
-- The SQLMesh model (bronze/bindingdb.sql) manages this table; migration
-- ensures it exists with all required columns for the new array-unnesting model.
CREATE TABLE IF NOT EXISTS mol_bronze.bindingdb (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id              UUID REFERENCES mol_raw.bindingdb(id),
    bindingdb_id        TEXT NOT NULL,
    ligand_name         TEXT,
    smiles              TEXT,
    inchi               TEXT,
    inchi_key           TEXT,
    target_name         TEXT,
    target_source       TEXT,
    target_source_id    TEXT,
    target_organism     TEXT,
    ki_nm               NUMERIC,
    kd_nm               NUMERIC,
    ic50_nm             NUMERIC,
    ec50_nm             NUMERIC,
    activity_type       TEXT,
    activity_value      NUMERIC,
    activity_unit       TEXT,
    pmid                TEXT,
    doi                 TEXT,
    patent_id           TEXT,
    processed_to_silver BOOLEAN DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    source              TEXT DEFAULT 'bindingdb',
    source_updated_at   TIMESTAMPTZ,
    UNIQUE(bindingdb_id)
);
-- Indexes only if SQLMesh has not already created mol_bronze.bindingdb as a view
DO $$ BEGIN
    IF (SELECT relkind FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
        WHERE n.nspname='mol_bronze' AND c.relname='bindingdb') = 'r' THEN
        CREATE INDEX IF NOT EXISTS idx_bindingdb_bro_id     ON mol_bronze.bindingdb(bindingdb_id);
        CREATE INDEX IF NOT EXISTS idx_bindingdb_bro_inchi  ON mol_bronze.bindingdb(inchi_key);
        CREATE INDEX IF NOT EXISTS idx_bindingdb_bro_target ON mol_bronze.bindingdb(target_name);
        CREATE INDEX IF NOT EXISTS idx_bindingdb_bro_flag   ON mol_bronze.bindingdb(processed_to_silver) WHERE processed_to_silver = FALSE;
    END IF;
END $$;

-- WHO INN Bronze — international nonproprietary names
CREATE TABLE IF NOT EXISTS mol_bronze.who_inn (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id              UUID REFERENCES mol_raw.who_inn(id),
    inn_name            TEXT NOT NULL,
    inn_latin           TEXT,
    inn_list_number     INTEGER,
    inn_year            INTEGER,
    cas_number          TEXT,
    molecular_formula   TEXT,
    smiles              TEXT,
    inchi_key           TEXT,
    inn_stem            TEXT,
    stem_definition     TEXT,
    research_codes      JSONB,
    synonyms            JSONB,
    status              TEXT,
    processed_to_silver BOOLEAN DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    source              TEXT DEFAULT 'who_inn',
    source_updated_at   TIMESTAMPTZ,
    UNIQUE(inn_name)
);
DO $$ BEGIN
    IF (SELECT relkind FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
        WHERE n.nspname='mol_bronze' AND c.relname='who_inn') = 'r' THEN
        CREATE INDEX IF NOT EXISTS idx_who_inn_bro_name  ON mol_bronze.who_inn(inn_name);
        CREATE INDEX IF NOT EXISTS idx_who_inn_bro_inchi ON mol_bronze.who_inn(inchi_key);
        CREATE INDEX IF NOT EXISTS idx_who_inn_bro_stem  ON mol_bronze.who_inn(inn_stem);
        CREATE INDEX IF NOT EXISTS idx_who_inn_bro_codes ON mol_bronze.who_inn USING GIN(research_codes);
        CREATE INDEX IF NOT EXISTS idx_who_inn_bro_flag  ON mol_bronze.who_inn(processed_to_silver) WHERE processed_to_silver = FALSE;
    END IF;
END $$;

-- RxNorm Bronze — FDA drug nomenclature concepts
CREATE TABLE IF NOT EXISTS mol_bronze.rxnorm_concepts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id              UUID REFERENCES mol_raw.rxnorm(id),
    rxcui               TEXT NOT NULL,
    name                TEXT,
    tty                 TEXT,   -- term type: IN, BN, SCD, etc.
    synonym             TEXT,
    suppress            TEXT,
    ingredients         JSONB,
    brand_names         JSONB,
    ndc_codes           JSONB,
    atc_codes           JSONB,
    drug_classes        JSONB,
    processed_to_silver BOOLEAN DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    source              TEXT DEFAULT 'rxnorm',
    source_updated_at   TIMESTAMPTZ,
    UNIQUE(rxcui)
);
DO $$ BEGIN
    IF (SELECT relkind FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
        WHERE n.nspname='mol_bronze' AND c.relname='rxnorm_concepts') = 'r' THEN
        CREATE INDEX IF NOT EXISTS idx_rxnorm_bro_rxcui ON mol_bronze.rxnorm_concepts(rxcui);
        CREATE INDEX IF NOT EXISTS idx_rxnorm_bro_name  ON mol_bronze.rxnorm_concepts(name);
        CREATE INDEX IF NOT EXISTS idx_rxnorm_bro_flag  ON mol_bronze.rxnorm_concepts(processed_to_silver) WHERE processed_to_silver = FALSE;
    END IF;
END $$;

-- TDC ADMET Bronze — ADMET property predictions
CREATE TABLE IF NOT EXISTS mol_bronze.tdc_admet (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id                UUID REFERENCES mol_raw.tdc_admet(id),
    compound_id           TEXT NOT NULL,
    smiles                TEXT,
    inchi_key             TEXT,
    dataset_name          TEXT NOT NULL,
    dataset_type          TEXT,
    property_name         TEXT NOT NULL,
    property_value        NUMERIC,
    property_category     TEXT,
    processed_to_silver   BOOLEAN DEFAULT FALSE,
    ingested_at           TIMESTAMPTZ DEFAULT NOW(),
    source                TEXT DEFAULT 'tdc_admet',
    source_updated_at     TIMESTAMPTZ
);
DO $$ BEGIN
    IF (SELECT relkind FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
        WHERE n.nspname='mol_bronze' AND c.relname='tdc_admet') = 'r' THEN
        CREATE INDEX IF NOT EXISTS idx_tdc_bro_compound ON mol_bronze.tdc_admet(compound_id);
        CREATE INDEX IF NOT EXISTS idx_tdc_bro_inchi    ON mol_bronze.tdc_admet(inchi_key);
        CREATE INDEX IF NOT EXISTS idx_tdc_bro_dataset  ON mol_bronze.tdc_admet(dataset_name);
        CREATE INDEX IF NOT EXISTS idx_tdc_bro_flag     ON mol_bronze.tdc_admet(processed_to_silver) WHERE processed_to_silver = FALSE;
    END IF;
END $$;

-- PharmGKB Bronze — pharmacogenomics annotations
CREATE TABLE IF NOT EXISTS mol_bronze.pharmgkb (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id                  UUID REFERENCES mol_raw.pharmgkb(id),
    pharmgkb_id             TEXT NOT NULL,
    name                    TEXT,
    entity_type             TEXT,
    drugbank_id             TEXT,
    chembl_id               TEXT,
    rxnorm_id               TEXT,
    pubchem_cid             BIGINT,
    cas_number              TEXT,
    drug_type               TEXT,
    smiles                  TEXT,
    inchi_key               TEXT,
    clinical_annotations    JSONB,
    dosing_guidelines       JSONB,
    drug_labels             JSONB,
    variant_annotations     JSONB,
    pathways                JSONB,
    processed_to_silver     BOOLEAN DEFAULT FALSE,
    ingested_at             TIMESTAMPTZ DEFAULT NOW(),
    source                  TEXT DEFAULT 'pharmgkb',
    source_updated_at       TIMESTAMPTZ,
    UNIQUE(pharmgkb_id)
);
DO $$ BEGIN
    IF (SELECT relkind FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
        WHERE n.nspname='mol_bronze' AND c.relname='pharmgkb') = 'r' THEN
        CREATE INDEX IF NOT EXISTS idx_pharmgkb_bro_id     ON mol_bronze.pharmgkb(pharmgkb_id);
        CREATE INDEX IF NOT EXISTS idx_pharmgkb_bro_name   ON mol_bronze.pharmgkb(name);
        CREATE INDEX IF NOT EXISTS idx_pharmgkb_bro_chembl ON mol_bronze.pharmgkb(chembl_id);
        CREATE INDEX IF NOT EXISTS idx_pharmgkb_bro_inchi  ON mol_bronze.pharmgkb(inchi_key);
        CREATE INDEX IF NOT EXISTS idx_pharmgkb_bro_flag   ON mol_bronze.pharmgkb(processed_to_silver) WHERE processed_to_silver = FALSE;
    END IF;
END $$;

-- KEGG Drug Bronze — KEGG drug entries with targets and pathways
CREATE TABLE IF NOT EXISTS mol_bronze.kegg_drug (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id              UUID REFERENCES mol_raw.kegg_drug(id),
    kegg_id             TEXT NOT NULL,
    name                TEXT,
    formula             TEXT,
    exact_mass          NUMERIC,
    smiles              TEXT,
    inchi               TEXT,
    inchi_key           TEXT,
    drug_class          JSONB,
    atc_codes           JSONB,
    therapeutic_target  TEXT,
    targets             JSONB,
    pathways            JSONB,
    enzymes             JSONB,
    drugbank_id         TEXT,
    pubchem_sid         BIGINT,
    chembl_id           TEXT,
    cas_number          TEXT,
    research_codes      JSONB,
    synonyms            JSONB,
    processed_to_silver BOOLEAN DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    source              TEXT DEFAULT 'kegg_drug',
    source_updated_at   TIMESTAMPTZ,
    UNIQUE(kegg_id)
);
DO $$ BEGIN
    IF (SELECT relkind FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
        WHERE n.nspname='mol_bronze' AND c.relname='kegg_drug') = 'r' THEN
        CREATE INDEX IF NOT EXISTS idx_kegg_bro_id      ON mol_bronze.kegg_drug(kegg_id);
        CREATE INDEX IF NOT EXISTS idx_kegg_bro_name    ON mol_bronze.kegg_drug(name);
        CREATE INDEX IF NOT EXISTS idx_kegg_bro_inchi   ON mol_bronze.kegg_drug(inchi_key);
        CREATE INDEX IF NOT EXISTS idx_kegg_bro_drugbank ON mol_bronze.kegg_drug(drugbank_id);
        CREATE INDEX IF NOT EXISTS idx_kegg_bro_flag    ON mol_bronze.kegg_drug(processed_to_silver) WHERE processed_to_silver = FALSE;
    END IF;
END $$;

-- WebSearch Bronze — web/news search results
CREATE TABLE IF NOT EXISTS mol_bronze.websearch_results (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id              UUID REFERENCES mol_raw.websearch(id),
    search_query        TEXT NOT NULL,
    search_engine       TEXT NOT NULL,
    search_type         TEXT,
    result_url          TEXT NOT NULL,
    result_title        TEXT,
    result_snippet      TEXT,
    result_rank         INTEGER,
    result_domain       TEXT,
    publication_date    DATE,
    authors             JSONB,
    source_name         TEXT,
    relevance_score     NUMERIC,
    processed_to_silver BOOLEAN DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    source              TEXT DEFAULT 'websearch',
    source_updated_at   TIMESTAMPTZ
);
DO $$ BEGIN
    IF (SELECT relkind FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
        WHERE n.nspname='mol_bronze' AND c.relname='websearch_results') = 'r' THEN
        CREATE INDEX IF NOT EXISTS idx_websearch_bro_query ON mol_bronze.websearch_results(search_query);
        CREATE INDEX IF NOT EXISTS idx_websearch_bro_url   ON mol_bronze.websearch_results(result_url);
        CREATE INDEX IF NOT EXISTS idx_websearch_bro_date  ON mol_bronze.websearch_results(publication_date);
        CREATE INDEX IF NOT EXISTS idx_websearch_bro_flag  ON mol_bronze.websearch_results(processed_to_silver) WHERE processed_to_silver = FALSE;
    END IF;
END $$;

-- ══════════════════════════════════════════════════════════════════════════════
-- Register in ops.sync_schedules
-- ══════════════════════════════════════════════════════════════════════════════

INSERT INTO ops.sync_schedules (source, tier, cron_expression, priority, enabled, options)
VALUES
    ('bindingdb', 'weekly', '0 3 * * 0', 'low', true,
     '{"source_name":"BindingDB","api_type":"rest","target_table":"mol_raw.bindingdb","supports_per_molecule":true}'::jsonb),
    ('who_inn', 'weekly', '0 3 * * 1', 'low', true,
     '{"source_name":"WHO INN","api_type":"rest","target_table":"mol_raw.who_inn","supports_per_molecule":true}'::jsonb),
    ('rxnorm', 'weekly', '0 3 * * 2', 'low', true,
     '{"source_name":"RxNorm","api_type":"rest","target_table":"mol_raw.rxnorm","supports_per_molecule":true}'::jsonb),
    ('tdc_admet', 'monthly', '0 3 1 * *', 'low', true,
     '{"source_name":"TDC ADMET","api_type":"rest","target_table":"mol_raw.tdc_admet","supports_per_molecule":true}'::jsonb),
    ('pharmgkb', 'weekly', '0 3 * * 3', 'low', true,
     '{"source_name":"PharmGKB","api_type":"rest","target_table":"mol_raw.pharmgkb","supports_per_molecule":true}'::jsonb),
    ('kegg_drug', 'weekly', '0 3 * * 4', 'low', true,
     '{"source_name":"KEGG Drug","api_type":"rest","target_table":"mol_raw.kegg_drug","supports_per_molecule":true}'::jsonb),
    ('websearch', 'daily', '0 6 * * *', 'low', true,
     '{"source_name":"Web Search","api_type":"rest","target_table":"mol_raw.websearch","supports_per_molecule":true}'::jsonb)
ON CONFLICT (source) DO UPDATE
    SET tier            = EXCLUDED.tier,
        cron_expression = EXCLUDED.cron_expression,
        priority        = EXCLUDED.priority,
        enabled         = EXCLUDED.enabled,
        options         = EXCLUDED.options;

-- ══════════════════════════════════════════════════════════════════════════════
-- Grants
-- ══════════════════════════════════════════════════════════════════════════════

GRANT SELECT ON mol_raw.bindingdb         TO analyst;
GRANT SELECT ON mol_raw.who_inn           TO analyst;
GRANT SELECT ON mol_raw.rxnorm            TO analyst;
GRANT SELECT ON mol_raw.tdc_admet         TO analyst;
GRANT SELECT ON mol_raw.pharmgkb          TO analyst;
GRANT SELECT ON mol_raw.kegg_drug         TO analyst;
GRANT SELECT ON mol_raw.websearch         TO analyst;

GRANT SELECT ON mol_bronze.bindingdb          TO analyst;
GRANT SELECT ON mol_bronze.who_inn            TO analyst;
GRANT SELECT ON mol_bronze.rxnorm_concepts    TO analyst;
GRANT SELECT ON mol_bronze.tdc_admet          TO analyst;
GRANT SELECT ON mol_bronze.pharmgkb           TO analyst;
GRANT SELECT ON mol_bronze.kegg_drug          TO analyst;
GRANT SELECT ON mol_bronze.websearch_results  TO analyst;

COMMIT;
