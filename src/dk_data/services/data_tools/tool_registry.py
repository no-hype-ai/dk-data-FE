"""Unified Data Tool Registry — all external data sources in one place.

Extends the original MCP tool registry with:
- supported_query_keys: which input keys each tool accepts
- category: "molecule", "cms_queryable", "cms_bulk_only"
- local_check: gold/silver table + key column for local-first lookup
- external_api_available: False for bulk-only sources

~54 total tools:
- 26 existing molecule/IP tools (from services.pipeline)
- 20 CMS queryable sources (real-time API fallback)
- 8 CMS bulk-only sources (local DB only, no external API)

Note: CMS queryable tools were previously removed from the MCP registry
in 016-cms-puf-datasource-integration. They are re-added here because
upstream agents need on-demand query access when gold views are empty.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .local_checker import LocalCheckConfig


@dataclass
class DataToolDefinition:
    """Enhanced tool definition for the unified data tools gateway."""
    name: str
    description: str
    category: str                      # "molecule", "cms_queryable", "cms_bulk_only"
    supported_query_keys: List[str]    # which keys this tool accepts
    adapter_module: str                # module path for lazy import
    api_base_url: str
    external_api_available: bool = True
    local_check: Optional[LocalCheckConfig] = None
    # Legacy fields carried over from MCP ToolDefinition
    tier: str = "direct_query"
    raw_table: str = ""
    raw_schema: str = "mol_raw"         # "mol_raw", "hcs_raw", "hcp_raw", etc.
    input_schema: Dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "drug_name": {"type": "string", "description": "Drug/molecule name"},
            "npi": {"type": "string", "description": "National Provider Identifier"},
            "ccn": {"type": "string", "description": "CMS Certification Number"},
            "ndc": {"type": "string", "description": "National Drug Code"},
            "state": {"type": "string", "description": "Two-letter state code"},
            "county": {"type": "string", "description": "County name"},
            "hcpcs_code": {"type": "string", "description": "HCPCS procedure code"},
            "molecule_id": {"type": "string", "description": "Internal molecule UUID"},
        },
    })


# =============================================================================
# Molecule / IP tools (26) — migrated from services.pipeline.tool_registry
# =============================================================================

_MOLECULE_TOOLS: Dict[str, DataToolDefinition] = {
    "clinicaltrials-search": DataToolDefinition(
        name="clinicaltrials-search",
        description="Search ClinicalTrials.gov for clinical trials by drug name",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.clinicaltrials",
        api_base_url="https://clinicaltrials.gov/api/v2/studies",
        tier="direct_query",
        raw_table="clinicaltrials",
        raw_schema="mol_raw",
    ),
    "chembl-search": DataToolDefinition(
        name="chembl-search",
        description="Search ChEMBL for molecule bioactivity data",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.chembl",
        api_base_url="https://www.ebi.ac.uk/chembl/api/data/molecule/search",
        tier="direct_query",
        raw_table="chembl",
        raw_schema="mol_raw",
    ),
    "openfda-faers-search": DataToolDefinition(
        name="openfda-faers-search",
        description="Search OpenFDA FAERS for adverse event reports",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.openfda_faers",
        api_base_url="https://api.fda.gov/drug/event.json",
        tier="direct_query",
        raw_table="openfda_faers",
        raw_schema="mol_raw",
    ),
    "openfda-labels-search": DataToolDefinition(
        name="openfda-labels-search",
        description="Search OpenFDA for drug labeling information",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.openfda_labels",
        api_base_url="https://api.fda.gov/drug/label.json",
        tier="direct_query",
        raw_table="openfda_labels",
        raw_schema="mol_raw",
    ),
    "drugbank-search": DataToolDefinition(
        name="drugbank-search",
        description="Search DrugBank for comprehensive drug information",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.drugbank",
        api_base_url="https://go.drugbank.com/services/v1/drugs",
        tier="direct_query",
        raw_table="drugbank",
        raw_schema="mol_raw",
    ),
    "pubchem-search": DataToolDefinition(
        name="pubchem-search",
        description="Search PubChem for chemical compound data",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.pubchem",
        api_base_url="https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name",
        tier="direct_query",
        raw_table="pubchem",
        raw_schema="mol_raw",
    ),
    "openalex-search": DataToolDefinition(
        name="openalex-search",
        description="Search OpenAlex for academic publications",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.openalex",
        api_base_url="https://api.openalex.org/works",
        tier="direct_query",
        raw_table="openalex",
        raw_schema="mol_raw",
    ),
    "uniprot-search": DataToolDefinition(
        name="uniprot-search",
        description="Search UniProt for protein/target information",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.uniprot",
        api_base_url="https://rest.uniprot.org/uniprotkb/search",
        tier="direct_query",
        raw_table="uniprot",
        raw_schema="mol_raw",
    ),
    "pubmed-search": DataToolDefinition(
        name="pubmed-search",
        description="Search PubMed for biomedical literature",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.pubmed",
        api_base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        tier="direct_query",
        raw_table="pubmed",
        raw_schema="mol_raw",
    ),
    "ema-search": DataToolDefinition(
        name="ema-search",
        description="Search EMA for European medicine regulatory decisions",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.ema",
        api_base_url="https://www.ema.europa.eu/en/medicines",
        tier="direct_query",
        raw_table="ema",
        raw_schema="mol_raw",
    ),
    "hta-decisions-search": DataToolDefinition(
        name="hta-decisions-search",
        description="Search HTA decisions (NICE, HAS, IQWiG, CADTH)",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.hta_decisions",
        api_base_url="https://www.nice.org.uk/guidance",
        tier="direct_query",
        raw_table="hta_decisions",
        raw_schema="mol_raw",
    ),
    "cochrane-search": DataToolDefinition(
        name="cochrane-search",
        description="Search Cochrane Library for systematic reviews",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.cochrane",
        api_base_url="https://www.cochranelibrary.com/cdsr/reviews",
        tier="direct_query",
        raw_table="cochrane_reviews",
        raw_schema="mol_raw",
    ),
    "orange-book-search": DataToolDefinition(
        name="orange-book-search",
        description="Search FDA Orange Book for patent and exclusivity data",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.orange_book",
        api_base_url="https://api.fda.gov/drug/drugsfda.json",
        tier="direct_query",
        raw_table="orange_book",
        raw_schema="mol_raw",
    ),
    "uspto-patents-search": DataToolDefinition(
        name="uspto-patents-search",
        description="Search USPTO PatentsView for patent filings",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.uspto_patents",
        api_base_url="https://api.patentsview.org/patents/query",
        tier="direct_query",
        raw_table="uspto_patents",
        raw_schema="mol_raw",
    ),
    "epo-patents-search": DataToolDefinition(
        name="epo-patents-search",
        description="Search EPO Open Patent Services for European patents",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.epo_patents",
        api_base_url="https://ops.epo.org/3.2/rest-services/published-data/search",
        tier="direct_query",
        raw_table="epo_patents",
        raw_schema="mol_raw",
    ),
    "sec-edgar-search": DataToolDefinition(
        name="sec-edgar-search",
        description="Search SEC EDGAR for company financial filings",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.sec_edgar",
        api_base_url="https://efts.sec.gov/LATEST/search-index?q=",
        tier="direct_query",
        raw_table="sec_edgar",
        raw_schema="mol_raw",
    ),
    "who-icd-search": DataToolDefinition(
        name="who-icd-search",
        description="Search WHO ICD-11 coding system",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.who_icd",
        api_base_url="https://id.who.int/icd/release/11/2024-01/mms/search",
        tier="direct_query",
        raw_table="who_icd",
        raw_schema="mol_raw",
    ),
    "pdb-search": DataToolDefinition(
        name="pdb-search",
        description="Search RCSB PDB for protein structures",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.pdb_structures",
        api_base_url="https://search.rcsb.org/rcsbsearch/v2/query",
        tier="direct_query",
        raw_table="pdb_structures",
        raw_schema="mol_raw",
    ),
    "orcid-search": DataToolDefinition(
        name="orcid-search",
        description="Search ORCID for researcher profiles",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.orcid",
        api_base_url="https://pub.orcid.org/v3.0/search/",
        tier="direct_query",
        raw_table="orcid",
        raw_schema="mol_raw",
    ),
    # Tier 2: Fetch + Filter
    "journal-rss-fetch": DataToolDefinition(
        name="journal-rss-fetch",
        description="Fetch and filter journal RSS feeds for drug mentions",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.journal_rss",
        api_base_url="https://feeds.feedburner.com/NatureReviewsDrugDiscovery",
        tier="fetch_filter",
        raw_table="journal_rss",
        raw_schema="mol_raw",
    ),
    "medical-news-fetch": DataToolDefinition(
        name="medical-news-fetch",
        description="Fetch and filter medical news for drug-related articles",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.medical_news",
        api_base_url="https://www.fiercepharma.com/rss/xml",
        tier="fetch_filter",
        raw_table="medical_news",
        raw_schema="mol_raw",
    ),
    "uspto-trademarks-search": DataToolDefinition(
        name="uspto-trademarks-search",
        description="Search USPTO TESS for trademark registrations",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.uspto_trademarks",
        api_base_url="https://tsdr.uspto.gov/",
        tier="fetch_filter",
        raw_table="uspto_trademarks",
        raw_schema="mol_raw",
    ),
    "euipo-trademarks-search": DataToolDefinition(
        name="euipo-trademarks-search",
        description="Search EUIPO for EU trademark registrations",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.euipo_trademarks",
        api_base_url="https://euipo.europa.eu/eSearch/",
        tier="fetch_filter",
        raw_table="euipo_trademarks",
        raw_schema="mol_raw",
    ),
    "euipo-designs-search": DataToolDefinition(
        name="euipo-designs-search",
        description="Search EUIPO for registered community designs",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.euipo_designs",
        api_base_url="https://api.euipo.europa.eu/design-search/designs",
        tier="fetch_filter",
        raw_table="euipo_designs",
        raw_schema="mol_raw",
    ),
    # Tier 3: Supplementary
    "acc-tvc-search": DataToolDefinition(
        name="acc-tvc-search",
        description="Search ACC/TVC cardiac center certifications",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.acc_tvc",
        api_base_url="https://www.acc.org/tools-and-practice-support/accreditation",
        tier="supplementary",
        raw_table="acc_tvc_certification",
        raw_schema="mol_raw",
    ),
    "hrsa-search": DataToolDefinition(
        name="hrsa-search",
        description="Search HRSA health professional shortage areas",
        category="molecule",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.pipeline.adapters.hrsa",
        api_base_url="https://data.hrsa.gov/api/hpsas",
        tier="supplementary",
        raw_table="hrsa_shortage_areas",
        raw_schema="mol_raw",
    ),
}

# =============================================================================
# CMS Queryable tools (20) — have real-time APIs for on-demand queries
# =============================================================================

_CMS_QUERYABLE_TOOLS: Dict[str, DataToolDefinition] = {
    "cms-care-compare": DataToolDefinition(
        name="cms-care-compare",
        description="CMS Care Compare hospital/provider quality ratings",
        category="cms_queryable",
        supported_query_keys=["ccn", "state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_care_compare",
        api_base_url="https://data.cms.gov/provider-data/api/1/datastore/sql",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_facility_360",
            gold_key_column="ccn",
            silver_schema="silver", silver_table="cms_facility_profile",
            silver_key_column="ccn",
        ),
        raw_table="cms_care_compare", raw_schema="hcs_raw",
    ),
    "cms-part-d-prescriber": DataToolDefinition(
        name="cms-part-d-prescriber",
        description="CMS Part D prescriber utilization and cost data",
        category="cms_queryable",
        supported_query_keys=["npi", "state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_part_d_prescriber",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_provider_360",
            gold_key_column="npi",
            silver_schema="silver", silver_table="cms_provider_profile",
            silver_key_column="npi",
        ),
        raw_table="cms_part_d_prescriber", raw_schema="hcs_raw",
    ),
    "cms-physician-puf": DataToolDefinition(
        name="cms-physician-puf",
        description="CMS Physician and Other Practitioners Public Use File",
        category="cms_queryable",
        supported_query_keys=["npi", "state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_physician_puf",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_provider_360",
            gold_key_column="npi",
            silver_schema="silver", silver_table="cms_provider_profile",
            silver_key_column="npi",
        ),
        raw_table="cms_physician_puf", raw_schema="hcs_raw",
    ),
    "cms-open-payments": DataToolDefinition(
        name="cms-open-payments",
        description="CMS Open Payments (physician/industry financial relationships)",
        category="cms_queryable",
        supported_query_keys=["npi", "state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_open_payments",
        api_base_url="https://openpaymentsdata.cms.gov/api/1/datastore/sql",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_provider_360",
            gold_key_column="npi",
            silver_schema="silver", silver_table="cms_provider_profile",
            silver_key_column="npi",
        ),
        raw_table="cms_open_payments", raw_schema="hcs_raw",
    ),
    "cms-pecos": DataToolDefinition(
        name="cms-pecos",
        description="CMS PECOS provider enrollment and certification",
        category="cms_queryable",
        supported_query_keys=["npi", "state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_pecos",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_provider_360",
            gold_key_column="npi",
            silver_schema="silver", silver_table="cms_provider_profile",
            silver_key_column="npi",
        ),
        raw_table="cms_pecos", raw_schema="hcs_raw",
    ),
    "cms-inpatient-puf": DataToolDefinition(
        name="cms-inpatient-puf",
        description="CMS Inpatient Prospective Payment System (IPPS) data",
        category="cms_queryable",
        supported_query_keys=["ccn", "state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_inpatient_puf",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_facility_360",
            gold_key_column="ccn",
            silver_schema="silver", silver_table="cms_facility_profile",
            silver_key_column="ccn",
        ),
        raw_table="cms_inpatient_puf", raw_schema="hcs_raw",
    ),
    "cms-outpatient-puf": DataToolDefinition(
        name="cms-outpatient-puf",
        description="CMS Outpatient Prospective Payment System data",
        category="cms_queryable",
        supported_query_keys=["ccn", "state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_outpatient_puf",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_facility_360",
            gold_key_column="ccn",
            silver_schema="silver", silver_table="cms_facility_profile",
            silver_key_column="ccn",
        ),
        raw_table="cms_outpatient_puf", raw_schema="hcs_raw",
    ),
    "cms-hospital-quality": DataToolDefinition(
        name="cms-hospital-quality",
        description="CMS Hospital Quality Star Ratings and measures",
        category="cms_queryable",
        supported_query_keys=["ccn", "state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_hospital_quality",
        api_base_url="https://data.cms.gov/provider-data/api/1/datastore/sql",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_facility_360",
            gold_key_column="ccn",
            silver_schema="silver", silver_table="cms_facility_profile",
            silver_key_column="ccn",
        ),
        raw_table="cms_hospital_quality", raw_schema="hcs_raw",
    ),
    "cms-hospital-affiliation": DataToolDefinition(
        name="cms-hospital-affiliation",
        description="CMS Hospital Physician Affiliations",
        category="cms_queryable",
        supported_query_keys=["ccn"],
        adapter_module="dk_data.services.data_tools.adapters.cms_hospital_affiliation",
        api_base_url="https://data.cms.gov/provider-data/api/1/datastore/sql",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_hospital_affiliation",
            gold_key_column="ccn",
        ),
        raw_table="cms_hospital_affiliation", raw_schema="hcs_raw",
    ),
    "cms-formulary": DataToolDefinition(
        name="cms-formulary",
        description="CMS Part D Formulary/drug coverage data",
        category="cms_queryable",
        supported_query_keys=["ndc"],
        adapter_module="dk_data.services.data_tools.adapters.cms_formulary",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_formulary",
            gold_key_column="ndc",
        ),
        raw_table="cms_formulary", raw_schema="hcs_raw",
    ),
    "cms-part-d-spending": DataToolDefinition(
        name="cms-part-d-spending",
        description="CMS Part D Drug Spending Dashboard data",
        category="cms_queryable",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.data_tools.adapters.cms_part_d_spending",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_part_d_spending",
            gold_key_column="drug_name",
        ),
        raw_table="cms_part_d_spending", raw_schema="hcs_raw",
    ),
    "cms-part-b-spending": DataToolDefinition(
        name="cms-part-b-spending",
        description="CMS Part B Drug Spending by HCPCS code",
        category="cms_queryable",
        supported_query_keys=["hcpcs_code"],
        adapter_module="dk_data.services.data_tools.adapters.cms_part_b_spending",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_part_b_spending",
            gold_key_column="hcpcs_code",
        ),
        raw_table="cms_part_b_spending", raw_schema="hcs_raw",
    ),
    "cms-ndc": DataToolDefinition(
        name="cms-ndc",
        description="FDA NDC Directory (drug product listings by NDC)",
        category="cms_queryable",
        supported_query_keys=["ndc"],
        adapter_module="dk_data.services.data_tools.adapters.cms_ndc",
        api_base_url="https://api.fda.gov/drug/ndc.json",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_ndc",
            gold_key_column="ndc",
        ),
        raw_table="cms_ndc", raw_schema="hcs_raw",
    ),
    "cms-chow": DataToolDefinition(
        name="cms-chow",
        description="CMS Change of Ownership (CHOW) records",
        category="cms_queryable",
        supported_query_keys=["ccn"],
        adapter_module="dk_data.services.data_tools.adapters.cms_chow",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_chow",
            gold_key_column="ccn",
        ),
        raw_table="cms_chow", raw_schema="hcs_raw",
    ),
    "cms-geographic-variation": DataToolDefinition(
        name="cms-geographic-variation",
        description="CMS Geographic Variation in Medicare spending/utilization",
        category="cms_queryable",
        supported_query_keys=["state", "county"],
        adapter_module="dk_data.services.data_tools.adapters.cms_geographic_variation",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_market_analytics",
            gold_key_column="state",
            silver_schema="silver", silver_table="cms_geographic",
            silver_key_column="state",
        ),
        raw_table="cms_geographic_variation", raw_schema="hcs_raw",
    ),
    "cms-chronic-conditions": DataToolDefinition(
        name="cms-chronic-conditions",
        description="CMS Chronic Conditions prevalence data by geography",
        category="cms_queryable",
        supported_query_keys=["state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_chronic_conditions",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_market_analytics",
            gold_key_column="state",
            silver_schema="silver", silver_table="cms_geographic",
            silver_key_column="state",
        ),
        raw_table="cms_chronic_conditions", raw_schema="hcs_raw",
    ),
    "cms-dmepos": DataToolDefinition(
        name="cms-dmepos",
        description="CMS DMEPOS (Durable Medical Equipment) utilization",
        category="cms_queryable",
        supported_query_keys=["npi", "hcpcs_code"],
        adapter_module="dk_data.services.data_tools.adapters.cms_dmepos",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_dmepos",
            gold_key_column="npi",
        ),
        raw_table="cms_dmepos", raw_schema="hcs_raw",
    ),
    "cms-post-acute": DataToolDefinition(
        name="cms-post-acute",
        description="CMS Post-Acute Care quality and utilization",
        category="cms_queryable",
        supported_query_keys=["ccn"],
        adapter_module="dk_data.services.data_tools.adapters.cms_post_acute",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_post_acute",
            gold_key_column="ccn",
        ),
        raw_table="cms_post_acute", raw_schema="hcs_raw",
    ),
    "cms-rbcs": DataToolDefinition(
        name="cms-rbcs",
        description="CMS RBCS (Restructured BETOS Classification System)",
        category="cms_queryable",
        supported_query_keys=["hcpcs_code"],
        adapter_module="dk_data.services.data_tools.adapters.cms_rbcs",
        api_base_url="https://data.cms.gov/data-api/v1/dataset",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_rbcs",
            gold_key_column="hcpcs_code",
        ),
        raw_table="cms_rbcs", raw_schema="hcs_raw",
    ),
    "cms-ddinter": DataToolDefinition(
        name="cms-ddinter",
        description="DDInter drug-drug interaction database",
        category="cms_queryable",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.data_tools.adapters.cms_ddinter",
        api_base_url="https://ddinter.scbdd.com/api/search",
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_ddinter",
            gold_key_column="drug_name",
        ),
        raw_table="cms_ddinter", raw_schema="hcs_raw",
    ),
}

# =============================================================================
# CMS Bulk-only tools (8) — local DB only, no external API fallback
# =============================================================================

_CMS_BULK_ONLY_TOOLS: Dict[str, DataToolDefinition] = {
    "cms-nppes": DataToolDefinition(
        name="cms-nppes",
        description="NPPES National Provider Identifier registry (bulk-loaded, local query only)",
        category="cms_bulk_only",
        supported_query_keys=["npi", "state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_bulk_stub",
        api_base_url="",
        external_api_available=False,
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_nppes",
            gold_key_column="npi",
            silver_schema="silver", silver_table="cms_provider_profile",
            silver_key_column="npi",
        ),
        raw_table="cms_nppes", raw_schema="hcs_raw",
    ),
    "cms-pos": DataToolDefinition(
        name="cms-pos",
        description="CMS Provider of Services (POS) file (bulk-loaded, local query only)",
        category="cms_bulk_only",
        supported_query_keys=["ccn", "state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_bulk_stub",
        api_base_url="",
        external_api_available=False,
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_pos",
            gold_key_column="ccn",
            silver_schema="silver", silver_table="cms_facility_profile",
            silver_key_column="ccn",
        ),
        raw_table="cms_pos", raw_schema="hcs_raw",
    ),
    "cms-hcris": DataToolDefinition(
        name="cms-hcris",
        description="CMS Hospital Cost Reports (HCRIS) (bulk-loaded, local query only)",
        category="cms_bulk_only",
        supported_query_keys=["ccn"],
        adapter_module="dk_data.services.data_tools.adapters.cms_bulk_stub",
        api_base_url="",
        external_api_available=False,
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_hcris",
            gold_key_column="ccn",
        ),
        raw_table="cms_hcris", raw_schema="hcs_raw",
    ),
    "cms-nucc": DataToolDefinition(
        name="cms-nucc",
        description="NUCC Healthcare Provider Taxonomy Codes (bulk-loaded, local query only)",
        category="cms_bulk_only",
        supported_query_keys=["hcpcs_code"],
        adapter_module="dk_data.services.data_tools.adapters.cms_bulk_stub",
        api_base_url="",
        external_api_available=False,
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_nucc",
            gold_key_column="hcpcs_code",
        ),
        raw_table="cms_nucc", raw_schema="hcs_raw",
    ),
    "cms-magnet": DataToolDefinition(
        name="cms-magnet",
        description="ANCC Magnet-designated hospitals (bulk-loaded, local query only)",
        category="cms_bulk_only",
        supported_query_keys=["ccn", "state"],
        adapter_module="dk_data.services.data_tools.adapters.cms_bulk_stub",
        api_base_url="",
        external_api_available=False,
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_magnet",
            gold_key_column="ccn",
        ),
        raw_table="cms_magnet", raw_schema="hcs_raw",
    ),
    "cms-usp": DataToolDefinition(
        name="cms-usp",
        description="USP Drug Classification (bulk-loaded, local query only)",
        category="cms_bulk_only",
        supported_query_keys=["drug_name", "ndc"],
        adapter_module="dk_data.services.data_tools.adapters.cms_bulk_stub",
        api_base_url="",
        external_api_available=False,
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_usp",
            gold_key_column="drug_name",
        ),
        raw_table="cms_usp", raw_schema="hcs_raw",
    ),
    "cms-stabilis": DataToolDefinition(
        name="cms-stabilis",
        description="Stabilis IV drug compatibility data (bulk-loaded, local query only)",
        category="cms_bulk_only",
        supported_query_keys=["drug_name"],
        adapter_module="dk_data.services.data_tools.adapters.cms_bulk_stub",
        api_base_url="",
        external_api_available=False,
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_stabilis",
            gold_key_column="drug_name",
        ),
        raw_table="cms_stabilis", raw_schema="hcs_raw",
    ),
    "cms-provider-network": DataToolDefinition(
        name="cms-provider-network",
        description="Provider referral network edges (agent-derived, local query only)",
        category="cms_bulk_only",
        supported_query_keys=["npi"],
        adapter_module="dk_data.services.data_tools.adapters.cms_bulk_stub",
        api_base_url="",
        external_api_available=False,
        local_check=LocalCheckConfig(
            gold_schema="gold", gold_table="cms_provider_network",
            gold_key_column="source_npi",
            silver_schema="silver", silver_table="cms_referral_edges",
            silver_key_column="source_npi",
        ),
        raw_table="", raw_schema="",
    ),
}

# =============================================================================
# Combined registry
# =============================================================================

TOOL_REGISTRY: Dict[str, DataToolDefinition] = {
    **_MOLECULE_TOOLS,
    **_CMS_QUERYABLE_TOOLS,
    **_CMS_BULK_ONLY_TOOLS,
}


def get_tool_count() -> int:
    """Return total number of registered tools."""
    return len(TOOL_REGISTRY)


def get_tools_by_category(category: str) -> Dict[str, DataToolDefinition]:
    """Get tools filtered by category."""
    return {k: v for k, v in TOOL_REGISTRY.items() if v.category == category}


def get_tools_by_tier(tier: str) -> Dict[str, DataToolDefinition]:
    """Get tools filtered by tier (legacy compat)."""
    return {k: v for k, v in TOOL_REGISTRY.items() if v.tier == tier}
