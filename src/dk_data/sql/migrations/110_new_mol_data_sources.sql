-- Migration 110: Add mol_silver tables for new data sources
-- Sources: CMS Open Payments, UniProt targets, EuropePMC, NICE HTA, NPI, Medicare, NIH Reporter,
--          Reactome, KEGG, FDA REMS
BEGIN;

-- ══════════════════════════════════════════════════════════════════════════════
-- 1. mol_silver.physician_payments (CMS Open Payments → KOL identification)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_silver.physician_payments (
    payment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    physician_npi VARCHAR(20),
    physician_name VARCHAR(500),
    physician_specialty VARCHAR(200),
    physician_state VARCHAR(5),
    manufacturer_name VARCHAR(500),
    payment_amount NUMERIC(12,2),
    payment_nature VARCHAR(200),  -- e.g. 'Consulting Fee', 'Speaker', 'Food and Beverage'
    payment_date DATE,
    payment_year INTEGER,
    payment_form VARCHAR(100),    -- 'Cash or cash equivalent', 'In-kind'
    associated_drug VARCHAR(500), -- drug name if specified in the payment record
    source VARCHAR(50) DEFAULT 'cms_open_payments',
    source_record_id VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_phys_pay_molecule ON mol_silver.physician_payments(molecule_id);
CREATE INDEX IF NOT EXISTS idx_phys_pay_npi ON mol_silver.physician_payments(physician_npi);
CREATE INDEX IF NOT EXISTS idx_phys_pay_manufacturer ON mol_silver.physician_payments(manufacturer_name);

-- ══════════════════════════════════════════════════════════════════════════════
-- 2. mol_silver.protein_targets (UniProt → mechanism of action)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_silver.protein_targets (
    protein_target_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    uniprot_accession VARCHAR(20) NOT NULL,
    protein_name VARCHAR(500),
    gene_name VARCHAR(100),
    organism VARCHAR(200) DEFAULT 'Homo sapiens',
    protein_function TEXT,
    subcellular_location TEXT,
    pathway_names TEXT[],         -- from UniProt 'pathway' annotations
    pdb_ids TEXT[],               -- cross-references to Protein Data Bank
    reactome_ids TEXT[],          -- cross-references to Reactome
    kegg_ids TEXT[],              -- cross-references to KEGG
    drugbank_ids TEXT[],          -- cross-references to DrugBank
    chembl_ids TEXT[],            -- cross-references to ChEMBL
    tissue_specificity TEXT,
    disease_associations JSONB,   -- from UniProt disease annotations
    source VARCHAR(50) DEFAULT 'uniprot',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(molecule_id, uniprot_accession)
);
CREATE INDEX IF NOT EXISTS idx_prot_tgt_molecule ON mol_silver.protein_targets(molecule_id);
CREATE INDEX IF NOT EXISTS idx_prot_tgt_uniprot ON mol_silver.protein_targets(uniprot_accession);
CREATE INDEX IF NOT EXISTS idx_prot_tgt_gene ON mol_silver.protein_targets(gene_name);

-- ══════════════════════════════════════════════════════════════════════════════
-- 3. mol_silver.hta_decisions (NICE/G-BA/HAS → cost-effectiveness, pricing)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_silver.hta_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    agency VARCHAR(50) NOT NULL,     -- 'NICE', 'G-BA', 'HAS', 'PBAC', 'CADTH'
    guidance_id VARCHAR(50),         -- e.g. 'TA1138'
    title TEXT,
    indication TEXT,
    decision VARCHAR(100),           -- 'Recommended', 'Not recommended', 'Optimised'
    decision_date DATE,
    icer_value VARCHAR(100),         -- e.g. '£30,000-50,000/QALY'
    cost_per_qaly VARCHAR(100),
    annual_treatment_cost VARCHAR(200),
    committee_summary TEXT,
    url TEXT,
    source VARCHAR(50) DEFAULT 'nice',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(molecule_id, agency, guidance_id)
);
CREATE INDEX IF NOT EXISTS idx_hta_molecule ON mol_silver.hta_decisions(molecule_id);
CREATE INDEX IF NOT EXISTS idx_hta_agency ON mol_silver.hta_decisions(agency);

-- ══════════════════════════════════════════════════════════════════════════════
-- 4. mol_silver.physician_profiles (NPI Registry → HCP segmentation)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_silver.physician_profiles (
    profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npi VARCHAR(20) UNIQUE NOT NULL,
    first_name VARCHAR(200),
    last_name VARCHAR(200),
    credential VARCHAR(50),
    gender VARCHAR(10),
    primary_specialty VARCHAR(200),
    secondary_specialty VARCHAR(200),
    practice_state VARCHAR(5),
    practice_city VARCHAR(200),
    practice_zip VARCHAR(20),
    organization_name VARCHAR(500),
    enumeration_date DATE,
    taxonomy_codes TEXT[],
    source VARCHAR(50) DEFAULT 'npi_registry',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_phys_prof_specialty ON mol_silver.physician_profiles(primary_specialty);
CREATE INDEX IF NOT EXISTS idx_phys_prof_state ON mol_silver.physician_profiles(practice_state);

-- ══════════════════════════════════════════════════════════════════════════════
-- 5. mol_silver.drug_spending (CMS Medicare Part B/D → market data)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_silver.drug_spending (
    spending_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    brand_name VARCHAR(200),
    generic_name VARCHAR(200),
    program VARCHAR(20) NOT NULL,    -- 'part_b', 'part_d'
    year INTEGER NOT NULL,
    total_claims INTEGER,
    total_beneficiaries INTEGER,
    total_spending NUMERIC(14,2),
    avg_cost_per_claim NUMERIC(10,2),
    avg_cost_per_day NUMERIC(10,2),
    avg_cost_per_beneficiary NUMERIC(12,2),
    total_supply_days INTEGER,
    source VARCHAR(50) DEFAULT 'cms_medicare',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(molecule_id, program, year)
);
CREATE INDEX IF NOT EXISTS idx_drug_spend_molecule ON mol_silver.drug_spending(molecule_id);

-- ══════════════════════════════════════════════════════════════════════════════
-- 6. mol_silver.research_grants (NIH Reporter → funded research / KOL PIs)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_silver.research_grants (
    grant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    project_number VARCHAR(50),
    project_title TEXT,
    pi_name VARCHAR(500),
    pi_institution VARCHAR(500),
    funding_agency VARCHAR(100),     -- 'NIH/NCI', 'NIH/NIAID', etc.
    award_amount NUMERIC(14,2),
    fiscal_year INTEGER,
    project_start DATE,
    project_end DATE,
    abstract TEXT,
    source VARCHAR(50) DEFAULT 'nih_reporter',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(molecule_id, project_number, fiscal_year)
);
CREATE INDEX IF NOT EXISTS idx_grants_molecule ON mol_silver.research_grants(molecule_id);
CREATE INDEX IF NOT EXISTS idx_grants_pi ON mol_silver.research_grants(pi_name);

-- ══════════════════════════════════════════════════════════════════════════════
-- 7. mol_silver.pathways (Reactome + KEGG → biological pathway context)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_silver.pathways (
    pathway_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    pathway_source VARCHAR(20) NOT NULL,  -- 'reactome', 'kegg'
    pathway_external_id VARCHAR(50),       -- e.g. 'R-HSA-9909620', 'hsa04080'
    pathway_name TEXT NOT NULL,
    pathway_category VARCHAR(200),         -- e.g. 'Signal Transduction', 'Immune System'
    target_gene VARCHAR(100),              -- gene involved in the pathway
    target_uniprot VARCHAR(20),
    species VARCHAR(100) DEFAULT 'Homo sapiens',
    url TEXT,
    source VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(molecule_id, pathway_source, pathway_external_id)
);
CREATE INDEX IF NOT EXISTS idx_pathways_molecule ON mol_silver.pathways(molecule_id);

-- ══════════════════════════════════════════════════════════════════════════════
-- 8. mol_silver.rems_programs (FDA REMS → restricted access)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_silver.rems_programs (
    rems_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    brand_name VARCHAR(200),
    generic_name VARCHAR(200),
    application_number VARCHAR(20),
    rems_type VARCHAR(100),           -- 'Medication Guide', 'ETASU', 'Communication Plan'
    initial_approval_date DATE,
    most_recent_modification DATE,
    rems_status VARCHAR(50),          -- 'Active', 'Released', 'Modified'
    elements TEXT[],                  -- list of REMS elements
    url TEXT,
    source VARCHAR(50) DEFAULT 'fda_rems',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(molecule_id, application_number)
);
CREATE INDEX IF NOT EXISTS idx_rems_molecule ON mol_silver.rems_programs(molecule_id);

-- Grant PostgREST access to all new tables
GRANT SELECT ON mol_silver.physician_payments TO analyst;
GRANT SELECT ON mol_silver.protein_targets TO analyst;
GRANT SELECT ON mol_silver.hta_decisions TO analyst;
GRANT SELECT ON mol_silver.physician_profiles TO analyst;
GRANT SELECT ON mol_silver.drug_spending TO analyst;
GRANT SELECT ON mol_silver.research_grants TO analyst;
GRANT SELECT ON mol_silver.pathways TO analyst;
GRANT SELECT ON mol_silver.rems_programs TO analyst;

COMMIT;
