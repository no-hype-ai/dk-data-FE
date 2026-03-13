#!/usr/bin/env python3
"""Smoke test: fetch + load ≤500 records from every API data source.

Usage:
    python scripts/smoke_test_all_sources.py
    python scripts/smoke_test_all_sources.py --max-records 200
    python scripts/smoke_test_all_sources.py --source cms_rbcs cms_ndc pubmed
    python scripts/smoke_test_all_sources.py --skip cms_nppes cms_hcris  # skip slow ZIP downloads
"""

import argparse
import json
import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Ensure the project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from dk_data.ingestion.main import SOURCES, log_to_meta, _meta_name  # noqa: E402
from dk_data.ingestion.utils.database import init_connection_pool, close_connection_pool  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("smoke_test")

# Sources that download large ZIP files — slow but functional
SLOW_ZIP_SOURCES = {"cms_nppes", "cms_hcris", "drugbank"}
# Sources that need credentials we may not have locally
CREDENTIAL_SOURCES = {"drugbank", "epo_ops"}


def run_one_source(
    source_key: str,
    max_records: int,
    data_dir: str,
) -> dict:
    """Fetch + load a single source with record cap. Returns result dict."""
    source_info = SOURCES[source_key]

    if "fetcher" not in source_info:
        return {"status": "skipped", "reason": "file-based source"}

    fetcher_cls = source_info["fetcher"]
    loader_fn = source_info["loader"]
    meta_source = _meta_name(source_key)

    # Instantiate fetcher
    fetcher = fetcher_cls(data_dir=data_dir)

    # Build fetch kwargs
    fetch_kwargs = {}

    # For PubMed, the param is max_results not max_records
    if source_key == "pubmed":
        fetch_kwargs["max_results"] = max_records
        fetch_kwargs["days_back"] = 7  # narrow window
    else:
        fetch_kwargs["max_records"] = max_records

    # Sources with days_back support — use small window
    default_days = source_info.get("default_days_back")
    if default_days is not None and source_key != "pubmed":
        fetch_kwargs["days_back"] = min(default_days, 7)

    t0 = time.monotonic()
    fetch_result = fetcher.fetch(**fetch_kwargs)
    fetch_duration = time.monotonic() - t0

    # Close fetcher session (Fix H)
    fetcher.close()

    status = fetch_result.get("status", "unknown")
    records = fetch_result.get("records", [])
    record_count = len(records) if isinstance(records, list) else 0
    content_hash = fetch_result.get("hash")

    if status == "failed" or record_count == 0:
        result = {
            "status": status if status == "failed" else "empty",
            "records_fetched": record_count,
            "records_inserted": 0,
            "fetch_seconds": round(fetch_duration, 1),
            "error": fetch_result.get("error"),
        }
        try:
            log_to_meta(meta_source, result)
        except Exception:
            pass
        return result

    # Load into database
    t1 = time.monotonic()
    load_result = loader_fn(records, source_hash=content_hash)
    load_duration = time.monotonic() - t1

    load_result["records_fetched"] = record_count
    load_result["content_hash"] = content_hash
    load_result["fetch_seconds"] = round(fetch_duration, 1)
    load_result["load_seconds"] = round(load_duration, 1)

    try:
        log_to_meta(meta_source, load_result)
    except Exception as e:
        logger.warning("Failed to log meta for %s: %s", source_key, e)

    return load_result


def main():
    parser = argparse.ArgumentParser(description="Smoke test all API data sources")
    parser.add_argument(
        "--max-records", type=int, default=500,
        help="Max records per source (default: 500)",
    )
    parser.add_argument(
        "--source", nargs="+",
        help="Only run these specific sources",
    )
    parser.add_argument(
        "--skip", nargs="+", default=[],
        help="Skip these sources",
    )
    parser.add_argument(
        "--skip-slow", action="store_true",
        help="Skip sources that download large ZIP files (cms_nppes, cms_hcris, drugbank)",
    )
    parser.add_argument(
        "--data-dir", default="/tmp/data/smoke_test",
        help="Temp directory for fetched files",
    )
    args = parser.parse_args()

    # Determine which sources to run
    api_sources = sorted(
        k for k, v in SOURCES.items() if "fetcher" in v
    )

    if args.source:
        api_sources = [s for s in args.source if s in SOURCES]

    skip_set = set(args.skip)
    if args.skip_slow:
        skip_set |= SLOW_ZIP_SOURCES

    api_sources = [s for s in api_sources if s not in skip_set]

    logger.info(
        "Running smoke test: %d sources, max_records=%d",
        len(api_sources), args.max_records,
    )

    # Ensure data dir exists
    Path(args.data_dir).mkdir(parents=True, exist_ok=True)

    # Init DB pool
    init_connection_pool()

    results = {}
    passed = 0
    failed = 0
    skipped = 0
    total_records = 0

    for i, source_key in enumerate(api_sources, 1):
        logger.info(
            "━━━ [%d/%d] %s ━━━",
            i, len(api_sources), source_key,
        )
        try:
            result = run_one_source(source_key, args.max_records, args.data_dir)
            results[source_key] = result

            status = result.get("status", "unknown")
            inserted = result.get("records_inserted", 0)
            fetched = result.get("records_fetched", 0)
            fetch_s = result.get("fetch_seconds", 0)
            load_s = result.get("load_seconds", 0)

            if status in ("success", "partial"):
                passed += 1
                total_records += inserted
                logger.info(
                    "  ✓ %s: fetched=%d inserted=%d (%.1fs fetch, %.1fs load)",
                    source_key, fetched, inserted, fetch_s, load_s,
                )
            elif status in ("skipped", "empty"):
                skipped += 1
                logger.warning(
                    "  ○ %s: %s (fetched=%d) — %s",
                    source_key, status, fetched,
                    result.get("error") or result.get("reason", "no records"),
                )
            else:
                failed += 1
                logger.error(
                    "  ✗ %s: %s — %s",
                    source_key, status, result.get("error", "unknown"),
                )
        except Exception as e:
            failed += 1
            tb = traceback.format_exc()
            results[source_key] = {
                "status": "exception",
                "error": str(e),
                "traceback": tb,
            }
            logger.error("  ✗ %s: EXCEPTION — %s", source_key, e)
            logger.debug(tb)

    close_connection_pool()

    # Summary
    print("\n" + "=" * 70)
    print("SMOKE TEST RESULTS")
    print("=" * 70)
    print(f"  Sources tested:  {len(api_sources)}")
    print(f"  Passed:          {passed}")
    print(f"  Failed:          {failed}")
    print(f"  Skipped/Empty:   {skipped}")
    print(f"  Total records:   {total_records}")
    print()

    # Detailed table
    print(f"{'Source':<30} {'Status':<10} {'Fetched':>8} {'Inserted':>9} {'Time':>6}")
    print("-" * 70)
    for source_key in api_sources:
        r = results.get(source_key, {})
        status = r.get("status", "?")
        fetched = r.get("records_fetched", 0)
        inserted = r.get("records_inserted", 0)
        total_time = r.get("fetch_seconds", 0) + r.get("load_seconds", 0)

        status_icon = "✓" if status in ("success", "partial") else ("○" if status in ("skipped", "empty") else "✗")
        print(f"  {status_icon} {source_key:<28} {status:<10} {fetched:>8} {inserted:>9} {total_time:>5.1f}s")

    # Print failures with details
    failures = {k: v for k, v in results.items() if v.get("status") in ("failed", "exception")}
    if failures:
        print(f"\n{'FAILURES':=^70}")
        for source_key, r in failures.items():
            print(f"\n  {source_key}:")
            print(f"    Error: {r.get('error', 'unknown')}")
            if r.get("traceback"):
                for line in r["traceback"].strip().split("\n")[-3:]:
                    print(f"    {line}")

    # Write JSON report
    report_path = Path(args.data_dir) / "smoke_test_report.json"
    with open(report_path, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "max_records": args.max_records,
                "summary": {
                    "total": len(api_sources),
                    "passed": passed,
                    "failed": failed,
                    "skipped": skipped,
                    "total_records": total_records,
                },
                "results": results,
            },
            f,
            indent=2,
            default=str,
        )
    print(f"\nFull report: {report_path}")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
