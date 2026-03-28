#!/usr/bin/env python3
"""Generate 1,000-row CSV samples from every table in the dk-data medallion stack.

Usage:
    python scripts/generate_data_samples.py                   # all layers
    python scripts/generate_data_samples.py --layer raw       # raw only
    python scripts/generate_data_samples.py --layer bronze
    python scripts/generate_data_samples.py --layer silver
    python scripts/generate_data_samples.py --layer gold
    python scripts/generate_data_samples.py --layer meta
    python scripts/generate_data_samples.py --schema hcs_raw  # one schema
    python scripts/generate_data_samples.py --rows 500        # smaller sample

Output is written to data-samples/<layer>/<domain>/<schema>.<table>.csv
A manifest.json is written at data-samples/manifest.json with row counts and
generation timestamps for each table.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Output root (relative to repo root)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
OUTPUT_ROOT = REPO_ROOT / "data-samples"

# ---------------------------------------------------------------------------
# Complete table registry — all schemas × tables across all layers.
# Organised as:
#   schema_name → { "layer": str, "domain": str, "tables": [str, ...] }
# ---------------------------------------------------------------------------
TABLE_REGISTRY: dict[str, dict] = {

    # ── Raw layer: Healthcare System ────────────────────────────────────────
    "hcs_raw": {
        "layer": "raw",
        "domain": "hcs",
        "tables": [
            # CMS PUF API/file sources (migration 085)
            "cms_part_d_spending",
            "cms_part_b_spending",
            "cms_open_payments",
            "cms_nppes",
            "cms_inpatient_puf",
            "cms_physician_puf",
            "cms_hospital_general_info",
            "cms_medicare_advantage",
            "cms_medicaid_drug_spending",
            "cms_dme_puf",
            "cms_home_health",
            "cms_hospice_puf",
            "cms_snf_puf",
            "cms_outpatient_puf",
            "cms_referring_providers",
            "cms_ordering_providers",
            "cms_lab_services",
            "cms_imaging_puf",
            "cms_mental_health_puf",
            "cms_opioid_puf",
            "cms_telehealth_puf",
            "cms_geographic_variation",
            "cms_chronic_conditions",
            "cms_dual_eligible",
            "cms_enrollment_puf",
            "cms_claim_type_puf",
            "cms_utilization_puf",
            "cms_cost_reports_puf",
            # Legacy facility sources (migration 099: raw.* → hcs_raw.*)
            "acc_tvc_certification",
            "cms_cost_reports",
            "cms_hospital_info",
            "cms_medicare_inpatient",
            "hrsa_shortage_areas",
        ],
    },

    # ── Raw layer: Molecules / Pharma (API response archive) ───────────────
    "mol_raw": {
        "layer": "raw",
        "domain": "mol",
        "tables": [
            # Core molecule sources (migration 099: raw.* → mol_raw.*)
            "bindingdb",
            "chembl",
            "clinicaltrials",
            "cochrane_reviews",
            "drugbank",
            "ema",
            "epo_patents",
            "euipo_trademarks",
            "hta_decisions",
            "journal_rss",
            "medical_news",
            "openalex_ci",
            "openfda_faers",
            "openfda_labels",
            "orange_book",
            "orcid",
            "pdb",
            "pubchem",
            "pubmed",
            "sec_edgar",
            "sider",
            "uniprot",
            "uspto_ci",
            "uspto_patents",
            "uspto_trademarks",
            "who_icd",
            # Already in mol_raw before 099
            "europepmc_raw",
            "nih_reporter_raw",
            # Vocabulary sources (migration 095: raw.* → mol_raw.*)
            "rxnorm",
            "pharmgkb",
            "kegg_drug",
            "who_inn",
            "tdc_admet",
            "websearch",
        ],
    },

    # ── Bronze layer: Healthcare System ────────────────────────────────────
    "hcs_bronze": {
        "layer": "bronze",
        "domain": "hcs",
        "tables": [
            # CMS PUF file-sourced bronze
            "cms_part_d_spending",
            "cms_part_b_spending",
            "cms_open_payments",
            "cms_nppes",
            "cms_inpatient_puf",
            "cms_physician_puf",
            "cms_physician_puf_services",
            "cms_hospital_general_info",
            "cms_medicare_advantage",
            "cms_medicaid_drug_spending",
            "cms_dme_puf",
            "cms_home_health",
            "cms_hospice_puf",
            "cms_snf_puf",
            "cms_outpatient_puf",
            "cms_referring_providers",
            "cms_ordering_providers",
            "cms_lab_services",
            "cms_imaging_puf",
            "cms_mental_health_puf",
            "cms_opioid_puf",
            "cms_telehealth_puf",
            "cms_geographic_variation",
            "cms_chronic_conditions",
            "cms_dual_eligible",
            "cms_enrollment_puf",
            "cms_claim_type_puf",
            "cms_utilization_puf",
            "cms_cost_reports_puf",
            "cms_cost_reports_puf_lines",
            # CMS API-fetched bronze (facility/provider/reference sources)
            "cms_care_compare",
            "cms_chow",
            "cms_ddinter",
            "cms_dmepos",
            "cms_formulary",
            "cms_hcris",
            "cms_hospital_affiliation",
            "cms_hospital_quality",
            "cms_magnet",
            "cms_ndc",
            "cms_nucc",
            "cms_part_d_prescriber",
            "cms_pecos",
            "cms_pos",
            "cms_post_acute",
            "cms_rbcs",
            "cms_stabilis",
            "cms_usp",
            # Legacy facility bronze (migration 099: bronze.* → hcs_bronze.*)
            "acc_tvc",
            "cms_cost_reports",
            "cms_hospital_info",
            "cms_inpatient",
            "hrsa",
        ],
    },

    # ── Bronze layer: Molecules ─────────────────────────────────────────────
    "mol_bronze": {
        "layer": "bronze",
        "domain": "mol",
        "tables": [
            # Core molecule bronze (migration 099: bronze.* → mol_bronze.*)
            "bindingdb",
            "cdc_vaccines",
            "chembl_molecules",
            "clinicaltrials",
            "cms_medicare",
            "cms_open_payments",
            "cochrane_reviews",
            "ct_gov_indication_stats",
            "dailymed",
            "drugbank",
            "ema",
            "epo_patents",
            "euipo_trademarks",
            "europepmc",
            "faers_events",
            "fda_drugs",
            "fda_drugsfda",
            "hta_decisions",
            "imgt",
            "journal_rss",
            "medical_news",
            "nice_hta",
            "npi_registry",
            "openalex",
            "openfda_labels",
            "orange_book",
            "orcid",
            "pdb_structures",
            "pubchem",
            "pubmed",
            "purple_book",
            "reactome",
            "sec_edgar",
            "sider",
            "ttd",
            "uniprot",
            "uspto_ci",
            "uspto_patents",
            "uspto_trademarks",
            "websearch",
            "who_gho",
            "who_icd",
            # Already mol_bronze before 099
            "nih_reporter",
            # Vocabulary bronze (feature 019)
            "rxnorm",
            "pharmgkb",
            "kegg_drug",
            "who_inn",
            "tdc_admet",
        ],
    },

    # ── Silver layer: Healthcare System ────────────────────────────────────
    "hcs_silver": {
        "layer": "silver",
        "domain": "hcs",
        "tables": [
            # SQLMesh entity-resolved profiles (deterministic SQL)
            "provider_profile",
            "facility_profile",
            "cms_facility_profile",
            "geographic_health",
            "healthcare_facilities",
            "drug_utilization",
            "cms_drug_market",
            "open_payments_drug_linkage",
            "part_d_prescribing",
            "ref_nucc_taxonomy",
        ],
    },

    # ── Agent layer: Healthcare System (LLM-written tables) ────────────────
    "hcs_agents": {
        "layer": "silver",
        "domain": "hcs",
        "tables": [
            "service_lines",
            "idn_hierarchy",
            "referral_network",
            "verified_contacts",
            "staffing_decomposition",
            "equipment_inventory",
        ],
    },

    # ── Agent layer: Molecules (LLM-written staging) ────────────────────────
    "mol_agents": {
        "layer": "silver",
        "domain": "mol",
        "tables": [
            "publication_evidence_staging",
        ],
    },

    # ── Agent shared: cross-domain quarantine ──────────────────────────────
    "agents": {
        "layer": "silver",
        "domain": "agents",
        "tables": [
            "agent_quarantine",
        ],
    },

    # ── Silver layer: Molecules ─────────────────────────────────────────────
    "mol_silver": {
        "layer": "silver",
        "domain": "mol",
        "tables": [
            "admet_properties",
            "adverse_events",
            "binding_affinities",
            "bioactivity",
            "cdc_vaccines",
            "chembl",
            "clinical_trials",
            "cochrane_reviews",
            "company_financials",
            "ct_gov_indication_stats",
            "dailymed_labels",
            "drug_labels",
            "drug_pharmacology",
            "drug_spending",
            "drug_synonyms",
            "drugbank",
            "ema_regulatory",
            "financial_data",
            "hcpcs_molecule_bridge",
            "icd_codes",
            "icd10_indicator_mapping",
            "identifier_mappings",
            "imgt",
            "indication_revenue",
            "journal_rss",
            "molecule_aliases",
            "molecule_publications",
            "molecule_targets",
            "molecules",
            "ndc_molecule_bridge",
            "news_signals",
            "patent_exclusivities",
            "patents",
            "pathways",
            "pharmacogenomics",
            "physician_payments",
            "physician_profiles",
            "protein_structures",
            "protein_targets",
            "proteins",
            "pubchem",
            "publication_evidence",
            "publications",
            "pubmed_articles",
            "regulatory_decisions",
            "regulatory_milestones",
            "rems_programs",
            "research_grants",
            "researchers",
            "rxnorm_concepts",
            "side_effects",
            "targets",
            "trademarks",
            "ttd",
            "web_content",
            "who_inn_names",
        ],
    },

    # ── Gold layer: Healthcare System ───────────────────────────────────────
    "hcs_gold": {
        "layer": "gold",
        "domain": "hcs",
        "tables": [
            "cms_drug_market_profile",
            "cms_facility_360",
            "cms_market_analytics",
            "cms_provider_360",
        ],
    },

    # ── Gold layer: Molecules ───────────────────────────────────────────────
    "mol_gold": {
        "layer": "gold",
        "domain": "mol",
        "tables": [
            "advocacy_groups",
            "advocacy_sentiment",
            "company_pipeline",
            "competitive_landscape",
            "financial_summary",
            "kol_drug_associations",
            "kol_network",
            "kol_profiles",
            "lifecycle_evidence",
            "lifecycle_stages",
            "market_summary",
            "molecule_profile",
            "regulatory_timeline",
            "safety_signals",
            "trial_outcomes",
        ],
    },

    # ── Indication pipeline (ind_silver) ───────────────────────────────────
    "ind_silver": {
        "layer": "silver",
        "domain": "ind",
        "tables": [
            "epidemiology",
            "indication_ontology",
        ],
    },

    # ── Staging / intermediate ─────────────────────────────────────────────
    "staging": {
        "layer": "staging",
        "domain": "staging",
        "tables": [
            "certifications",
            "geographic_designations",
            "hospitals",
            "tavr_volumes",
        ],
    },

    # ── Mart (fact / dimension tables) ──────────────────────────────────────
    "mart": {
        "layer": "staging",
        "domain": "staging",
        "tables": [
            "dim_hospital",
            "fact_financial_metrics",
            "fact_tavr_program",
        ],
    },

    # ── Governance / metadata ───────────────────────────────────────────────
    "meta": {
        "layer": "meta",
        "domain": "meta",
        "tables": [
            "data_sources",
            "refresh_log",
        ],
    },
}

# Which layers map to which output subdirectory
LAYER_OUTPUT_MAP: dict[str, str] = {
    "raw": "raw",
    "bronze": "bronze",
    "silver": "silver",
    "gold": "gold",
    "staging": "staging",
    "meta": "meta",
}


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def get_connection() -> psycopg2.extensions.connection:
    """Build a psycopg2 connection from env vars (same pattern as the platform)."""
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        dbname=os.environ.get("POSTGRES_DB", "dk_data"),
        connect_timeout=10,
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


# ---------------------------------------------------------------------------
# Sampling logic
# ---------------------------------------------------------------------------

def table_exists(cur: psycopg2.extensions.cursor, schema: str, table: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table),
    )
    return cur.fetchone() is not None


def sample_table(
    cur: psycopg2.extensions.cursor,
    schema: str,
    table: str,
    rows: int,
) -> tuple[list[str], list[tuple], int]:
    """Return (columns, data_rows, total_count) for schema.table."""
    # Total row count (approximate via stats for speed — exact for small tables)
    cur.execute(
        """
        SELECT reltuples::bigint
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relname = %s
        """,
        (schema, table),
    )
    row = cur.fetchone()
    approx_count = int(row[0]) if row and row[0] > 0 else 0

    # For mol_raw tables the "response_body" is a large JSONB blob — truncate
    # it so samples stay readable. All other columns pass through unmodified.
    truncate_jsonb = schema in ("mol_raw", "raw")

    cur.execute(
        f"""
        SELECT *
        FROM {schema}.{table}
        ORDER BY random()
        LIMIT %s
        """,
        (rows,),
    )
    columns = [d[0] for d in cur.description]
    data = cur.fetchall()

    if truncate_jsonb:
        jsonb_indices = [
            i for i, d in enumerate(cur.description)
            if d[1] == psycopg2.extensions.new_type((114, 3802), "JSON", None) or
               "body" in d[0] or "params" in d[0] or "headers" in d[0]
        ]
        truncated = []
        for row_ in data:
            row_ = list(row_)
            for idx in jsonb_indices:
                val = row_[idx]
                if isinstance(val, (dict, list)):
                    serialized = json.dumps(val)
                    if len(serialized) > 500:
                        row_[idx] = serialized[:497] + "..."
            truncated.append(tuple(row_))
        data = truncated

    return columns, data, max(approx_count, len(data))


def write_csv(
    output_path: Path,
    columns: list[str],
    data: list[tuple],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(columns)
        for row_ in data:
            writer.writerow([
                str(v) if v is not None else ""
                for v in row_
            ])


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run(
    layer_filter: str | None,
    schema_filter: str | None,
    rows: int,
) -> None:
    start = time.monotonic()
    generated_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    cur = conn.cursor()

    manifest: list[dict] = []
    skipped: list[str] = []
    total_rows_sampled = 0

    for schema, meta in TABLE_REGISTRY.items():
        layer = meta["layer"]
        domain = meta["domain"]

        if layer_filter and layer != layer_filter:
            continue
        if schema_filter and schema != schema_filter:
            continue

        output_subdir = OUTPUT_ROOT / LAYER_OUTPUT_MAP.get(layer, layer) / domain
        logger.info("sampling_schema", schema=schema, layer=layer)

        for table in meta["tables"]:
            qualified = f"{schema}.{table}"

            if not table_exists(cur, schema, table):
                logger.warning("table_not_found", table=qualified)
                skipped.append(qualified)
                manifest.append({
                    "table": qualified,
                    "schema": schema,
                    "layer": layer,
                    "domain": domain,
                    "status": "not_found",
                    "rows_sampled": 0,
                    "total_rows_approx": 0,
                    "output_file": None,
                    "generated_at": generated_at,
                })
                continue

            try:
                columns, data, total = sample_table(cur, schema, table, rows)
            except Exception as exc:
                logger.error("sample_failed", table=qualified, error=str(exc))
                skipped.append(qualified)
                manifest.append({
                    "table": qualified,
                    "schema": schema,
                    "layer": layer,
                    "domain": domain,
                    "status": "error",
                    "error": str(exc),
                    "rows_sampled": 0,
                    "total_rows_approx": 0,
                    "output_file": None,
                    "generated_at": generated_at,
                })
                continue

            out_file = output_subdir / f"{schema}.{table}.csv"
            write_csv(out_file, columns, data)
            total_rows_sampled += len(data)

            rel_path = str(out_file.relative_to(REPO_ROOT))
            logger.info(
                "sampled",
                table=qualified,
                rows_sampled=len(data),
                total_rows=total,
                file=rel_path,
            )
            manifest.append({
                "table": qualified,
                "schema": schema,
                "layer": layer,
                "domain": domain,
                "status": "ok",
                "rows_sampled": len(data),
                "total_rows_approx": total,
                "output_file": rel_path,
                "columns": columns,
                "generated_at": generated_at,
            })

    cur.close()
    conn.close()

    # Write manifest
    manifest_path = OUTPUT_ROOT / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "generated_at": generated_at,
                "rows_per_table": rows,
                "layer_filter": layer_filter,
                "schema_filter": schema_filter,
                "total_tables_attempted": len(manifest),
                "total_tables_ok": sum(1 for m in manifest if m["status"] == "ok"),
                "total_tables_skipped": len(skipped),
                "total_rows_sampled": total_rows_sampled,
                "elapsed_seconds": round(time.monotonic() - start, 1),
                "tables": manifest,
            },
            fh,
            indent=2,
            default=str,
        )

    print(f"\n{'─' * 60}")
    print(f"  Samples written to: {OUTPUT_ROOT}")
    print(f"  Tables sampled    : {sum(1 for m in manifest if m['status'] == 'ok')}")
    print(f"  Tables skipped    : {len(skipped)}")
    print(f"  Total rows        : {total_rows_sampled:,}")
    print(f"  Manifest          : {manifest_path}")
    print(f"  Elapsed           : {round(time.monotonic() - start, 1)}s")
    print(f"{'─' * 60}\n")

    if skipped:
        print("Skipped (table not found or error):")
        for t in skipped:
            print(f"  - {t}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate 1,000-row CSV samples from all dk-data medallion tables."
    )
    parser.add_argument(
        "--layer",
        choices=["raw", "bronze", "silver", "gold", "staging", "meta"],
        default=None,
        help="Only sample tables in this layer",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="Only sample tables in this exact schema (e.g. hcs_raw, mol_silver)",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=1000,
        help="Rows per table (default: 1000)",
    )
    args = parser.parse_args()

    # Check connection early
    try:
        conn = get_connection()
        conn.close()
    except Exception as exc:
        print(f"ERROR: Cannot connect to database: {exc}", file=sys.stderr)
        print(
            "Set POSTGRES_HOST / POSTGRES_PORT / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB",
            file=sys.stderr,
        )
        sys.exit(1)

    run(
        layer_filter=args.layer,
        schema_filter=args.schema,
        rows=args.rows,
    )


if __name__ == "__main__":
    main()
