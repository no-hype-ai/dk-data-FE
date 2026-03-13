#!/usr/bin/env python3
"""dk-data-fe MCP Server for Claude Code.

Exposes PostgREST-backed database tables and dk-data-fe tool invocations
as MCP tools accessible from Claude Code sessions.

Usage (stdio):
    python3 mcp_server.py
    # or: uvx mcp run mcp_server.py

Requires: mcp, httpx
"""

import json
import os
import sys
from typing import Any

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "MCP SDK not found. Install with: pip install mcp",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
POSTGREST_URL = os.environ.get("POSTGREST_URL", "http://localhost:3030")
MAX_ROWS = int(os.environ.get("MCP_MAX_ROWS", "50"))

SCHEMAS = {
    "gold": [
        "molecule_profile",
        "safety_signals",
        "trial_outcomes",
        "lifecycle_stages",
        "competitive_landscape",
        "epidemiology",
        "kol_profiles",
        "molecule_patents",
        "molecule_pipeline",
        "molecule_targets",
        # CMS gold views (016-cms-puf-datasource-integration)
        "cms_provider_360",
        "cms_facility_360",
        "cms_drug_market_profile",
        "cms_market_analytics",
        "cms_provider_network",
        "cms_part_d_spending",
        "cms_part_b_spending",
        "cms_chow",
        "cms_hospital_affiliation",
        "cms_rbcs",
        "cms_nucc",
        "cms_usp",
        "cms_stabilis",
        "cms_ddinter",
        "cms_formulary",
        "cms_ndc",
        "cms_dmepos",
        "cms_post_acute",
        "cms_nppes",
        "cms_pos",
        "cms_hcris",
        "cms_magnet",
    ],
    "silver": [
        "molecules",
        "clinical_trials",
        "drug_labels",
        "adverse_events",
        "publications",
        "targets",
        "patents",
        "identifier_mappings",
        "molecule_aliases",
        "molecule_publications",
        "molecule_targets",
        "bioactivity",
    ],
    "bronze": [
        "clinicaltrials",
        "chembl",
        "openfda_faers",
        "openfda_labels",
        "orange_book",
        "drugbank",
        "pubchem",
        "pubmed",
        "openalex",
    ],
    "xenon": [
        "assessment_generated",
        "publication_evidence",
    ],
    "mol_raw": [
        "clinicaltrials",
        "chembl",
        "openfda_faers",
        "openfda_labels",
        "drugbank",
        "pubchem",
        "openalex",
        "pdb",
        "sider",
        "uniprot",
    ],
    "raw": [
        "pubmed",
        "orange_book",
        "ema",
        "cochrane",
        "hta_decisions",
        "uspto_patents",
        "epo_patents",
        "sec_edgar",
        "who_icd",
        "orcid",
        "cms_nppes",
        "cms_part_d_prescriber",
        "cms_physician_puf",
        "cms_open_payments_general",
        "cms_care_compare_physicians",
        "cms_pos",
        "cms_pecos",
        "cms_inpatient_puf",
        "cms_outpatient_puf",
        "cms_hospital_quality",
        "cms_hospital_general_info",
        "cms_hcris",
        "cms_ndc",
        "cms_part_d_spending",
        "cms_part_b_spending",
        "cms_formulary",
        "cms_rbcs",
        "cms_geographic_variation",
        "cms_chronic_conditions",
        "acc_tvc_certification",
        "hrsa_shortage_areas",
        "mcp_responses",
    ],
    "meta": [
        "batch_jobs",
        "batch_job_runs",
        "data_sources",
        "data_quality",
        "table_health",
        "refresh_log",
    ],
    "api": [
        "health",
        "data_catalog",
        "data_sources",
        "targets",
        "scoring",
        "scoring_details",
        "hospitals",
    ],
}

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP("dk-data-fe")

client = httpx.Client(timeout=30.0)


def _postgrest_query(
    table: str,
    schema: str = "api",
    filters: dict[str, str] | None = None,
    select: str | None = None,
    order: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Query PostgREST and return rows."""
    headers = {}
    if schema != "api":
        headers["Accept-Profile"] = schema

    params: dict[str, str] = {}
    if select:
        params["select"] = select
    if order:
        params["order"] = order
    params["limit"] = str(limit or MAX_ROWS)

    if filters:
        for key, value in filters.items():
            params[key] = value

    url = f"{POSTGREST_URL}/{table}"
    resp = client.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Tool: list available schemas and tables
# ---------------------------------------------------------------------------
@mcp.tool()
def list_tables() -> str:
    """List all available database schemas and tables in dk-data-fe.

    Returns the full schema map: gold, silver, bronze, xenon, mol_raw, raw, meta, api.
    """
    lines = []
    for schema, tables in SCHEMAS.items():
        lines.append(f"\n## {schema} ({len(tables)} tables)")
        for t in tables:
            lines.append(f"  - {t}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: query any table
# ---------------------------------------------------------------------------
@mcp.tool()
def query_table(
    schema: str,
    table: str,
    filters: str = "",
    select: str = "",
    order: str = "",
    limit: int = 20,
) -> str:
    """Query a dk-data-fe database table via PostgREST.

    Args:
        schema: Database schema (gold, silver, bronze, xenon, mol_raw, raw, meta, api)
        table: Table name within the schema
        filters: PostgREST filter string as JSON object, e.g. {"molecule_name":"eq.Dupilumab"}
                 Operators: eq, neq, gt, gte, lt, lte, like, ilike, in, is, cs, cd
        select: Comma-separated columns to return, e.g. "molecule_name,lifecycle_stage"
        order: Column to order by, e.g. "created_at.desc"
        limit: Max rows to return (default 20, max 200)
    """
    if schema not in SCHEMAS:
        return f"Error: Unknown schema '{schema}'. Available: {', '.join(SCHEMAS.keys())}"
    if table not in SCHEMAS[schema]:
        return f"Error: Table '{table}' not in schema '{schema}'. Available: {', '.join(SCHEMAS[schema])}"

    limit = min(limit, 200)

    filter_dict = {}
    if filters:
        try:
            filter_dict = json.loads(filters)
        except json.JSONDecodeError:
            return f"Error: Invalid JSON in filters: {filters}"

    try:
        rows = _postgrest_query(
            table=table,
            schema=schema,
            filters=filter_dict,
            select=select or None,
            order=order or None,
            limit=limit,
        )
    except httpx.HTTPStatusError as e:
        return f"Error {e.response.status_code}: {e.response.text}"
    except httpx.ConnectError:
        return "Error: Cannot connect to PostgREST at " + POSTGREST_URL

    if not rows:
        return "No rows returned."

    return json.dumps(rows, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool: molecule search (convenience)
# ---------------------------------------------------------------------------
@mcp.tool()
def search_molecule(name: str) -> str:
    """Search for a molecule by name across gold.molecule_profile.

    Returns profile data including lifecycle stage, identifiers, pipeline indications,
    safety signals summary, and data completeness score.

    Args:
        name: Molecule name (case-insensitive search)
    """
    try:
        rows = _postgrest_query(
            table="molecule_profile",
            schema="gold",
            filters={"molecule_name": f"ilike.*{name}*"},
            limit=10,
        )
    except httpx.HTTPStatusError as e:
        return f"Error {e.response.status_code}: {e.response.text}"
    except httpx.ConnectError:
        return "Error: Cannot connect to PostgREST"

    if not rows:
        return f"No molecule found matching '{name}'."

    return json.dumps(rows, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool: safety signals for a molecule
# ---------------------------------------------------------------------------
@mcp.tool()
def get_safety_signals(molecule_name: str, limit: int = 30) -> str:
    """Get adverse event safety signals for a molecule from gold.safety_signals.

    Args:
        molecule_name: Molecule name or ID to search for
        limit: Max signals to return (default 30)
    """
    try:
        rows = _postgrest_query(
            table="safety_signals",
            schema="gold",
            filters={"molecule_id": f"ilike.*{molecule_name}*"},
            order="case_count.desc",
            limit=min(limit, 100),
        )
    except httpx.HTTPStatusError as e:
        return f"Error {e.response.status_code}: {e.response.text}"
    except httpx.ConnectError:
        return "Error: Cannot connect to PostgREST"

    if not rows:
        return f"No safety signals found for '{molecule_name}'."

    return json.dumps(rows, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool: clinical trials for a molecule
# ---------------------------------------------------------------------------
@mcp.tool()
def get_clinical_trials(molecule_name: str, phase: str = "", limit: int = 20) -> str:
    """Get clinical trials for a molecule from silver.clinical_trials.

    Args:
        molecule_name: Molecule name to search for
        phase: Optional phase filter (e.g. "PHASE3", "PHASE2")
        limit: Max trials to return (default 20)
    """
    filters: dict[str, str] = {}

    # First find molecule_id from silver.molecules
    try:
        molecules = _postgrest_query(
            table="molecules",
            schema="silver",
            filters={"canonical_name": f"ilike.*{molecule_name}*"},
            select="id,canonical_name",
            limit=5,
        )
    except httpx.HTTPStatusError as e:
        return f"Error {e.response.status_code}: {e.response.text}"
    except httpx.ConnectError:
        return "Error: Cannot connect to PostgREST"

    if not molecules:
        return f"No molecule found matching '{molecule_name}'."

    mol_id = molecules[0]["id"]
    filters["molecule_id"] = f"eq.{mol_id}"

    if phase:
        filters["phase"] = f"eq.{phase}"

    try:
        rows = _postgrest_query(
            table="clinical_trials",
            schema="silver",
            filters=filters,
            order="start_date.desc",
            limit=min(limit, 50),
        )
    except httpx.HTTPStatusError as e:
        return f"Error {e.response.status_code}: {e.response.text}"

    if not rows:
        return f"No trials found for '{molecule_name}'" + (f" phase={phase}" if phase else "") + "."

    return json.dumps(rows, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool: xenon assessments
# ---------------------------------------------------------------------------
@mcp.tool()
def get_assessment(molecule_id: str, section_type: str = "") -> str:
    """Get AI-generated assessments from xenon.assessment_generated.

    Available section_types: executive_summary, competitive_landscape,
    financial_analysis, kol_mapping, hcp_segmentation, patient_journey,
    discovered_competitors, risk_assessment, strategic_recommendations,
    investment_thesis

    Args:
        molecule_id: Molecule identifier (e.g. "durvalumab", "pembrolizumab")
        section_type: Optional section type filter
    """
    filters = {"molecule_id": f"eq.{molecule_id}"}
    if section_type:
        filters["section_type"] = f"eq.{section_type}"

    try:
        rows = _postgrest_query(
            table="assessment_generated",
            schema="xenon",
            filters=filters,
            order="created_at.desc",
            limit=10,
        )
    except httpx.HTTPStatusError as e:
        return f"Error {e.response.status_code}: {e.response.text}"
    except httpx.ConnectError:
        return "Error: Cannot connect to PostgREST"

    if not rows:
        return f"No assessments found for molecule_id='{molecule_id}'."

    return json.dumps(rows, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool: publication evidence from xenon
# ---------------------------------------------------------------------------
@mcp.tool()
def get_publication_evidence(molecule_id: str, limit: int = 20) -> str:
    """Get LLM-extracted clinical evidence from xenon.publication_evidence.

    Returns endpoint data: hazard ratios, p-values, response rates,
    survival data, sample sizes, confidence scores.

    Args:
        molecule_id: Molecule identifier
        limit: Max rows (default 20)
    """
    try:
        rows = _postgrest_query(
            table="publication_evidence",
            schema="xenon",
            filters={"molecule_id": f"eq.{molecule_id}"},
            order="confidence_score.desc",
            limit=min(limit, 50),
        )
    except httpx.HTTPStatusError as e:
        return f"Error {e.response.status_code}: {e.response.text}"
    except httpx.ConnectError:
        return "Error: Cannot connect to PostgREST"

    if not rows:
        return f"No publication evidence found for '{molecule_id}'."

    return json.dumps(rows, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool: competitive landscape
# ---------------------------------------------------------------------------
@mcp.tool()
def get_competitive_landscape(molecule_name: str) -> str:
    """Get competitive landscape data for a molecule from gold.competitive_landscape.

    Shows competing molecules by indication, phase distribution, and counts.

    Args:
        molecule_name: Molecule name or ID
    """
    try:
        rows = _postgrest_query(
            table="competitive_landscape",
            schema="gold",
            filters={"molecule_id": f"ilike.*{molecule_name}*"},
            limit=20,
        )
    except httpx.HTTPStatusError as e:
        return f"Error {e.response.status_code}: {e.response.text}"
    except httpx.ConnectError:
        return "Error: Cannot connect to PostgREST"

    if not rows:
        return f"No competitive landscape data for '{molecule_name}'."

    return json.dumps(rows, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool: data quality / health
# ---------------------------------------------------------------------------
@mcp.tool()
def get_data_health() -> str:
    """Get data quality and table health status from meta schema.

    Returns recent table health checks and data quality metrics.
    """
    results = {}
    try:
        results["table_health"] = _postgrest_query(
            table="table_health",
            schema="meta",
            order="checked_at.desc",
            limit=20,
        )
    except Exception as e:
        results["table_health_error"] = str(e)

    try:
        results["data_quality"] = _postgrest_query(
            table="data_quality",
            schema="meta",
            order="checked_at.desc",
            limit=10,
        )
    except Exception as e:
        results["data_quality_error"] = str(e)

    return json.dumps(results, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool: raw SQL-like query (advanced)
# ---------------------------------------------------------------------------
@mcp.tool()
def postgrest_raw(
    path: str,
    schema: str = "gold",
    accept: str = "application/json",
) -> str:
    """Make a raw PostgREST GET request for advanced queries.

    Useful for complex filters, joins via embedding, or RPC calls.
    See PostgREST docs for query syntax.

    Examples:
        path="/molecule_profile?select=molecule_name,lifecycle_stage&lifecycle_stage=eq.approved"
        path="/molecules?select=canonical_name,clinical_trials(nct_id,phase,status)"
        path="/rpc/my_function?arg=value"

    Args:
        path: Full PostgREST path with query params (e.g. "/molecule_profile?molecule_name=ilike.*pembro*")
        schema: Schema to query (default: gold)
        accept: Response content type
    """
    headers = {"Accept": accept}
    if schema != "api":
        headers["Accept-Profile"] = schema

    try:
        resp = client.get(f"{POSTGREST_URL}{path}", headers=headers)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return f"Error {e.response.status_code}: {e.response.text}"
    except httpx.ConnectError:
        return "Error: Cannot connect to PostgREST at " + POSTGREST_URL

    if accept == "text/csv":
        return resp.text

    try:
        data = resp.json()
        return json.dumps(data, indent=2, default=str)
    except Exception:
        return resp.text


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
