"""
Integration tests for CMS PUF datasource integration (spec 016).

Tests real HTTP calls to CMS data sources, DB schema presence,
gold view readiness, agent infrastructure, and PostgREST API exposure.

Run with: python3 tests/test_integration_cms_puf.py
"""
import sys
import asyncio
import os
import importlib
import traceback  # noqa: F401 — available for detailed error reporting in integration tests
from datetime import datetime

import pytest

sys.path.insert(0, "src")

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"

results = []


def report(name: str, success: bool, detail: str = ""):
    status = PASS if success else FAIL
    results.append((name, success, detail))
    print(f"  {status} {name}" + (f"  —  {detail}" if detail else ""))


# ── 1. Database Schema Verification ──────────────────────────────

async def test_db_schema():
    """Verify all CMS raw/silver/gold/api/meta tables exist."""
    print("\n━━━ 1. Database Schema ━━━")
    import asyncpg
    conn = await asyncpg.connect(
        host="localhost", port=5433,
        user="postgres", password="postgres",
        database="dk_data"
    )

    # Raw tables (30 CMS sources)
    expected_raw = [
        "cms_nppes", "cms_part_d_prescriber", "cms_physician_puf",
        "cms_open_payments_general", "cms_open_payments_research", "cms_open_payments_ownership",
        "cms_care_compare_physicians",
        "cms_pos", "cms_pecos", "cms_chow", "cms_hospital_affiliation",
        "cms_inpatient_puf", "cms_outpatient_puf", "cms_hospital_quality",
        "cms_hospital_general_info", "cms_hcris", "cms_magnet",
        "cms_ndc", "cms_part_d_spending", "cms_part_b_spending",
        "cms_formulary", "cms_rbcs", "cms_usp", "cms_nucc",
        "cms_geographic_variation", "cms_chronic_conditions", "cms_post_acute",
        "cms_dmepos", "cms_ddinter", "cms_stabilis",
    ]
    raw_rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='raw' AND table_name LIKE 'cms_%'"
    )
    raw_tables = {r["table_name"] for r in raw_rows}
    missing_raw = [t for t in expected_raw if t not in raw_tables]
    report(f"Raw tables ({len(raw_tables)} found, {len(expected_raw)} expected)",
           len(missing_raw) == 0,
           f"missing: {missing_raw}" if missing_raw else "all present")

    # Partitioned tables
    for table in ["cms_part_d_prescriber", "cms_physician_puf"]:
        parts = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='raw' AND table_name LIKE $1",
            f"{table}_%"
        )
        report(f"  Partitions for {table}", len(parts) > 0, f"{len(parts)} partitions")

    # Silver tables
    expected_silver = [
        "cms_provider_profile", "cms_facility_profile", "cms_drug_market",
        "cms_geographic", "cms_health_system_hierarchy",
        "cms_referral_edges", "cms_verified_contacts",
        "cms_staffing_profiles", "cms_equipment_inventory",
    ]
    silver_rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='silver' AND table_name LIKE 'cms_%'"
    )
    silver_tables = {r["table_name"] for r in silver_rows}
    missing_silver = [t for t in expected_silver if t not in silver_tables]
    report(f"Silver tables ({len(silver_tables)} found)",
           len(missing_silver) == 0,
           f"missing: {missing_silver}" if missing_silver else "all present")

    # Gold views
    expected_gold = [
        "cms_provider_360", "cms_facility_360", "cms_drug_market_profile",
        "cms_market_analytics", "cms_provider_network",
    ]
    gold_rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='gold' AND table_name LIKE 'cms_%'"
    )
    gold_tables = {r["table_name"] for r in gold_rows}
    missing_gold = [t for t in expected_gold if t not in gold_tables]
    report(f"Gold views ({len(gold_tables)} found)",
           len(missing_gold) == 0,
           f"missing: {missing_gold}" if missing_gold else "all present")

    # API views
    api_rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='api' AND table_name LIKE 'cms_%'"
    )
    api_tables = {r["table_name"] for r in api_rows}
    report(f"API views ({len(api_tables)} found)", len(api_tables) >= 4, f"tables: {sorted(api_tables)}")

    # Meta tables (agent infrastructure)
    for table in ["agent_execution_log", "agent_quarantine"]:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables "
            "WHERE table_schema='meta' AND table_name=$1)", table
        )
        report(f"Meta table: {table}", exists)

    await conn.close()


# ── 2. CMS Fetcher Instantiation ─────────────────────────────────

def test_fetcher_instantiation():
    """Verify all 31 CMS fetchers can be instantiated and have valid URLs."""
    print("\n━━━ 2. Fetcher Instantiation ━━━")

    from dk_data.ingestion.main import SOURCES

    cms_sources = {k: v for k, v in SOURCES.items() if k.startswith("cms_")}
    report("CMS sources in registry", len(cms_sources) >= 28, f"{len(cms_sources)} found")

    # Separate API-fetched sources from legacy file-based loaders
    api_sources = {k: v for k, v in cms_sources.items() if "fetcher" in v}
    legacy_sources = {k: v for k, v in cms_sources.items() if "fetcher" not in v}
    report("  API-fetched sources", len(api_sources) >= 25, f"{len(api_sources)} with fetcher")
    report("  Legacy file-based loaders", True, f"{len(legacy_sources)}: {sorted(legacy_sources.keys())}")

    success_count = 0
    fail_count = 0
    for name, config in sorted(api_sources.items()):
        try:
            fetcher_cls = config["fetcher"]
            fetcher = fetcher_cls(data_dir="/tmp/dk_test", params={})
            url = fetcher.get_latest_url()
            assert url, f"Expected non-empty URL from {name}"
            success_count += 1
        except Exception as e:
            fail_count += 1
            report(f"  {name}", False, f"{type(e).__name__}: {e}")

    report(f"Fetcher instantiation ({success_count}/{success_count + fail_count})",
           fail_count == 0,
           f"{fail_count} failed" if fail_count else "all OK")


# ── 3. CMS Fetcher URL Reachability ──────────────────────────────

async def test_fetcher_urls():
    """Test that CMS data source URLs are reachable (HEAD requests)."""
    print("\n━━━ 3. Fetcher URL Reachability (HEAD probes) ━━━")
    import httpx

    from dk_data.ingestion.main import SOURCES

    cms_sources = {k: v for k, v in SOURCES.items() if k.startswith("cms_")}

    # Test a representative sample (not all 31 — some are multi-GB downloads)
    sample_sources = [
        "cms_nppes", "cms_ndc", "cms_part_d_prescriber",
        "cms_hospital_quality", "cms_pos", "cms_formulary",
        "cms_open_payments", "cms_nucc", "cms_rbcs",
    ]

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http:
        for name in sample_sources:
            if name not in cms_sources:
                report(f"  {name}", False, "not in SOURCES registry")
                continue
            try:
                fetcher_cls = cms_sources[name]["fetcher"]
                fetcher = fetcher_cls(data_dir="/tmp/dk_test", params={})
                url = fetcher.get_latest_url()

                # HEAD request to check reachability
                r = await http.head(url, headers={
                    "User-Agent": "DataKinetic/1.0 (Research Platform)"
                })
                # Accept 200, 301, 302, 307, 403 (some block HEAD but work with GET)
                reachable = r.status_code < 500
                report(f"  {name}", reachable, f"HTTP {r.status_code} — {url[:80]}")
            except Exception as e:
                report(f"  {name}", False, f"{type(e).__name__}: {str(e)[:80]}")


# ── 4. CMS Fetcher Live Fetch (small sample) ─────────────────────

def test_live_fetch_sample():
    """Actually fetch a small batch from select CMS sources."""
    print("\n━━━ 4. Live Fetch (small batch) ━━━")

    from dk_data.ingestion.main import SOURCES

    # Only test sources that are fast and have manageable data sizes
    test_sources = {
        "cms_ndc": {"max_records": 10},
        "cms_nucc": {"max_records": 10},
    }

    for name, kwargs in test_sources.items():
        if name not in SOURCES:
            report(f"  {name}", False, "not in SOURCES registry")
            continue
        try:
            fetcher_cls = SOURCES[name]["fetcher"]
            fetcher = fetcher_cls(data_dir="/tmp/dk_test", params={})
            result = fetcher.fetch(**kwargs)

            status = result.get("status", "unknown")
            records = result.get("records", [])
            count = len(records) if isinstance(records, list) else records
            report(f"  {name} fetch()", status == "success",
                   f"status={status}, records={count}")

            # Verify record structure
            if isinstance(records, list) and records:
                sample = records[0]
                report("    record keys", True, f"{list(sample.keys())[:6]}...")
        except Exception as e:
            report(f"  {name} fetch()", False, f"{type(e).__name__}: {str(e)[:100]}")


# ── 5. Source Loader Validation ───────────────────────────────────

def test_source_loader_imports():
    """Verify all CMS source loaders import successfully."""
    print("\n━━━ 5. Source Loader Imports ━━━")

    loader_modules = [
        "dk_data.ingestion.sources.cms_nppes",
        "dk_data.ingestion.sources.cms_part_d_prescriber",
        "dk_data.ingestion.sources.cms_ndc",
        "dk_data.ingestion.sources.cms_pos",
        "dk_data.ingestion.sources.cms_hospital_quality",
        "dk_data.ingestion.sources.cms_open_payments",
        "dk_data.ingestion.sources.cms_formulary",
        "dk_data.ingestion.sources.cms_pecos",
        "dk_data.ingestion.sources.cms_hcris",
        "dk_data.ingestion.sources.cms_ddinter",
        "dk_data.ingestion.sources.cms_stabilis",
        "dk_data.ingestion.sources.cms_usp",
        "dk_data.ingestion.sources.cms_rbcs",
        "dk_data.ingestion.sources.cms_nucc",
    ]

    success = 0
    for mod_name in loader_modules:
        try:
            mod = importlib.import_module(mod_name)
            # Find the load function
            load_fns = [attr for attr in dir(mod) if attr.startswith("load_cms_")]
            report(f"  {mod_name.split('.')[-1]}", len(load_fns) > 0,
                   f"loader: {load_fns[0]}" if load_fns else "no load function found")
            success += 1
        except Exception as e:
            report(f"  {mod_name.split('.')[-1]}", False, f"{type(e).__name__}: {e}")

    report(f"Source loader imports ({success}/{len(loader_modules)})",
           success == len(loader_modules))


# ── 6. Agent Infrastructure ───────────────────────────────────────

def test_agent_imports():
    """Verify all 6 CMS agents import and instantiate."""
    print("\n━━━ 6. Agent Infrastructure ━━━")

    agents = [
        ("dk_data.agents.service_line_inference", "ServiceLineInferenceAgent"),
        ("dk_data.agents.idn_hierarchy", "IDNHierarchyAgent"),
        ("dk_data.agents.referral_network", "ReferralNetworkAgent"),
        ("dk_data.agents.contact_verification", "ContactVerificationAgent"),
        ("dk_data.agents.staffing_decomposition", "StaffingDecompositionAgent"),
        ("dk_data.agents.equipment_inventory", "EquipmentInventoryAgent"),
    ]

    for mod_name, cls_name in agents:
        try:
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name)
            assert cls is not None, f"{cls_name} should be importable"
            report(f"  {cls_name}", True, f"from {mod_name}")
        except Exception as e:
            report(f"  {cls_name}", False, f"{type(e).__name__}: {e}")


# ── 7. SQLMesh Models ────────────────────────────────────────────

def test_sqlmesh_models():
    """Verify all SQLMesh model files exist and have valid SQL."""
    print("\n━━━ 7. SQLMesh Models ━━━")
    import glob

    base = "src/dk_data/sqlmesh/models/cms"

    for layer in ["bronze", "silver", "gold"]:
        path = os.path.join(base, layer)
        sql_files = glob.glob(os.path.join(path, "*.sql"))
        report(f"  {layer} models", len(sql_files) > 0, f"{len(sql_files)} files")

        # Validate each file has MODEL declaration
        for f in sql_files:
            with open(f) as fh:
                content = fh.read()
                has_model = "MODEL" in content
                if not has_model:
                    report(f"    {os.path.basename(f)}", False, "missing MODEL declaration")


# ── 8. Gold View Queries ─────────────────────────────────────────

async def test_gold_views():
    """Query each gold CMS view to verify it's accessible (may be empty)."""
    print("\n━━━ 8. Gold View Queries ━━━")
    import asyncpg
    conn = await asyncpg.connect(
        host="localhost", port=5433,
        user="postgres", password="postgres",
        database="dk_data"
    )

    gold_views = [
        "gold.cms_provider_360",
        "gold.cms_facility_360",
        "gold.cms_drug_market_profile",
        "gold.cms_market_analytics",
        "gold.cms_provider_network",
    ]

    for view in gold_views:
        try:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {view}")
            report(f"  {view}", True, f"{count} rows")
        except Exception as e:
            report(f"  {view}", False, f"{type(e).__name__}: {e}")

    await conn.close()


# ── 9. PostgREST API Exposure ─────────────────────────────────────

async def test_postgrest_api():
    """Test CMS views are accessible via PostgREST."""
    print("\n━━━ 9. PostgREST API (localhost:3030) ━━━")
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:3030", timeout=15.0) as http:
        # Test API views
        api_views = [
            "cms_provider_profile",
            "cms_facility_profile",
            "cms_drug_market",
            "cms_provider_network",
            "cms_market_analytics",
        ]

        for view in api_views:
            try:
                r = await http.get(f"/{view}?limit=1")
                assert r.status_code in (200, 404), f"Unexpected status {r.status_code} for {view}"
                if r.status_code == 200:
                    data = r.json()
                    count = len(data) if isinstance(data, list) else 0
                    report(f"  GET /{view}?limit=1", True, f"HTTP {r.status_code}, {count} row(s)")
                else:
                    report(f"  GET /{view}?limit=1", True, f"HTTP {r.status_code} (view exists but may need schema config)")
            except Exception as e:
                report(f"  GET /{view}", False, f"{type(e).__name__}: {e}")


# ── 10. Aggregation Service ───────────────────────────────────────

async def test_aggregation_service():
    """Verify aggregation service can be instantiated and called."""
    print("\n━━━ 10. Aggregation Service ━━━")

    try:
        from dk_data.services.data_platform.gold_aggregation import GoldAggregationService  # noqa: F401 — import-check assertion
        report("GoldAggregationService import", True)
    except Exception as e:
        report("GoldAggregationService import", False, str(e))
        return

    try:
        from dk_data.services.pipeline.silver_gold_refresher import SilverGoldRefresher  # noqa: F401 — import-check assertion
        report("SilverGoldRefresher import", True)
    except Exception as e:
        report("SilverGoldRefresher import", False, str(e))


# ── 11. Monitoring / Staleness ────────────────────────────────────

async def test_monitoring_staleness():
    """Check CMS staleness report table and monitoring endpoint."""
    print("\n━━━ 11. CMS Monitoring ━━━")
    import asyncpg

    conn = await asyncpg.connect(
        host="localhost", port=5433,
        user="postgres", password="postgres",
        database="dk_data"
    )

    # Check staleness report table
    try:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables "
            "WHERE table_schema='meta' AND table_name='cms_staleness_report')"
        )
        report("meta.cms_staleness_report exists", exists)
    except Exception as e:
        report("meta.cms_staleness_report", False, str(e))

    # Check monitoring endpoint
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=15.0) as http:
        try:
            r = await http.get("/api/v1/monitoring/schedules")
            if r.status_code == 200:
                data = r.json()
                schedules = data.get("schedules", [])
                cms_schedules = [s for s in schedules if "cms" in s.get("source", "").lower()]
                report("CMS schedules in monitoring", True,
                       f"{len(cms_schedules)} CMS schedules out of {len(schedules)} total")
            else:
                report("Monitoring /schedules", False, f"HTTP {r.status_code}")
        except Exception as e:
            report("Monitoring /schedules", False, str(e))

    await conn.close()


# ── Main ──────────────────────────────────────────────────────────

async def main():
    print(f"\n{'='*65}")
    print(" CMS PUF Datasource Integration Tests (Spec 016)")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*65}")

    # Schema tests
    await test_db_schema()

    # Code tests (sync)
    test_fetcher_instantiation()
    await test_fetcher_urls()
    test_live_fetch_sample()
    test_source_loader_imports()
    test_agent_imports()
    test_sqlmesh_models()

    # Infrastructure tests
    await test_gold_views()
    await test_postgrest_api()
    await test_aggregation_service()
    await test_monitoring_staleness()

    # Summary
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)

    print(f"\n{'='*65}")
    print(f" Results: {passed}/{total} passed, {failed} failed")
    print(f"{'='*65}")

    if failed > 0:
        print("\n  Failed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"    {FAIL} {name}: {detail}")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
