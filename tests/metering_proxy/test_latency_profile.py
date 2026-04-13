"""T024c — Metering proxy latency profile.

Measures the overhead the metering proxy adds to a round-trip (with
the upstream call stubbed out). The SLO is p99 ≤ 200 ms for the
full call chain; the proxy itself should contribute ≤ 10 ms p99
under normal load.

This is not a full performance benchmark — it's a sanity guard
against regressions (e.g., an O(n) lookup landing in the hot path).
For a real load test, see `tests/load/phase2_concurrent.py`.
"""

from __future__ import annotations

import statistics
import time

import pytest


class TestProxyOverhead:
    def test_p99_under_50ms(self, client):
        # Warm-up
        for _ in range(10):
            client.get(
                "/mol_silver/molecules",
                headers={"Authorization": "Bearer dk_data_load_test_key"},
            )

        samples = []
        for _ in range(200):
            start = time.perf_counter()
            response = client.get(
                "/mol_silver/molecules",
                headers={"Authorization": "Bearer dk_data_load_test_key"},
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            assert response.status_code == 200
            samples.append(elapsed_ms)

        samples.sort()
        p50 = samples[len(samples) // 2]
        p99 = samples[int(len(samples) * 0.99)]

        # Much looser than 10 ms because TestClient adds its own overhead.
        # The real-world proxy overhead (no TestClient) is well under 5 ms;
        # this test guards against 10x regressions.
        assert p99 < 50, f"p99 {p99:.2f} ms exceeds 50 ms budget"
        assert p50 < 20, f"p50 {p50:.2f} ms exceeds 20 ms budget"

    def test_no_request_exceeds_1s(self, client):
        """Worst-case guard — nothing in the hot path should block for seconds."""
        for _ in range(50):
            start = time.perf_counter()
            client.get(
                "/mol_silver/molecules",
                headers={"Authorization": "Bearer dk_data_load_test_key"},
            )
            elapsed = time.perf_counter() - start
            assert elapsed < 1.0, f"single request took {elapsed:.2f}s"
