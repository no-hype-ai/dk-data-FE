"""
build_model_lineage.py — Parse SQLMesh SQL files and populate meta.model_lineage.

Run after deploys to refresh the DAG used by Grafana sqlmesh-lineage dashboard:

    python -m dk_data.ingestion.utils.build_model_lineage

Or with explicit DB URL:

    python -m dk_data.ingestion.utils.build_model_lineage --db-url postgresql://...

The script:
  1. Walks src/dk_data/sqlmesh/models/**/*.sql
  2. Extracts the target model name from the MODEL(...) declaration
  3. Finds all schema.table references in FROM / JOIN clauses
  4. Classifies each (source, target) pair by domain + subdomain
  5. Upserts into meta.model_lineage (TRUNCATE + INSERT for simplicity)
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Iterator

import psycopg2

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[4]  # dk-data-FE/
MODELS_DIR = REPO_ROOT / "src" / "dk_data" / "sqlmesh" / "models"

# ---------------------------------------------------------------------------
# Layer classification  schema → layer
# ---------------------------------------------------------------------------
LAYER_MAP: dict[str, str] = {
    "mol_raw": "raw",
    "hcs_raw": "raw",
    "ind_raw": "raw",
    "raw": "raw",
    "staging": "raw",
    "mol_bronze": "bronze",
    "hcs_bronze": "bronze",
    "ind_bronze": "bronze",
    "mol_silver": "silver",
    "hcs_silver": "silver",
    "ind_silver": "silver",
    "mol_gold": "gold",
    "hcs_gold": "gold",
    "ind_gold": "gold",
    "mart": "gold",
    "scoring": "gold",
    "targeting": "gold",
    "meta": "raw",      # meta tables are operational / external to lineage
}

# External sources declared in _external_sources.yaml are "external" layer
EXTERNAL_SCHEMAS: set[str] = set()  # populated from _external_sources.yaml scan

# ---------------------------------------------------------------------------
# Domain + subdomain classification  schema → (domain, subdomain)
# ---------------------------------------------------------------------------
# Subdomains designed for ~20-30 nodes per panel:
#   mol  → mol-molecule-core | mol-clinical-fda | mol-literature |
#           mol-ip-regulatory | mol-safety-pharma
#   hcs  → hcs-spending | hcs-provider | hcs-facility
#   ind  → ind
#   mart / scoring / targeting → platform

MOL_SUBDOMAINS: dict[str, str] = {
    # core molecule identity / chemistry
    "molecules": "mol-molecule-core",
    "molecule_aliases": "mol-molecule-core",
    "admet_properties": "mol-molecule-core",
    "binding_affinities": "mol-molecule-core",
    "bioactivity": "mol-molecule-core",
    "chembl": "mol-molecule-core",
    "chembl_molecules": "mol-molecule-core",
    "chembl_activities": "mol-molecule-core",
    "bindingdb": "mol-molecule-core",
    "drug_synonyms": "mol-molecule-core",
    "drug_pharmacology": "mol-molecule-core",
    "drugbank": "mol-molecule-core",
    # clinical + FDA
    "clinical_trials": "mol-clinical-fda",
    "ct_gov_indication_stats": "mol-clinical-fda",
    "clinicaltrials": "mol-clinical-fda",
    "fda_drugs": "mol-clinical-fda",
    "regulatory_milestones": "mol-clinical-fda",
    "regulatory_timeline": "mol-clinical-fda",
    "trial_outcomes": "mol-clinical-fda",
    "daily_med": "mol-clinical-fda",
    "dailymed": "mol-clinical-fda",
    "dailymed_labels": "mol-clinical-fda",
    "drug_labels": "mol-clinical-fda",
    "ema": "mol-clinical-fda",
    "ema_regulatory": "mol-clinical-fda",
    "cdc_vaccines": "mol-clinical-fda",
    "cochrane_reviews": "mol-clinical-fda",
    # literature / evidence
    "publication_evidence": "mol-literature",
    "publications": "mol-literature",
    "europepmc": "mol-literature",
    "nih_reporter": "mol-literature",
    # IP / regulatory filings
    "epo_patents": "mol-ip-regulatory",
    "euipo_designs": "mol-ip-regulatory",
    "euipo_trademarks": "mol-ip-regulatory",
    "company_financials": "mol-ip-regulatory",
    "financial_data": "mol-ip-regulatory",
    "financial_summary": "mol-ip-regulatory",
    "company_pipeline": "mol-ip-regulatory",
    # safety / pharma market
    "adverse_events": "mol-safety-pharma",
    "faers_events": "mol-safety-pharma",
    "safety_signals": "mol-safety-pharma",
    "drug_spending": "mol-safety-pharma",
    "cms_coverage": "mol-safety-pharma",
    "cms_medicare": "mol-safety-pharma",
    "cms_open_payments": "mol-safety-pharma",
    "market_summary": "mol-safety-pharma",
    "molecule_profile": "mol-safety-pharma",
    "lifecycle_evidence": "mol-safety-pharma",
    "lifecycle_stages": "mol-safety-pharma",
    "competitive_landscape": "mol-safety-pharma",
    "kol_profiles": "mol-safety-pharma",
    "kol_network": "mol-safety-pharma",
    "kol_drug_associations": "mol-safety-pharma",
    "advocacy_groups": "mol-safety-pharma",
    "advocacy_sentiment": "mol-safety-pharma",
}

HCS_SUBDOMAINS: dict[str, str] = {
    # spending / payments
    "cms_chronic_conditions": "hcs-spending",
    "cms_claim_type_puf": "hcs-spending",
    "cms_cost_reports": "hcs-spending",
    "cms_cost_reports_puf": "hcs-spending",
    "cms_cost_reports_puf_lines": "hcs-spending",
    "cms_dme_puf": "hcs-spending",
    "cms_dual_eligible": "hcs-spending",
    "cms_enrollment_puf": "hcs-spending",
    "cms_geographic_variation": "hcs-spending",
    "cms_imaging_puf": "hcs-spending",
    "cms_inpatient_puf": "hcs-spending",
    "cms_lab_services": "hcs-spending",
    "cms_medicaid_drug_spending": "hcs-spending",
    "cms_medicare_advantage": "hcs-spending",
    "cms_mental_health_puf": "hcs-spending",
    "cms_open_payments": "hcs-spending",
    "cms_opioid_puf": "hcs-spending",
    "cms_outpatient_puf": "hcs-spending",
    "cms_part_b_spending": "hcs-spending",
    "cms_part_d_spending": "hcs-spending",
    "cms_snf_puf": "hcs-spending",
    "cms_telehealth_puf": "hcs-spending",
    "cms_utilization_puf": "hcs-spending",
    "drug_utilization": "hcs-spending",
    "cms_drug_market": "hcs-spending",
    "cms_drug_market_profile": "hcs-spending",
    "cms_market_analytics": "hcs-spending",
    "open_payments_drug_linkage": "hcs-spending",
    "part_d_prescribing": "hcs-spending",
    # provider directory / credentials
    "cms_nppes": "hcs-provider",
    "cms_ordering_providers": "hcs-provider",
    "cms_referring_providers": "hcs-provider",
    "cms_physician_puf": "hcs-provider",
    "provider_profile": "hcs-provider",
    "cms_provider_360": "hcs-provider",
    "cms_hospice_puf": "hcs-provider",
    "cms_home_health": "hcs-provider",
    "ref_nucc_taxonomy": "hcs-provider",
    "geographic_health": "hcs-provider",
    # facility / hospital
    "cms_hospital_general_info": "hcs-facility",
    "cms_hospital_affiliation": "hcs-facility",
    "cms_hospital_quality": "hcs-facility",
    "cms_care_compare": "hcs-facility",
    "cms_chow": "hcs-facility",
    "cms_hcris": "hcs-facility",
    "cms_pos": "hcs-facility",
    "cms_post_acute": "hcs-facility",
    "cms_magnet": "hcs-facility",
    "acc_tvc_certification": "hcs-facility",
    "acc_tvc": "hcs-facility",
    "cms_facility_profile": "hcs-facility",
    "cms_facility_360": "hcs-facility",
    "facility_profile": "hcs-facility",
    "healthcare_facilities": "hcs-facility",
    "cms_medicare_inpatient": "hcs-facility",
}


def _schema_to_domain_subdomain(schema: str, table: str) -> tuple[str, str]:
    """Return (domain, subdomain) for a given schema.table reference."""
    if schema.startswith("mol_") or schema == "mol":
        sd = MOL_SUBDOMAINS.get(table)
        return "mol", sd or "mol-molecule-core"
    if schema.startswith("hcs_") or schema == "hcs":
        sd = HCS_SUBDOMAINS.get(table)
        return "hcs", sd or "hcs-spending"
    if schema.startswith("ind_") or schema == "ind":
        return "ind", "ind"
    if schema in ("mart", "scoring", "targeting"):
        return schema, schema
    return "platform", "platform"


def _layer(schema: str) -> str:
    if schema in EXTERNAL_SCHEMAS:
        return "external"
    return LAYER_MAP.get(schema, "unknown")


# ---------------------------------------------------------------------------
# SQL parsing
# ---------------------------------------------------------------------------
# Matches:  schema.table  where schema contains only word chars + underscore
_SCHEMA_TABLE_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b")
_MODEL_NAME_RE = re.compile(
    r"MODEL\s*\([^)]*name\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)", re.IGNORECASE | re.DOTALL
)
_FROM_JOINS_RE = re.compile(
    r"(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)", re.IGNORECASE
)

# Known non-table schema references to skip
_SKIP_SCHEMAS = {
    "information_schema", "pg_catalog", "sqlmesh", "ops", "api",
    "public", "extensions",
}


def _extract_model_name(sql: str) -> str | None:
    """Extract the target model name from MODEL(...name ...) declaration."""
    m = _MODEL_NAME_RE.search(sql)
    return m.group(1) if m else None


def _extract_sources(sql: str) -> set[str]:
    """Extract all schema.table references from FROM/JOIN clauses."""
    sources: set[str] = set()
    for m in _FROM_JOINS_RE.finditer(sql):
        ref = m.group(1).lower()
        schema, table = ref.split(".", 1)
        if schema in _SKIP_SCHEMAS:
            continue
        # Skip SQLMesh internal CTEs / aliases (single-word schemas already filtered by dot)
        if any(c.isupper() for c in ref):  # shouldn't match but guard
            continue
        sources.add(ref)
    return sources


def iter_model_files() -> Iterator[Path]:
    for path in MODELS_DIR.rglob("*.sql"):
        yield path


# ---------------------------------------------------------------------------
# External source collection from _external_sources.yaml files
# ---------------------------------------------------------------------------
def _load_external_schemas() -> None:
    import yaml  # optional — only needed here

    for yaml_path in MODELS_DIR.rglob("_external_sources.yaml"):
        try:
            with yaml_path.open() as f:
                data = yaml.safe_load(f)
            for source in data.get("sources", []):
                name = source.get("name", "")
                if "." in name:
                    schema = name.split(".")[0]
                    EXTERNAL_SCHEMAS.add(schema)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Build edge list
# ---------------------------------------------------------------------------
def build_edges() -> list[dict]:
    """Return list of edge dicts for all model dependencies."""
    edges: list[dict] = []

    for sql_path in iter_model_files():
        sql = sql_path.read_text(encoding="utf-8")
        target_ref = _extract_model_name(sql)
        if not target_ref:
            continue
        target_ref = target_ref.lower()
        if "." not in target_ref:
            continue

        target_schema, target_table = target_ref.split(".", 1)
        target_layer = _layer(target_schema)
        target_domain, target_subdomain = _schema_to_domain_subdomain(target_schema, target_table)

        sources = _extract_sources(sql)
        for source_ref in sources:
            if source_ref == target_ref:
                continue
            source_schema, source_table = source_ref.split(".", 1)
            source_layer = _layer(source_schema)
            source_domain, _ = _schema_to_domain_subdomain(source_schema, source_table)

            # Use target model's domain/subdomain for the edge (what drives the panel filter)
            edges.append(
                {
                    "source_model": source_ref,
                    "target_model": target_ref,
                    "source_schema": source_schema,
                    "target_schema": target_schema,
                    "source_layer": source_layer,
                    "target_layer": target_layer,
                    "domain": target_domain,
                    "subdomain": target_subdomain,
                }
            )

    return edges


# ---------------------------------------------------------------------------
# Database upsert
# ---------------------------------------------------------------------------
_UPSERT_SQL = """
INSERT INTO meta.model_lineage
    (source_model, target_model, source_schema, target_schema,
     source_layer, target_layer, domain, subdomain, updated_at)
VALUES
    (%(source_model)s, %(target_model)s, %(source_schema)s, %(target_schema)s,
     %(source_layer)s, %(target_layer)s, %(domain)s, %(subdomain)s, NOW())
ON CONFLICT (source_model, target_model)
DO UPDATE SET
    source_schema = EXCLUDED.source_schema,
    target_schema = EXCLUDED.target_schema,
    source_layer  = EXCLUDED.source_layer,
    target_layer  = EXCLUDED.target_layer,
    domain        = EXCLUDED.domain,
    subdomain     = EXCLUDED.subdomain,
    updated_at    = NOW()
"""


def _get_db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    user = os.getenv("DB_USER", "dk_data")
    password = os.getenv("DB_PASSWORD", "")
    dbname = os.getenv("DB_NAME", "dk_data")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def persist_edges(edges: list[dict], db_url: str) -> None:
    conn = psycopg2.connect(db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                # Delete stale edges not in current parse
                current_pairs = {(e["source_model"], e["target_model"]) for e in edges}
                cur.execute("SELECT source_model, target_model FROM meta.model_lineage")
                existing = set(cur.fetchall())
                stale = existing - current_pairs
                if stale:
                    cur.executemany(
                        "DELETE FROM meta.model_lineage "
                        "WHERE source_model = %s AND target_model = %s",
                        list(stale),
                    )
                cur.executemany(_UPSERT_SQL, edges)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild meta.model_lineage from SQLMesh SQL files")
    parser.add_argument("--db-url", default=None, help="PostgreSQL connection URL")
    parser.add_argument("--dry-run", action="store_true", help="Print edges without writing to DB")
    args = parser.parse_args()

    try:
        _load_external_schemas()
    except ImportError:
        pass  # yaml not installed — external schema detection skipped

    edges = build_edges()
    print(f"Parsed {len(edges)} lineage edges from {MODELS_DIR}")

    if args.dry_run:
        for e in sorted(edges, key=lambda x: (x["domain"], x["subdomain"], x["target_model"])):
            print(f"  {e['source_model']} → {e['target_model']}  [{e['domain']}/{e['subdomain']}]")
        return

    db_url = args.db_url or _get_db_url()
    persist_edges(edges, db_url)
    print(f"Upserted {len(edges)} edges into meta.model_lineage")


if __name__ == "__main__":
    main()
