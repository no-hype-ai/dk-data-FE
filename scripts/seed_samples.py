#!/usr/bin/env python3
"""Seed the database with real external data (1,000 rows per source) and export CSV samples.

This script does three things in sequence:
  1. DOWNLOAD — for CMS PUF file sources, fetch the actual file from data.cms.gov
                (uses the CKAN API; cached for 30 days in /tmp/cms_downloads/)
  2. LOAD     — run every source's real loader with --limit 1000
                (API sources: live HTTP calls; CMS sources: loaded from downloaded file)
  3. EXPORT   — write 1,000-row CSV samples from every DB table into data-samples/

Usage:
    # All sources (API + CMS file)
    python scripts/seed_samples.py

    # API-only sources (no file downloads needed)
    python scripts/seed_samples.py --category api

    # CMS file sources only
    python scripts/seed_samples.py --category cms

    # Single source
    python scripts/seed_samples.py --source pubmed
    python scripts/seed_samples.py --source cms_nppes --year 2023

    # Skip loading, just export what's already in the DB
    python scripts/seed_samples.py --export-only

    # Skip export, just load
    python scripts/seed_samples.py --load-only

Options:
    --limit N       Rows per source (default: 1000)
    --year YYYY     Source year for CMS PUF files (default: 2023)
    --force         Re-download CMS files even if cached
    --workers N     Parallel API workers (default: 4; CMS is always sequential)
    --category      api | cms | all (default: all)
    --source        Run a single named source
    --load-only     Skip export step
    --export-only   Skip load step, go straight to export

Environment variables (from Doppler or .env):
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
    NCBI_API_KEY     (optional — speeds up PubMed)
    Any other API keys the fetchers use (see .env.example)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("seed_samples")

REPO_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Source catalogue
# Mirrors the SOURCES dict in ingestion/main.py but adds download metadata.
# ---------------------------------------------------------------------------

# API sources — fetched live from external services
API_SOURCES: list[dict] = [
    # Literature / publications
    {"key": "pubmed",          "days_back": 30},
    {"key": "europepmc",       "days_back": 30},
    {"key": "nih_reporter",    "days_back": 90},
    {"key": "openalex_ci",     "days_back": 90},
    {"key": "journal_rss",     "days_back": None},
    {"key": "medical_news",    "days_back": 30},
    {"key": "cochrane",        "days_back": 180},
    # Regulatory / HTA
    {"key": "ema_regulatory",  "days_back": 90},
    {"key": "hta_bodies",      "days_back": 90},
    # Financial / IP
    {"key": "sec_edgar",       "days_back": 90},
    {"key": "uspto_patents",   "days_back": 90,  "credential_gated": True},
    {"key": "uspto_ci",        "days_back": 90},
    {"key": "uspto_trademarks","days_back": None},
    {"key": "euipo_trademarks","days_back": 90,  "credential_gated": True},
    {"key": "euipo_designs",   "days_back": 90,  "credential_gated": True},
    {"key": "epo_ops",         "days_back": 90,  "credential_gated": True},
    # Drug / molecule data
    {"key": "drugbank",        "days_back": None, "credential_gated": True},
    {"key": "uniprot",         "days_back": None},
    {"key": "pdb",             "days_back": None},
    {"key": "orcid",           "days_back": None},
    {"key": "who_icd",         "days_back": None},
    {"key": "bindingdb",       "days_back": None},
    {"key": "sider",           "days_back": None},
    # Drug vocabulary / pharmacology
    {"key": "rxnorm",          "days_back": None},
    {"key": "who_inn",         "days_back": None},
    {"key": "pharmgkb",        "days_back": None, "credential_gated": True},
    {"key": "kegg_drug",       "days_back": None},
    {"key": "tdc_admet",       "days_back": None},
    # CMS API-based sources (no file download needed)
    {"key": "cms_geographic_variation",  "days_back": None},
    {"key": "cms_care_compare",          "days_back": None},
    {"key": "cms_chow",                  "days_back": None},
    {"key": "cms_ddinter",               "days_back": None},
    {"key": "cms_dmepos",                "days_back": None},
    {"key": "cms_formulary",             "days_back": None},
    {"key": "cms_hcris",                 "days_back": None},
    {"key": "cms_hospital_affiliation",  "days_back": None},
    {"key": "cms_hospital_quality",      "days_back": None},
    {"key": "cms_magnet",                "days_back": None},
    {"key": "cms_ndc",                   "days_back": None},
    {"key": "cms_nucc",                  "days_back": None},
    {"key": "cms_pecos",                 "days_back": None},
    {"key": "cms_pos",                   "days_back": None},
    {"key": "cms_post_acute",            "days_back": None},
    {"key": "cms_rbcs",                  "days_back": None},
    {"key": "cms_stabilis",              "days_back": None},
    {"key": "cms_usp",                   "days_back": None},
    # Healthcare system / shortage areas
    {"key": "hrsa",                      "days_back": None},
]

# CMS PUF file sources — downloaded from data.cms.gov, then loaded with --batch-size
CMS_SOURCES: list[dict] = [
    {"key": "cms_nppes",                 "cms_key": "cms_nppes"},
    {"key": "cms_physician_puf",         "cms_key": "cms_physician_puf"},
    {"key": "cms_physician_puf_services","cms_key": "cms_physician_puf_services"},
    {"key": "cms_part_d_spending",       "cms_key": "cms_part_d_spending"},
    {"key": "cms_part_b_spending",       "cms_key": "cms_part_b_spending"},
    {"key": "cms_open_payments",         "cms_key": "cms_open_payments"},
    {"key": "cms_inpatient_puf",         "cms_key": "cms_inpatient_puf"},
    {"key": "cms_hospital_general_info", "cms_key": "cms_hospital_general_info"},
    {"key": "cms_medicare_advantage",    "cms_key": "cms_medicare_advantage"},
    {"key": "cms_medicaid_drug_spending","cms_key": "cms_medicaid_drug_spending"},
    {"key": "cms_dme_puf",               "cms_key": "cms_dme_puf"},
    {"key": "cms_home_health",           "cms_key": "cms_home_health"},
    {"key": "cms_hospice_puf",           "cms_key": "cms_hospice_puf"},
    {"key": "cms_snf_puf",               "cms_key": "cms_snf_puf"},
    {"key": "cms_outpatient_puf",        "cms_key": "cms_outpatient_puf"},
    {"key": "cms_referring_providers",   "cms_key": "cms_referring_providers"},
    {"key": "cms_ordering_providers",    "cms_key": "cms_ordering_providers"},
    {"key": "cms_lab_services",          "cms_key": "cms_lab_services"},
    {"key": "cms_imaging_puf",           "cms_key": "cms_imaging_puf"},
    {"key": "cms_mental_health_puf",     "cms_key": "cms_mental_health_puf"},
    {"key": "cms_opioid_puf",            "cms_key": "cms_opioid_puf"},
    {"key": "cms_telehealth_puf",        "cms_key": "cms_telehealth_puf"},
    {"key": "cms_chronic_conditions",    "cms_key": "cms_chronic_conditions"},
    {"key": "cms_dual_eligible",         "cms_key": "cms_dual_eligible"},
    {"key": "cms_enrollment_puf",        "cms_key": "cms_enrollment_puf"},
    {"key": "cms_claim_type_puf",        "cms_key": "cms_claim_type_puf"},
    {"key": "cms_utilization_puf",       "cms_key": "cms_utilization_puf"},
    {"key": "cms_cost_reports_puf",      "cms_key": "cms_cost_reports_puf"},
    {"key": "cms_cost_reports_puf_lines","cms_key": "cms_cost_reports_puf_lines"},
    # Annual PUF (~25M rows, January release). seed_samples already skips gracefully
    # when the downloader returns no file (non-January runs). To run directly:
    #   python -m dk_data.ingestion.main cms_part_d_prescriber --file <path> --skip-if-no-file
    {"key": "cms_part_d_prescriber",     "cms_key": "cms_part_d_prescriber"},
]

# Legacy file sources — require a manually-provided --file path, no auto-fetch
LEGACY_FILE_SOURCES: list[dict] = [
    {"key": "cms_inpatient",    "requires_file": True, "requires_fiscal_year": True},
    {"key": "cms_hospital_info","requires_file": True},
    {"key": "cms_cost_reports", "requires_file": True},
    {"key": "acc_tvc",          "requires_file": True},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _python() -> str:
    return sys.executable


# Sources that download large files or make many paginated requests.
_LARGE_FILE_TIMEOUT: dict[str, int] = {
    "bindingdb":     2400,  # ~4 GB zip; 40 min
    "pdb":           1200,  # large PDB mirror; 20 min
    "orcid":         1200,  # large ORCID dump; 20 min
    "who_icd":       1800,  # ICD tree traversal; WHO API slow; 30 min
    "kegg_drug":     1200,  # 6000+ individual API calls; 20 min
    "cms_formulary": 1800,  # Large CMS Part D ZIP; 30 min
    "hrsa":           900,  # ~44 MB bulk CSV; 15 min
}
_DEFAULT_TIMEOUT = 600  # 10 minutes for all other sources


def _run_ingestion(source_key: str, extra_args: list[str]) -> tuple[str, bool, str]:
    """Run `python -m dk_data.ingestion.main <source> <extra_args>` as subprocess.

    Returns (source_key, success, stdout_tail).
    """
    cmd = [_python(), "-m", "dk_data.ingestion.main", source_key] + extra_args
    logger.info("Running: %s", " ".join(cmd))
    t0 = time.monotonic()
    timeout = _LARGE_FILE_TIMEOUT.get(source_key, _DEFAULT_TIMEOUT)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=timeout,
        )
        elapsed = round(time.monotonic() - t0, 1)
        tail = (proc.stdout + proc.stderr)[-800:]
        success = proc.returncode == 0
        logger.info(
            "%s %s in %.1fs",
            source_key,
            "succeeded" if success else "FAILED",
            elapsed,
        )
        if not success:
            logger.warning("Output:\n%s", tail)
        return source_key, success, tail
    except subprocess.TimeoutExpired:
        logger.error("%s timed out after %ds", source_key, timeout)
        return source_key, False, "TIMEOUT"
    except Exception as exc:
        logger.error("%s error: %s", source_key, exc)
        return source_key, False, str(exc)


def _download_cms_file(cms_key: str, year: int, force: bool) -> str | None:
    """Call cms_downloader to get the file for a CMS source. Returns local path or None."""
    script = f"""
import sys
sys.path.insert(0, '{REPO_ROOT / "src"}')
from dk_data.ingestion.downloaders.cms_downloader import download_cms_file
result = download_cms_file('{cms_key}', year={year}, force={force})
if result:
    filepath, was_new = result
    print(filepath)
else:
    print('')
"""
    try:
        proc = subprocess.run(
            [_python(), "-c", script],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=1800,  # 30 min — large files
        )
        path = proc.stdout.strip()
        if proc.returncode != 0 or not path:
            logger.warning(
                "Download failed for %s (year=%d): %s", cms_key, year, proc.stderr[-400:]
            )
            return None
        logger.info("Downloaded %s → %s", cms_key, path)
        return path
    except Exception as exc:
        logger.error("Download error for %s: %s", cms_key, exc)
        return None


def _run_export() -> bool:
    """Run generate_data_samples.py to write CSVs from the DB."""
    logger.info("Exporting DB samples to data-samples/...")
    cmd = [_python(), "scripts/generate_data_samples.py"]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Load phases
# ---------------------------------------------------------------------------

def load_api_sources(
    sources: list[dict],
    limit: int,
    workers: int,
) -> list[dict]:
    """Run all API sources in parallel."""
    results = []

    def _run(s: dict) -> dict:
        key = s["key"]
        if s.get("credential_gated"):
            # Check if likely available (rough env var presence check)
            hint = key.upper().replace("-", "_").split("_")[0]
            env_key = f"{hint}_API_KEY"
            if not os.environ.get(env_key):
                logger.warning(
                    "Skipping credential-gated source %s (no %s in env)", key, env_key
                )
                return {"source": key, "status": "skipped", "reason": f"no {env_key}"}

        extra = ["--batch-size", str(limit), "--max-records", str(limit)]
        _, success, tail = _run_ingestion(key, extra)
        if "status: source_unavailable" in tail:
            status_val = "source_unavailable"
        elif success:
            status_val = "success"
        else:
            status_val = "failed"
        return {"source": key, "status": status_val, "output": tail}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_run, s): s["key"] for s in sources}
        for fut in concurrent.futures.as_completed(futs):
            results.append(fut.result())

    return results


def load_cms_sources(
    sources: list[dict],
    limit: int,
    year: int,
    force: bool,
) -> list[dict]:
    """Download + load each CMS PUF source sequentially (disk-bound, large files)."""
    results = []

    for s in sources:
        key = s["key"]
        cms_key = s["cms_key"]

        # 1. Download
        logger.info("=== CMS: %s (year=%d) ===", key, year)
        filepath = _download_cms_file(cms_key, year, force)

        if not filepath:
            results.append({
                "source": key, "status": "skipped",
                "reason": "download failed or no file available for this year",
            })
            continue

        # 2. Load with batch-size
        extra = ["--file", filepath, "--batch-size", str(limit)]
        _, success, tail = _run_ingestion(key, extra)
        results.append({
            "source": key,
            "status": "success" if success else "failed",
            "file": filepath,
            "output": tail,
        })

    return results


def load_legacy_sources(sources: list[dict], limit: int) -> list[dict]:
    """Legacy TAVR/HRSA sources — skip file-required ones (no known file path at runtime)."""
    results = []
    for s in sources:
        key = s["key"]
        if s.get("requires_file"):
            logger.info(
                "Skipping legacy source %s — requires manual --file path. "
                "Run: python -m dk_data.ingestion.main %s --file <path> --batch-size %d",
                key, key, limit,
            )
            results.append({
                "source": key, "status": "skipped",
                "reason": "requires manual --file path",
            })
        else:
            extra = ["--batch-size", str(limit), "--max-records", str(limit)]
            _, success, tail = _run_ingestion(key, extra)
            if "status: source_unavailable" in tail:
                status_val = "source_unavailable"
            elif success:
                status_val = "success"
            else:
                status_val = "failed"
            results.append({"source": key, "status": status_val, "output": tail})
    return results


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _print_summary(all_results: list[dict], elapsed: float) -> None:
    ok   = [r for r in all_results if r["status"] == "success"]
    sk   = [r for r in all_results if r["status"] == "skipped"]
    unav = [r for r in all_results if r["status"] == "source_unavailable"]
    err  = [r for r in all_results if r["status"] == "failed"]

    print(f"\n{'═' * 64}")
    print(f"  SEED SAMPLES COMPLETE — {round(elapsed, 1)}s")
    print(f"{'═' * 64}")
    print(f"  Loaded     : {len(ok):3d} sources")
    print(f"  Skipped    : {len(sk):3d} sources (credential-gated)")
    print(f"  Unavailable: {len(unav):3d} sources (external service offline)")
    print(f"  Failed     : {len(err):3d} sources")
    print(f"{'─' * 64}")

    if unav:
        print("\n  UNAVAILABLE (external service offline):")
        for r in unav:
            print(f"    ~ {r['source']}")

    if err:
        print("\n  FAILED:")
        for r in err:
            print(f"    ✗ {r['source']}")

    if sk:
        print("\n  SKIPPED:")
        for r in sk:
            reason = r.get("reason", "")
            print(f"    - {r['source']}" + (f"  ({reason})" if reason else ""))

    print(f"\n  Samples exported to: {REPO_ROOT / 'data-samples'}")
    print(f"  Manifest           : {REPO_ROOT / 'data-samples' / 'manifest.json'}")
    print(f"{'═' * 64}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed the database with 1,000 real rows per source and export CSVs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--limit", type=int, default=1000,
                        help="Rows per source (default: 1000)")
    parser.add_argument("--year", type=int, default=2023,
                        help="CMS PUF source year (default: 2023)")
    parser.add_argument("--force", action="store_true",
                        help="Force re-download of CMS files even if cached")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel workers for API sources (default: 4)")
    parser.add_argument("--category", choices=["api", "cms", "legacy", "all"],
                        default="all", help="Source category to run (default: all)")
    parser.add_argument("--source", default=None,
                        help="Run a single named source (e.g. pubmed, cms_nppes)")
    parser.add_argument("--load-only", action="store_true",
                        help="Skip export step")
    parser.add_argument("--export-only", action="store_true",
                        help="Skip all loading — just export from what's in the DB")
    parser.add_argument("--skip-puf", action="store_true",
                        help="Skip CMS PUF file-download sources (large files; use for quick local seeds)")
    args = parser.parse_args()

    t_start = time.monotonic()
    all_results: list[dict] = []

    # ── Single-source mode ───────────────────────────────────────────────────
    if args.source:
        source_key = args.source
        # Detect if it's a CMS file source
        cms_entry = next((s for s in CMS_SOURCES if s["key"] == source_key), None)
        if cms_entry:
            filepath = _download_cms_file(cms_entry["cms_key"], args.year, args.force)
            if filepath:
                extra = ["--file", filepath, "--batch-size", str(args.limit)]
                _, ok, tail = _run_ingestion(source_key, extra)
                all_results.append({"source": source_key, "status": "success" if ok else "failed"})
            else:
                logger.error("Could not download file for %s", source_key)
                return 1
        else:
            extra = ["--batch-size", str(args.limit)]
            _, ok, tail = _run_ingestion(source_key, extra)
            all_results.append({"source": source_key, "status": "success" if ok else "failed"})

        if not args.load_only and not args.export_only:
            _run_export()

        _print_summary(all_results, time.monotonic() - t_start)
        return 0

    # ── Full run ─────────────────────────────────────────────────────────────
    if not args.export_only:
        if args.category in ("api", "all"):
            logger.info("─── Loading API sources (%d sources, %d workers) ───",
                        len(API_SOURCES), args.workers)
            all_results += load_api_sources(API_SOURCES, args.limit, args.workers)

        if args.category in ("cms", "all"):
            if args.skip_puf:
                logger.info("─── Skipping CMS PUF sources (--skip-puf) ───")
                all_results += [{"source": s["key"], "status": "skipped", "reason": "--skip-puf"} for s in CMS_SOURCES]
            else:
                logger.info("─── Loading CMS PUF sources (%d sources, year=%d) ───",
                            len(CMS_SOURCES), args.year)
                all_results += load_cms_sources(CMS_SOURCES, args.limit, args.year, args.force)

        if args.category in ("legacy", "all"):
            logger.info("─── Loading legacy file sources ───")
            all_results += load_legacy_sources(LEGACY_FILE_SOURCES, args.limit)

    if not args.load_only:
        export_ok = _run_export()
        if not export_ok:
            logger.error("Export step failed")

    _print_summary(all_results, time.monotonic() - t_start)
    return 0 if all(r["status"] in ("success", "skipped", "source_unavailable") for r in all_results) else 1


if __name__ == "__main__":
    sys.exit(main())
