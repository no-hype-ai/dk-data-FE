#!/usr/bin/env python3
"""Audit silver SQLMesh models for missing bronze columns.

Parses each silver SQL model to find its upstream bronze source(s),
then diffs the bronze SELECT columns against the silver SELECT columns.
Reports missing domain columns that should be carried forward.

Usage:
    python scripts/audit_silver_columns.py
    python scripts/audit_silver_columns.py --model mol_silver.drugbank
    python scripts/audit_silver_columns.py --domain mol_silver
"""

import argparse
import re
import sys
from pathlib import Path

# Columns excluded from silver by design (system/ETL metadata)
EXCLUDED_COLUMNS = {
    "raw_json",
    "raw_source_id",
    "processed_to_bronze",
    "processed_to_silver",
    "_bronze_loaded_at",
    "_loaded_at",
    "_source_file",
    "request_timestamp",  # SQLMesh time_column, not a domain column
    "processed_at",
    "processing_error",
    "request_headers",
    "response_headers",
    "response_size_bytes",
    "response_time_ms",
    "response_body_hash",
    "api_endpoint",
    "api_version",
    "request_params",
    "response_status",
}

# Bronze surrogate keys that silver regenerates
EXCLUDED_ID_COLUMNS = {
    "id",
}

MODELS_DIR = Path(__file__).parent.parent / "src" / "dk_data" / "sqlmesh" / "models"

DOMAIN_MAP = {
    "mol_silver": ("molecules/silver", "molecules/bronze"),
    "hcs_silver": ("hcs/silver", "hcs/bronze"),
    "ind_silver": ("ind/silver", "ind/bronze"),
}


def extract_select_columns(sql: str) -> list[str]:
    """Extract column names/aliases from a SQL SELECT statement.

    Looks for patterns like:
    - column_name
    - column_name AS alias
    - expression AS alias
    - table.column_name AS alias
    """
    columns = []

    # Find the main SELECT ... FROM block
    # Remove MODEL(...) block first
    sql_clean = re.sub(r"MODEL\s*\(.*?\);", "", sql, flags=re.DOTALL | re.IGNORECASE)

    # Find SELECT ... FROM
    select_match = re.search(
        r"\bSELECT\b(.*?)\bFROM\b",
        sql_clean,
        re.DOTALL | re.IGNORECASE,
    )
    if not select_match:
        return columns

    select_body = select_match.group(1)

    # Remove comments
    select_body = re.sub(r"--[^\n]*", "", select_body)
    select_body = re.sub(r"/\*.*?\*/", "", select_body, flags=re.DOTALL)

    # Split by comma, handling nested parentheses and CASE expressions
    depth = 0
    current = []
    parts = []
    for char in select_body:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Extract the alias (last word after AS, or last word if no AS)
        # Handle: expression AS alias, table.column, plain column
        as_match = re.search(r"\bAS\s+(\w+)\s*$", part, re.IGNORECASE)
        if as_match:
            columns.append(as_match.group(1).lower())
        else:
            # Last word, possibly qualified (table.column)
            words = re.findall(r"[\w.]+", part)
            if words:
                last = words[-1]
                # Strip table prefix
                if "." in last:
                    last = last.split(".")[-1]
                columns.append(last.lower())

    return columns


def extract_from_sources(sql: str) -> list[str]:
    """Extract bronze table references from FROM/JOIN clauses."""
    sources = []

    # Remove MODEL block
    sql_clean = re.sub(r"MODEL\s*\(.*?\);", "", sql, flags=re.DOTALL | re.IGNORECASE)

    # Find FROM table references (schema.table pattern)
    from_matches = re.findall(
        r"\bFROM\s+([\w]+\.[\w]+)",
        sql_clean,
        re.IGNORECASE,
    )
    sources.extend(from_matches)

    # Find JOIN table references
    join_matches = re.findall(
        r"\bJOIN\s+([\w]+\.[\w]+)",
        sql_clean,
        re.IGNORECASE,
    )
    sources.extend(join_matches)

    # Filter to bronze sources only
    bronze_sources = [
        s for s in sources
        if any(
            prefix in s.lower()
            for prefix in ("mol_bronze.", "hcs_bronze.", "ind_bronze.")
        )
    ]

    return list(set(bronze_sources))


def find_bronze_model_file(bronze_ref: str) -> Path | None:
    """Find the SQL file for a bronze model reference like 'mol_bronze.drugbank'."""
    schema, table = bronze_ref.split(".", 1)

    schema_to_dir = {
        "mol_bronze": "molecules/bronze",
        "hcs_bronze": "hcs/bronze",
        "ind_bronze": "ind/bronze",
    }

    bronze_dir = MODELS_DIR / schema_to_dir.get(schema, "")
    if not bronze_dir.exists():
        return None

    # Try exact match
    candidates = [
        bronze_dir / f"{table}.sql",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def audit_silver_model(silver_file: Path) -> dict:
    """Audit a single silver model for missing bronze columns."""
    sql = silver_file.read_text()
    silver_columns = set(extract_select_columns(sql))
    bronze_sources = extract_from_sources(sql)

    result = {
        "silver_file": str(silver_file.relative_to(MODELS_DIR)),
        "silver_columns": sorted(silver_columns),
        "bronze_sources": bronze_sources,
        "missing_columns": [],
        "bronze_columns": {},
    }

    all_bronze_columns = set()
    for source in bronze_sources:
        bronze_file = find_bronze_model_file(source)
        if bronze_file is None:
            continue

        bronze_sql = bronze_file.read_text()
        bronze_cols = set(extract_select_columns(bronze_sql))
        result["bronze_columns"][source] = sorted(bronze_cols)
        all_bronze_columns.update(bronze_cols)

    # Find missing: in bronze but not in silver, excluding system columns
    missing = (
        all_bronze_columns
        - silver_columns
        - EXCLUDED_COLUMNS
        - EXCLUDED_ID_COLUMNS
    )

    # Also exclude columns that are just differently named (common aliases)
    result["missing_columns"] = sorted(missing)

    return result


def main():
    parser = argparse.ArgumentParser(description="Audit silver models for missing bronze columns")
    parser.add_argument("--model", help="Audit a specific model (e.g., mol_silver.drugbank)")
    parser.add_argument("--domain", help="Audit a domain (mol_silver, hcs_silver, ind_silver)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all columns")
    args = parser.parse_args()

    total_gaps = 0
    total_models = 0
    models_with_gaps = 0

    for domain, (silver_dir, bronze_dir) in DOMAIN_MAP.items():
        if args.domain and args.domain != domain:
            continue

        silver_path = MODELS_DIR / silver_dir
        if not silver_path.exists():
            continue

        for silver_file in sorted(silver_path.glob("*.sql")):
            model_name = f"{domain}.{silver_file.stem}"

            if args.model and args.model != model_name:
                continue

            total_models += 1
            result = audit_silver_model(silver_file)

            if result["missing_columns"]:
                models_with_gaps += 1
                total_gaps += len(result["missing_columns"])
                print(f"GAPS  {model_name}: {len(result['missing_columns'])} missing columns")
                for col in result["missing_columns"]:
                    print(f"  - {col}")
                if args.verbose:
                    print(f"  Bronze sources: {result['bronze_sources']}")
                    print(f"  Silver columns: {result['silver_columns']}")
                print()
            else:
                print(f"OK    {model_name}")

    print(f"\n{'='*60}")
    print(f"Total models audited: {total_models}")
    print(f"Models with gaps: {models_with_gaps}")
    print(f"Total missing columns: {total_gaps}")
    print(f"Models complete: {total_models - models_with_gaps}")

    return 1 if total_gaps > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
