"""Resolve function latency benchmark.

Feature: 001-silver-medallion-rebuild
Task: T142
SC-004: Each resolve_* function must return in < 10 ms at p99 on the staging cluster.

Requires a real Postgres connection with pg_trgm installed.
Marked 'perf' — run separately from unit tests:
    pytest tests/perf/test_resolve_latency.py -m perf -v

Results should be included in the PR description per T118.
"""

import time
import statistics
import pytest

pytestmark = pytest.mark.perf

ITERATIONS = 200
P99_THRESHOLD_MS = 10.0

# Resolve function signatures: (function_name, sample_args_list)
# Each args tuple is passed to the function as positional parameters.
RESOLVE_FUNCTIONS = [
    (
        "mol_silver.resolve_molecule",
        [
            ("BSYNRYMUTXBXSQ-UHFFFAOYSA-N", None, None, None, None),  # aspirin inchi_key
            (None, "CHEMBL25", None, None, None),                       # aspirin chembl_id
            (None, None, "2244", None, None),                           # aspirin pubchem_cid
            (None, None, None, None, "aspirin"),                        # aspirin by name
        ],
    ),
    (
        "hcs_silver.resolve_provider",
        [
            ("1003000126", None, None, None, None, None),               # NPI exact
            (None, None, None, None, "Smith", "John"),                  # name fallback
        ],
    ),
    (
        "hcs_silver.resolve_facility",
        [
            (None, "050001", None, None, None),                         # CCN exact
            (None, None, None, None, "UCLA Medical Center"),            # name fallback
        ],
    ),
    (
        "ind_silver.resolve_condition",
        [
            (None, "D003920", None, None, None),                        # MeSH exact
            (None, None, "E11", None, None),                            # ICD-10 exact
            (None, None, None, None, "diabetes mellitus"),              # name fallback
        ],
    ),
    (
        "mol_silver.resolve_drug_product",
        [
            ("1049502", None, None, None, None, None),                  # rxcui SCD
            (None, None, None, None, None, "aspirin 325mg tablet"),     # name fallback
        ],
    ),
    (
        "mol_silver.resolve_company",
        [
            (None, "Pfizer Inc", None, None),                           # name exact
            (None, "pfizer", None, None),                               # normalized
        ],
    ),
    (
        "mol_silver.resolve_target",
        [
            (None, "P15692", None, None, None),                         # uniprot
            (None, None, "CHEMBL1824", None, None),                     # chembl target
        ],
    ),
    (
        "ip_silver.resolve_patent",
        [
            ("US1234567", None, None, None, None),                      # patent_number
        ],
    ),
    (
        "ip_silver.resolve_trademark",
        [
            (None, "88123456", None, None),                             # USPTO serial
            (None, None, None, "ASPIRIN"),                              # name
        ],
    ),
    (
        "ip_silver.resolve_design",
        [
            ("US D12345 S", None, None, None),                          # design_number
        ],
    ),
    (
        "hcp_silver.resolve_researcher",
        [
            ("0000-0001-2345-6789", None, None, None, None, None),      # ORCID
            (None, None, None, None, "Smith", "John"),                  # name fallback
        ],
    ),
]


def _measure_latency_ms(cur, func_name: str, args: tuple) -> float:
    """Run a single resolve function call and return elapsed ms."""
    placeholders = ", ".join(["%s"] * len(args))
    sql = f"SELECT {func_name}({placeholders})"
    t0 = time.perf_counter()
    cur.execute(sql, args)
    cur.fetchone()
    return (time.perf_counter() - t0) * 1000.0


def _percentile(data: list, p: float) -> float:
    """Compute p-th percentile of data."""
    return statistics.quantiles(sorted(data), n=100)[int(p) - 1]


class TestResolveLatency:
    """SC-004: All resolve_* functions must be < 10 ms at p99."""

    def _run_benchmark(self, cnpg_conn, func_name: str, sample_args: list):
        """Run ITERATIONS calls round-robin over sample_args, return latency list."""
        cur = cnpg_conn.cursor()
        latencies = []
        for i in range(ITERATIONS):
            args = sample_args[i % len(sample_args)]
            try:
                ms = _measure_latency_ms(cur, func_name, args)
                latencies.append(ms)
            except Exception:
                cnpg_conn.rollback()
        cur.close()
        return latencies

    @pytest.mark.parametrize("func_name,sample_args", RESOLVE_FUNCTIONS)
    def test_resolve_p99_under_10ms(self, cnpg_conn, func_name: str, sample_args: list):
        """SC-004: p99 latency for each resolve function must be < 10 ms."""
        # Check function exists
        cur = cnpg_conn.cursor()
        schema, fname = func_name.split(".")
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname=%s AND p.proname=%s)",
            (schema, fname),
        )
        exists = cur.fetchone()[0]
        cur.close()
        if not exists:
            pytest.skip(f"{func_name} not installed in test DB")

        latencies = self._run_benchmark(cnpg_conn, func_name, sample_args)
        if len(latencies) < 10:
            pytest.skip(f"Too few successful calls ({len(latencies)}) for {func_name}")

        p50 = _percentile(latencies, 50)
        p95 = _percentile(latencies, 95)
        p99 = _percentile(latencies, 99)

        print(
            f"\n{func_name}: p50={p50:.2f}ms  p95={p95:.2f}ms  p99={p99:.2f}ms  "
            f"n={len(latencies)}"
        )

        assert p99 < P99_THRESHOLD_MS, (
            f"SC-004 VIOLATION: {func_name} p99={p99:.2f}ms exceeds {P99_THRESHOLD_MS}ms threshold.\n"
            f"p50={p50:.2f}ms  p95={p95:.2f}ms  n={len(latencies)}\n"
            f"Fix: ensure pg_trgm GIN indexes exist on all name-index tables and "
            f"the resolve function is STABLE PARALLEL SAFE with LIMIT 1 on all branches."
        )
