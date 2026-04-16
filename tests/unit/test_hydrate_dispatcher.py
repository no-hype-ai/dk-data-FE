"""Unit tests for dk_data.ingestion.hydrate_dispatcher.HydrateDispatcher.

Horizon 3 / plan §D.1 — in-cluster per-source Job fan-out.

Coverage (5 tests per the plan):
  1. Tier batch ordering respects depends_on (and tier precedence).
  2. Quarantined sources are skipped — no Job object is created.
  3. Parallelism caps at --max-parallel (semaphore bounds in-flight count).
  4. Terminal state is written to meta.transform_runs (mock pool).
  5. Failed Job increments hydration_backlog failure_count (mock writer).

Every external dependency is mocked:
  - kubernetes API client (KubeJobClient → FakeKubeClient)
  - meta.transform_runs INSERT (TransformRunsWriter._conn → FakeConn)
  - meta.hydration_backlog (HydrationBacklogWriter → FakeBacklog)

No real cluster / Postgres / pool access is ever established, so these
tests run in CI without infrastructure.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

import pytest


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeKubeClient:
    """In-memory Job lifecycle machine.

    Jobs created via ``create_job`` start in the ``pending`` state and can
    be transitioned to a terminal state via ``mark_completed`` /
    ``mark_failed`` from the test body. Tracks max concurrent in-flight
    count so the parallelism test can assert the cap.
    """

    def __init__(self, auto_complete: bool = True) -> None:
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.auto_complete = auto_complete
        # (source_id → outcome) override; default is 'completed'.
        self.outcomes: Dict[str, str] = {}
        # Max simultaneous in-flight count observed (for parallelism test).
        self.max_in_flight = 0
        self.create_calls: List[Dict[str, Any]] = []

    def create_job(self, manifest: Dict[str, Any]) -> str:
        with self._lock:
            name = manifest["metadata"]["name"]
            src = manifest["metadata"]["annotations"].get("dk-data/source-id", name)
            self.jobs[name] = {
                "source_id": src,
                "state": "running",  # pending/running/completed/failed
            }
            self.create_calls.append(manifest)
            in_flight = sum(1 for j in self.jobs.values() if j["state"] == "running")
            if in_flight > self.max_in_flight:
                self.max_in_flight = in_flight
            return name

    def get_job_status(self, name: str) -> Dict[str, Any]:
        with self._lock:
            job = self.jobs.get(name)
            if job is None:
                return {"active": 0, "succeeded": 0, "failed": 0, "conditions": []}
            if job["state"] == "running":
                if self.auto_complete:
                    # Transition based on outcomes table; default is completed.
                    desired = self.outcomes.get(job["source_id"], "completed")
                    job["state"] = desired
                else:
                    return {
                        "active": 1,
                        "succeeded": 0,
                        "failed": 0,
                        "conditions": [],
                    }
            if job["state"] == "completed":
                return {
                    "active": 0,
                    "succeeded": 1,
                    "failed": 0,
                    "conditions": [
                        {"type": "Complete", "status": "True", "reason": "ok"}
                    ],
                }
            if job["state"] == "failed":
                return {
                    "active": 0,
                    "succeeded": 0,
                    "failed": 1,
                    "conditions": [
                        {
                            "type": "Failed",
                            "status": "True",
                            "reason": "BackoffLimitExceeded",
                        }
                    ],
                }
            return {"active": 0, "succeeded": 0, "failed": 0, "conditions": []}

    def mark_completed(self, job_name: str) -> None:
        with self._lock:
            self.jobs[job_name]["state"] = "completed"

    def mark_failed(self, job_name: str) -> None:
        with self._lock:
            self.jobs[job_name]["state"] = "failed"


@dataclass
class FakeCursor:
    executions: List[Any] = field(default_factory=list)

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: Any = ()) -> None:
        self.executions.append((sql, params))

    def fetchone(self) -> Any:
        return None


class FakeConn:
    """Minimal psycopg2-compatible connection stub."""

    def __init__(self) -> None:
        self.executions: List[Any] = []
        self.autocommit = True

    def cursor(self, cursor_factory: Any = None) -> FakeCursor:
        # Every cursor shares the same execution log so tests can assert
        # on the union of SQL issued.
        cur = FakeCursor(executions=self.executions)
        return cur

    def close(self) -> None:
        pass


class FakeWriter:
    """Fake TransformRunsWriter that captures records."""

    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn  # Dispatcher uses getattr(writer, '_conn', None).


class FakeBacklog:
    """Fake HydrationBacklogWriter — configurable quarantine set + record log."""

    def __init__(self) -> None:
        self.quarantined: Set[str] = set()
        self.record_failure_calls: List[Dict[str, Any]] = []
        self.is_quarantined_calls: List[Any] = []

    def is_quarantined(self, source_id: str, schema: str, table: str) -> bool:
        self.is_quarantined_calls.append((source_id, schema, table))
        return source_id in self.quarantined

    def record_failure(
        self,
        *,
        source_id: str,
        schema: str,
        table: str,
        error_code: str,
        error_detail: str,
    ) -> Dict[str, Any]:
        self.record_failure_calls.append(
            {
                "source_id": source_id,
                "schema": schema,
                "table": table,
                "error_code": error_code,
                "error_detail": error_detail,
            }
        )
        return {"failure_count": len(self.record_failure_calls)}

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_kube() -> FakeKubeClient:
    return FakeKubeClient()


@pytest.fixture
def fake_conn() -> FakeConn:
    return FakeConn()


@pytest.fixture
def fake_writer(fake_conn: FakeConn) -> FakeWriter:
    return FakeWriter(fake_conn)


@pytest.fixture
def fake_backlog() -> FakeBacklog:
    return FakeBacklog()


@pytest.fixture
def descriptors():
    """Synthetic 3-tier descriptor set used across all tests."""
    from dk_data.ingestion.load_order import SourceDescriptor

    return [
        # Tier 1 — 2 roots, no deps.
        SourceDescriptor("meta.a", "meta", "a", 1),
        SourceDescriptor("meta.b", "meta", "b", 1),
        # Tier 2 — b depends on meta.a (intra-tier is fine, we just need a
        # dependency that must be satisfied before scheduling).
        SourceDescriptor("mol_raw.x", "mol_raw", "x", 2),
        SourceDescriptor(
            "mol_raw.y", "mol_raw", "y", 2, depends_on=["mol_raw.x"]
        ),
        # Tier 3 — spokes depending on tier-2 aggregates.
        SourceDescriptor(
            "mol_bronze.z", "mol_bronze", "z", 3, depends_on=["mol_raw.x", "mol_raw.y"]
        ),
    ]


def _new_dispatcher(
    *,
    fake_kube: FakeKubeClient,
    fake_writer: FakeWriter,
    fake_backlog: FakeBacklog,
    descriptors: List,
    max_parallel: int = 4,
):
    from dk_data.ingestion.hydrate_dispatcher import HydrateDispatcher

    return HydrateDispatcher(
        max_parallel=max_parallel,
        namespace="dk-data-prod",
        run_label="test-run",
        poll_interval_seconds=0,  # no real wall-clock wait in tests
        writer=fake_writer,
        backlog=fake_backlog,
        kube_client=fake_kube,
        descriptors=descriptors,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTierBatchOrdering:
    """Test 1 — tier batch ordering respects depends_on and tier gates.

    A tier-N source must NEVER dispatch before every tier<N source has
    reached a terminal state. Within a batch, a source with a
    ``depends_on`` ancestor only dispatches once that ancestor completes.
    """

    def test_dispatch_order_respects_tiers_and_depends_on(
        self, fake_kube, fake_writer, fake_backlog, descriptors
    ):
        dispatcher = _new_dispatcher(
            fake_kube=fake_kube,
            fake_writer=fake_writer,
            fake_backlog=fake_backlog,
            descriptors=descriptors,
        )
        results = dispatcher.dispatch_all()

        # All 5 sources reached terminal state.
        assert len(results) == 5
        assert all(r.status == "completed" for r in results)

        # Create-call order: tier-1 sources precede tier-2, tier-2 precede tier-3.
        create_order = [
            m["metadata"]["annotations"]["dk-data/source-id"]
            for m in fake_kube.create_calls
        ]
        tier_of = {
            "meta.a": 1, "meta.b": 1,
            "mol_raw.x": 2, "mol_raw.y": 2,
            "mol_bronze.z": 3,
        }
        tiers_seen = [tier_of[s] for s in create_order]
        # Tiers must be monotonic non-decreasing.
        assert tiers_seen == sorted(tiers_seen), (
            f"tier order violated: {create_order}"
        )
        # mol_raw.y depends on mol_raw.x — x must come first.
        assert create_order.index("mol_raw.x") < create_order.index(
            "mol_raw.y"
        ), "depends_on ordering within tier violated"
        # mol_bronze.z depends on both tier-2 entries.
        assert create_order.index("mol_raw.y") < create_order.index("mol_bronze.z")
        assert create_order.index("mol_raw.x") < create_order.index("mol_bronze.z")


class TestQuarantineSkip:
    """Test 2 — quarantined sources are skipped (no Job is created)."""

    def test_quarantined_source_does_not_create_job(
        self, fake_kube, fake_writer, fake_backlog, descriptors
    ):
        # Quarantine meta.a — dispatcher should short-circuit it.
        fake_backlog.quarantined.add("meta.a")

        dispatcher = _new_dispatcher(
            fake_kube=fake_kube,
            fake_writer=fake_writer,
            fake_backlog=fake_backlog,
            descriptors=descriptors,
        )
        results = dispatcher.dispatch_all()

        # 5 terminal results, but meta.a was NOT dispatched to kube.
        assert len(results) == 5
        created_source_ids = [
            m["metadata"]["annotations"]["dk-data/source-id"]
            for m in fake_kube.create_calls
        ]
        assert "meta.a" not in created_source_ids

        # The quarantined source has status 'skipped_quarantined'.
        meta_a_result = next(r for r in results if r.source_id == "meta.a")
        assert meta_a_result.status == "skipped_quarantined"

        # is_quarantined was actually called at least once for meta.a.
        assert any(
            c[0] == "meta.a" for c in fake_backlog.is_quarantined_calls
        )

        # The rest of the sources still ran (tier gate only advances when
        # a status is terminal; 'skipped_quarantined' is terminal, so
        # tier 2+ still get dispatched).
        assert "mol_raw.x" in created_source_ids
        assert "mol_bronze.z" in created_source_ids


class TestParallelismCap:
    """Test 3 — parallelism caps at --max-parallel (semaphore bound)."""

    def test_max_parallel_is_observed_by_semaphore(
        self, fake_writer, fake_backlog
    ):
        """With max_parallel=2 and a tier of 5 parallel-safe sources, at
        most 2 Jobs can be in-flight at any instant.

        We disable auto-complete so the fake kube returns 'running' for
        each Job the first time it's polled, forcing the dispatcher to
        wait on the semaphore between dispatches. A background thread
        sweeps marked Jobs to completion so the run eventually finishes.
        """
        from dk_data.ingestion.load_order import SourceDescriptor

        # 5 tier-1 sources, no cross-deps — all parallel-safe.
        descriptors = [
            SourceDescriptor(f"meta.p{i}", "meta", f"p{i}", 1) for i in range(5)
        ]
        fake_kube = FakeKubeClient(auto_complete=False)

        dispatcher = _new_dispatcher(
            fake_kube=fake_kube,
            fake_writer=fake_writer,
            fake_backlog=fake_backlog,
            descriptors=descriptors,
            max_parallel=2,
        )

        # Sweeper thread: periodically mark the oldest running Job as
        # completed so the dispatcher makes progress. This simulates
        # real-world Job terminations without the auto-complete shortcut.
        stop_sweep = threading.Event()

        def sweep() -> None:
            while not stop_sweep.is_set():
                for name, job in list(fake_kube.jobs.items()):
                    if job["state"] == "running":
                        fake_kube.mark_completed(name)
                        break
                time.sleep(0.01)

        sweeper = threading.Thread(target=sweep, daemon=True)
        sweeper.start()
        try:
            results = dispatcher.dispatch_all()
        finally:
            stop_sweep.set()
            sweeper.join(timeout=1.0)

        assert len(results) == 5
        # The key invariant: the kube client never saw more than 2 jobs
        # running simultaneously.
        assert fake_kube.max_in_flight <= 2, (
            f"semaphore cap violated — observed max_in_flight="
            f"{fake_kube.max_in_flight}"
        )


class TestTerminalStateWrite:
    """Test 4 — terminal state is written to meta.transform_runs."""

    def test_dispatcher_inserts_transform_runs_row_per_source(
        self, fake_kube, fake_writer, fake_backlog, fake_conn
    ):
        from dk_data.ingestion.load_order import SourceDescriptor

        descriptors = [
            SourceDescriptor("meta.single", "meta", "single", 1),
        ]

        dispatcher = _new_dispatcher(
            fake_kube=fake_kube,
            fake_writer=fake_writer,
            fake_backlog=fake_backlog,
            descriptors=descriptors,
        )
        results = dispatcher.dispatch_all()

        assert len(results) == 1
        assert results[0].status == "completed"

        # Exactly one INSERT INTO meta.transform_runs.
        inserts = [
            (sql, params)
            for (sql, params) in fake_conn.executions
            if "INSERT INTO meta.transform_runs" in sql
        ]
        assert len(inserts) == 1, (
            f"expected 1 transform_runs INSERT, got {len(inserts)}: "
            f"{fake_conn.executions}"
        )
        _, params = inserts[0]
        procedure_name = params[0]
        status = params[6]
        # The dispatcher records under the `dispatcher:` prefix so
        # operators can filter dispatcher-level outcomes.
        assert procedure_name == "dispatcher:meta.single"
        assert status == "completed"


class TestFailureIncrementsBacklog:
    """Test 5 — failed Job increments hydration_backlog failure_count."""

    def test_failed_job_calls_backlog_record_failure(
        self, fake_kube, fake_writer, fake_backlog
    ):
        from dk_data.ingestion.load_order import SourceDescriptor

        descriptors = [
            SourceDescriptor("meta.ok", "meta", "ok", 1),
            SourceDescriptor("meta.bad", "meta", "bad", 1),
        ]
        # Force meta.bad to come out as failed.
        fake_kube.outcomes["meta.bad"] = "failed"

        dispatcher = _new_dispatcher(
            fake_kube=fake_kube,
            fake_writer=fake_writer,
            fake_backlog=fake_backlog,
            descriptors=descriptors,
        )
        results = dispatcher.dispatch_all()

        by_src = {r.source_id: r for r in results}
        assert by_src["meta.ok"].status == "completed"
        assert by_src["meta.bad"].status == "failed"

        # backlog.record_failure invoked exactly once (only for the
        # failed source).
        failures = fake_backlog.record_failure_calls
        assert len(failures) == 1
        assert failures[0]["source_id"] == "meta.bad"
        assert failures[0]["schema"] == "meta"
        assert failures[0]["table"] == "bad"
        assert failures[0]["error_code"] == "DISPATCH_JOB_FAILED"
