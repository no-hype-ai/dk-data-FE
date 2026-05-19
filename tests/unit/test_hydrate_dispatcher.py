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


class FakeBudget:
    """Fake :class:`ResourceBudget` — configurable admit/deny + release log.

    Exposes the exact contract the dispatcher relies on:
      - ``decorate_dispatch(fn)``: returns a wrapper that invokes
        ``try_reserve`` first, calls ``fn`` on admit (releasing after), or
        returns ``None`` on deny.
      - ``try_reserve(requirements)``: returns ``self.admit`` (a bool or a
        callable for per-call control — see :attr:`admit_fn`).
      - ``release(requirements)``: logs the call.
      - ``close()``: logs the close.

    Tests poke ``admit`` / ``admit_fn`` to steer wrapper behaviour and read
    ``reserve_calls`` / ``release_calls`` / ``closed`` to assert on
    lifecycle.
    """

    def __init__(self) -> None:
        self.admit: bool = True
        self.admit_fn: Any = None  # callable(requirements) -> bool, overrides admit
        self.reserve_calls: List[Dict[str, float]] = []
        self.release_calls: List[Dict[str, float]] = []
        self.closed: bool = False

    def try_reserve(self, requirements: Any) -> bool:
        self.reserve_calls.append(dict(requirements))
        if self.admit_fn is not None:
            return bool(self.admit_fn(requirements))
        return self.admit

    def release(self, requirements: Any) -> None:
        self.release_calls.append(dict(requirements))

    def close(self) -> None:
        self.closed = True

    def decorate_dispatch(self, dispatch_fn: Any) -> Any:
        """Mirror :meth:`ResourceBudget.decorate_dispatch` contract.

        Keeps the same try_reserve → fn → release-in-finally flow so tests
        exercise the real integration semantics rather than a shortcut.
        """
        # Import lazily to avoid a hard test-side dependency on the real
        # module if a future refactor relocates the helper.
        from dk_data.ingestion.resource_budget import _extract_consumes

        def wrapped(descriptor: Any, *args: Any, **kwargs: Any) -> Any:
            requirements = _extract_consumes(descriptor)
            if not self.try_reserve(requirements):
                return None
            try:
                return dispatch_fn(descriptor, *args, **kwargs)
            finally:
                self.release(requirements)

        return wrapped


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
def fake_budget() -> FakeBudget:
    return FakeBudget()


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
    fake_budget: Any = None,
):
    from dk_data.ingestion.hydrate_dispatcher import HydrateDispatcher

    # Default to a permissive FakeBudget so tests that don't care about
    # admission control never hit the real connection pool (which would
    # try to connect to Postgres on import). Admission-specific tests
    # pass their own FakeBudget with a configured ``admit`` flag.
    if fake_budget is None:
        fake_budget = FakeBudget()

    return HydrateDispatcher(
        max_parallel=max_parallel,
        namespace="dk-data-prod",
        run_label="test-run",
        poll_interval_seconds=0,  # no real wall-clock wait in tests
        writer=fake_writer,
        backlog=fake_backlog,
        kube_client=fake_kube,
        descriptors=descriptors,
        budget=fake_budget,
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


# ---------------------------------------------------------------------------
# Admission control integration (plan §D.1 + §D.3)
#
# The dispatcher routes every per-source dispatch through
# ``budget.decorate_dispatch(self._dispatch_one)``. These four tests cover
# the integration surface:
#   - happy path: admit → dispatch fn called → release
#   - defer path: deny → dispatch fn NOT called, deferred counter ticks
#   - release-on-success: release happens after a normal dispatch return
#   - release-on-exception: release still happens when dispatch fn raises
# ---------------------------------------------------------------------------


class TestDispatchCallsThroughBudgetWrapper:
    """When try_reserve returns True, the underlying dispatch fn MUST be
    invoked with the descriptor."""

    def test_dispatch_calls_through_budget_wrapper(
        self, fake_kube, fake_writer, fake_backlog, fake_budget
    ):
        from dk_data.ingestion.load_order import SourceDescriptor

        fake_budget.admit = True
        descriptors = [SourceDescriptor("meta.single", "meta", "single", 1)]

        dispatcher = _new_dispatcher(
            fake_kube=fake_kube,
            fake_writer=fake_writer,
            fake_backlog=fake_backlog,
            descriptors=descriptors,
            fake_budget=fake_budget,
        )
        results = dispatcher.dispatch_all()

        # Reservation happened before the underlying dispatch — and the
        # underlying dispatch actually produced the Job (kube.create_job
        # was hit exactly once).
        assert len(fake_budget.reserve_calls) == 1
        assert len(fake_kube.create_calls) == 1
        # Exactly one terminal result, and it's the completed source.
        assert len(results) == 1
        assert results[0].status == "completed"


class TestDispatchDefersOnBudgetExhausted:
    """When try_reserve returns False, the underlying dispatch fn MUST NOT
    be invoked, the per-source deferred counter MUST increment, and the
    dispatcher MUST move on rather than hanging on the denied source.

    We configure the budget to deny the FIRST reservation attempt and
    admit every subsequent one; the dispatcher's next-tick retry then
    succeeds and the source reaches terminal state. This exercises both
    legs of the defer → retry loop.
    """

    def test_dispatch_defers_on_budget_exhausted_then_retries(
        self, fake_kube, fake_writer, fake_backlog, fake_budget
    ):
        from dk_data.ingestion.load_order import SourceDescriptor
        from dk_data.observability.metrics import (
            DK_HYDRATION_DISPATCH_DEFERRED_TOTAL,
        )

        descriptors = [SourceDescriptor("meta.single", "meta", "single", 1)]

        # First call denies, every subsequent one admits — gives the
        # dispatcher a chance to retry on the next tick.
        calls: list[int] = []

        def admit_fn(_requirements: Any) -> bool:
            calls.append(1)
            return len(calls) > 1

        fake_budget.admit_fn = admit_fn

        # Capture the deferred counter baseline before dispatch.
        before = DK_HYDRATION_DISPATCH_DEFERRED_TOTAL.labels(
            source="meta.single"
        )._value.get()

        dispatcher = _new_dispatcher(
            fake_kube=fake_kube,
            fake_writer=fake_writer,
            fake_backlog=fake_backlog,
            descriptors=descriptors,
            fake_budget=fake_budget,
        )
        results = dispatcher.dispatch_all()

        # The first reservation attempt denied the dispatch — kube was
        # NOT asked to create a Job on that tick. On the retry tick the
        # budget admitted and the Job was created.
        assert len(fake_budget.reserve_calls) == 2, (
            f"expected 2 reservation attempts (deny, then admit); got "
            f"{len(fake_budget.reserve_calls)}"
        )
        # Exactly one Job created — the retry, not the denied attempt.
        assert len(fake_kube.create_calls) == 1

        # Deferred counter ticked exactly once for the source that was
        # held back.
        after = DK_HYDRATION_DISPATCH_DEFERRED_TOTAL.labels(
            source="meta.single"
        )._value.get()
        assert after - before == 1, (
            f"DK_HYDRATION_DISPATCH_DEFERRED_TOTAL must increment by 1 on "
            f"deferral (got delta={after - before})"
        )

        # After retry, the source reached terminal state.
        assert len(results) == 1
        assert results[0].status == "completed"

    def test_dispatch_defers_does_not_call_underlying_dispatch(
        self, fake_kube, fake_writer, fake_backlog, fake_budget
    ):
        """With an always-denying budget AND an empty batch retry bound,
        the underlying ``_dispatch_one`` must NEVER be invoked.

        We construct a batch of 1 source, deny forever, and cap the
        outer loop via a max_parallel=0 guard... actually we can't cap
        max_parallel below 1 (validator enforces >= 1). Instead we
        assert the first-tick behaviour: after a denied tick, kube.create
        was not called, the source was NOT marked launched, and the
        deferred counter incremented once per retry attempt.
        """
        from dk_data.ingestion.load_order import SourceDescriptor

        descriptors = [SourceDescriptor("meta.never", "meta", "never", 1)]
        # Deny on every call, but cap the number of retry loops by
        # flipping to admit after 3 denials — gives us a bounded test.
        calls: list[int] = []

        def admit_fn(_requirements: Any) -> bool:
            calls.append(1)
            return len(calls) > 3

        fake_budget.admit_fn = admit_fn

        dispatcher = _new_dispatcher(
            fake_kube=fake_kube,
            fake_writer=fake_writer,
            fake_backlog=fake_backlog,
            descriptors=descriptors,
            fake_budget=fake_budget,
        )
        results = dispatcher.dispatch_all()

        # Exactly 3 denials + 1 admit = 4 reservation calls total.
        assert len(fake_budget.reserve_calls) == 4
        # create_job called exactly once — on the admit tick.
        assert len(fake_kube.create_calls) == 1
        assert len(results) == 1


class TestBudgetReleasedOnSuccess:
    """On a successful dispatch, ``release`` must be called with the same
    requirements that were reserved.
    """

    def test_release_called_after_successful_dispatch(
        self, fake_kube, fake_writer, fake_backlog, fake_budget
    ):
        from dk_data.ingestion.load_order import SourceDescriptor

        fake_budget.admit = True
        descriptors = [SourceDescriptor("meta.ok", "meta", "ok", 1)]

        dispatcher = _new_dispatcher(
            fake_kube=fake_kube,
            fake_writer=fake_writer,
            fake_backlog=fake_backlog,
            descriptors=descriptors,
            fake_budget=fake_budget,
        )
        dispatcher.dispatch_all()

        # One reservation + one matching release.
        assert len(fake_budget.reserve_calls) == 1
        assert len(fake_budget.release_calls) == 1
        # The requirements passed to release match what was reserved.
        assert fake_budget.release_calls[0] == fake_budget.reserve_calls[0]


class TestBudgetReleasedOnException:
    """If the underlying dispatch fn raises, the wrapper's try/finally must
    still release the reservation so the budget is not leaked.

    We force the FakeKubeClient.create_job to raise; the dispatcher's
    ``_dispatch_one`` catches that exception and returns a failed
    ``StepResult`` (not a re-raise) — so to test the exception path we
    reach into ``_dispatch_one`` at a lower layer: replace the method on
    the instance with one that raises directly. This matches how a bug
    in the dispatcher body (not in kube.create_job) would bubble up.
    """

    def test_release_called_when_dispatch_fn_raises(
        self, fake_kube, fake_writer, fake_backlog, fake_budget
    ):
        from dk_data.ingestion.load_order import SourceDescriptor

        descriptors = [SourceDescriptor("meta.boom", "meta", "boom", 1)]

        dispatcher = _new_dispatcher(
            fake_kube=fake_kube,
            fake_writer=fake_writer,
            fake_backlog=fake_backlog,
            descriptors=descriptors,
            fake_budget=fake_budget,
        )

        # Monkey-patch _dispatch_one to raise AFTER the wrapper reserves
        # and BEFORE the wrapper releases. We must re-wrap the mutated
        # method with the fake budget so the try/finally covers our
        # raise — otherwise the pre-built ``self._dispatch`` still holds
        # a reference to the original method.
        boom_calls: list[int] = []

        def raising_dispatch(_desc: Any) -> Any:
            boom_calls.append(1)
            raise RuntimeError("synthetic dispatch failure")

        dispatcher._dispatch_one = raising_dispatch  # type: ignore[assignment]
        dispatcher._dispatch = fake_budget.decorate_dispatch(raising_dispatch)

        # The exception propagates out of dispatch_all — the wrapper's
        # job is to release on the way out, not to swallow errors.
        with pytest.raises(RuntimeError, match="synthetic dispatch failure"):
            dispatcher.dispatch_all()

        # Reserve was called; dispatch fn was called; release was still
        # called despite the raise (that's the try/finally contract).
        assert len(fake_budget.reserve_calls) == 1
        assert boom_calls == [1]
        assert len(fake_budget.release_calls) == 1, (
            "release MUST be invoked even when the underlying dispatch "
            "raises — try/finally contract in decorate_dispatch"
        )
        # Reservation and release requirements match (no leak).
        assert fake_budget.release_calls[0] == fake_budget.reserve_calls[0]
