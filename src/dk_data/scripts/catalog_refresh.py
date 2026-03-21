#!/usr/bin/env python3
"""
Catalog Refresh Script
Feature: 001-data-layer-postgrest-gitops
Task: T019

Populates semantic metadata (descriptions, topic_tags, ai_description)
for data sources in the catalog.

Usage:
    python scripts/catalog_refresh.py [--check-only]
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor, Json

# Database configuration from environment
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5433")),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
}

# Semantic metadata definitions for known data sources
SOURCE_METADATA = {
    "cms_medicare_inpatient": {
        "topic_tags": ["cms", "medicare", "hospital", "financial", "drg"],
        "ai_description": "CMS Medicare inpatient hospital discharge data by DRG code. Contains procedure volumes, charges, and payments for Medicare fee-for-service patients. Key source for TAVR volume estimation.",
        "column_descriptions": {
            "provider_id": {
                "description": "CMS 6-digit provider identification number",
                "type": "string",
                "examples": ["010001", "050001"],
            },
            "drg_code": {
                "description": "Diagnosis Related Group code for procedure classification",
                "type": "string",
                "examples": ["266", "267"],
            },
            "total_discharges": {
                "description": "Number of Medicare fee-for-service discharges for this DRG",
                "type": "integer",
            },
            "average_medicare_payments": {
                "description": "Average Medicare payment per discharge in USD",
                "type": "decimal",
            },
        },
        "staleness_threshold_hours": 720,  # Monthly data - 30 days
        "target_tables": ["staging.tavr_volumes", "mart.fact_tavr_program"],
    },
    "cms_hospital_info": {
        "topic_tags": ["cms", "hospital", "demographics", "quality"],
        "ai_description": "CMS Hospital Compare general information dataset. Contains hospital demographics, ownership, bed counts, quality ratings, and contact information.",
        "column_descriptions": {
            "provider_id": {
                "description": "CMS 6-digit provider identification number",
                "type": "string",
            },
            "hospital_name": {
                "description": "Official hospital name",
                "type": "string",
            },
            "hospital_overall_rating": {
                "description": "CMS overall quality star rating (1-5)",
                "type": "integer",
                "range": "1-5",
            },
            "hospital_type": {
                "description": "Type of hospital (Acute Care, Critical Access, etc.)",
                "type": "string",
            },
        },
        "staleness_threshold_hours": 168,  # Weekly updates
        "target_tables": ["staging.hospitals", "mart.dim_hospital"],
    },
    "acc_tvc": {
        "topic_tags": ["acc", "certification", "tavr", "quality", "ncdr", "tvt"],
        "ai_description": "ACC Transcatheter Valve Certification and TVT Registry data from NCDR Public Reporting API. Contains TAVR volumes, quality ratings, and certification status for facilities participating in the STS/ACC TVT Registry.",
        "column_descriptions": {
            "facility_name": {
                "description": "Branded name of the certified facility (FacilityBrandedName)",
                "type": "string",
            },
            "facility_linking_id": {
                "description": "NCDR unique facility linking identifier",
                "type": "string",
            },
            "npi": {
                "description": "National Provider Identifier",
                "type": "string",
            },
            "state": {
                "description": "Two-letter US state code",
                "type": "string",
            },
            "cumulative_tavr_volume": {
                "description": "Cumulative total TAVR procedures performed at the facility",
                "type": "integer",
            },
            "annual_tavr_volume": {
                "description": "Annual TAVR procedure volume",
                "type": "integer",
            },
            "participant_rating": {
                "description": "NCDR quality participant rating (1-3 scale)",
                "type": "integer",
            },
            "certification_type": {
                "description": "Type of ACC certification (Transcatheter Valve Certification)",
                "type": "string",
            },
        },
        "staleness_threshold_hours": 2160,  # Quarterly — 90 days
        "target_tables": ["staging.certifications"],
    },
    "hrsa_shortage_areas": {
        "topic_tags": ["hrsa", "geographic", "hpsa", "rural"],
        "ai_description": "HRSA Health Professional Shortage Area designations. Identifies underserved areas for healthcare access analysis and rural hospital targeting.",
        "column_descriptions": {
            "hpsa_id": {
                "description": "HRSA unique identifier for the shortage area",
                "type": "string",
            },
            "hpsa_score": {
                "description": "Shortage severity score (higher = more severe)",
                "type": "integer",
            },
            "rural_status": {
                "description": "Urban/rural classification",
                "type": "string",
            },
        },
        "staleness_threshold_hours": 720,  # Monthly
        "target_tables": ["staging.geographic_designations"],
    },
    "cms_cost_reports": {
        "topic_tags": ["cms", "financial", "hospital", "cost"],
        "ai_description": "CMS Hospital Cost Report data with financial metrics. Contains operating margins, revenue, expenses, and bed counts for financial capacity analysis.",
        "column_descriptions": {
            "provider_id": {
                "description": "CMS 6-digit provider identification number",
                "type": "string",
            },
            "operating_margin": {
                "description": "Operating margin ratio (revenue - expenses) / revenue",
                "type": "decimal",
            },
            "total_beds": {
                "description": "Total number of hospital beds",
                "type": "integer",
            },
        },
        "staleness_threshold_hours": 2160,  # Quarterly - 90 days
        "target_tables": ["mart.fact_financial_metrics"],
    },
    "bindingdb": {
        "topic_tags": ["molecule", "binding", "affinity", "drug-target"],
        "ai_description": "BindingDB binding affinity measurements for drug-target interactions. Contains IC50, Ki, Kd values for protein-ligand binding. Used for molecular pharmacology analysis and target identification.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete BindingDB API response with binding measurements",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 720,
        "target_tables": ["mol_bronze.bindingdb", "mol_silver.bioactivity"],
    },
    "orange_book": {
        "topic_tags": ["molecule", "fda", "patent", "exclusivity", "generic"],
        "ai_description": "FDA Orange Book listing of approved drug products with therapeutic equivalence evaluations, patent information, and exclusivity data. Key source for generic drug competition and patent expiry analysis.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete FDA Orange Book CSV parsed response",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["mol_bronze.orange_book"],
    },
    "sider": {
        "topic_tags": ["molecule", "side-effect", "adverse-reaction", "safety"],
        "ai_description": "SIDER database of drug side effects mined from drug labels and adverse event reports. Links drugs to MedDRA-coded adverse reactions with frequency information.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete SIDER data file parsed as structured JSON",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 720,
        "target_tables": ["mol_bronze.sider", "mol_gold.safety_signals"],
    },
    "tdc_admet": {
        "topic_tags": ["molecule", "admet", "pharmacokinetics", "toxicity", "prediction"],
        "ai_description": "Therapeutics Data Commons ADMET property predictions. Contains absorption, distribution, metabolism, excretion, and toxicity predictions for drug compounds from ML models.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete TDC ADMET API response with property predictions",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 720,
        "target_tables": ["mol_bronze.tdc_admet"],
    },
    "ema": {
        "topic_tags": ["molecule", "regulatory", "ema", "european", "approval"],
        "ai_description": "European Medicines Agency approved medicines database. Contains marketing authorization details, EPAR documents, and regulatory decisions for medicines in the EU market.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete EMA API response with medicine details",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["mol_bronze.ema"],
    },
    "rxnorm": {
        "topic_tags": ["molecule", "nomenclature", "drug-name", "nlm"],
        "ai_description": "NLM RxNorm normalized drug nomenclature. Provides standardized drug names, ingredient mappings, and dose form classifications for drug name harmonization across data sources.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete RxNorm API response with drug concept data",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["mol_bronze.rxnorm"],
    },
    "dailymed": {
        "topic_tags": ["molecule", "label", "spl", "fda"],
        "ai_description": "NLM DailyMed structured product labeling. Contains FDA-approved drug labels with dosing, indications, warnings, and pharmacology sections in structured format.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete DailyMed SPL response with label sections",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["mol_bronze.dailymed"],
    },
    "fda_drugs": {
        "topic_tags": ["molecule", "fda", "approval", "regulatory"],
        "ai_description": "FDA Drugs@FDA database of approved drug products. Contains approval history, regulatory actions, review documents, and therapeutic equivalence data for FDA-regulated drugs.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete FDA Drugs@FDA API response with approval data",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["mol_bronze.fda_drugs"],
    },
    "kegg_drug": {
        "topic_tags": ["molecule", "pathway", "target", "kegg"],
        "ai_description": "KEGG Drug database linking drugs to biological pathways, molecular targets, and disease associations. Key source for mechanism of action and pathway analysis.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete KEGG Drug API response with pathway data",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 720,
        "target_tables": ["mol_bronze.kegg_drug"],
    },
    "ttd": {
        "topic_tags": ["molecule", "target", "drug-target", "therapeutic"],
        "ai_description": "Therapeutic Target Database linking therapeutic targets to drugs and diseases. Contains target validation status, drug-target binding data, and clinical trial mappings.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete TTD API response with target-drug data",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 720,
        "target_tables": ["mol_bronze.ttd"],
    },
    "pharmgkb": {
        "topic_tags": ["molecule", "pharmacogenomics", "genetic", "variant"],
        "ai_description": "PharmGKB pharmacogenomics knowledge base. Contains gene-drug-disease relationships, clinical pharmacogenomic guidelines, and variant-drug response annotations.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete PharmGKB API response with pharmacogenomic data",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 720,
        "target_tables": ["mol_bronze.pharmgkb"],
    },
    "imgt": {
        "topic_tags": ["molecule", "antibody", "biologic", "immunogenetics"],
        "ai_description": "ImMunoGeneTics information system for antibody and biologic sequence data. Contains immunoglobulin gene sequences, antibody structures, and nomenclature for biologic drug analysis.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete IMGT API response with antibody sequence data",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 720,
        "target_tables": ["mol_bronze.imgt"],
    },
    "cdc_vaccines": {
        "topic_tags": ["molecule", "vaccine", "immunization", "cdc"],
        "ai_description": "CDC vaccine information including recommended schedules, coverage rates, and safety monitoring data. Used for vaccine pipeline competitive analysis and market sizing.",
        "column_descriptions": {
            "response_body": {
                "description": "Complete CDC vaccine API response with schedule data",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 720,
        "target_tables": ["mol_bronze.cdc_vaccines"],
    },
    "pubmed": {
        "topic_tags": ["ci", "literature", "pubmed", "pharmaceutical"],
        "ai_description": "PubMed literature from NCBI E-utilities. Contains pharmaceutical research articles with abstracts, MeSH terms, and citation data for competitive intelligence monitoring.",
        "column_descriptions": {
            "pmid": {
                "description": "PubMed unique article identifier",
                "type": "string",
            },
            "title": {
                "description": "Article title",
                "type": "string",
            },
            "publication_date": {
                "description": "Date of publication",
                "type": "date",
            },
            "mesh_terms": {
                "description": "Medical Subject Heading terms assigned to article",
                "type": "jsonb",
            },
        },
        "staleness_threshold_hours": 24,
        "target_tables": ["raw.pubmed"],
    },
    "openalex_ci": {
        "topic_tags": ["ci", "literature", "openalex", "research"],
        "ai_description": "OpenAlex pharmaceutical research works. Contains scholarly works with citation counts, concept tags, and institutional affiliations for competitive intelligence analysis.",
        "column_descriptions": {
            "work_id": {
                "description": "OpenAlex unique work identifier (W-prefixed)",
                "type": "string",
            },
            "doi": {
                "description": "Digital Object Identifier for the work",
                "type": "string",
            },
            "cited_by_count": {
                "description": "Number of citations received",
                "type": "integer",
            },
            "publication_date": {
                "description": "Date of publication",
                "type": "date",
            },
        },
        "staleness_threshold_hours": 24,
        "target_tables": ["raw.openalex_ci"],
    },
    "ema_regulatory": {
        "topic_tags": ["ci", "regulatory", "ema", "european"],
        "ai_description": "EMA regulatory decisions including CHMP opinions, EPAR documents, and safety signals. Key source for tracking European pharmaceutical regulatory landscape.",
        "column_descriptions": {
            "document_id": {
                "description": "EMA unique document identifier",
                "type": "string",
            },
            "document_type": {
                "description": "Type of regulatory document (chmp_opinion, epar, safety_signal)",
                "type": "string",
            },
            "decision_type": {
                "description": "Type of regulatory decision (authorisation, variation, withdrawal, etc.)",
                "type": "string",
            },
            "decision_date": {
                "description": "Date the regulatory decision was made",
                "type": "date",
            },
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["raw.ema_regulatory"],
    },
    "drugbank": {
        "topic_tags": ["ci", "drug", "target", "pharmacology"],
        "ai_description": "DrugBank comprehensive drug data including targets, enzymes, pharmacology, and drug-drug interactions. Credential-gated source requiring DRUGBANK_API_KEY.",
        "column_descriptions": {
            "drugbank_id": {"description": "DrugBank unique identifier (DB-prefixed)", "type": "string"},
            "name": {"description": "Drug name", "type": "string"},
            "targets": {"description": "Drug target proteins", "type": "jsonb"},
        },
        "staleness_threshold_hours": 720,
        "target_tables": ["raw.drugbank"],
    },
    "uspto_patents": {
        "topic_tags": ["ci", "patent", "uspto", "pharmaceutical"],
        "ai_description": "USPTO PatentsView pharmaceutical patents filtered by CPC codes A61K/A61P/C07D. Credential-gated source requiring USPTO_API_KEY.",
        "column_descriptions": {
            "patent_number": {"description": "USPTO patent number", "type": "string"},
            "cpc_codes": {"description": "Cooperative Patent Classification codes", "type": "array"},
            "grant_date": {"description": "Patent grant date", "type": "date"},
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["raw.uspto_patents"],
    },
    "journal_rss": {
        "topic_tags": ["ci", "literature", "rss", "journal"],
        "ai_description": "Journal RSS feeds from NEJM, Lancet, JAMA, BMJ, and Nature Medicine. Daily ingestion of pharmaceutical research article metadata.",
        "column_descriptions": {
            "article_id": {"description": "Unique article identifier (DOI or URL hash)", "type": "string"},
            "feed_source": {"description": "Journal name or feed URL", "type": "string"},
            "doi": {"description": "Digital Object Identifier", "type": "string"},
        },
        "staleness_threshold_hours": 24,
        "target_tables": ["raw.journal_rss"],
    },
    "uspto_ci": {
        "topic_tags": ["ci", "patent", "uspto", "competitive-intelligence"],
        "ai_description": "USPTO PatentsView CI patents with query-scoped search terms from meta.ops_ci_search_terms. Filtered by pharmaceutical CPC codes.",
        "column_descriptions": {
            "patent_id": {"description": "USPTO patent identifier", "type": "string"},
            "cpc_codes": {"description": "Cooperative Patent Classification codes", "type": "array"},
            "filing_date": {"description": "Patent filing date", "type": "date"},
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["raw.uspto_ci"],
    },
    "hta_bodies": {
        "topic_tags": ["ci", "regulatory", "hta", "reimbursement"],
        "ai_description": "HTA body decisions from NICE (UK), G-BA (Germany), HAS (France), and PBAC (Australia). Query-scoped drug name matching.",
        "column_descriptions": {
            "decision_id": {"description": "HTA decision unique identifier", "type": "string"},
            "agency": {"description": "HTA agency code (nice, gba, has, pbac)", "type": "string"},
            "decision_type": {"description": "Type of HTA decision", "type": "string"},
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["raw.hta_decisions"],
    },
    "epo_ops": {
        "topic_tags": ["ci", "patent", "epo", "european"],
        "ai_description": "EPO Open Patent Services pharmaceutical patents with OAuth2 authentication and IPC code filtering. Credential-gated source.",
        "column_descriptions": {
            "publication_id": {"description": "EPO publication identifier", "type": "string"},
            "ipc_codes": {"description": "International Patent Classification codes", "type": "array"},
            "family_id": {"description": "Patent family identifier", "type": "string"},
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["raw.epo_patents"],
    },
    "cochrane": {
        "topic_tags": ["ci", "evidence", "cochrane", "systematic-review"],
        "ai_description": "Cochrane Library systematic reviews for pharmaceutical interventions. Monthly search for evidence-based medicine assessments.",
        "column_descriptions": {
            "review_id": {"description": "Cochrane review unique identifier", "type": "string"},
            "review_type": {"description": "Type of review (intervention, diagnostic, etc.)", "type": "string"},
            "interventions": {"description": "Drug/treatment interventions studied", "type": "array"},
        },
        "staleness_threshold_hours": 720,
        "target_tables": ["raw.cochrane_reviews"],
    },
    "medical_news": {
        "topic_tags": ["ci", "news", "media", "pharmaceutical"],
        "ai_description": "Medical news from Medscape, Healio, and FiercePharma RSS feeds. Extracts drug mentions from article titles and summaries.",
        "column_descriptions": {
            "article_id": {"description": "Unique article identifier (source+URL hash)", "type": "string"},
            "source_name": {"description": "News source (medscape, healio, fiercepharma)", "type": "string"},
            "drug_mentions": {"description": "Drug names mentioned in article", "type": "array"},
        },
        "staleness_threshold_hours": 24,
        "target_tables": ["raw.medical_news"],
    },
    "sec_edgar": {
        "topic_tags": ["ci", "financial", "sec", "regulatory"],
        "ai_description": "SEC EDGAR pharmaceutical company filings (10-K, 10-Q, 8-K) filtered by SIC codes 2830-2836. Daily monitoring of pharma financial disclosures.",
        "column_descriptions": {
            "accession_number": {"description": "SEC filing accession number", "type": "string"},
            "filing_type": {"description": "Filing type (10-K, 10-Q, 8-K)", "type": "string"},
            "cik": {"description": "SEC Central Index Key for the company", "type": "string"},
        },
        "staleness_threshold_hours": 24,
        "target_tables": ["raw.sec_edgar"],
    },
    "uniprot": {
        "topic_tags": ["protein", "drug-target", "molecular-biology", "uniprot"],
        "ai_description": "UniProt protein database entries for drug target identification. Contains protein accessions, gene names, organism, function annotations, and sequence data for reviewed human drug targets.",
        "column_descriptions": {
            "accession": {"description": "UniProt accession number", "type": "string", "examples": ["P00533", "Q9Y6K9"]},
            "gene_name": {"description": "Primary gene name (HGNC symbol)", "type": "string"},
            "organism": {"description": "Source organism scientific name", "type": "string"},
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["raw.uniprot"],
    },
    "pdb": {
        "topic_tags": ["protein-structure", "crystallography", "drug-target", "pdb"],
        "ai_description": "RCSB Protein Data Bank entries for 3D protein structure data. Contains PDB IDs, experimental methods, resolution, and deposit dates for drug target structures.",
        "column_descriptions": {
            "pdb_id": {"description": "4-character PDB identifier", "type": "string", "examples": ["1ABC", "2XYZ"]},
            "method": {"description": "Experimental method (X-RAY DIFFRACTION, ELECTRON MICROSCOPY, etc.)", "type": "string"},
            "resolution": {"description": "Structure resolution in Angstroms", "type": "float"},
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["raw.pdb"],
    },
    "orcid": {
        "topic_tags": ["researcher", "kol", "author", "orcid"],
        "ai_description": "ORCID researcher profiles for key opinion leader identification in pharmaceutical research. Contains names, affiliations, publication counts, and external identifiers.",
        "column_descriptions": {
            "orcid_id": {"description": "ORCID iD in format 0000-0000-0000-000X", "type": "string"},
            "family_name": {"description": "Researcher family/last name", "type": "string"},
            "works_count": {"description": "Total number of publications", "type": "integer"},
        },
        "staleness_threshold_hours": 168,
        "target_tables": ["raw.orcid"],
    },
}


def get_connection():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


def get_current_sources(cursor) -> list[dict[str, Any]]:
    """Get all active data sources."""
    cursor.execute("""
        SELECT source_id, source_name, topic_tags, ai_description,
               column_descriptions, staleness_threshold_hours, target_tables
        FROM meta.ops_data_sources
        WHERE is_active = TRUE
        ORDER BY source_name
    """)
    return cursor.fetchall()


def update_source_metadata(cursor, source_id: int, metadata: dict) -> bool:
    """Update metadata for a data source."""
    cursor.execute("""
        UPDATE meta.ops_data_sources
        SET
            topic_tags = %(topic_tags)s,
            ai_description = %(ai_description)s,
            column_descriptions = %(column_descriptions)s,
            staleness_threshold_hours = %(staleness_threshold_hours)s,
            target_tables = %(target_tables)s
        WHERE source_id = %(source_id)s
    """, {
        "source_id": source_id,
        "topic_tags": metadata.get("topic_tags", []),
        "ai_description": metadata.get("ai_description"),
        "column_descriptions": Json(metadata.get("column_descriptions", {})),
        "staleness_threshold_hours": metadata.get("staleness_threshold_hours", 24),
        "target_tables": metadata.get("target_tables", []),
    })
    return cursor.rowcount > 0


def record_health_check(cursor, source_id: int) -> int | None:
    """Record a health check for the source."""
    cursor.execute("""
        SELECT meta.record_health_check(%(source_id)s, 0, 0, %(details)s) AS health_id
    """, {
        "source_id": source_id,
        "details": Json({"source": "catalog_refresh", "timestamp": datetime.now().isoformat()}),
    })
    result = cursor.fetchone()
    return result["health_id"] if result else None


def main():
    parser = argparse.ArgumentParser(description="Refresh catalog metadata")
    parser.add_argument("--check-only", action="store_true",
                        help="Only check current status, don't update")
    args = parser.parse_args()

    print("=" * 60)
    print("Catalog Refresh Script")
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print("=" * 60)

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get current sources
        sources = get_current_sources(cursor)
        print(f"\nFound {len(sources)} active data sources")

        updated_count = 0
        skipped_count = 0
        unknown_count = 0

        for source in sources:
            source_name = source["source_name"]
            source_id = source["source_id"]

            if source_name in SOURCE_METADATA:
                metadata = SOURCE_METADATA[source_name]
                has_metadata = bool(source["ai_description"])

                if args.check_only:
                    status = "HAS_METADATA" if has_metadata else "NEEDS_UPDATE"
                    print(f"  [{status}] {source_name}")
                else:
                    if update_source_metadata(cursor, source_id, metadata):
                        print(f"  [UPDATED] {source_name}")
                        updated_count += 1
                        # Record health check after update
                        health_id = record_health_check(cursor, source_id)
                        if health_id:
                            print(f"    -> Health check recorded (id: {health_id})")
                    else:
                        print(f"  [SKIPPED] {source_name} - no changes")
                        skipped_count += 1
            else:
                print(f"  [UNKNOWN] {source_name} - no metadata defined")
                unknown_count += 1

        if not args.check_only:
            conn.commit()
            print(f"\n{'=' * 60}")
            print(f"Summary: {updated_count} updated, {skipped_count} skipped, {unknown_count} unknown")
        else:
            print(f"\n{'=' * 60}")
            print("Check-only mode - no changes made")

        cursor.close()
        conn.close()
        return 0

    except psycopg2.Error as e:
        print(f"\nDatabase error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
