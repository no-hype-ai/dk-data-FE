"""
DATA REGISTRY — Single source of truth for ALL dk-data-FE molecule tables.

RULES:
- All molecule-related tables use mol_silver.* or mol_gold.* schemas
- Bronze tables use mol_bronze.* schema
- Raw tables use mol_raw.* schema
- Non-molecule tables (CMS, healthcare, scoring) use their own schemas
- External consumers (Xenon) mirror this registry locally

SQLMesh physical_schema_mapping ensures both naming styles work:
  silver.X → mol_silver.X, gold.X → mol_gold.X
PostgREST exposes the mol_silver/mol_gold physical schemas.

To add a new table:
1. Create the SQLMesh model in the appropriate schema
2. Add entry to MOL_SILVER_TABLES, MOL_GOLD_TABLES, etc.
3. Run entity linking to populate
4. Notify Xenon team to update their local registry
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TableDef:
    """Definition of a dk-data-FE table."""
    name: str               # Table name (e.g., 'clinical_trials')
    schema: str             # Schema (e.g., 'mol_silver')
    description: str        # Human-readable description
    molecule_id_type: str   # 'uuid' (FK to mol_silver.molecules), 'text', or 'none'
    source: str             # Primary data source (e.g., 'clinicaltrials_gov')
    postgrest_path: str     # PostgREST path segment (e.g., '/clinical_trials')


# ─── mol_silver (normalized, entity-linked) ────────────────────────────────
# Source of truth: sqlmesh/models/molecules/silver/*.sql

MOL_SILVER_TABLES = {
    'molecules': TableDef(
        name='molecules',
        schema='mol_silver',
        description='Master molecule entity (canonical identity, InChI key, cross-references)',
        molecule_id_type='uuid',
        source='resolution',
        postgrest_path='/molecules',
    ),
    'clinical_trials': TableDef(
        name='clinical_trials',
        schema='mol_silver',
        description='ClinicalTrials.gov studies linked to molecules',
        molecule_id_type='uuid',
        source='clinicaltrials_gov',
        postgrest_path='/clinical_trials',
    ),
    'drug_labels': TableDef(
        name='drug_labels',
        schema='mol_silver',
        description='FDA drug labels from openFDA',
        molecule_id_type='uuid',
        source='openfda_labels',
        postgrest_path='/drug_labels',
    ),
    'targets': TableDef(
        name='targets',
        schema='mol_silver',
        description='Drug targets from DrugBank/ChEMBL/UniProt',
        molecule_id_type='uuid',
        source='drugbank',
        postgrest_path='/targets',
    ),
    'adverse_events': TableDef(
        name='adverse_events',
        schema='mol_silver',
        description='FAERS adverse event reports',
        molecule_id_type='uuid',
        source='openfda_faers',
        postgrest_path='/adverse_events',
    ),
    'publications': TableDef(
        name='publications',
        schema='mol_silver',
        description='OpenAlex/PubMed publications linked to molecules',
        molecule_id_type='uuid',
        source='openalex',
        postgrest_path='/publications',
    ),
    'financial_data': TableDef(
        name='financial_data',
        schema='mol_silver',
        description='SEC EDGAR financial filings (10-K, 20-F)',
        molecule_id_type='uuid',
        source='sec_edgar',
        postgrest_path='/financial_data',
    ),
    'regulatory_decisions': TableDef(
        name='regulatory_decisions',
        schema='mol_silver',
        description='Regulatory decisions from EMA, NICE HTA, PMDA etc.',
        molecule_id_type='uuid',
        source='hta_decisions',
        postgrest_path='/regulatory_decisions',
    ),
    'patents': TableDef(
        name='patents',
        schema='mol_silver',
        description='Drug patents from DrugBank, USPTO, EPO, Orange Book',
        molecule_id_type='uuid',
        source='drugbank',
        postgrest_path='/patents',
    ),
    'patent_exclusivities': TableDef(
        name='patent_exclusivities',
        schema='mol_silver',
        description='FDA Orange Book (NDA patents) + Purple Book (BLA BPCIA exclusivity)',
        molecule_id_type='uuid',
        source='orange_book',
        postgrest_path='/patent_exclusivities',
    ),
    'indication_epidemiology': TableDef(
        name='indication_epidemiology',
        schema='mol_silver',
        description='Indication-level epidemiology from WHO GHO + ClinicalTrials.gov',
        molecule_id_type='none',  # Keyed by icd10_code, not molecule_id
        source='who_gho',
        postgrest_path='/indication_epidemiology',
    ),
    'indication_revenue': TableDef(
        name='indication_revenue',
        schema='mol_silver',
        description='Per-indication revenue from SEC 10-K/20-F MD&A parsing (raw)',
        molecule_id_type='uuid',
        source='sec_edgar',
        postgrest_path='/indication_revenue',
    ),
    'indication_revenue_summary': TableDef(
        name='indication_revenue_summary',
        schema='mol_gold',
        description='Per-indication revenue summary with trend, CAGR, confidence (gold aggregate)',
        molecule_id_type='text',
        source='sec_edgar',
        postgrest_path='/indication_revenue_summary',
    ),
    'dailymed_labels': TableDef(
        name='dailymed_labels',
        schema='mol_silver',
        description='DailyMed SPL label metadata (setid links to drug_labels.spl_set_id)',
        molecule_id_type='uuid',
        source='dailymed',
        postgrest_path='/dailymed_labels',
    ),
    'bioactivity': TableDef(
        name='bioactivity',
        schema='mol_silver',
        description='ChEMBL bioactivity assay data (IC50, Ki, EC50)',
        molecule_id_type='uuid',
        source='chembl',
        postgrest_path='/bioactivity',
    ),
    'trademarks': TableDef(
        name='trademarks',
        schema='mol_silver',
        description='Drug trademarks from USPTO and EUIPO',
        molecule_id_type='uuid',
        source='uspto_trademarks',
        postgrest_path='/trademarks',
    ),
    'icd_codes': TableDef(
        name='icd_codes',
        schema='mol_silver',
        description='WHO ICD-10 code hierarchy',
        molecule_id_type='none',
        source='who_icd',
        postgrest_path='/icd_codes',
    ),
    'news_signals': TableDef(
        name='news_signals',
        schema='mol_silver',
        description='Medical news and press release signals',
        molecule_id_type='uuid',
        source='medical_news',
        postgrest_path='/news_signals',
    ),
    'researchers': TableDef(
        name='researchers',
        schema='mol_silver',
        description='Researcher profiles from ORCID and publication data',
        molecule_id_type='none',
        source='orcid',
        postgrest_path='/researchers',
    ),
    # ── Junction tables (not directly queried via PostgREST, but exist) ──
    'identifier_mappings': TableDef(
        name='identifier_mappings',
        schema='mol_silver',
        description='Cross-reference identifier mappings (ChEMBL, DrugBank, PubChem, etc.)',
        molecule_id_type='uuid',
        source='resolution',
        postgrest_path='/identifier_mappings',
    ),
    'molecule_aliases': TableDef(
        name='molecule_aliases',
        schema='mol_silver',
        description='Molecule name aliases (brand, generic, synonyms)',
        molecule_id_type='uuid',
        source='resolution',
        postgrest_path='/molecule_aliases',
    ),
    'molecule_targets': TableDef(
        name='molecule_targets',
        schema='mol_silver',
        description='Molecule-to-target associations with activity data',
        molecule_id_type='uuid',
        source='chembl',
        postgrest_path='/molecule_targets',
    ),
    'molecule_publications': TableDef(
        name='molecule_publications',
        schema='mol_silver',
        description='Molecule-to-publication linking with relevance scores',
        molecule_id_type='uuid',
        source='openalex',
        postgrest_path='/molecule_publications',
    ),
    'healthcare_facilities': TableDef(
        name='healthcare_facilities',
        schema='mol_silver',
        description='Healthcare facility data from CMS',
        molecule_id_type='none',
        source='cms_hospital_info',
        postgrest_path='/healthcare_facilities',
    ),
}

# ─── mol_gold (aggregated, enriched) ───────────────────────────────────────
# Source of truth: sqlmesh/models/molecules/gold/*.sql

MOL_GOLD_TABLES = {
    'molecule_profile': TableDef(
        name='molecule_profile',
        schema='mol_gold',
        description='Aggregated molecule profile (identity, approval, company)',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/molecule_profile',
    ),
    'safety_signals': TableDef(
        name='safety_signals',
        schema='mol_gold',
        description='Aggregated safety signals from FAERS',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/safety_signals',
    ),
    'company_pipeline': TableDef(
        name='company_pipeline',
        schema='mol_gold',
        description='Company development pipeline programs',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/company_pipeline',
    ),
    'competitive_landscape': TableDef(
        name='competitive_landscape',
        schema='mol_gold',
        description='Competitive landscape analysis',
        molecule_id_type='text',  # uses molecule_ids UUID[] array
        source='aggregation',
        postgrest_path='/competitive_landscape',
    ),
    'lifecycle_stages': TableDef(
        name='lifecycle_stages',
        schema='mol_gold',
        description='Molecule lifecycle stage tracking',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/lifecycle_stages',
    ),
    'lifecycle_evidence': TableDef(
        name='lifecycle_evidence',
        schema='mol_gold',
        description='Consolidated evidence for lifecycle stage validation',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/lifecycle_evidence',
    ),
    'financial_summary': TableDef(
        name='financial_summary',
        schema='mol_gold',
        description='Cross-source financial data per molecule/company',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/financial_summary',
    ),
    'regulatory_timeline': TableDef(
        name='regulatory_timeline',
        schema='mol_gold',
        description='Cross-source regulatory decision history per molecule',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/regulatory_timeline',
    ),
    'kol_profiles': TableDef(
        name='kol_profiles',
        schema='mol_gold',
        description='Key Opinion Leader profiles with influence scoring',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/kol_profiles',
    ),
    'kol_drug_associations': TableDef(
        name='kol_drug_associations',
        schema='mol_gold',
        description='KOL-to-drug association data',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/kol_drug_associations',
    ),
    'kol_network': TableDef(
        name='kol_network',
        schema='mol_gold',
        description='KOL collaboration network',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/kol_network',
    ),
    'trial_outcomes': TableDef(
        name='trial_outcomes',
        schema='mol_gold',
        description='Combined trial outcomes from registry and publication evidence',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/trial_outcomes',
    ),
    'advocacy_groups': TableDef(
        name='advocacy_groups',
        schema='mol_gold',
        description='Patient/disease advocacy organizations from news signals',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/advocacy_groups',
    ),
    'advocacy_sentiment': TableDef(
        name='advocacy_sentiment',
        schema='mol_gold',
        description='Advocacy group sentiment analysis',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/advocacy_sentiment',
    ),
}

# ─── Deprecated table names (DO NOT USE) ───────────────────────────────────

DEPRECATED_TABLES = [
    'silver.clinical_trials',        # → mol_silver.clinical_trials
    'silver.adverse_events',         # → mol_silver.adverse_events
    'silver.drug_labels',            # → mol_silver.drug_labels
    'silver.molecules',              # → mol_silver.molecules
    'silver.targets',                # → mol_silver.targets
    'silver.molecule_publications',  # → mol_silver.molecule_publications
    'silver.kol_candidates',         # REMOVED — use mol_gold.kol_profiles
    'silver.financial_filings',      # RENAMED → mol_silver.financial_data
    'gold.molecule_profile',         # → mol_gold.molecule_profile (same name, mol_ prefix)
    'gold.competitive_landscape',    # → mol_gold.competitive_landscape
    'gold.lifecycle_stages',         # → mol_gold.lifecycle_stages
    'gold.safety_signals',           # → mol_gold.safety_signals
    'gold.molecule_profiles',        # WRONG — actual table is mol_gold.molecule_profile (singular)
]


def get_all_tables():
    """Return all registered tables as a flat dict."""
    return {**MOL_SILVER_TABLES, **MOL_GOLD_TABLES}


def get_postgrest_schema(table_name: str) -> Optional[str]:
    """Get the schema for a table name (for PostgREST Accept-Profile header)."""
    all_tables = get_all_tables()
    for t in all_tables.values():
        if t.name == table_name:
            return t.schema
    return None
