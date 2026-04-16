"""In-cluster hydrate dispatcher — plan §D.1 (Horizon 3).

Reads :data:`dk_data.ingestion.load_order.SOURCE_LOAD_ORDER` for the tier +
``depends_on`` graph, groups sources into tier batches, applies one
pre-rendered ``batch/v1`` Job per source via the in-cluster Kubernetes
Python client, watches each Job to a terminal state, records the outcome
to ``meta.transform_runs`` (``procedure_name='dispatcher:<source_id>'``),
and increments the ``meta.hydration_backlog`` failure counter on
non-``succeeded`` Jobs.

Key guarantees
--------------
* **Tier ordering is never violated.** A tier-N source is NEVER dispatched
  until every tier<N source has reached a terminal state (``succeeded``,
  ``failed``, ``skipped_quarantined``, ``blocked``). Inside a tier,
  ``depends_on`` is respected: a source is held back if any of its declared
  ancestors is not yet in a terminal state — bounded parallelism applies
  only to sources that are simultaneously admitted.
* **Quarantine short-circuit.** Before creating a Job the dispatcher calls
  ``HydrationBacklogWriter.is_quarantined(...)``; if True, the source is
  recorded as ``skipped_quarantined`` with no Job object created.
* **FR-030 compliance.** All Postgres work goes through
  ``get_connection_pool()`` (via the two writers).
* **No hardcoded cluster DNS.** The in-cluster kube client loads config
  from the ServiceAccount (``/var/run/secrets/kubernetes.io/serviceaccount``)
  which has no cluster-DNS literal. Postgres hostname is env-injected.
* **Graceful timeout.** ``activeDeadlineSeconds`` is carried on the
  rendered Job itself — the dispatcher doesn't have to enforce it; the
  kubelet does. We just observe the eventual Failed state.
* **Bounded parallelism.** A ``threading.Semaphore`` caps concurrent
  Jobs in flight at ``--max-parallel`` (default 4). This is a dispatcher-
  side cap; the kubelet may still queue Pods if cluster scheduling is
  tight, which is fine.

Usage
-----
::

    python -m dk_data.ingestion.hydrate_dispatcher --max-parallel 4

The dispatcher is intended to run as a one-shot in-cluster Job (see
``k8s/apps/hydrate/base/job-hydrate-dispatch.yaml``); it is NOT a
long-lived controller. Finishes when every source in SOURCE_LOAD_ORDER
has reached a terminal state or the Job's own
``activeDeadlineSeconds`` elapses.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from dk_data.ingestion.hydration_backlog import HydrationBacklogWriter
from dk_data.ingestion.load_order import (
    OUT_OF_SCOPE_SCHEMA_PREFIXES,
    SOURCE_LOAD_ORDER,
    SourceDescriptor,
)
from dk_data.ingestion.transform_runs_writer import TransformRunsWriter
from dk_data.ingestion.utils.database import get_connection_pool, init_connection_pool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Terminal states
# ---------------------------------------------------------------------------
TERMINAL_STATUSES: Set[str] = {
    "completed",            # Job succeeded
    "failed",               # Job failed (backoffLimit exhausted / deadline)
    "skipped_quarantined",  # DLQ entry blocked the dispatch
    "blocked",              # An ancestor was failed/quarantined
    "skipped_out_of_scope", # schema is in OUT_OF_SCOPE_SCHEMA_PREFIXES
}

DEFAULT_POLL_INTERVAL_SECONDS = 10
DEFAULT_MAX_PARALLEL = 4


@dataclass
class StepResult:
    """Per-source terminal state captured by the dispatcher."""

    source_id: str
    schema: str
    table: str
    tier: int
    status: str
    started_at: _dt.datetime
    ended_at: _dt.datetime
    job_name: Optional[str] = None
    error_detail: Optional[str] = None
    rows_processed: int = 0
    depends_on: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Kube client surface — kept thin + mock-friendly.
# ---------------------------------------------------------------------------


class KubeJobClient:
    """Thin wrapper around ``kubernetes.client.BatchV1Api``.

    Isolated into its own class so unit tests can inject a fake. Real
    cluster access is only initialised inside ``_connect()`` — importing
    the module on a laptop with no kube-config available never raises.
    """

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self._batch_api: Any = None

    def _connect(self) -> None:  # pragma: no cover — requires in-cluster env
        if self._batch_api is not None:
            return
        # Import lazily so tests that don't touch Kubernetes don't need
        # the in-cluster service account secret layout.
        from kubernetes import client, config

        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        self._batch_api = client.BatchV1Api()

    def create_job(self, manifest: Dict[str, Any]) -> str:
        """Create a Job, return its ``.metadata.name``."""
        self._connect()
        resp = self._batch_api.create_namespaced_job(
            namespace=self.namespace, body=manifest
        )
        return resp.metadata.name

    def get_job_status(self, name: str) -> Dict[str, Any]:
        """Return a JSON-friendly snapshot of ``status`` for the named Job."""
        self._connect()
        resp = self._batch_api.read_namespaced_job_status(
            name=name, namespace=self.namespace
        )
        status = resp.status
        conditions = []
        for cond in (status.conditions or []):
            conditions.append(
                {"type": cond.type, "status": cond.status, "reason": cond.reason}
            )
        return {
            "active": status.active or 0,
            "succeeded": status.succeeded or 0,
            "failed": status.failed or 0,
            "conditions": conditions,
        }


def _classify_job_status(snapshot: Dict[str, Any]) -> Optional[str]:
    """Map a Job status snapshot to a terminal state, or None if still running.

    Uses the ``conditions[].type in ('Complete','Failed')`` sentinel from
    the Kubernetes Job API — those conditions only appear once the Job
    has reached a terminal state.
    """
    for cond in snapshot.get("conditions") or []:
        if cond.get("type") == "Complete" and cond.get("status") == "True":
            return "completed"
        if cond.get("type") == "Failed" and cond.get("status") == "True":
            return "failed"
    # Fallback: if active==0 and succeeded>=1 treat as completed (ack to
    # clusters that haven't populated conditions yet).
    if (snapshot.get("active") or 0) == 0 and (snapshot.get("succeeded") or 0) >= 1:
        return "completed"
    return None


# ---------------------------------------------------------------------------
# Batching logic — pure functions, heavily unit-tested.
# ---------------------------------------------------------------------------


def _in_scope(desc: SourceDescriptor) -> bool:
    """Drop descriptors whose schema prefix is in OUT_OF_SCOPE (FR-014)."""
    return not any(
        desc.schema.startswith(prefix) for prefix in OUT_OF_SCOPE_SCHEMA_PREFIXES
    )


def tier_batches(
    descriptors: List[SourceDescriptor],
) -> List[List[SourceDescriptor]]:
    """Group descriptors into tier batches preserving declared order.

    A batch contains every source with the same tier number. Batches are
    returned in ascending-tier order. ``OUT_OF_SCOPE_SCHEMA_PREFIXES``
    are filtered out here — the dispatcher will never see them.
    """
    groups: Dict[int, List[SourceDescriptor]] = {}
    for d in descriptors:
        if not _in_scope(d):
            continue
        groups.setdefault(d.tier, []).append(d)
    return [groups[t] for t in sorted(groups.keys())]


def ready_in_batch(
    batch: List[SourceDescriptor],
    completed: Set[str],
    launched: Set[str],
) -> List[SourceDescriptor]:
    """Return descriptors in ``batch`` that are not yet launched AND whose
    ``depends_on`` is fully contained in ``completed``.

    ``launched`` contains source_ids the dispatcher has already dispatched
    (either still in-flight or terminal). Prevents double-scheduling.
    """
    out: List[SourceDescriptor] = []
    for d in batch:
        if d.source_id in launched:
            continue
        if all(dep in completed for dep in d.depends_on):
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class HydrateDispatcher:
    """Owns the tier-ordered fan-out loop.

    Exposed as a class (rather than a free function) so tests can
    instantiate with mocks and call public methods directly. Instance
    state is confined to writers + client + config; all per-run data is
    local to :meth:`dispatch_all`.
    """

    def __init__(
        self,
        *,
        max_parallel: int = DEFAULT_MAX_PARALLEL,
        namespace: str = "dk-data-prod",
        run_label: Optional[str] = None,
        poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
        writer: Optional[TransformRunsWriter] = None,
        backlog: Optional[HydrationBacklogWriter] = None,
        kube_client: Optional[KubeJobClient] = None,
        descriptors: Optional[List[SourceDescriptor]] = None,
    ) -> None:
        if max_parallel < 1:
            raise ValueError(f"max_parallel must be >= 1 (got {max_parallel})")
        self.max_parallel = max_parallel
        self.namespace = namespace
        self.run_label = run_label or _default_run_label()
        self.poll_interval_seconds = poll_interval_seconds

        # Writers default to pool-backed real ones; tests inject mocks.
        # FR-030: every new pool-backed handle goes through
        # get_connection_pool()/init_connection_pool().
        if writer is None or backlog is None:
            try:
                pool = get_connection_pool()
            except RuntimeError:
                init_connection_pool()
                pool = get_connection_pool()
            if writer is None:
                conn = pool.getconn()
                conn.autocommit = True
                self._writer_conn = conn
                writer = TransformRunsWriter(conn)
                self._owns_writer_conn = True
            else:
                self._writer_conn = None
                self._owns_writer_conn = False
            if backlog is None:
                backlog = HydrationBacklogWriter()
        else:
            self._writer_conn = None
            self._owns_writer_conn = False

        self.writer = writer
        self.backlog = backlog
        self.kube = kube_client or KubeJobClient(namespace=namespace)
        self.descriptors = descriptors or SOURCE_LOAD_ORDER

        # Semaphore caps concurrency — acquired before create_job, released
        # once the Job reaches a terminal state.
        self._sem = threading.Semaphore(self.max_parallel)

    # ------------------------------------------------------------------
    # Dispatch loop
    # ------------------------------------------------------------------

    def dispatch_all(self) -> List[StepResult]:
        """Run the whole tier-ordered fan-out. Returns every StepResult."""
        batches = tier_batches(self.descriptors)
        results: List[StepResult] = []
        completed: Set[str] = set()
        # Sources already in a "blocked" or "skipped" terminal state — we
        # count these toward dependency satisfaction so that a tier-N
        # spoke whose ancestor was quarantined does not hang forever. The
        # downstream silver models still get the `blocked` treatment via
        # propagate_blocked() in prestaged.py — this is only for the
        # outer tier gate.
        advanced: Set[str] = set()

        for tier_idx, batch in enumerate(batches, start=1):
            launched: Set[str] = set()
            # In-flight: {source_id: (descriptor, job_name, started_at)}
            in_flight: Dict[str, _InFlight] = {}

            # Loop until every source in this batch has reached a terminal state.
            while len(launched) < len(batch) or in_flight:
                # Dispatch anything newly ready.
                ready = ready_in_batch(batch, completed | advanced, launched)
                for desc in ready:
                    if len(in_flight) >= self.max_parallel:
                        break
                    # Acquire a slot. Non-blocking — we poll rather than
                    # block so the watcher runs for already-in-flight work.
                    if not self._sem.acquire(blocking=False):
                        break
                    launched.add(desc.source_id)

                    result = self._dispatch_one(desc)
                    if result is not None:
                        # Short-circuit terminal state (quarantined / OOS).
                        self._sem.release()
                        self._record_terminal(result)
                        results.append(result)
                        advanced.add(desc.source_id)
                        if result.status == "completed":
                            completed.add(desc.source_id)
                        continue

                    in_flight[desc.source_id] = _InFlight(
                        descriptor=desc,
                        job_name=self._job_name_for(desc),
                        started_at=_now_utc(),
                    )

                # Poll in-flight Jobs for completion.
                finished_ids: List[str] = []
                for src_id, info in in_flight.items():
                    status = self._poll_terminal(info.job_name)
                    if status is None:
                        continue
                    finished_ids.append(src_id)
                    ended_at = _now_utc()
                    result = StepResult(
                        source_id=src_id,
                        schema=info.descriptor.schema,
                        table=info.descriptor.table,
                        tier=info.descriptor.tier,
                        status=status,
                        started_at=info.started_at,
                        ended_at=ended_at,
                        job_name=info.job_name,
                        depends_on=list(info.descriptor.depends_on),
                    )
                    self._record_terminal(result)
                    if status == "failed":
                        self._record_failure(info.descriptor, reason="job-failed")
                    results.append(result)
                    advanced.add(src_id)
                    if status == "completed":
                        completed.add(src_id)
                    self._sem.release()

                for src_id in finished_ids:
                    del in_flight[src_id]

                # Backoff — don't busy-spin.
                if in_flight or len(launched) < len(batch):
                    time.sleep(self.poll_interval_seconds)

            logger.info(
                "Tier %d batch complete: %d/%d sources done",
                tier_idx,
                sum(1 for r in results if r.tier == tier_idx),
                len(batch),
            )

        return results

    # ------------------------------------------------------------------
    # Per-source helpers
    # ------------------------------------------------------------------

    def _dispatch_one(self, desc: SourceDescriptor) -> Optional[StepResult]:
        """Create (or short-circuit) the per-source Job.

        Returns a StepResult if the source was short-circuited (quarantined
        etc.) or None if a real Job was created (caller adds to in-flight).
        """
        started_at = _now_utc()
        # 1. Quarantine short-circuit (C.3).
        try:
            if self.backlog is not None and self.backlog.is_quarantined(
                desc.source_id, desc.schema, desc.table
            ):
                return StepResult(
                    source_id=desc.source_id,
                    schema=desc.schema,
                    table=desc.table,
                    tier=desc.tier,
                    status="skipped_quarantined",
                    started_at=started_at,
                    ended_at=started_at,
                    depends_on=list(desc.depends_on),
                )
        except Exception as exc:  # noqa: BLE001
            # A backlog-read failure must not block dispatch.
            logger.warning(
                "is_quarantined(%s) raised %s — proceeding to dispatch",
                desc.source_id,
                exc,
            )

        # 2. Build the Job manifest (reuses the rendered one on disk).
        manifest = self._build_job_manifest(desc)

        # 3. Create via kube API.
        try:
            self.kube.create_job(manifest)
        except Exception as exc:  # noqa: BLE001
            logger.error("create_job failed for %s: %s", desc.source_id, exc)
            self._record_failure(desc, reason=f"create-failed:{exc}")
            return StepResult(
                source_id=desc.source_id,
                schema=desc.schema,
                table=desc.table,
                tier=desc.tier,
                status="failed",
                started_at=started_at,
                ended_at=_now_utc(),
                error_detail=f"kube create_job: {exc}",
                depends_on=list(desc.depends_on),
            )
        return None

    def _poll_terminal(self, job_name: str) -> Optional[str]:
        """Poll the Job once; return terminal status or None if still running."""
        try:
            snapshot = self.kube.get_job_status(job_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_job_status(%s) failed: %s", job_name, exc)
            return None
        return _classify_job_status(snapshot)

    def _build_job_manifest(self, desc: SourceDescriptor) -> Dict[str, Any]:
        """Construct a minimal Job manifest keyed on the rendered base name.

        In production ArgoCD has already applied the base Job objects via
        ``kustomization.yaml``; the dispatcher's create call is effectively
        a per-run clone (different ``<date>`` suffix). We build a fresh
        manifest rather than mutating the rendered one so the dispatcher
        is idempotent across reruns.
        """
        # Kubernetes Job names: <=63 chars, lowercase, alphanumeric + '-'.
        # source_id dots → hyphens; plus a time-based suffix keeps per-run uniqueness.
        safe = desc.source_id.replace(".", "-").replace("_", "-")
        suffix = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d%H%M%S")
        job_name = f"hydrate-{safe}-{suffix}"[:63].rstrip("-")

        # Dispatch a minimal CronJob-like shell. The heavy lifting (affinity,
        # priority, secrets) is inherited from the on-disk rendered Job
        # of the same base name — the kube API resolves the full spec at
        # admission. We only need the name + spec shape.
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": job_name,
                "namespace": self.namespace,
                "labels": {
                    "app": "prestaged-hydrate",
                    "app.kubernetes.io/component": "per-source-hydrate",
                    "dk-data/dispatcher-run": self.run_label,
                    "dk-data/source-id": safe,
                },
                "annotations": {
                    "dk-data/source-id": desc.source_id,
                    "dk-data/tier": str(desc.tier),
                    "dk-data/run-label": self.run_label,
                },
            },
            "spec": {
                "backoffLimit": 2,
                "activeDeadlineSeconds": 14400,
                "ttlSecondsAfterFinished": 604800,
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "prestaged-hydrate",
                            "dk-data/source-id": safe,
                        }
                    },
                    "spec": {
                        "restartPolicy": "OnFailure",
                        "priorityClassName": "production-critical",
                        "serviceAccountName": "hydrate-dispatcher",
                        "imagePullSecrets": [{"name": "ghcr-credentials"}],
                        "affinity": {
                            "nodeAffinity": {
                                "requiredDuringSchedulingIgnoredDuringExecution": {
                                    "nodeSelectorTerms": [
                                        {
                                            "matchExpressions": [
                                                {
                                                    "key": "dk.role",
                                                    "operator": "In",
                                                    "values": ["general"],
                                                }
                                            ]
                                        }
                                    ]
                                }
                            }
                        },
                        "tolerations": [
                            {
                                "key": "nvidia.com/gpu",
                                "operator": "Equal",
                                "value": "true",
                                "effect": "NoSchedule",
                            }
                        ],
                        "containers": [
                            {
                                "name": "hydrate",
                                "image": "ghcr.io/data-kinetic/dk-data:prod-<sha>",
                                "command": [
                                    "python",
                                    "-m",
                                    "dk_data.ingestion.prestaged",
                                ],
                                "args": [
                                    "--source",
                                    desc.source_id,
                                    "--run-label",
                                    self.run_label,
                                ],
                                "envFrom": [
                                    {"secretRef": {"name": "dk-data-secrets"}}
                                ],
                                "env": [
                                    {
                                        "name": "PRESTAGED_ROOT",
                                        "value": "/data/prestaged",
                                    }
                                ],
                                "resources": {
                                    "requests": {
                                        "cpu": "500m",
                                        "memory": "512Mi",
                                        "ephemeral-storage": "5Gi",
                                    },
                                    "limits": {
                                        "cpu": "2",
                                        "memory": "4Gi",
                                        "ephemeral-storage": "20Gi",
                                    },
                                },
                            }
                        ],
                        "volumes": [
                            {
                                "name": "prestaged",
                                "hostPath": {
                                    "path": "/opt/dk-data-prestaged",
                                    "type": "Directory",
                                },
                            }
                        ],
                    },
                },
            },
        }

    def _job_name_for(self, desc: SourceDescriptor) -> str:
        """Mirror the name formula used by :meth:`_build_job_manifest`."""
        safe = desc.source_id.replace(".", "-").replace("_", "-")
        suffix = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"hydrate-{safe}-{suffix}"[:63].rstrip("-")

    # ------------------------------------------------------------------
    # Writers
    # ------------------------------------------------------------------

    def _record_terminal(self, result: StepResult) -> None:
        """Write a terminal StepResult into ``meta.transform_runs``.

        ``procedure_name`` uses the ``dispatcher:`` prefix (distinct from
        ``prestaged:``) so operators can filter dispatcher-level outcomes
        from per-source loader outcomes::

            SELECT * FROM meta.transform_runs
             WHERE procedure_name LIKE 'dispatcher:%'
             ORDER BY started_at DESC;
        """
        try:
            # TransformRunsWriter.record() keys the procedure_name off
            # schema/table with a fixed ``prestaged:`` prefix — we want a
            # different prefix, so write the INSERT manually but go
            # through the writer's connection (same transactional scope).
            details = json.dumps(
                {
                    "run_label": self.run_label,
                    "source_id": result.source_id,
                    "target_schema": result.schema,
                    "target_table": result.table,
                    "tier": result.tier,
                    "job_name": result.job_name,
                    "depends_on": result.depends_on,
                    "error_detail": result.error_detail,
                }
            )
            conn = getattr(self.writer, "_conn", None)
            if conn is None:
                logger.warning(
                    "writer conn unavailable — skipping transform_runs record for %s",
                    result.source_id,
                )
                return
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meta.transform_runs
                      (procedure_name, chunk_position, started_at, ended_at,
                       rows_processed, wal_bytes, status, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        f"dispatcher:{result.source_id}",
                        "-",
                        result.started_at,
                        result.ended_at,
                        result.rows_processed,
                        0,
                        result.status,
                        details,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "failed to record dispatcher outcome for %s: %s",
                result.source_id,
                exc,
            )

    def _record_failure(self, desc: SourceDescriptor, *, reason: str) -> None:
        """Increment the C.3 backlog failure counter."""
        if self.backlog is None:
            return
        try:
            self.backlog.record_failure(
                source_id=desc.source_id,
                schema=desc.schema,
                table=desc.table,
                error_code="DISPATCH_JOB_FAILED",
                error_detail=reason,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "backlog.record_failure failed for %s: %s", desc.source_id, exc
            )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Return pool connections and close the backlog writer."""
        if self._owns_writer_conn and self._writer_conn is not None:
            try:
                pool = get_connection_pool()
                pool.putconn(self._writer_conn)
            except Exception:  # pragma: no cover — defensive
                pass
            self._writer_conn = None
        if self.backlog is not None:
            try:
                self.backlog.close()
            except Exception:  # pragma: no cover — defensive
                pass


@dataclass
class _InFlight:
    descriptor: SourceDescriptor
    job_name: str
    started_at: _dt.datetime


def _default_run_label() -> str:
    """Deterministic dispatcher-run label (UTC wall clock to minute precision).

    The per-source prestaged run still computes its own run_label from
    artifact hashes + cluster fingerprint — this dispatcher-level label
    just groups the Jobs produced by one dispatcher invocation.
    """
    return "dispatcher-" + _dt.datetime.now(_dt.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dk_data.ingestion.hydrate_dispatcher",
        description="In-cluster tier-ordered per-source hydrate dispatcher (D.1).",
    )
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=DEFAULT_MAX_PARALLEL,
        help=f"Max concurrent Jobs in flight (default: {DEFAULT_MAX_PARALLEL}).",
    )
    parser.add_argument(
        "--namespace",
        default=os.environ.get("POD_NAMESPACE") or "dk-data-prod",
        help="Kubernetes namespace for created Jobs (default: dk-data-prod).",
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="Dispatcher run label (default: auto-generated from UTC wall clock).",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=(
            "Seconds between Job-status polls + new-dispatch passes "
            f"(default: {DEFAULT_POLL_INTERVAL_SECONDS})."
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable DEBUG logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    dispatcher = HydrateDispatcher(
        max_parallel=args.max_parallel,
        namespace=args.namespace,
        run_label=args.run_label,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    try:
        results = dispatcher.dispatch_all()
    finally:
        dispatcher.close()

    # Emit a JSON summary for log-aggregator-friendly parsing.
    summary = {
        "run_label": dispatcher.run_label,
        "total": len(results),
        "completed": sum(1 for r in results if r.status == "completed"),
        "failed": sum(1 for r in results if r.status == "failed"),
        "quarantined": sum(
            1 for r in results if r.status == "skipped_quarantined"
        ),
        "blocked": sum(1 for r in results if r.status == "blocked"),
    }
    print(json.dumps(summary))
    return 0 if summary["failed"] == 0 else 2


if __name__ == "__main__":  # pragma: no cover — real entry point
    sys.exit(main(sys.argv[1:]))
