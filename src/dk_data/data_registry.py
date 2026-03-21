"""
DATA REGISTRY — Single source of truth for ALL dk-data-FE molecule tables.

RULES:
- All molecule-related tables use mol_silver.* or mol_gold.* schemas
- Bronze tables use mol_bronze.* schema
- Raw tables use mol_raw.* schema
- Non-molecule tables (CMS, healthcare, scoring) use their own schemas
- External consumers (Xenon) mirror this registry locally

To add a new table:
1. Create the table in the appropriate schema
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
    molecule_id_type: str   # 'uuid' (FK to mol_silver.molecules) or 'text'
    source: str             # Primary data source (e.g., 'clinicaltrials_gov')
    postgrest_path: str     # PostgREST path segment (e.g., '/clinical_trials')


# ─── mol_silver (normalized, entity-linked) ────────────────────────────────

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
        description='Drug targets from DrugBank/ChEMBL',
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
    'kol_candidates': TableDef(
        name='kol_candidates',
        schema='mol_silver',
        description='Key Opinion Leader candidates from publications',
        molecule_id_type='uuid',
        source='openalex',
        postgrest_path='/kol_candidates',
    ),
    'financial_filings': TableDef(
        name='financial_filings',
        schema='mol_silver',
        description='SEC EDGAR financial filings (10-K, 20-F)',
        molecule_id_type='uuid',
        source='sec_edgar',
        postgrest_path='/financial_filings',
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
        description='Per-indication revenue from SEC 10-K/20-F MD&A parsing',
        molecule_id_type='uuid',
        source='sec_edgar',
        postgrest_path='/indication_revenue',
    ),
    'dailymed_labels': TableDef(
        name='dailymed_labels',
        schema='mol_silver',
        description='DailyMed SPL label metadata (setid links to drug_labels.spl_set_id)',
        molecule_id_type='uuid',
        source='dailymed',
        postgrest_path='/dailymed_labels',
    ),
}

# ─── mol_gold (aggregated, enriched) ───────────────────────────────────────

MOL_GOLD_TABLES = {
    'molecule_profiles': TableDef(
        name='molecule_profiles',
        schema='mol_gold',
        description='Aggregated molecule profile (identity, approval, company)',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/molecule_profiles',
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
    'trial_publication_features': TableDef(
        name='trial_publication_features',
        schema='mol_gold',
        description='Trial-publication feature matrix for evidence scoring',
        molecule_id_type='text',
        source='aggregation',
        postgrest_path='/trial_publication_features',
    ),
}

# ─── Deprecated table names (DO NOT USE) ───────────────────────────────────

DEPRECATED_TABLES = [
    'silver.clinical_trials',        # → mol_silver.clinical_trials
    'silver.adverse_events',         # → mol_silver.adverse_events
    'silver.drug_labels',            # → mol_silver.drug_labels
    'silver.molecules',              # → mol_silver.molecules
    'silver.targets',                # → mol_silver.targets
    'silver.molecule_publications',  # → mol_silver.publications
    'silver.kol_candidates',         # → mol_silver.kol_candidates
    'gold.molecule_profile',         # → mol_gold.molecule_profiles (plural)
    'gold.competitive_landscape',    # → mol_gold.competitive_landscape
    'gold.lifecycle_stages',         # → mol_gold.lifecycle_stages
    'gold.safety_signals',           # → mol_gold.safety_signals
    'gold.trial_outcomes',           # DOES NOT EXIST — removed
    'gold.advocacy_groups',          # DOES NOT EXIST — removed
    'gold.kol_profiles',             # → mol_silver.kol_candidates
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
