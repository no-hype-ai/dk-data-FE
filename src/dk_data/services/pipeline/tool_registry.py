"""MCP Tool Registry — maps tool names to definitions and adapters.

Feature: 015-assessment-dashboard-integration
Task: T062

All 25 MCP tools organized by tier:
- Tier 1 (19 tools): Direct drug-name query against external APIs
- Tier 2 (4 tools): Fetch + filter (RSS, news, trademarks)
- Tier 3 (2 tools): Supplementary context (ACC, HRSA)

Note: CMS tools (cms-inpatient, cms-hospital-info, cms-cost-reports) removed
in 016-cms-puf-datasource-integration — CMS data now served via PostgREST gold views.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ToolDefinition:
    """Definition of an MCP tool."""
    name: str
    description: str
    tier: str  # "direct_query", "fetch_filter", "supplementary"
    raw_table: str
    raw_schema: str  # "mol_raw" or "raw"
    adapter_module: str  # Module path for lazy import
    api_base_url: str
    input_schema: Dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "drug_name": {"type": "string", "description": "Drug/molecule name to search"},
            "molecule_id": {"type": "string", "description": "Optional molecule UUID"},
        },
        "required": ["drug_name"],
    })


# ============================================================================
# Tier 1: Direct Query Tools (19)
# ============================================================================

TOOL_REGISTRY: Dict[str, ToolDefinition] = {
    # --- mol_raw sources (molecule-specific) ---
    "clinicaltrials-search": ToolDefinition(
        name="clinicaltrials-search",
        description="Search ClinicalTrials.gov for clinical trials by drug name",
        tier="direct_query",
        raw_table="clinicaltrials",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.pipeline.adapters.clinicaltrials",
        api_base_url="https://clinicaltrials.gov/api/v2/studies",
    ),
    "chembl-search": ToolDefinition(
        name="chembl-search",
        description="Search ChEMBL for molecule bioactivity data",
        tier="direct_query",
        raw_table="chembl",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.pipeline.adapters.chembl",
        api_base_url="https://www.ebi.ac.uk/chembl/api/data/molecule/search",
    ),
    "openfda-faers-search": ToolDefinition(
        name="openfda-faers-search",
        description="Search OpenFDA FAERS for adverse event reports",
        tier="direct_query",
        raw_table="openfda_faers",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.pipeline.adapters.openfda_faers",
        api_base_url="https://api.fda.gov/drug/event.json",
    ),
    "openfda-labels-search": ToolDefinition(
        name="openfda-labels-search",
        description="Search OpenFDA for drug labeling information",
        tier="direct_query",
        raw_table="openfda_labels",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.pipeline.adapters.openfda_labels",
        api_base_url="https://api.fda.gov/drug/label.json",
    ),
    "drugbank-search": ToolDefinition(
        name="drugbank-search",
        description="Search DrugBank for comprehensive drug information",
        tier="direct_query",
        raw_table="drugbank",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.pipeline.adapters.drugbank",
        api_base_url="https://go.drugbank.com/services/v1/drugs",
    ),
    "pubchem-search": ToolDefinition(
        name="pubchem-search",
        description="Search PubChem for chemical compound data",
        tier="direct_query",
        raw_table="pubchem",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.pipeline.adapters.pubchem",
        api_base_url="https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name",
    ),
    "openalex-search": ToolDefinition(
        name="openalex-search",
        description="Search OpenAlex for academic publications",
        tier="direct_query",
        raw_table="openalex",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.pipeline.adapters.openalex",
        api_base_url="https://api.openalex.org/works",
    ),
    "uniprot-search": ToolDefinition(
        name="uniprot-search",
        description="Search UniProt for protein/target information",
        tier="direct_query",
        raw_table="uniprot",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.pipeline.adapters.uniprot",
        api_base_url="https://rest.uniprot.org/uniprotkb/search",
    ),
    # --- raw sources (regulatory/IP) ---
    "pubmed-search": ToolDefinition(
        name="pubmed-search",
        description="Search PubMed for biomedical literature",
        tier="direct_query",
        raw_table="pubmed",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.pubmed",
        api_base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
    ),
    "ema-search": ToolDefinition(
        name="ema-search",
        description="Search EMA for European medicine regulatory decisions",
        tier="direct_query",
        raw_table="ema",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.ema",
        api_base_url="https://www.ema.europa.eu/en/medicines",
    ),
    "hta-decisions-search": ToolDefinition(
        name="hta-decisions-search",
        description="Search HTA decisions (NICE, HAS, IQWiG, CADTH)",
        tier="direct_query",
        raw_table="hta_decisions",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.hta_decisions",
        api_base_url="https://www.nice.org.uk/guidance",
    ),
    "cochrane-search": ToolDefinition(
        name="cochrane-search",
        description="Search Cochrane Library for systematic reviews",
        tier="direct_query",
        raw_table="cochrane_reviews",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.cochrane",
        api_base_url="https://www.cochranelibrary.com/cdsr/reviews",
    ),
    "orange-book-search": ToolDefinition(
        name="orange-book-search",
        description="Search FDA Orange Book for patent and exclusivity data",
        tier="direct_query",
        raw_table="orange_book",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.orange_book",
        api_base_url="https://api.fda.gov/drug/drugsfda.json",
    ),
    "uspto-patents-search": ToolDefinition(
        name="uspto-patents-search",
        description="Search USPTO PatentsView for patent filings",
        tier="direct_query",
        raw_table="uspto_patents",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.uspto_patents",
        api_base_url="https://api.patentsview.org/patents/query",
    ),
    "epo-patents-search": ToolDefinition(
        name="epo-patents-search",
        description="Search EPO Open Patent Services for European patents",
        tier="direct_query",
        raw_table="epo_patents",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.epo_patents",
        api_base_url="https://ops.epo.org/3.2/rest-services/published-data/search",
    ),
    "sec-edgar-search": ToolDefinition(
        name="sec-edgar-search",
        description="Search SEC EDGAR for company financial filings",
        tier="direct_query",
        raw_table="sec_edgar",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.sec_edgar",
        api_base_url="https://efts.sec.gov/LATEST/search-index?q=",
    ),
    "who-icd-search": ToolDefinition(
        name="who-icd-search",
        description="Search WHO ICD-11 coding system",
        tier="direct_query",
        raw_table="who_icd",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.who_icd",
        api_base_url="https://id.who.int/icd/release/11/2024-01/mms/search",
    ),
    "pdb-search": ToolDefinition(
        name="pdb-search",
        description="Search RCSB PDB for protein structures",
        tier="direct_query",
        raw_table="pdb_structures",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.pdb_structures",
        api_base_url="https://search.rcsb.org/rcsbsearch/v2/query",
    ),
    "orcid-search": ToolDefinition(
        name="orcid-search",
        description="Search ORCID for researcher profiles",
        tier="direct_query",
        raw_table="orcid",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.orcid",
        api_base_url="https://pub.orcid.org/v3.0/search/",
    ),

    # ============================================================================
    # Tier 2: Fetch + Filter Tools (4)
    # ============================================================================

    "journal-rss-fetch": ToolDefinition(
        name="journal-rss-fetch",
        description="Fetch and filter journal RSS feeds for drug mentions",
        tier="fetch_filter",
        raw_table="journal_rss",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.journal_rss",
        api_base_url="https://feeds.feedburner.com/NatureReviewsDrugDiscovery",
    ),
    "medical-news-fetch": ToolDefinition(
        name="medical-news-fetch",
        description="Fetch and filter medical news for drug-related articles",
        tier="fetch_filter",
        raw_table="medical_news",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.medical_news",
        api_base_url="https://www.fiercepharma.com/rss/xml",
    ),
    "uspto-trademarks-search": ToolDefinition(
        name="uspto-trademarks-search",
        description="Search USPTO TESS for trademark registrations",
        tier="fetch_filter",
        raw_table="uspto_trademarks",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.uspto_trademarks",
        api_base_url="https://tsdr.uspto.gov/",
    ),
    "euipo-trademarks-search": ToolDefinition(
        name="euipo-trademarks-search",
        description="Search EUIPO for EU trademark registrations",
        tier="fetch_filter",
        raw_table="euipo_trademarks",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.euipo_trademarks",
        api_base_url="https://euipo.europa.eu/eSearch/",
    ),
    "euipo-designs-search": ToolDefinition(
        name="euipo-designs-search",
        description="Search EUIPO for registered community designs (pharma packaging, medical devices)",
        tier="fetch_filter",
        raw_table="euipo_designs",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.euipo_designs",
        api_base_url="https://api.euipo.europa.eu/design-search/designs",
    ),

    # ============================================================================
    # Tier 3: Supplementary Context Tools (2)
    # CMS tools removed — CMS data served via PostgREST gold views (016-cms-puf)
    # ============================================================================

    "acc-tvc-search": ToolDefinition(
        name="acc-tvc-search",
        description="Search ACC/TVC cardiac center certifications",
        tier="supplementary",
        raw_table="acc_tvc_certification",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.acc_tvc",
        api_base_url="https://www.acc.org/tools-and-practice-support/accreditation",
    ),
    "hrsa-search": ToolDefinition(
        name="hrsa-search",
        description="Search HRSA health professional shortage areas",
        tier="supplementary",
        raw_table="hrsa_shortage_areas",
        raw_schema="raw",
        adapter_module="dk_data.services.pipeline.adapters.hrsa",
        api_base_url="https://data.hrsa.gov/api/hpsas",
    ),
}


def get_tool_count() -> int:
    """Return total number of registered tools."""
    return len(TOOL_REGISTRY)


def get_tools_by_tier(tier: str) -> Dict[str, ToolDefinition]:
    """Get tools filtered by tier."""
    return {k: v for k, v in TOOL_REGISTRY.items() if v.tier == tier}
