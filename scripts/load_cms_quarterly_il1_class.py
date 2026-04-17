#!/usr/bin/env python3
"""One-shot loader for CMS Quarterly Part B + Part D spending data for the IL-1 class.

Closes the 2024-2025 data gap that exists because the annual CMS Spending datasets
lag by ~2 years. The Quarterly datasets are refreshed every quarter and contain
CY2024 (Q1-Q4) and CY2025 (Q1-Q2) rows as of 2026-01-29.

Creates (idempotently):
  mol_bronze.cms_quarterly_part_d_il1
  mol_bronze.cms_quarterly_part_b_il1

Drugs covered: rilonacept, anakinra, canakinumab, colchicine.

Usage:
  python3 scripts/load_cms_quarterly_il1_class.py

Env:
  POSTGRES_HOST, POSTGRES_PORT (default 5433), POSTGRES_DB (default dk_data),
  POSTGRES_USER (default postgres), POSTGRES_PASSWORD
"""
import json
import os
import sys
import time
from typing import Any, Dict, List

import httpx
import psycopg2
from psycopg2.extras import Json

DB_DSN = (
    f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
    f"port={os.getenv('POSTGRES_PORT', '5433')} "
    f"dbname={os.getenv('POSTGRES_DB', 'dk_data')} "
    f"user={os.getenv('POSTGRES_USER', 'postgres')} "
    f"password={os.getenv('POSTGRES_PASSWORD', '1wFs27wL6qwEG2TMtVpjwPzP')}"
)

PART_D_QUARTERLY_UUID = "b4d19308-eba3-430e-a994-063197c3aef5"
PART_B_QUARTERLY_UUID = "bf6a5b3b-31ee-4abb-b1ad-2607a1e7510a"
API_BASE = "https://data.cms.gov/data-api/v1/dataset"

# IL-1 class drugs we care about for Arcalyst competitive analysis.
PART_D_GENERIC_NAMES = ["RILONACEPT", "ANAKINRA", "COLCHICINE", "CANAKINUMAB"]
PART_B_HCPCS = [
    ("J2793", "Rilonacept"),
    ("J0638", "Canakinumab"),
    ("J0207", "Anakinra"),
]

DDL_PART_D = """
CREATE SCHEMA IF NOT EXISTS mol_bronze;
CREATE TABLE IF NOT EXISTS mol_bronze.cms_quarterly_part_d_il1 (
    id            bigserial PRIMARY KEY,
    brnd_name     text,
    gnrc_name     text,
    mftr_name     text,
    year_period   text,          -- e.g. "2024 (Q1-Q4)"
    tot_benes     integer,
    tot_clms      integer,
    tot_spndng    numeric,
    avg_spnd_per_bene numeric,
    avg_spnd_per_clm  numeric,
    drug_uses     text,
    raw_json      jsonb,
    ingested_at   timestamptz DEFAULT now(),
    UNIQUE (gnrc_name, mftr_name, year_period)
);
CREATE INDEX IF NOT EXISTS ix_q_partd_gnrc ON mol_bronze.cms_quarterly_part_d_il1 (gnrc_name);
CREATE INDEX IF NOT EXISTS ix_q_partd_year ON mol_bronze.cms_quarterly_part_d_il1 (year_period);
"""

DDL_PART_B = """
CREATE TABLE IF NOT EXISTS mol_bronze.cms_quarterly_part_b_il1 (
    id            bigserial PRIMARY KEY,
    hcpcs_cd      text,
    hcpcs_desc    text,
    brnd_name     text,
    gnrc_name     text,
    year_period   text,
    tot_benes     integer,
    tot_clms      integer,
    tot_spndng    numeric,
    avg_spnd_per_bene numeric,
    avg_spnd_per_clm  numeric,
    raw_json      jsonb,
    ingested_at   timestamptz DEFAULT now(),
    UNIQUE (hcpcs_cd, year_period)
);
CREATE INDEX IF NOT EXISTS ix_q_partb_hcpcs ON mol_bronze.cms_quarterly_part_b_il1 (hcpcs_cd);
"""

UPSERT_PART_D = """
INSERT INTO mol_bronze.cms_quarterly_part_d_il1
    (brnd_name, gnrc_name, mftr_name, year_period,
     tot_benes, tot_clms, tot_spndng,
     avg_spnd_per_bene, avg_spnd_per_clm, drug_uses, raw_json)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (gnrc_name, mftr_name, year_period) DO UPDATE SET
    tot_benes = EXCLUDED.tot_benes,
    tot_clms  = EXCLUDED.tot_clms,
    tot_spndng = EXCLUDED.tot_spndng,
    avg_spnd_per_bene = EXCLUDED.avg_spnd_per_bene,
    avg_spnd_per_clm  = EXCLUDED.avg_spnd_per_clm,
    raw_json = EXCLUDED.raw_json,
    ingested_at = now();
"""

UPSERT_PART_B = """
INSERT INTO mol_bronze.cms_quarterly_part_b_il1
    (hcpcs_cd, hcpcs_desc, brnd_name, gnrc_name, year_period,
     tot_benes, tot_clms, tot_spndng,
     avg_spnd_per_bene, avg_spnd_per_clm, raw_json)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (hcpcs_cd, year_period) DO UPDATE SET
    tot_benes = EXCLUDED.tot_benes,
    tot_clms  = EXCLUDED.tot_clms,
    tot_spndng = EXCLUDED.tot_spndng,
    avg_spnd_per_bene = EXCLUDED.avg_spnd_per_bene,
    avg_spnd_per_clm  = EXCLUDED.avg_spnd_per_clm,
    raw_json = EXCLUDED.raw_json,
    ingested_at = now();
"""


def _to_int(v: Any) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _to_num(v: Any) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def fetch_part_d(client: httpx.Client, generic_name: str) -> List[Dict]:
    url = f"{API_BASE}/{PART_D_QUARTERLY_UUID}/data"
    r = client.get(url, params={"filter[Gnrc_Name]": generic_name}, timeout=60.0)
    r.raise_for_status()
    return r.json()


def fetch_part_b(client: httpx.Client, hcpcs: str) -> List[Dict]:
    url = f"{API_BASE}/{PART_B_QUARTERLY_UUID}/data"
    r = client.get(url, params={"filter[HCPCS_Cd]": hcpcs}, timeout=60.0)
    r.raise_for_status()
    return r.json()


def main() -> int:
    print("[cms-quarterly-il1] Connecting to Postgres...")
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(DDL_PART_D)
    cur.execute(DDL_PART_B)

    with httpx.Client() as client:
        # --- Part D ---
        total_d = 0
        for gn in PART_D_GENERIC_NAMES:
            print(f"[cms-quarterly-il1] Fetching Part D for {gn}...")
            rows = fetch_part_d(client, gn)
            print(f"  got {len(rows)} rows")
            for r in rows:
                cur.execute(
                    UPSERT_PART_D,
                    (
                        r.get("Brnd_Name"),
                        r.get("Gnrc_Name"),
                        r.get("Mftr_Name"),
                        r.get("Year"),
                        _to_int(r.get("Tot_Benes")),
                        _to_int(r.get("Tot_Clms")),
                        _to_num(r.get("Tot_Spndng")),
                        _to_num(r.get("Avg_Spnd_Per_Bene")),
                        _to_num(r.get("Avg_Spnd_Per_Clm")),
                        r.get("Drug_Uses"),
                        Json(r),
                    ),
                )
                total_d += 1
            time.sleep(0.2)

        # --- Part B ---
        total_b = 0
        for hcpcs, label in PART_B_HCPCS:
            print(f"[cms-quarterly-il1] Fetching Part B for {hcpcs} ({label})...")
            rows = fetch_part_b(client, hcpcs)
            print(f"  got {len(rows)} rows")
            for r in rows:
                cur.execute(
                    UPSERT_PART_B,
                    (
                        r.get("HCPCS_Cd"),
                        r.get("HCPCS_Desc"),
                        r.get("Brnd_Name"),
                        r.get("Gnrc_Name"),
                        r.get("Year"),
                        _to_int(r.get("Tot_Benes")),
                        _to_int(r.get("Tot_Clms")),
                        _to_num(r.get("Tot_Spndng")),
                        _to_num(r.get("Avg_Spnd_Per_Bene")),
                        _to_num(r.get("Avg_Spnd_Per_Clm")),
                        Json(r),
                    ),
                )
                total_b += 1
            time.sleep(0.2)

    print(f"[cms-quarterly-il1] Part D rows upserted: {total_d}")
    print(f"[cms-quarterly-il1] Part B rows upserted: {total_b}")

    cur.execute(
        "SELECT gnrc_name, mftr_name, year_period, tot_benes, tot_clms, "
        "ROUND(tot_spndng/1e6, 2) AS spend_m "
        "FROM mol_bronze.cms_quarterly_part_d_il1 "
        "WHERE mftr_name = 'Overall' "
        "ORDER BY gnrc_name, year_period;"
    )
    print("\n[cms-quarterly-il1] Part D summary (Mftr_Name='Overall'):")
    print(f"  {'drug':<14} {'year':<16} {'benes':>8} {'claims':>8} {'spend ($M)':>14}")
    for row in cur.fetchall():
        gn, mn, yr, benes, clms, sp = row
        print(f"  {gn:<14} {yr:<16} {benes:>8} {clms:>8} {sp:>14}")

    cur.execute(
        "SELECT hcpcs_cd, gnrc_name, year_period, tot_benes, tot_clms, "
        "ROUND(tot_spndng/1e6, 2) AS spend_m "
        "FROM mol_bronze.cms_quarterly_part_b_il1 "
        "ORDER BY hcpcs_cd, year_period;"
    )
    print("\n[cms-quarterly-il1] Part B summary:")
    print(f"  {'hcpcs':<8} {'drug':<16} {'year':<16} {'benes':>8} {'claims':>8} {'spend ($M)':>14}")
    for row in cur.fetchall():
        hc, gn, yr, benes, clms, sp = row
        print(f"  {hc:<8} {gn:<16} {yr:<16} {benes:>8} {clms:>8} {sp:>14}")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
