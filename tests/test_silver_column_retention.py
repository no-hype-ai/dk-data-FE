"""Column-retention contract tests for Silver SQLMesh models.

Feature: 001-silver-medallion-rebuild (Wave 2)
Task: T020 — Column retention audit

Tests verify that each silver SQL model carries forward ALL domain columns from its
upstream bronze source(s). System/metadata columns are explicitly exempted per FR-001.

These are STATIC contract tests — they parse SQL files, no live DB required.

FR-001: Every non-system column from a bronze upstream must appear in silver.
FR-002: Name collisions between two upstream bronze tables must be prefixed.
FR-003: JSONB columns must be carried as JSONB (not cast to TEXT).
FR-004: NULL casts for optional cross-source fields are acceptable as placeholders.
"""

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODELS_BASE = Path(__file__).resolve().parent.parent / "src" / "dk_data" / "sqlmesh" / "models"

# ---------------------------------------------------------------------------
# Selective models: intentionally extract a semantic subset of bronze columns.
# These models transform bronze into a PURPOSE-BUILT structure (entity resolution,
# cross-reference table, alias extraction, bridge table, etc.) rather than being
# full passthroughs. They are skipped from strict column-retention enforcement.
# Each entry is (domain/silver/model.sql, reason).
# ---------------------------------------------------------------------------
SELECTIVE_MODELS: dict[str, str] = {
    # Entity resolution models — use multiple sources, extract canonical fields only
    "molecules/silver/molecules.sql": "Entity resolution: canonical molecule from chembl/drugbank/pubchem",
    "molecules/silver/identifier_mappings.sql": "Cross-reference: extracts identifiers only from multi-source",
    "molecules/silver/molecule_aliases.sql": "Alias extraction: extracts names/aliases only from multi-source",
    # Bioactivity / pharmacology models — extract specific assay/pharma fields from broad bronze
    "molecules/silver/bioactivity.sql": "Bioactivity extraction: specific assay columns from chembl",
    "molecules/silver/drug_pharmacology.sql": "Pharmacology extraction: mechanism/pharma subset of drugbank",
    "molecules/silver/adverse_events.sql": "Adverse event extraction: signal fields from faers/sider",
    "molecules/silver/side_effects.sql": "Side effect extraction: specific fields from sider",
    "molecules/silver/pathways.sql": "Pathway extraction: specific fields from kegg_drug/reactome",
    # Bridge / join-key models
    "molecules/silver/ndc_molecule_bridge.sql": "Bridge table: NDC-molecule join keys only",
    # Multi-source aggregation models
    "molecules/silver/regulatory_decisions.sql": "Regulatory: decision-specific fields from ema/hta",
    "molecules/silver/regulatory_milestones.sql": "Milestones: timeline fields from fda_drugs",
    "molecules/silver/researchers.sql": "Researchers: profile + grant linkage from orcid/nih_reporter",
    "molecules/silver/molecule_publications.sql": "Publications: pub fields + chembl linkage",
    "molecules/silver/molecule_targets.sql": "Targets: target-specific fields from drugbank",
    # Patents: drugbank used as patent source only (not pharmacology), orange_book used for patent fields
    "molecules/silver/patents.sql": "Patents: drugbank used for patent extraction only; orange_book carries only patent fields",
    # Source-specific models where bronze has infrastructure artifacts as output cols
    "molecules/silver/chembl.sql": "Chembl passthrough: floats is LATERAL CTE alias, not domain column",
    "molecules/silver/drug_synonyms.sql": "WHO INN synonyms: info_item is LATERAL jsonb_array_elements alias",
    "molecules/silver/who_inn_names.sql": "WHO INN names: info_item is LATERAL jsonb_array_elements alias",
    "molecules/silver/publications.sql": "Publications aggregation: selective fields from europepmc/openalex/rss",
    # HCS multi-source aggregation models
    "hcs/silver/geographic_health.sql": "Geographic health: aggregates subset across CMS benefit sources",
    "hcs/silver/provider_profile.sql": "Provider profile: aggregates subset across NPI/NPPES/CMS sources",
    "hcs/silver/cms_facility_profile.sql": "Facility profile: aggregates subset across HCRIS/PECOS/affiliation",
    "hcs/silver/drug_utilization.sql": "Drug utilization: utilization-specific fields from Part B/D/Medicaid",
    "hcs/silver/healthcare_facilities.sql": "Facilities: core fields from ACC TVC/HRSA/CMS sources",
}

# System/metadata columns intentionally NOT required in silver
# Includes infrastructure, HTTP response, and bronze-layer tracking columns
SYSTEM_COLUMNS = frozenset({
    # Spec-listed exemptions
    "ingested_at", "request_id", "source_file", "batch_id", "etl_version",
    "row_hash", "_sqlmesh_start", "_sqlmesh_end", "_api_hidden", "id",
    "raw_id", "raw_json", "request_timestamp", "source", "source_updated_at",
    "processed_to_silver", "processed_to_bronze", "_loaded_at",
    # Additional infrastructure columns common across all bronze models
    "raw_source_id",           # Internal bronze request tracking ID
    "response_body",           # Raw HTTP response body (not domain data)
    "response_status",         # HTTP status code
    "response_text",           # Alias for raw response text
    "response_type",           # HTTP response content type
    "created_at", "updated_at",
    # Short SQL query aliases that appear in bronze CTEs (not actual columns)
    "r", "m", "a", "b", "c", "d", "e", "f", "s", "t", "v",
    # Common CTE/subquery variable aliases used inside bronze SQL bodies
    "rec", "elem", "item", "row", "sub", "act", "ref", "obj", "prod",
    # SQL structural keywords / type aliases that regex may pick up
    "jsonb", "text", "date", "bool", "int", "bigint", "numeric",
    # HCS bronze internal columns
    "_bronze_loaded_at",
})

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _read_sql(path: Path) -> str:
    assert path.exists(), f"SQL file not found: {path}"
    return path.read_text()


def _extract_model_name(sql: str) -> str:
    m = re.search(r"MODEL\s*\(.*?name\s+([\w.]+)", sql, re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else "unknown"


def _extract_select_columns(sql: str) -> list[str]:
    """
    Extract output column names from a SELECT clause.
    Handles:
      - `expr AS alias`  → returns alias
      - `r.column_name`  → returns column_name
      - bare column names
    """
    # Strip MODEL block and CTEs — we want the final SELECT
    # Find the last SELECT in the file (the output SELECT, not inside CTEs)
    selects = list(re.finditer(r"\bSELECT\b", sql, re.IGNORECASE))
    if not selects:
        return []

    # Take the first top-level SELECT after any CTE definitions
    # A simple heuristic: find the SELECT that is NOT inside a WITH CTE definition
    # We'll just get all col aliases from the whole file
    columns = []

    # Match `... AS alias` patterns
    for m in re.finditer(r"(?:^|\s)(\w+)\s+AS\s+(\w+)\b", sql, re.IGNORECASE | re.MULTILINE):
        columns.append(m.group(2).lower())

    # Also match bare `table.column` or `column` in SELECT (no AS)
    # Extract column names from SELECT lists — look for patterns like `r.col_name,`
    for m in re.finditer(r"\br\.(\w+)(?:\s*,|\s*$)", sql, re.IGNORECASE | re.MULTILINE):
        columns.append(m.group(1).lower())

    return list(set(columns))


def _get_bronze_output_columns(bronze_path: Path) -> set[str]:
    """
    Parse a bronze model SQL file and return its non-system output columns.

    Strategy: only take explicit AS aliases from SELECT expressions.
    Filters out:
      - Table/CTE aliases: `FROM table AS alias`, `JOIN ... AS alias`
      - LATERAL function aliases: `jsonb_array_elements(...) AS alias(column)`
      - SQL keyword aliases: AS raw, AS mol (when used as table aliases)
    """
    sql = _read_sql(bronze_path)
    cols = set()

    # Skip table-level AS aliases: pattern `FROM|JOIN ... AS alias` and `AS alias(`
    # We do this by scanning the full file for `AS word` patterns and filtering
    for m in re.finditer(r"\bAS\s+(\w+)\s*(\(?)", sql, re.IGNORECASE):
        col = m.group(1).lower()
        next_char = m.group(2)

        # Skip if followed by `(` — this is a LATERAL/table function alias like `AS prod(col)`
        if next_char == "(":
            continue

        # Skip if this is a table alias: preceded by FROM/JOIN/,/table-name on same line
        # Check the 30 chars before this AS keyword
        start = max(0, m.start() - 40)
        pre = sql[start:m.start()].strip()
        # If pre ends with a table name pattern (word.word or just word) → table alias
        if re.search(r"\b(FROM|JOIN|,)\s+[\w.]+\s*$", pre, re.IGNORECASE):
            continue

        if col not in SYSTEM_COLUMNS and len(col) > 1 and not col.isdigit():
            cols.add(col)

    return cols - SYSTEM_COLUMNS


def _find_bronze_refs(silver_sql: str) -> list[tuple[str, str]]:
    """
    Find PRIMARY bronze table references in a silver SQL file.

    A bronze table is considered a PRIMARY source if it appears in a FROM clause
    (not just in a LEFT JOIN used for dimension lookup). We heuristically identify
    primary sources as tables in:
      - `FROM schema.table` (without being a dimension-join target)
      - CTEs that contain `processed_to_silver` or `WHERE ... = FALSE`

    Dimension-lookup bronzes (e.g., `LEFT JOIN mol_silver.molecules` for entity
    resolution) are excluded to avoid false positives.

    Strategy: collect all bronze references, then filter to those that appear
    in the same CTE block as `processed_to_silver` usage (marking them as primary),
    OR appear in the first `FROM` in the file.
    """
    refs = []
    for m in re.finditer(
        r"\b(mol_bronze|hcs_bronze|ind_bronze|ip_bronze)\.([\w]+)\b",
        silver_sql,
        re.IGNORECASE,
    ):
        schema = m.group(1).lower()
        table = m.group(2).lower()
        # Check if this reference is within a context that indicates it's a primary source:
        # 1. The surrounding CTE/block contains `processed_to_silver`
        # 2. Or the table is in a FROM clause (not a LEFT JOIN for lookups)
        ref_pos = m.start()

        # Get 500 chars of context around the reference
        start = max(0, ref_pos - 200)
        end = min(len(silver_sql), ref_pos + 300)
        context = silver_sql[start:end]

        is_primary = (
            "processed_to_silver" in context.lower()
            or re.search(r"\bFROM\s+$".rstrip(), context[:context.find(f"{schema}.{table}")], re.IGNORECASE)
            or re.search(rf"FROM\s+{re.escape(schema)}\.{re.escape(table)}\b", context, re.IGNORECASE)
        )

        if is_primary:
            refs.append((schema, table))

    return list(set(refs))


def _silver_references_column(silver_sql: str, col: str) -> bool:
    """
    Return True if `col` (or a reasonable alias) appears in the silver SQL.
    Checks:
      - Exact column name as a word boundary
      - Column appears as an AS alias
      - Column appears in a compound alias (prefix_col)
    """
    pattern = rf"\b{re.escape(col)}\b"
    return bool(re.search(pattern, silver_sql, re.IGNORECASE))


def _find_missing_columns(silver_path: Path, bronze_paths: list[Path]) -> dict[str, list[str]]:
    """
    For each bronze upstream, return the list of columns missing from the silver model.
    Returns dict: {bronze_table_name: [missing_col, ...]}
    """
    silver_sql = _read_sql(silver_path)
    result = {}
    for bp in bronze_paths:
        bronze_cols = _get_bronze_output_columns(bp)
        missing = [
            col for col in sorted(bronze_cols)
            if not _silver_references_column(silver_sql, col)
        ]
        if missing:
            result[bp.stem] = missing
    return result


# ---------------------------------------------------------------------------
# Bronze model path helpers
# ---------------------------------------------------------------------------

def _bronze_path(schema: str, table: str) -> Path | None:
    """Return the Path to a bronze model SQL file, or None if it doesn't exist."""
    domain_map = {
        "mol_bronze": "molecules",
        "hcs_bronze": "hcs",
        "ind_bronze": "ind",
        "ip_bronze": "ip",
    }
    domain = domain_map.get(schema)
    if not domain:
        return None
    p = MODELS_BASE / domain / "bronze" / f"{table}.sql"
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# Parametrized retention test
# ---------------------------------------------------------------------------

def _collect_silver_cases() -> list[tuple[Path, list[Path], str]]:
    """
    Walk all silver model directories and build (silver_path, [bronze_paths], label)
    for models that have at least one resolvable bronze upstream.
    Models listed in SELECTIVE_MODELS are excluded from strict enforcement.
    """
    cases = []
    for domain in ("molecules", "hcs", "ind", "ip"):
        silver_dir = MODELS_BASE / domain / "silver"
        if not silver_dir.exists():
            continue
        for silver_file in sorted(silver_dir.glob("*.sql")):
            label = f"{domain}/silver/{silver_file.name}"
            if label in SELECTIVE_MODELS:
                continue  # Skip intentionally selective models
            silver_sql = silver_file.read_text()
            bronze_refs = _find_bronze_refs(silver_sql)
            bronze_paths = []
            for schema, table in bronze_refs:
                bp = _bronze_path(schema, table)
                if bp is not None:
                    bronze_paths.append(bp)
            if bronze_paths:
                cases.append((silver_file, bronze_paths, label))
    return cases


_CASES = _collect_silver_cases()


@pytest.mark.parametrize("silver_path,bronze_paths,label", _CASES, ids=[c[2] for c in _CASES])
def test_silver_carries_all_bronze_columns(silver_path, bronze_paths, label):
    """FR-001: Every non-system bronze column must appear in the silver model."""
    missing = _find_missing_columns(silver_path, bronze_paths)
    assert not missing, (
        f"Silver model {label} drops columns from bronze upstreams:\n"
        + "\n".join(f"  {bronze}: {cols}" for bronze, cols in missing.items())
    )


# ---------------------------------------------------------------------------
# JSONB carry-forward test (FR-003)
# ---------------------------------------------------------------------------

_JSONB_BRONZE_COLS = {
    "mol_bronze.uspto_patents": ["cpc_codes", "inventors"],
    "mol_bronze.epo_patents": ["ipc_codes", "cpc_codes", "inventors"],
    "mol_bronze.euipo_trademarks": ["nice_classes"],
    "mol_bronze.euipo_designs": ["locarno_classes"],
    "mol_bronze.uspto_trademarks": ["nice_classes", "us_classes"],
}


@pytest.mark.parametrize("bronze_ref,cols", _JSONB_BRONZE_COLS.items())
def test_jsonb_columns_not_cast_to_text(bronze_ref, cols):
    """FR-003: JSONB columns must not be cast to TEXT in silver models."""
    schema, table = bronze_ref.split(".")
    domain_map = {"mol_bronze": "molecules", "hcs_bronze": "hcs"}
    domain = domain_map.get(schema, "molecules")
    silver_dir = MODELS_BASE / domain / "silver"
    if not silver_dir.exists():
        pytest.skip("Silver directory not found")
    for silver_file in silver_dir.glob("*.sql"):
        sql = silver_file.read_text()
        if bronze_ref not in sql and bronze_ref.replace("mol_", "") not in sql:
            continue  # This silver doesn't reference this bronze
        for col in cols:
            bad_cast = rf"{re.escape(col)}\s*::\s*TEXT"
            if re.search(bad_cast, sql, re.IGNORECASE):
                pytest.fail(
                    f"{silver_file.name}: JSONB column `{col}` from {bronze_ref} is cast to TEXT"
                )


# ---------------------------------------------------------------------------
# Standalone audit function (called by T020 to generate report)
# ---------------------------------------------------------------------------

def generate_column_retention_report() -> str:
    """Run the column retention audit and return a text report."""
    lines = ["# Silver Column Retention Audit Report", "# Generated by test_silver_column_retention.py", ""]
    failing: list[tuple[str, dict]] = []
    passing: list[str] = []

    for silver_path, bronze_paths, label in _CASES:
        missing = _find_missing_columns(silver_path, bronze_paths)
        if missing:
            failing.append((label, missing))
        else:
            passing.append(label)

    lines.append(f"TOTAL MODELS AUDITED: {len(_CASES)}")
    lines.append(f"PASSING: {len(passing)}")
    lines.append(f"FAILING: {len(failing)}")
    lines.append("")
    lines.append("## FAILING MODELS")
    lines.append("")

    for label, missing in failing:
        lines.append(f"### {label}")
        for bronze, cols in missing.items():
            lines.append(f"  Missing from {bronze}: {', '.join(cols)}")
        lines.append("")

    lines.append("## PASSING MODELS")
    lines.append("")
    for m in passing:
        lines.append(f"  OK: {m}")

    return "\n".join(lines)


if __name__ == "__main__":
    report = generate_column_retention_report()
    out_path = Path("/tmp/wave2-t020-failing-models.txt")
    out_path.write_text(report)
    print(f"Report written to {out_path}")
    print(report[:2000])
