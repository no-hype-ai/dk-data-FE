#!/usr/bin/env python3
"""
Fetch real data from all external sources, run SQLMesh, and export CSVs.

Phases:
  1. API-based sources (48) — run via main.py --max-records 1000 (mol, ind, hcs)
  2. CMS PUF sources — fetch 1000 rows via data-api JSON → temp CSV → loader
  3. SQLMesh plan --restate-model for all models
  4. Export all medallion views as 1000-row CSVs to data-samples/

Usage:
  POSTGRES_PASSWORD=... python3 scripts/fetch_all_real_data.py
  POSTGRES_PASSWORD=... python3 scripts/fetch_all_real_data.py --phase 1
  POSTGRES_PASSWORD=... python3 scripts/fetch_all_real_data.py --phase 2
  POSTGRES_PASSWORD=... python3 scripts/fetch_all_real_data.py --phase 3
  POSTGRES_PASSWORD=... python3 scripts/fetch_all_real_data.py --phase 4
"""

import argparse
import csv
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import requests

# ── Project path setup ───────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("fetch_all")

# ── CMS streaming API ─────────────────────────────────────────────────────────
CMS_DATA_API = "https://data.cms.gov/data-api/v1/dataset"

# Verified working UUIDs (tested 2026-03-29)
CMS_STREAMING_SOURCES: dict[str, dict] = {
    "cms_geographic_variation": {
        "uuid": "6219697b-8f6c-4164-bed4-cd9317c58ebc",
        "year": 2022,
    },
    "cms_part_d_spending": {
        "uuid": "7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b",
        "year": 2022,
    },
    "cms_part_b_spending": {
        "uuid": "76a714ad-3a2c-43ac-b76d-9dadf8f7d890",
        "year": 2022,
    },
    "cms_physician_puf": {
        "uuid": "8889d81e-2ee7-448f-8713-f071038289b5",
        "year": 2022,
    },
    "cms_physician_puf_services": {
        "uuid": "92396110-2aed-4d63-a6a2-5d6207d46a29",
        "year": 2022,
    },
    "cms_inpatient_puf": {
        "uuid": "ee6fb1a5-39b9-46b3-a980-a7284551a732",
        "year": 2022,
    },
    "cms_outpatient_puf": {
        "uuid": "ccbc9a44-40d4-46b4-a709-5caa59212e50",
        "year": 2022,
    },
    "cms_dme_puf": {
        "uuid": "a2d56d3f-3531-4315-9d87-e29986516b41",
        "year": 2022,
    },
    "cms_ordering_providers": {
        "uuid": "c99b5865-1119-4436-bb80-c5af2773ea1f",
        "year": 2022,
    },
    "cms_referring_providers": {
        "uuid": "c99b5865-1119-4436-bb80-c5af2773ea1f",  # same combined file
        "year": 2022,
    },
    "cms_opioid_puf": {
        "uuid": "94d00f36-73ce-4520-9b3f-83cd3cded25c",
        "year": 2022,
    },
    "cms_telehealth_puf": {
        "uuid": "939226be-b107-476e-8777-f199a840138a",
        "year": 2022,
    },
    "cms_medicaid_drug_spending": {
        "uuid": "be64fce3-e835-4589-b46b-024198e524a6",
        "year": 2022,
    },
    "cms_part_d_prescriber": {
        "uuid": "9552739e-3d05-4c1b-8eff-ecabf391e2e5",
        "year": 2022,
    },
    "cms_enrollment_puf": {
        "uuid": "d7fabe1e-d19b-4333-9eff-e80e0643f2fd",
        "year": 2022,
    },
    "cms_snf_puf": {
        "uuid": "eaed338b-847e-41b1-a4d3-a206f40dc72b",
        "year": 2022,
    },
    "cms_hospice_puf": {
        "uuid": "4e73f1b5-82cb-4682-8ad2-28493f0b6840",
        "year": 2022,
    },
    "cms_lab_services": {
        "uuid": "0e57f57d-0acc-4c9c-8f8c-973e3f4a3c4b",
        "year": 2022,
    },
    "cms_claim_type_puf": {
        "uuid": "164fc736-4179-4100-9f79-592b69e41975",
        "year": 2022,
    },
    "cms_cost_reports_puf": {
        "uuid": "44060663-47d8-4ced-a115-b53b4c270acb",
        "year": 2022,
    },
}

# API-based sources that work with --max-records
API_BASED_SOURCES = [
    # Healthcare / HCS
    "cms_geographic_variation",  # also in streaming, but its fetcher handles it well
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
    "hrsa",
    # Molecular / pharma
    "pubmed",
    "europepmc",
    "nih_reporter",
    "openalex_ci",
    "drugbank",
    "ema_regulatory",
    "cochrane",
    "bindingdb",
    "sider",
    "pdb",
    "uniprot",
    "pharmgkb",
    "kegg_drug",
    "tdc_admet",
    "rxnorm",
    "who_icd",
    "who_inn",
    # IP / patents
    "epo_ops",
    "uspto_patents",
    "uspto_ci",
    "euipo_trademarks",
    "euipo_designs",
    "uspto_trademarks",
    # Financial / market
    "sec_edgar",
    "hta_bodies",
    "medical_news",
    "journal_rss",
    "orcid",
]

ROWS = 1000


def fetch_cms_streaming(source_name: str, uuid: str, year: int, rows: int = ROWS) -> Optional[str]:
    """Fetch rows from CMS streaming API, return path to temp CSV file."""
    url = f"{CMS_DATA_API}/{uuid}/data"
    try:
        logger.info(f"  Fetching {rows} rows from CMS API: {source_name} ({uuid[:8]}...)")
        r = requests.get(url, params={"size": rows, "offset": 0}, timeout=60)
        r.raise_for_status()
        records = r.json()
        if not records:
            logger.warning(f"  {source_name}: API returned 0 records")
            return None

        # Write to temp CSV
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", prefix=f"cms_{source_name}_",
            delete=False, newline=""
        )
        writer = csv.DictWriter(tmp, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
        tmp.close()
        logger.info(f"  {source_name}: {len(records)} rows → {tmp.name}")
        return tmp.name
    except Exception as e:
        logger.error(f"  {source_name} fetch failed: {e}")
        return None


def run_source_via_cli(source: str, max_records: int = ROWS) -> dict:
    """Run ingestion for a source via subprocess."""
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}
    cmd = [
        sys.executable, "-m", "dk_data.ingestion.main",
        source, "--max-records", str(max_records),
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            return {"status": "ok", "source": source, "stdout": result.stdout[-500:]}
        else:
            return {"status": "error", "source": source, "stderr": result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "source": source}
    except Exception as e:
        return {"status": "exception", "source": source, "error": str(e)}


def phase1_api_sources(workers: int = 8):
    """Run all API-based fetchers with --max-records 1000."""
    logger.info(f"\n{'='*60}")
    logger.info(f"PHASE 1: API-based sources ({len(API_BASED_SOURCES)} sources, {workers} workers)")
    logger.info('='*60)

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_source_via_cli, src): src for src in API_BASED_SOURCES}
        for future in as_completed(futures):
            src = futures[future]
            result = future.result()
            status = result["status"]
            logger.info(f"  [{status:8s}] {src}")
            results.append(result)

    ok = sum(1 for r in results if r["status"] == "ok")
    err = len(results) - ok
    logger.info(f"\nPhase 1 complete: {ok} OK, {err} failed")
    return results


def phase2_cms_streaming():
    """Fetch CMS PUF data via streaming API → temp CSV → file loader."""
    logger.info(f"\n{'='*60}")
    logger.info(f"PHASE 2: CMS streaming API ({len(CMS_STREAMING_SOURCES)} sources)")
    logger.info('='*60)

    # Import loaders
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from dk_data.ingestion.main import SOURCES, run_ingestion

    results = []
    for source_name, cfg in CMS_STREAMING_SOURCES.items():
        uuid = cfg["uuid"]
        year = cfg["year"]

        # Skip if source not in SOURCES dict
        if source_name not in SOURCES:
            logger.warning(f"  SKIP {source_name}: not in SOURCES dict")
            continue

        tmp_path = fetch_cms_streaming(source_name, uuid, year)
        if not tmp_path:
            results.append({"status": "fetch_failed", "source": source_name})
            continue

        try:
            result = run_ingestion(
                source_name,
                filepath=tmp_path,
                source_year=year,
                max_records=ROWS,
            )
            status = result.get("status", "unknown")
            inserted = result.get("records_inserted", result.get("records", "?"))
            logger.info(f"  [{status:8s}] {source_name}: {inserted} rows loaded")
            results.append({"status": status, "source": source_name, "rows": inserted})
        except Exception as e:
            logger.error(f"  [ERROR   ] {source_name}: {e}")
            results.append({"status": "error", "source": source_name, "error": str(e)})
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        time.sleep(0.3)  # polite delay

    ok = sum(1 for r in results if r.get("status") in ("success", "ok"))
    logger.info(f"\nPhase 2 complete: {ok}/{len(results)} OK")
    return results


def phase3_sqlmesh():
    """Run SQLMesh plan to transform all layers."""
    logger.info(f"\n{'='*60}")
    logger.info("PHASE 3: SQLMesh plan (raw → bronze → silver → gold)")
    logger.info('='*60)

    env = {
        **os.environ,
        "POSTGRES_HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "POSTGRES_PORT": os.getenv("POSTGRES_PORT", "5433"),
        "POSTGRES_USER": os.getenv("POSTGRES_USER", "postgres"),
        "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "POSTGRES_DB": os.getenv("POSTGRES_DB", "dk_data"),
    }

    cmd = [
        "uv", "run", "sqlmesh",
        "-p", "src/dk_data/sqlmesh",
        "plan", "--no-prompts", "--auto-apply",
    ]
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd, cwd=str(PROJECT_ROOT), env=env,
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode == 0:
        logger.info("SQLMesh plan complete")
        logger.info(result.stdout[-1000:])
    else:
        logger.error("SQLMesh plan failed:")
        logger.error(result.stderr[-2000:])

    return result.returncode == 0


def phase4_export():
    """Export 1000-row CSVs from all medallion views."""
    logger.info(f"\n{'='*60}")
    logger.info("PHASE 4: Export data-samples CSVs")
    logger.info('='*60)

    export_script = PROJECT_ROOT / "scripts" / "export_data_samples.py"
    env = {**os.environ}
    result = subprocess.run(
        [sys.executable, str(export_script)],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode == 0:
        logger.info(result.stdout[-2000:])
    else:
        logger.error(result.stderr[-500:])
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Fetch real data from all sources")
    parser.add_argument(
        "--phase", type=int, choices=[1, 2, 3, 4],
        help="Run only this phase (default: all)"
    )
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    phase = args.phase

    if phase is None or phase == 1:
        phase1_api_sources(workers=args.workers)

    if phase is None or phase == 2:
        phase2_cms_streaming()

    if phase is None or phase == 3:
        phase3_sqlmesh()

    if phase is None or phase == 4:
        phase4_export()

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
