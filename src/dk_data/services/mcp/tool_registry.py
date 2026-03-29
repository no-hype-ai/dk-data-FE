"""MCP Tool Registry — maps tool names to definitions and adapters.

Feature: 015-assessment-dashboard-integration
Task: T062

All 28 MCP tools organized by tier:
- Tier 1 (19 tools): Direct drug-name query against external APIs
- Tier 2 (4 tools): Fetch + filter (RSS, news, trademarks)
- Tier 3 (5 tools): Supplementary context (CMS, ACC, HRSA)
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
        adapter_module="dk_data.services.mcp.adapters.clinicaltrials",
        api_base_url="https://clinicaltrials.gov/api/v2/studies",
    ),
    "chembl-search": ToolDefinition(
        name="chembl-search",
        description="Search ChEMBL for molecule bioactivity data",
        tier="direct_query",
        raw_table="chembl",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.chembl",
        api_base_url="https://www.ebi.ac.uk/chembl/api/data/molecule/search",
    ),
    "openfda-faers-search": ToolDefinition(
        name="openfda-faers-search",
        description="Search OpenFDA FAERS for adverse event reports",
        tier="direct_query",
        raw_table="openfda_faers",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.openfda_faers",
        api_base_url="https://api.fda.gov/drug/event.json",
    ),
    "openfda-labels-search": ToolDefinition(
        name="openfda-labels-search",
        description="Search OpenFDA for drug labeling information",
        tier="direct_query",
        raw_table="openfda_labels",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.openfda_labels",
        api_base_url="https://api.fda.gov/drug/label.json",
    ),
    "drugbank-search": ToolDefinition(
        name="drugbank-search",
        description="Search DrugBank for comprehensive drug information",
        tier="direct_query",
        raw_table="drugbank",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.drugbank",
        api_base_url="https://go.drugbank.com/services/v1/drugs",
    ),
    "pubchem-search": ToolDefinition(
        name="pubchem-search",
        description="Search PubChem for chemical compound data",
        tier="direct_query",
        raw_table="pubchem",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.pubchem",
        api_base_url="https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name",
    ),
    "openalex-search": ToolDefinition(
        name="openalex-search",
        description="Search OpenAlex for academic publications",
        tier="direct_query",
        raw_table="openalex",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.openalex",
        api_base_url="https://api.openalex.org/works",
    ),
    "uniprot-search": ToolDefinition(
        name="uniprot-search",
        description="Search UniProt for protein/target information",
        tier="direct_query",
        raw_table="uniprot",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.uniprot",
        api_base_url="https://rest.uniprot.org/uniprotkb/search",
    ),
    # --- raw sources (regulatory/IP) ---
    "pubmed-search": ToolDefinition(
        name="pubmed-search",
        description="Search PubMed for biomedical literature",
        tier="direct_query",
        raw_table="pubmed",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.pubmed",
        api_base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
    ),
    "ema-search": ToolDefinition(
        name="ema-search",
        description="Search EMA for European medicine regulatory decisions",
        tier="direct_query",
        raw_table="ema",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.ema",
        api_base_url="https://www.ema.europa.eu/en/medicines",
    ),
    "hta-decisions-search": ToolDefinition(
        name="hta-decisions-search",
        description="Search HTA decisions (NICE, HAS, IQWiG, CADTH)",
        tier="direct_query",
        raw_table="hta_decisions",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.hta_decisions",
        api_base_url="https://www.nice.org.uk/guidance",
    ),
    "cochrane-search": ToolDefinition(
        name="cochrane-search",
        description="Search Cochrane Library for systematic reviews",
        tier="direct_query",
        raw_table="cochrane_reviews",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.cochrane",
        api_base_url="https://www.cochranelibrary.com/cdsr/reviews",
    ),
    "orange-book-search": ToolDefinition(
        name="orange-book-search",
        description="Search FDA Orange Book for patent and exclusivity data",
        tier="direct_query",
        raw_table="orange_book",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.orange_book",
        api_base_url="https://api.fda.gov/drug/drugsfda.json",
    ),
    "uspto-patents-search": ToolDefinition(
        name="uspto-patents-search",
        description="Search USPTO PatentsView for patent filings",
        tier="direct_query",
        raw_table="uspto_patents",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.uspto_patents",
        api_base_url="https://api.patentsview.org/patents/query",
    ),
    "epo-patents-search": ToolDefinition(
        name="epo-patents-search",
        description="Search EPO Open Patent Services for European patents",
        tier="direct_query",
        raw_table="epo_patents",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.epo_patents",
        api_base_url="https://ops.epo.org/3.2/rest-services/published-data/search",
    ),
    "sec-edgar-search": ToolDefinition(
        name="sec-edgar-search",
        description="Search SEC EDGAR for company financial filings",
        tier="direct_query",
        raw_table="sec_edgar",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.sec_edgar",
        api_base_url="https://efts.sec.gov/LATEST/search-index?q=",
    ),
    "who-icd-search": ToolDefinition(
        name="who-icd-search",
        description="Search WHO ICD-11 coding system",
        tier="direct_query",
        raw_table="who_icd",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.who_icd",
        api_base_url="https://id.who.int/icd/release/11/2024-01/mms/search",
    ),
    "pdb-search": ToolDefinition(
        name="pdb-search",
        description="Search RCSB PDB for protein structures",
        tier="direct_query",
        raw_table="pdb_structures",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.pdb_structures",
        api_base_url="https://search.rcsb.org/rcsbsearch/v2/query",
    ),
    "orcid-search": ToolDefinition(
        name="orcid-search",
        description="Search ORCID for researcher profiles",
        tier="direct_query",
        raw_table="orcid",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.orcid",
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
        adapter_module="dk_data.services.mcp.adapters.journal_rss",
        api_base_url="https://feeds.feedburner.com/NatureReviewsDrugDiscovery",
    ),
    "medical-news-fetch": ToolDefinition(
        name="medical-news-fetch",
        description="Fetch and filter medical news for drug-related articles",
        tier="fetch_filter",
        raw_table="medical_news",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.medical_news",
        api_base_url="https://www.fiercepharma.com/rss/xml",
    ),
    "uspto-trademarks-search": ToolDefinition(
        name="uspto-trademarks-search",
        description="Search USPTO TESS for trademark registrations",
        tier="fetch_filter",
        raw_table="uspto_trademarks",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.uspto_trademarks",
        api_base_url="https://tsdr.uspto.gov/",
    ),
    "euipo-trademarks-search": ToolDefinition(
        name="euipo-trademarks-search",
        description="Search EUIPO for EU trademark registrations",
        tier="fetch_filter",
        raw_table="euipo_trademarks",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.euipo_trademarks",
        api_base_url="https://euipo.europa.eu/eSearch/",
    ),

    # ============================================================================
    # Tier 3: Supplementary Context Tools (5)
    # ============================================================================

    "cms-inpatient-search": ToolDefinition(
        name="cms-inpatient-search",
        description="Search CMS Medicare inpatient claims data",
        tier="supplementary",
        raw_table="cms_medicare_inpatient",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.cms_inpatient",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals",
    ),
    "cms-hospital-info-search": ToolDefinition(
        name="cms-hospital-info-search",
        description="Search CMS hospital general information",
        tier="supplementary",
        raw_table="cms_hospital_info",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.cms_hospital_info",
        api_base_url="https://data.cms.gov/provider-data/hospital-general-information",
    ),
    "cms-cost-reports-search": ToolDefinition(
        name="cms-cost-reports-search",
        description="Search CMS hospital cost report data",
        tier="supplementary",
        raw_table="cms_cost_reports",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.cms_cost_reports",
        api_base_url="https://data.cms.gov/provider-compliance/cost-report",
    ),
    "acc-tvc-search": ToolDefinition(
        name="acc-tvc-search",
        description="Search ACC/TVC cardiac center certifications",
        tier="supplementary",
        raw_table="acc_tvc_certification",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.acc_tvc",
        api_base_url="https://www.acc.org/tools-and-practice-support/accreditation",
    ),
    "hrsa-search": ToolDefinition(
        name="hrsa-search",
        description="Search HRSA health professional shortage areas",
        tier="supplementary",
        raw_table="hrsa_shortage_areas",
        raw_schema="raw",
        adapter_module="dk_data.services.mcp.adapters.hrsa",
        api_base_url="https://data.hrsa.gov/api/hpsas",
    ),

    # ============================================================================
    # Tier 3: CMS PUF Tools (28) — 019-cms-puf-platform-reconciliation (T044)
    # NOTE: new CMS PUF tools use raw_schema="hcs_raw" (not "raw")
    # ============================================================================

    "cms-part-d-spending": ToolDefinition(
        name="cms-part-d-spending",
        description="CMS Medicare Part D drug spending by drug and manufacturer",
        tier="supplementary",
        raw_table="cms_part_d_spending",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_part_d_spending",
        api_base_url="https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug",
    ),
    "cms-part-b-spending": ToolDefinition(
        name="cms-part-b-spending",
        description="CMS Medicare Part B drug spending by manufacturer and product",
        tier="supplementary",
        raw_table="cms_part_b_spending",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_part_b_spending",
        api_base_url="https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug",
    ),
    "cms-open-payments": ToolDefinition(
        name="cms-open-payments",
        description="CMS Open Payments (Sunshine Act) physician payment records",
        tier="supplementary",
        raw_table="cms_open_payments",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_open_payments",
        api_base_url="https://openpaymentsdata.cms.gov/api/1/datastore/query",
    ),
    "cms-nppes": ToolDefinition(
        name="cms-nppes",
        description="CMS NPPES National Provider Identifier registry",
        tier="supplementary",
        raw_table="cms_nppes",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_nppes",
        api_base_url="https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment/national-plan-and-provider-enumeration-system-nppes",
    ),
    "cms-inpatient-puf": ToolDefinition(
        name="cms-inpatient-puf",
        description="CMS Inpatient PUF — all DRGs by provider (new hcs_raw source)",
        tier="supplementary",
        raw_table="cms_inpatient_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_inpatient_puf",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals",
    ),
    "cms-physician-puf": ToolDefinition(
        name="cms-physician-puf",
        description="CMS Medicare Physician and Other Practitioners PUF",
        tier="supplementary",
        raw_table="cms_physician_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_physician_puf",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners",
    ),
    "cms-hospital-general-info": ToolDefinition(
        name="cms-hospital-general-info",
        description="CMS Hospital General Information — ratings and characteristics",
        tier="supplementary",
        raw_table="cms_hospital_general_info",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_hospital_general_info",
        api_base_url="https://data.cms.gov/provider-data/hospital-general-information",
    ),
    "cms-medicare-advantage": ToolDefinition(
        name="cms-medicare-advantage",
        description="CMS Medicare Advantage enrollment by plan and county",
        tier="supplementary",
        raw_table="cms_medicare_advantage",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_medicare_advantage",
        api_base_url="https://data.cms.gov/medicare-enrollment",
    ),
    "cms-medicaid-drug-spending": ToolDefinition(
        name="cms-medicaid-drug-spending",
        description="CMS Medicaid drug spending by drug and state",
        tier="supplementary",
        raw_table="cms_medicaid_drug_spending",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_medicaid_drug_spending",
        api_base_url="https://data.medicaid.gov/datasets",
    ),
    "cms-dme-puf": ToolDefinition(
        name="cms-dme-puf",
        description="CMS Durable Medical Equipment PUF",
        tier="supplementary",
        raw_table="cms_dme_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_dme_puf",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/medicare-durable-medical-equipment-devices-supplies",
    ),
    "cms-home-health": ToolDefinition(
        name="cms-home-health",
        description="CMS Home Health Agency compare data",
        tier="supplementary",
        raw_table="cms_home_health",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_home_health",
        api_base_url="https://data.cms.gov/provider-data/home-health-care-agencies",
    ),
    "cms-hospice-puf": ToolDefinition(
        name="cms-hospice-puf",
        description="CMS Hospice provider utilization PUF",
        tier="supplementary",
        raw_table="cms_hospice_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_hospice_puf",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/hospice-providers",
    ),
    "cms-snf-puf": ToolDefinition(
        name="cms-snf-puf",
        description="CMS Skilled Nursing Facility PUF",
        tier="supplementary",
        raw_table="cms_snf_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_snf_puf",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/skilled-nursing-facility-utilization-and-payment-public-use-files",
    ),
    "cms-outpatient-puf": ToolDefinition(
        name="cms-outpatient-puf",
        description="CMS Hospital Outpatient PUF",
        tier="supplementary",
        raw_table="cms_outpatient_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_outpatient_puf",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/hospital-outpatient",
    ),
    "cms-referring-providers": ToolDefinition(
        name="cms-referring-providers",
        description="CMS Medicare referring provider patterns",
        tier="supplementary",
        raw_table="cms_referring_providers",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_referring_providers",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/referring-durable-medical-equipment-home-health",
    ),
    "cms-ordering-providers": ToolDefinition(
        name="cms-ordering-providers",
        description="CMS Medicare ordering/referring/prescribing PUF",
        tier="supplementary",
        raw_table="cms_ordering_providers",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_ordering_providers",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners",
    ),
    "cms-lab-services": ToolDefinition(
        name="cms-lab-services",
        description="CMS Medicare lab services utilization PUF",
        tier="supplementary",
        raw_table="cms_lab_services",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_lab_services",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/laboratory-tests",
    ),
    "cms-imaging-puf": ToolDefinition(
        name="cms-imaging-puf",
        description="CMS Medicare imaging services PUF",
        tier="supplementary",
        raw_table="cms_imaging_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_imaging_puf",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/radiology",
    ),
    "cms-mental-health-puf": ToolDefinition(
        name="cms-mental-health-puf",
        description="CMS Medicare mental health services PUF",
        tier="supplementary",
        raw_table="cms_mental_health_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_mental_health_puf",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/mental-health",
    ),
    "cms-opioid-puf": ToolDefinition(
        name="cms-opioid-puf",
        description="CMS Medicare opioid prescribing rates by geography",
        tier="supplementary",
        raw_table="cms_opioid_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_opioid_puf",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/opioid-treatment",
    ),
    "cms-telehealth-puf": ToolDefinition(
        name="cms-telehealth-puf",
        description="CMS Medicare telehealth utilization PUF",
        tier="supplementary",
        raw_table="cms_telehealth_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_telehealth_puf",
        api_base_url="https://data.cms.gov/provider-summary-by-type-of-service/telehealth",
    ),
    "cms-geographic-variation": ToolDefinition(
        name="cms-geographic-variation",
        description="CMS Medicare geographic variation public use file",
        tier="supplementary",
        raw_table="cms_geographic_variation",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_geographic_variation",
        api_base_url="https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-geographic-variation",
    ),
    "cms-chronic-conditions": ToolDefinition(
        name="cms-chronic-conditions",
        description="CMS Medicare chronic conditions prevalence data",
        tier="supplementary",
        raw_table="cms_chronic_conditions",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_chronic_conditions",
        api_base_url="https://data.cms.gov/chronic-conditions",
    ),
    "cms-dual-eligible": ToolDefinition(
        name="cms-dual-eligible",
        description="CMS Medicare-Medicaid dual eligible beneficiaries",
        tier="supplementary",
        raw_table="cms_dual_eligible",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_dual_eligible",
        api_base_url="https://data.cms.gov/medicare-medicaid-coordination/medicare-medicaid-dual-enrollment",
    ),
    "cms-enrollment-puf": ToolDefinition(
        name="cms-enrollment-puf",
        description="CMS Medicare enrollment by geography and demographics",
        tier="supplementary",
        raw_table="cms_enrollment_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_enrollment_puf",
        api_base_url="https://data.cms.gov/medicare-enrollment",
    ),
    "cms-claim-type-puf": ToolDefinition(
        name="cms-claim-type-puf",
        description="CMS Medicare claims by type and service category",
        tier="supplementary",
        raw_table="cms_claim_type_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_claim_type_puf",
        api_base_url="https://data.cms.gov/summary-statistics-on-use-and-payments",
    ),
    "cms-utilization-puf": ToolDefinition(
        name="cms-utilization-puf",
        description="CMS Medicare utilization by service category",
        tier="supplementary",
        raw_table="cms_utilization_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_utilization_puf",
        api_base_url="https://data.cms.gov/summary-statistics-on-use-and-payments",
    ),
    "cms-cost-reports-puf": ToolDefinition(
        name="cms-cost-reports-puf",
        description="CMS Hospital Cost Reports PUF (all providers)",
        tier="supplementary",
        raw_table="cms_cost_reports_puf",
        raw_schema="hcs_raw",
        adapter_module="dk_data.services.mcp.adapters.cms_cost_reports_puf",
        api_base_url="https://data.cms.gov/provider-compliance/cost-report/hospital-provider-cost-report",
    ),
    # --- New molecule vocabulary sources (019-cms-puf-platform-reconciliation) ---
    "dailymed-search": ToolDefinition(
        name="dailymed-search",
        description="Search NLM DailyMed for structured drug product labels (SPL)",
        tier="direct_query",
        raw_table="dailymed",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.dailymed",
        api_base_url="https://dailymed.nlm.nih.gov/dailymed/services/v2",
    ),
    "fda-drugs-search": ToolDefinition(
        name="fda-drugs-search",
        description="Search FDA Drugs@FDA for NDA/ANDA/BLA drug application approvals",
        tier="direct_query",
        raw_table="fda_drugs",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.fda_drugs",
        api_base_url="https://api.fda.gov/drug/drugsfda.json",
    ),
    "ttd-search": ToolDefinition(
        name="ttd-search",
        description="Search Therapeutic Target Database for drug-target interactions",
        tier="direct_query",
        raw_table="ttd",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.ttd",
        api_base_url="https://db.idrblab.net/ttd",
    ),
    "imgt-search": ToolDefinition(
        name="imgt-search",
        description="Search IMGT for immunoglobulin and T-cell receptor gene sequences",
        tier="direct_query",
        raw_table="imgt",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.imgt",
        api_base_url="https://www.imgt.org/genedb",
    ),
    "cdc-vaccines-search": ToolDefinition(
        name="cdc-vaccines-search",
        description="Search CDC CVX/MVX vaccine code sets",
        tier="direct_query",
        raw_table="cdc_vaccines",
        raw_schema="mol_raw",
        adapter_module="dk_data.services.mcp.adapters.cdc_vaccines",
        api_base_url="https://data.cdc.gov",
    ),
}


def get_tool_count() -> int:
    """Return total number of registered tools."""
    return len(TOOL_REGISTRY)


def get_tools_by_tier(tier: str) -> Dict[str, ToolDefinition]:
    """Get tools filtered by tier."""
    return {k: v for k, v in TOOL_REGISTRY.items() if v.tier == tier}
