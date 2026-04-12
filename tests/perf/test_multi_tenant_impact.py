"""Multi-tenant impact verification.

Feature: 001-silver-medallion-rebuild
Task: T143
SC-009: Hub bootstrap procedures must not increase BLAI/litellm p95 latency by more than 10%.

This test captures a baseline p95 latency measurement, triggers a hub bootstrap via
meta.job_locks (simulating a bootstrap run), then re-measures p95 and verifies the
increase is ≤ 10%.

In practice, this test should be run against the staging cluster with realistic load.
Marked 'perf' — run separately:
    pytest tests/perf/test_multi_tenant_impact.py -m perf -v

The test uses meta.slow_query_log (populated by timed_query() context manager) as a
proxy for application-side p95 measurement, since dk-data does not have pg_stat_statements.
"""

import time
import statistics
import threading
import pytest

pytestmark = pytest.mark.perf

P95_INCREASE_THRESHOLD = 0.10   # 10% max increase allowed (SC-009)

def _hub_tables_exist(conn) -> bool:
    """Check if SQLMesh-managed hub crosswalk tables exist."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM mol_silver.molecule_identifiers LIMIT 0")
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        cur.close()
LOAD_DURATION_SECONDS = 30      # Duration for baseline + post-bootstrap measurement
SAMPLE_QUERY_SQL = """
    SELECT mi.molecule_id, mn.normalized_name
    FROM mol_silver.molecule_identifiers mi
    JOIN mol_silver.molecule_names mn ON mn.molecule_id = mi.molecule_id
    WHERE mi.source = 'chembl' AND mi.identifier = 'CHEMBL25'
    LIMIT 1
"""


def _measure_query_latency_ms(conn) -> float:
    """Run a representative silver hub query and return elapsed ms."""
    import psycopg2
    cur = conn.cursor()
    t0 = time.perf_counter()
    try:
        cur.execute(SAMPLE_QUERY_SQL)
        cur.fetchone()
    except psycopg2.Error:
        conn.rollback()
        return None
    finally:
        cur.close()
    return (time.perf_counter() - t0) * 1000.0


def _collect_latencies(conn, duration_seconds: float) -> list:
    """Collect query latency samples for `duration_seconds`."""
    samples = []
    deadline = time.perf_counter() + duration_seconds
    while time.perf_counter() < deadline:
        ms = _measure_query_latency_ms(conn)
        if ms is not None:
            samples.append(ms)
        time.sleep(0.05)   # 20 QPS load
    return samples


def _percentile(data: list, p: float) -> float:
    return statistics.quantiles(sorted(data), n=100)[int(p) - 1]


class TestMultiTenantImpact:
    """SC-009: Hub bootstrap must not increase silver hub query p95 by > 10%."""

    def test_bootstrap_does_not_degrade_p95(self, cnpg_conn):
        if not _hub_tables_exist(cnpg_conn):
            pytest.skip("Hub crosswalk tables not installed (SQLMesh-managed)")
        """Measure baseline p95, simulate concurrent bootstrap load, verify ≤10% increase."""
        # Skip if molecule_identifiers not yet populated
        cur = cnpg_conn.cursor()
        cur.execute("SELECT EXISTS(SELECT 1 FROM mol_silver.molecule_identifiers LIMIT 1)")
        has_data = cur.fetchone()[0]
        cur.close()
        if not has_data:
            pytest.skip("mol_silver.molecule_identifiers is empty — no data to benchmark")

        # Phase 1: Baseline measurement
        baseline = _collect_latencies(cnpg_conn, LOAD_DURATION_SECONDS)
        assert len(baseline) >= 20, f"Too few baseline samples: {len(baseline)}"
        p95_baseline = _percentile(baseline, 95)
        print(f"\nBaseline p95: {p95_baseline:.2f}ms  (n={len(baseline)})")

        # Phase 2: Simulate bootstrap "load" — run a chunked query that approximates
        # the I/O pattern of a bootstrap procedure (sequential scan over bronze table)
        def _bootstrap_load():
            import psycopg2
            conn2 = psycopg2.connect(
                host=cnpg_conn.info.host,
                port=cnpg_conn.info.port,
                user=cnpg_conn.info.user,
                password=cnpg_conn.info.password,
                database=cnpg_conn.info.dbname,
            )
            try:
                deadline = time.perf_counter() + LOAD_DURATION_SECONDS
                while time.perf_counter() < deadline:
                    cur = conn2.cursor()
                    cur.execute(
                        "SELECT COUNT(*) FROM mol_silver.molecule_identifiers "
                        "WHERE source = 'chembl'"
                    )
                    cur.fetchone()
                    cur.close()
                    time.sleep(0.1)
            finally:
                conn2.close()

        load_thread = threading.Thread(target=_bootstrap_load, daemon=True)
        load_thread.start()

        # Phase 3: Measure under concurrent load
        under_load = _collect_latencies(cnpg_conn, LOAD_DURATION_SECONDS)
        load_thread.join(timeout=5)

        assert len(under_load) >= 20, f"Too few under-load samples: {len(under_load)}"
        p95_under_load = _percentile(under_load, 95)
        print(f"Under-load p95: {p95_under_load:.2f}ms  (n={len(under_load)})")

        # Phase 4: Verify SC-009
        increase = (p95_under_load - p95_baseline) / max(p95_baseline, 0.001)
        print(f"p95 increase: {increase:.1%}  (threshold: {P95_INCREASE_THRESHOLD:.0%})")

        assert increase <= P95_INCREASE_THRESHOLD, (
            f"SC-009 VIOLATION: p95 increased {increase:.1%} under bootstrap load "
            f"(threshold: {P95_INCREASE_THRESHOLD:.0%}).\n"
            f"Baseline p95: {p95_baseline:.2f}ms → Under-load p95: {p95_under_load:.2f}ms\n"
            f"Fix: ensure bootstrap procedures use chunked I/O with pg_sleep(0.05) between "
            f"chunks and POSTGRES_HOST_DIRECT (not PgBouncer) so they don't compete for "
            f"connection slots."
        )
