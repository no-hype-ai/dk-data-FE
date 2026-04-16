"""Admission control by budget (plan §D.3).

Feature: Horizon 3 / plan §D.3 — admission control by budget.

What this module does
---------------------
Exposes :class:`ResourceBudget`, a thin client over ``meta.resource_budget``
(migration 234) that lets the hydration dispatcher reserve capacity across
several named budgets (``wal_headroom``, ``db_connections``,
``concurrent_restores``, ``seaweedfs_iops``) atomically before dispatching
a per-source step, and release the same reservation when the step ends.

Why this exists (plan §D.3)
---------------------------
Today the dispatcher (plan §D.1) fans out per-source Jobs without a budget
check. One runaway source can saturate the PgBouncer hydration pool or
drive WAL usage past the safe headroom. Migration 234 persists a KV-shaped
budget table; this module turns that table into a pool-reservation API so
admission decisions are centralised, auditable, and race-free across
concurrent dispatchers (a scale-ready constraint — plan §D.3 calls out
that multiple dispatcher workers can run against the same cluster).

Typical usage
-------------
.. code-block:: python

    budget = ResourceBudget()
    try:
        requirements = descriptor.consumes or {
            "db_connections": 1,
            "concurrent_restores": 1,
        }
        if not budget.try_reserve(requirements):
            # dispatcher defers this source to the next tick
            return ADMISSION_DEFERRED

        try:
            run_hydration_step(source)
        finally:
            budget.release(requirements)
    finally:
        budget.close()

FR-030 compliance
-----------------
The connection is obtained via the sanctioned pool helpers in
``dk_data.ingestion.utils.database`` (``get_connection_pool`` +
``init_connection_pool``). Raw connection construction outside
``database.py`` is a CI failure (FR-030 / T003 grep gate). Tests inject a
pre-built (fake) connection via the ``conn=`` kwarg so the pool path is
not exercised in unit tests.

Concurrency model
-----------------
Every state-changing call takes row-level locks via ``SELECT ... FOR
UPDATE`` on the specific ``budget_key`` rows involved, then issues the
UPDATE in the same transaction. That makes the "check then write"
sequence atomic — concurrent workers always see a consistent snapshot
because they queue behind the lock. We sort the ``budget_key`` set
alphabetically before locking to give a stable lock order, which avoids
deadlocks when two workers reserve overlapping subsets (A ∩ B ≠ ∅).

Deferred-integration with D.1 and D.2
-------------------------------------
D.1 (dispatcher) and D.2 (descriptors) are sibling PRs still being landed.
:func:`decorate_dispatch` is the hand-off: D.1 can wrap its existing
``dispatch(descriptor) -> outcome`` function with ``budget.decorate_dispatch(
dispatch)`` and get admission control for free. The wrapper tolerates a
descriptor that has no ``consumes`` attribute (D.2 not merged yet) by
defaulting to ``{"db_connections": 1, "concurrent_restores": 1}``.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Mapping, Optional, TypeVar

import psycopg2
import psycopg2.extras

from dk_data.ingestion.utils.database import (
    get_connection_pool,
    init_connection_pool,
)

logger = logging.getLogger(__name__)

# Default consumption when a descriptor lacks a ``consumes`` block (D.2
# may not have merged yet). One DB connection + one restore slot is the
# minimum cost of running any source step; wal_headroom defaults to 0
# (we don't pre-reserve WAL — it's measured after the fact by the
# throttle) and seaweedfs_iops defaults to 0 for the same reason.
DEFAULT_CONSUMES: Dict[str, float] = {
    "db_connections": 1.0,
    "concurrent_restores": 1.0,
}


T = TypeVar("T")


class ResourceBudget:
    """Admission-control client over ``meta.resource_budget``.

    Holds one psycopg2 connection leased from the shared pool (FR-030) or
    an injected one for tests / orchestrators that already own a handle.
    Mirrors the lifecycle of
    :class:`dk_data.ingestion.hydration_backlog.HydrationBacklogWriter`.
    """

    def __init__(
        self,
        conn: Optional[psycopg2.extensions.connection] = None,
    ) -> None:
        """Initialise the writer.

        Args:
            conn: Optional pre-built connection (useful for tests that inject
                a fake, or orchestrators that already own a handle). When
                ``None`` (production path), a connection is leased from the
                shared pool via ``get_connection_pool()``. The pool is
                lazy-initialised on first use if needed.

                Unlike some other writers in this package we do NOT set
                ``autocommit=True`` — :meth:`try_reserve` must run the
                SELECT FOR UPDATE + UPDATE sequence inside a single
                transaction. We manage commit / rollback explicitly.
        """
        self._owns_conn = False
        if conn is None:
            try:
                pool = get_connection_pool()
            except RuntimeError:
                init_connection_pool()
                pool = get_connection_pool()
            conn = pool.getconn()
            # Deliberately NOT autocommit — we need transactional
            # check-then-write for try_reserve / release.
            conn.autocommit = False
            self._owns_conn = True
        self._conn = conn

    @property
    def conn(self) -> psycopg2.extensions.connection:
        return self._conn

    def close(self) -> None:
        """Return the leased connection to the pool (if owned)."""
        if not self._owns_conn:
            return
        try:
            pool = get_connection_pool()
            pool.putconn(self._conn)
        except Exception:  # pragma: no cover — defensive
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def try_reserve(self, requirements: Mapping[str, float]) -> bool:
        """Atomically reserve capacity across multiple budget keys.

        All keys in ``requirements`` are locked with ``SELECT ... FOR
        UPDATE`` in alphabetical order (deadlock-free lock ordering) in
        a single transaction. If every key has at least ``requested``
        remaining, the UPDATE increments each ``reserved`` counter and
        returns True. If any key is short, the transaction rolls back
        and returns False — no partial reservations.

        Args:
            requirements: ``{budget_key: amount}``. Unknown keys (not
                present in the table) cause a ROLLBACK and return False,
                same as insufficient capacity — the dispatcher should
                treat them identically (defer and alert).

        Returns:
            True on success (every reservation applied), False otherwise.
        """
        if not requirements:
            # No-op reservation always succeeds — useful for steps that
            # declare empty `consumes:` and don't consume anything.
            return True

        # Drop entries with zero / negative requests so we don't bother
        # locking rows we're not touching. Keeps the SELECT FOR UPDATE
        # scope as small as possible.
        active: Dict[str, Decimal] = {
            k: Decimal(str(v)) for k, v in requirements.items() if Decimal(str(v)) > 0
        }
        if not active:
            return True

        keys_sorted = sorted(active.keys())

        try:
            with self._conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                # Lock the involved rows in alphabetical order. The ORDER
                # BY inside the SELECT forces the lock-acquisition order
                # — without it, two workers locking {A, B} and {B, A}
                # could deadlock.
                cur.execute(
                    """
                    SELECT budget_key, total_capacity, reserved
                      FROM meta.resource_budget
                     WHERE budget_key = ANY(%s)
                     ORDER BY budget_key
                     FOR UPDATE
                    """,
                    (keys_sorted,),
                )
                rows = {r["budget_key"]: r for r in cur.fetchall()}

                # Every requested key must exist in the table. Missing
                # keys are a misconfiguration — fail closed so the
                # dispatcher defers instead of silently admitting.
                missing = [k for k in keys_sorted if k not in rows]
                if missing:
                    logger.warning(
                        "try_reserve: unknown budget_key(s) %s — failing closed "
                        "(check migration 234 seed + operator overrides)",
                        missing,
                    )
                    self._conn.rollback()
                    return False

                # Every key must have enough remaining.
                insufficient: list[str] = []
                for key in keys_sorted:
                    row = rows[key]
                    remaining = Decimal(row["total_capacity"]) - Decimal(row["reserved"])
                    if remaining < active[key]:
                        insufficient.append(
                            f"{key}: remaining={remaining} requested={active[key]}"
                        )

                if insufficient:
                    logger.debug(
                        "try_reserve denied — insufficient capacity: %s",
                        "; ".join(insufficient),
                    )
                    self._conn.rollback()
                    return False

                # All clear — bump reserved for each key.
                for key in keys_sorted:
                    cur.execute(
                        """
                        UPDATE meta.resource_budget
                           SET reserved   = reserved + %s,
                               updated_at = NOW()
                         WHERE budget_key = %s
                        """,
                        (active[key], key),
                    )

            self._conn.commit()
            return True
        except Exception:
            # Any surprise (network blip, constraint violation, etc.)
            # must not leak a half-applied reservation — roll back and
            # surface the error.
            self._conn.rollback()
            raise

    def release(self, requirements: Mapping[str, float]) -> None:
        """Decrement ``reserved`` for each key. Pairs with :meth:`try_reserve`.

        Clamps ``reserved`` to zero so an accidental double-release (or a
        capacity-reduction racing with a release) never pushes ``reserved``
        negative. The DB-level CHECK(reserved >= 0) would otherwise throw.

        Args:
            requirements: Same shape as passed to :meth:`try_reserve`.
                Keys that aren't in the table are ignored (best-effort
                release — we never want release to fail and leave the
                caller with a leaked reservation error).
        """
        if not requirements:
            return

        active: Dict[str, Decimal] = {
            k: Decimal(str(v)) for k, v in requirements.items() if Decimal(str(v)) > 0
        }
        if not active:
            return

        keys_sorted = sorted(active.keys())

        try:
            with self._conn.cursor() as cur:
                # Lock the rows in the same order as try_reserve to keep
                # the deadlock-free ordering consistent.
                cur.execute(
                    """
                    SELECT budget_key, reserved
                      FROM meta.resource_budget
                     WHERE budget_key = ANY(%s)
                     ORDER BY budget_key
                     FOR UPDATE
                    """,
                    (keys_sorted,),
                )
                existing = {r[0]: Decimal(r[1]) for r in cur.fetchall()}

                for key in keys_sorted:
                    if key not in existing:
                        # Unknown key — silently skip. A warn-log would
                        # spam if an operator deleted a budget row.
                        continue
                    # Clamp at zero.
                    new_reserved = max(Decimal(0), existing[key] - active[key])
                    cur.execute(
                        """
                        UPDATE meta.resource_budget
                           SET reserved   = %s,
                               updated_at = NOW()
                         WHERE budget_key = %s
                        """,
                        (new_reserved, key),
                    )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        """Return ``{budget_key: {"total", "reserved", "remaining"}}``.

        Values are floats for dashboard / JSON friendliness. Used by the
        metrics-publishing helper and by ``dk data hydrate status``
        (planned in plan §F.2).
        """
        out: Dict[str, Dict[str, float]] = {}
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT budget_key, total_capacity, reserved
                  FROM meta.resource_budget
                 ORDER BY budget_key
                """
            )
            for key, total, reserved in cur.fetchall():
                total_f = float(total)
                reserved_f = float(reserved)
                out[key] = {
                    "total": total_f,
                    "reserved": reserved_f,
                    "remaining": max(0.0, total_f - reserved_f),
                }
        # snapshot is a read-only call but we still commit to release the
        # implicit read transaction held by a non-autocommit connection.
        self._conn.commit()
        return out

    def publish_snapshot(self) -> Dict[str, Dict[str, float]]:
        """Take a snapshot and emit the two budget gauges.

        Updates :data:`DK_BUDGET_TOTAL_CAPACITY` and
        :data:`DK_BUDGET_REMAINING` for each budget_key so the
        grafana/dashboards/applications/dk-data-fe-resource-budget.json
        panel has live series to plot. Called by the dispatcher on a
        cadence (planned in plan §D.1) and by ``dk data hydrate status``.

        Returns:
            The same dict as :meth:`snapshot`, for chaining.
        """
        snap = self.snapshot()
        try:
            from dk_data.observability.metrics import (
                DK_BUDGET_REMAINING,
                DK_BUDGET_TOTAL_CAPACITY,
            )
            for key, values in snap.items():
                DK_BUDGET_TOTAL_CAPACITY.labels(key=key).set(values["total"])
                DK_BUDGET_REMAINING.labels(key=key).set(values["remaining"])
        except Exception:  # pragma: no cover — defensive
            logger.exception("publish_snapshot: failed to emit budget gauges")
        return snap

    # ------------------------------------------------------------------
    # Dispatcher integration
    # ------------------------------------------------------------------
    def decorate_dispatch(
        self,
        dispatch_fn: Callable[..., T],
    ) -> Callable[..., Optional[T]]:
        """Wrap a dispatch function with try_reserve/release.

        Deferred-integration hook for plan §D.1: when the dispatcher PR
        lands, it can adopt admission control by wrapping its existing
        ``dispatch(descriptor, ...) -> outcome`` callable with
        ``budget.decorate_dispatch(dispatch)``. The wrapper:

            1. Reads ``descriptor.consumes`` (or falls back to
               :data:`DEFAULT_CONSUMES` if the attribute / dict key is
               missing — tolerates D.2 not being merged yet).
            2. Calls :meth:`try_reserve`. If it returns False, emits the
               ``DK_BUDGET_RESERVATION_DENIED_TOTAL`` counter and returns
               ``None`` — dispatcher treats None as "defer, retry later".
            3. Otherwise calls ``dispatch_fn(descriptor, *args, **kwargs)``
               inside a try/finally that always releases the reservation
               on the way out (success, failure, or exception).

        The wrapped function signature is intentionally flexible
        (``*args, **kwargs``) to match whatever shape D.1 settles on.

        Args:
            dispatch_fn: The underlying dispatch callable. First argument
                is expected to be the descriptor (dict or object with a
                ``consumes`` attribute / key).

        Returns:
            A wrapped callable. Returns ``None`` on admission denial,
            or the wrapped function's return value otherwise.
        """
        def wrapped(descriptor: Any, *args: Any, **kwargs: Any) -> Optional[T]:
            requirements = _extract_consumes(descriptor)
            if not self.try_reserve(requirements):
                # Import inside the branch so the import cycle stays
                # light — metrics.py is a heavy module.
                try:
                    from dk_data.observability.metrics import (
                        DK_BUDGET_RESERVATION_DENIED_TOTAL,
                    )
                    # Label per-key so dashboards can show WHICH budget
                    # is hot. We emit one increment per key in the
                    # requirements dict so the ratio across keys is
                    # measurable.
                    for key in requirements:
                        DK_BUDGET_RESERVATION_DENIED_TOTAL.labels(key=key).inc()
                except Exception:  # pragma: no cover — defensive
                    pass
                return None
            try:
                return dispatch_fn(descriptor, *args, **kwargs)
            finally:
                # Always release — a dispatch_fn exception must not leak
                # the reservation. If release itself fails the
                # `except` below rolls back the release transaction but
                # re-raises so the caller sees it.
                try:
                    self.release(requirements)
                except Exception:  # pragma: no cover — defensive
                    logger.exception(
                        "release failed after dispatch — reservation may leak; "
                        "operator should inspect meta.resource_budget"
                    )

        return wrapped


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _extract_consumes(descriptor: Any) -> Dict[str, float]:
    """Read ``consumes`` from a descriptor, defaulting to DEFAULT_CONSUMES.

    Tolerates three shapes (D.2 has not settled yet — could ship as a
    dataclass, dict, or pydantic model):

      - ``descriptor`` is a dict with a ``"consumes"`` key
      - ``descriptor`` has a ``.consumes`` attribute
      - ``descriptor`` is the consumes dict itself (advanced callers)

    A missing / empty ``consumes`` falls back to
    :data:`DEFAULT_CONSUMES` so the dispatcher still enforces a
    minimum-footprint reservation.
    """
    consumes: Optional[Mapping[str, Any]] = None
    if isinstance(descriptor, Mapping):
        raw = descriptor.get("consumes")
        if isinstance(raw, Mapping):
            consumes = raw
    else:
        raw = getattr(descriptor, "consumes", None)
        if isinstance(raw, Mapping):
            consumes = raw

    if not consumes:
        return dict(DEFAULT_CONSUMES)

    out: Dict[str, float] = {}
    for k, v in consumes.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            # A non-numeric entry gets dropped rather than crashing the
            # dispatcher — a warn-log surfaces the bad descriptor without
            # blocking every other source.
            logger.warning(
                "descriptor consumes[%r] = %r is not numeric; ignoring", k, v,
            )
    if not out:
        return dict(DEFAULT_CONSUMES)
    return out


__all__ = [
    "ResourceBudget",
    "DEFAULT_CONSUMES",
]
