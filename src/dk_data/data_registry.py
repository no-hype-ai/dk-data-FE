"""
DATA REGISTRY — Single source of truth for ALL dk-data-FE tables.

Schema convention: schema IS the domain prefix. No prefix on table names.
  mol_silver / mol_gold  — molecule data
  ind_silver / ind_gold  — indication/disease data
  hcp_silver / hcp_gold  — HCP/researcher data
  hcs_silver / hcs_gold  — healthcare system (CMS) data
  xenon                  — xenon application data (read-only for dk-data-FE)

To add a new table:
1. Create the SQLMesh model in the appropriate domain schema
2. Add entry to the correct *_TABLES dict below
3. Notify Xenon team to update their local registry
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


# ─── mol_silver (molecule data, entity-linked) ─────────────────────────────

MOL_SILVER_TABLES = {
    'molecules': TableDef(
        name='molecules', schema='mol_silver',
        description='Master molecule entity (canonical identity, InChI key)',
        molecule_id_type='uuid', source='resolution',
        postgrest_path='/molecules',
    ),
    'clinical_trials': TableDef(
        name='clinical_trials', schema='mol_silver',
        description='ClinicalTrials.gov studies linked to molecules',
        molecule_id_type='uuid', source='clinicaltrials_gov',
        postgrest_path='/clinical_trials',
    ),
    'drug_labels': TableDef(
        name='drug_labels', schema='mol_silver',
        description='FDA drug labels from openFDA',
        molecule_id_type='uuid', source='openfda_labels',
        postgrest_path='/drug_labels',
    ),
    'targets': TableDef(
        name='targets', schema='mol_silver',
        description='Drug targets from DrugBank/ChEMBL/UniProt',
        molecule_id_type='uuid', source='drugbank',
        postgrest_path='/targets',
    ),
    'adverse_events': TableDef(
        name='adverse_events', schema='mol_silver',
        description='FAERS adverse event reports',
        molecule_id_type='uuid', source='openfda_faers',
        postgrest_path='/adverse_events',
    ),
    'publications': TableDef(
        name='publications', schema='mol_silver',
        description='OpenAlex/PubMed publications',
        molecule_id_type='uuid', source='openalex',
        postgrest_path='/publications',
    ),
    'financial_data': TableDef(
        name='financial_data', schema='mol_silver',
        description='SEC EDGAR financial filings (10-K, 20-F)',
        molecule_id_type='uuid', source='sec_edgar',
        postgrest_path='/financial_data',
    ),
    'regulatory_decisions': TableDef(
        name='regulatory_decisions', schema='mol_silver',
        description='Regulatory decisions from EMA, NICE HTA, PMDA',
        molecule_id_type='uuid', source='hta_decisions',
        postgrest_path='/regulatory_decisions',
    ),
    'patents': TableDef(
        name='patents', schema='mol_silver',
        description='Drug patents from DrugBank, USPTO, EPO, Orange Book',
        molecule_id_type='uuid', source='drugbank',
        postgrest_path='/patents',
    ),
    'patent_exclusivities': TableDef(
        name='patent_exclusivities', schema='mol_silver',
        description='FDA Orange Book + Purple Book exclusivity',
        molecule_id_type='uuid', source='orange_book',
        postgrest_path='/patent_exclusivities',
    ),
    'dailymed_labels': TableDef(
        name='dailymed_labels', schema='mol_silver',
        description='DailyMed SPL label metadata',
        molecule_id_type='uuid', source='dailymed',
        postgrest_path='/dailymed_labels',
    ),
    'bioactivity': TableDef(
        name='bioactivity', schema='mol_silver',
        description='ChEMBL bioactivity assay data (IC50, Ki, EC50)',
        molecule_id_type='uuid', source='chembl',
        postgrest_path='/bioactivity',
    ),
    'trademarks': TableDef(
        name='trademarks', schema='mol_silver',
        description='Drug trademarks from USPTO and EUIPO',
        molecule_id_type='uuid', source='uspto_trademarks',
        postgrest_path='/trademarks',
    ),
    'news_signals': TableDef(
        name='news_signals', schema='mol_silver',
        description='Medical news and press release signals',
        molecule_id_type='uuid', source='medical_news',
        postgrest_path='/news_signals',
    ),
    'identifier_mappings': TableDef(
        name='identifier_mappings', schema='mol_silver',
        description='Cross-reference identifier mappings',
        molecule_id_type='uuid', source='resolution',
        postgrest_path='/identifier_mappings',
    ),
    'molecule_aliases': TableDef(
        name='molecule_aliases', schema='mol_silver',
        description='Molecule name aliases (brand, generic, synonyms)',
        molecule_id_type='uuid', source='resolution',
        postgrest_path='/molecule_aliases',
    ),
    'molecule_targets': TableDef(
        name='molecule_targets', schema='mol_silver',
        description='Molecule-to-target associations with activity data',
        molecule_id_type='uuid', source='chembl',
        postgrest_path='/molecule_targets',
    ),
    'molecule_publications': TableDef(
        name='molecule_publications', schema='mol_silver',
        description='Molecule-to-publication linking',
        molecule_id_type='uuid', source='openalex',
        postgrest_path='/molecule_publications',
    ),
}

# ─── mol_gold (molecule aggregated) ────────────────────────────────────────

MOL_GOLD_TABLES = {
    'molecule_profile': TableDef(
        name='molecule_profile', schema='mol_gold',
        description='Aggregated molecule profile',
        molecule_id_type='text', source='aggregation',
        postgrest_path='/molecule_profile',
    ),
    'safety_signals': TableDef(
        name='safety_signals', schema='mol_gold',
        description='Aggregated safety signals from FAERS',
        molecule_id_type='text', source='aggregation',
        postgrest_path='/safety_signals',
    ),
    'company_pipeline': TableDef(
        name='company_pipeline', schema='mol_gold',
        description='Company development pipeline programs',
        molecule_id_type='text', source='aggregation',
        postgrest_path='/company_pipeline',
    ),
    'competitive_landscape': TableDef(
        name='competitive_landscape', schema='mol_gold',
        description='Competitive landscape analysis',
        molecule_id_type='text', source='aggregation',
        postgrest_path='/competitive_landscape',
    ),
    'lifecycle_stages': TableDef(
        name='lifecycle_stages', schema='mol_gold',
        description='Molecule lifecycle stage tracking',
        molecule_id_type='text', source='aggregation',
        postgrest_path='/lifecycle_stages',
    ),
    'lifecycle_evidence': TableDef(
        name='lifecycle_evidence', schema='mol_gold',
        description='Consolidated lifecycle evidence',
        molecule_id_type='text', source='aggregation',
        postgrest_path='/lifecycle_evidence',
    ),
    'financial_summary': TableDef(
        name='financial_summary', schema='mol_gold',
        description='Cross-source financial data per molecule/company',
        molecule_id_type='text', source='aggregation',
        postgrest_path='/financial_summary',
    ),
    'regulatory_timeline': TableDef(
        name='regulatory_timeline', schema='mol_gold',
        description='Cross-source regulatory decision history',
        molecule_id_type='text', source='aggregation',
        postgrest_path='/regulatory_timeline',
    ),
    'advocacy_groups': TableDef(
        name='advocacy_groups', schema='mol_gold',
        description='Patient/disease advocacy organizations',
        molecule_id_type='text', source='aggregation',
        postgrest_path='/advocacy_groups',
    ),
    'advocacy_sentiment': TableDef(
        name='advocacy_sentiment', schema='mol_gold',
        description='Advocacy group sentiment analysis',
        molecule_id_type='text', source='aggregation',
        postgrest_path='/advocacy_sentiment',
    ),
}

# ─── ind_silver (indication/disease data) ──────────────────────────────────

IND_SILVER_TABLES = {
    'epidemiology': TableDef(
        name='epidemiology', schema='ind_silver',
        description='Indication-level epidemiology from WHO GHO + ClinicalTrials.gov',
        molecule_id_type='none', source='who_gho',
        postgrest_path='/epidemiology',
    ),
    'icd_codes': TableDef(
        name='icd_codes', schema='ind_silver',
        description='WHO ICD-10 code hierarchy',
        molecule_id_type='none', source='who_icd',
        postgrest_path='/icd_codes',
    ),
    'revenue': TableDef(
        name='revenue', schema='ind_silver',
        description='Per-indication revenue from SEC 10-K/20-F MD&A parsing',
        molecule_id_type='uuid', source='sec_edgar',
        postgrest_path='/revenue',
    ),
}

# ─── hcp_silver (HCP/researcher data) ─────────────────────────────────────

HCP_SILVER_TABLES = {
    'researchers': TableDef(
        name='researchers', schema='hcp_silver',
        description='Researcher profiles from ORCID',
        molecule_id_type='none', source='orcid',
        postgrest_path='/researchers',
    ),
    'facilities': TableDef(
        name='facilities', schema='hcp_silver',
        description='Healthcare facility data from CMS',
        molecule_id_type='none', source='cms_hospital_info',
        postgrest_path='/facilities',
    ),
}

# ─── hcp_gold (HCP/researcher aggregated) ─────────────────────────────────

HCP_GOLD_TABLES = {
    'kol_profiles': TableDef(
        name='kol_profiles', schema='hcp_gold',
        description='Key Opinion Leader profiles with influence scoring',
        molecule_id_type='none', source='aggregation',
        postgrest_path='/kol_profiles',
    ),
    'kol_drug_associations': TableDef(
        name='kol_drug_associations', schema='hcp_gold',
        description='KOL-to-drug association data',
        molecule_id_type='text', source='aggregation',
        postgrest_path='/kol_drug_associations',
    ),
    'kol_network': TableDef(
        name='kol_network', schema='hcp_gold',
        description='KOL collaboration network',
        molecule_id_type='none', source='aggregation',
        postgrest_path='/kol_network',
    ),
}

# ─── hcs_gold (healthcare system / CMS data) ──────────────────────────────

HCS_GOLD_TABLES = {
    'cms_drug_market_profile': TableDef(
        name='cms_drug_market_profile', schema='hcs_gold',
        description='NDC-level Part B/D spending, formulary, tier',
        molecule_id_type='none', source='cms',
        postgrest_path='/cms_drug_market_profile',
    ),
    'cms_provider_360': TableDef(
        name='cms_provider_360', schema='hcs_gold',
        description='Provider profiles: prescribing, procedures, specialty',
        molecule_id_type='none', source='cms',
        postgrest_path='/cms_provider_360',
    ),
    'cms_market_analytics': TableDef(
        name='cms_market_analytics', schema='hcs_gold',
        description='Geographic market: state/county conditions, spending',
        molecule_id_type='none', source='cms',
        postgrest_path='/cms_market_analytics',
    ),
    'cms_provider_network': TableDef(
        name='cms_provider_network', schema='hcs_gold',
        description='Provider referral network: NPI-to-NPI',
        molecule_id_type='none', source='cms',
        postgrest_path='/cms_provider_network',
    ),
    'cms_facility_360': TableDef(
        name='cms_facility_360', schema='hcs_gold',
        description='Facility profiles: beds, quality, ownership',
        molecule_id_type='none', source='cms',
        postgrest_path='/cms_facility_360',
    ),
}


def get_all_tables():
    """Return all registered tables as a flat dict."""
    return {
        **MOL_SILVER_TABLES, **MOL_GOLD_TABLES,
        **IND_SILVER_TABLES, **HCP_SILVER_TABLES,
        **HCP_GOLD_TABLES, **HCS_GOLD_TABLES,
    }


def get_postgrest_schema(table_name: str) -> Optional[str]:
    """Get the schema for a table name (for PostgREST Accept-Profile header)."""
    for t in get_all_tables().values():
        if t.name == table_name:
            return t.schema
    return None
