#!/usr/bin/env python3
"""Export 1000-row CSVs from every medallion view to data-samples/.

Directory structure:
  data-samples/{layer}/{domain}/{schema}.{table}.csv

Layer mapping:
  *_raw    → raw
  *_bronze → bronze
  *_silver → silver
  *_gold   → gold

Domain mapping:
  hcs_*    → hcs
  mol_*    → mol
  ind_*    → ind
"""

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2

PG = dict(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", "5433")),
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD", ""),
    database=os.getenv("POSTGRES_DB", "dk_data"),
)

SCHEMAS = [
    "hcs_raw", "hcs_bronze", "hcs_silver", "hcs_gold",
    "mol_raw", "mol_bronze", "mol_silver", "mol_gold",
    "ind_silver", "ind_gold",
]

LIMIT = 1000
BASE = Path(__file__).parent.parent / "data-samples"


def layer(schema: str) -> str:
    if schema.endswith("_raw"):
        return "raw"
    if schema.endswith("_bronze"):
        return "bronze"
    if schema.endswith("_silver"):
        return "silver"
    if schema.endswith("_gold"):
        return "gold"
    return "other"


def domain(schema: str) -> str:
    if schema.startswith("hcs_"):
        return "hcs"
    if schema.startswith("mol_"):
        return "mol"
    if schema.startswith("ind_"):
        return "ind"
    return "other"


RAW_SCHEMAS = ["hcs_raw", "mol_raw"]


def get_objects(cur) -> list[tuple[str, str]]:
    """Get all views (medallion schemas) + tables (raw schemas)."""
    placeholders = ",".join(["%s"] * len(SCHEMAS))
    cur.execute(
        f"""
        SELECT schemaname, viewname
        FROM pg_views
        WHERE schemaname IN ({placeholders})
        ORDER BY schemaname, viewname
        """,
        SCHEMAS,
    )
    views = cur.fetchall()

    # Raw schemas use actual tables (no SQLMesh views)
    raw_placeholders = ",".join(["%s"] * len(RAW_SCHEMAS))
    cur.execute(
        f"""
        SELECT schemaname, tablename
        FROM pg_tables
        WHERE schemaname IN ({raw_placeholders})
        ORDER BY schemaname, tablename
        """,
        RAW_SCHEMAS,
    )
    tables = cur.fetchall()

    # Deduplicate (views take precedence)
    seen = set(views)
    combined = list(views)
    for t in tables:
        if t not in seen:
            combined.append(t)
            seen.add(t)
    return sorted(combined)


def export_view(cur, schema: str, table: str) -> tuple[int, str]:
    """Export up to LIMIT rows. Returns (row_count, csv_path)."""
    lyr = layer(schema)
    dom = domain(schema)
    out_dir = BASE / lyr / dom
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{schema}.{table}.csv"

    cur.execute(
        f"SELECT * FROM {schema}.{table} LIMIT {LIMIT}"
    )
    rows = cur.fetchall()
    col_names = [desc[0] for desc in cur.description]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(col_names)
        for row in rows:
            # Convert non-serializable types to string
            writer.writerow([
                str(v) if v is not None and not isinstance(v, (int, float, str, bool)) else v
                for v in row
            ])

    return len(rows), str(csv_path)


def update_manifest(results: list[dict]) -> None:
    manifest_path = BASE / "manifest.json"
    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_files": len(results),
        "total_rows": sum(r["rows"] for r in results),
        "sources": results,
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest updated: {manifest_path}")


def main():
    conn = psycopg2.connect(**PG)
    conn.autocommit = True
    cur = conn.cursor()

    objects = get_objects(cur)
    print(f"Found {len(objects)} objects across {len(SCHEMAS) + len(RAW_SCHEMAS)} schemas\n")

    results = []
    errors = []
    total_rows = 0

    for schema, table in objects:
        try:
            row_count, csv_path = export_view(cur, schema, table)
            total_rows += row_count
            results.append({"schema": schema, "table": table, "rows": row_count, "path": csv_path})
            status = "OK" if row_count > 0 else "EMPTY"
            print(f"  [{status:5s}] {schema}.{table} → {row_count} rows")
        except Exception as e:
            errors.append({"schema": schema, "table": table, "error": str(e)})
            print(f"  [ERROR] {schema}.{table}: {e}", file=sys.stderr)

    cur.close()
    conn.close()

    update_manifest(results)

    print(f"\n{'='*60}")
    print(f"Exported {len(results)} views, {total_rows:,} total rows")
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  {e['schema']}.{e['table']}: {e['error']}")
    else:
        print("No errors.")

    # Summary by schema
    print("\nRows per schema:")
    schema_totals: dict[str, int] = {}
    for r in results:
        schema_totals[r["schema"]] = schema_totals.get(r["schema"], 0) + r["rows"]
    for s, count in sorted(schema_totals.items()):
        print(f"  {s:<20} {count:>8,} rows across {sum(1 for r in results if r['schema']==s)} tables")


if __name__ == "__main__":
    main()
