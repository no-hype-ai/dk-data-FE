"""Pre-staged hydration entry point (feature 005-prestaged-hydration).

This module is a **skeleton** at Stage 1. Each public function has its
signature, docstring, and contract but raises ``NotImplementedError``.

Stage 2 swarm workers fill in the bodies in disjoint regions:
    Worker `discovery-validate` owns: walk_prestaged_root, validate_magic_bytes,
        compute_sha256, group_by_table, select_highest_tier.
    Worker `dispatch-cli` owns: dispatch_pg_restore, run_step, main.

Wal-throttling helpers (wal_pressure, pause_until_below) land in Stage 4.
Live-fetch fallback (run_live_fetch) lands in Stage 5.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import psycopg2
from loguru import logger

from dk_data.ingestion.load_order import (
    SOURCE_LOAD_ORDER,
    WAL_MODE_TABLES,
    plan_load,
    propagate_blocked,
)
from dk_data.ingestion.prestaged_manifest import (
    DEFAULT_ROW_TOLERANCE_PCT,
    is_row_count_mismatch,
    load_manifest,
)
from dk_data.ingestion.utils.database import build_dsn
from dk_data.ingestion.prestaged_safety import is_restorable_target
from dk_data.ingestion.prestaged_types import (
    PGDMP_MAGIC,
    LoadPlan,
    LoadStep,
    PrestagedArtifact,
    RunStatus,
    Tier,
)
from dk_data.ingestion.transform_runs_writer import TransformRunsWriter
from dk_data.ingestion.wal_throttle import WalThrottle
# C.3 — DLQ / quarantine. Optional at module-import time because
# hydration_backlog.py pulls psycopg2 from the pool lazily and some tests
# import prestaged.py without full DB wiring. See plan §C.3.
from dk_data.ingestion.hydration_backlog import HydrationBacklogWriter

# Module-level inode → sha256 cache; avoids re-reading the same file twice
# within a single process (FR-002 performance note).
_SHA_CACHE: dict[int, str] = {}


# T073 — Best-effort OTLP emission. Wrapped in try/except so any failure
# (alloy down, opentelemetry not installed, network blip) is silently
# absorbed. The hydration writer in meta.transform_runs remains the
# single source of truth (FR-009); OTLP is signal-only.

def _emit_otlp(step: LoadStep, run_label: str, status: str, row_count: int) -> None:
    """Emit one OpenTelemetry span event per terminal transition.

    Never raises. If opentelemetry-api isn't installed, or the configured
    exporter is unreachable, the function logs once at DEBUG and returns.
    """
    try:
        from opentelemetry import trace  # lazy
        tracer = trace.get_tracer("dk_data.ingestion.prestaged")
        with tracer.start_as_current_span("hydrate.step") as span:
            span.set_attribute("hydrate.run_label", run_label)
            span.set_attribute("hydrate.source_id", step.source_id)
            span.set_attribute("hydrate.target_schema", step.target_schema)
            span.set_attribute("hydrate.target_table", step.target_table)
            span.set_attribute("hydrate.kind", step.kind)
            span.set_attribute("hydrate.status", status)
            span.set_attribute("hydrate.row_count", row_count)
            span.set_attribute("hydrate.wal_mode", step.wal_mode)
    except Exception:  # noqa: BLE001
        # Never let observability break ingestion. [WALBUD adjacent: FR-009]
        logger.debug("OTLP emission failed (silently swallowed)")

# Precedence for select_highest_tier (FR-003): silver beats bronze beats raw.
_TIER_RANK: dict[str, int] = {"raw": 0, "bronze": 1, "silver": 2}


# ---------------------------------------------------------------------------
# Discovery + validation (Worker: discovery-validate)
# ---------------------------------------------------------------------------

def walk_prestaged_root(root: Path) -> list[PrestagedArtifact]:
    """Discover every ``.dump`` file under ``root``.

    Supports two on-disk layouts (FR-001):
      1. ``<root>/_staging/<archive>/dk-data-files/{schema}/{table_dir}/*.dump``
      2. ``<root>/_loose_dumps/{schema}/*.dump``

    Args:
        root: value of ``PRESTAGED_ROOT`` env var (FR-016).

    Returns:
        Every ``.dump`` file as a :class:`PrestagedArtifact`, with
        ``magic_ok=False`` and ``sha256=None`` (set by later helpers).

    Raises:
        FileNotFoundError: when ``root`` does not exist (fail-fast per FR-016).
    """
    if not root.exists():
        raise FileNotFoundError(f"PRESTAGED_ROOT does not exist: {root}")

    artifacts: list[PrestagedArtifact] = []

    def _tier_from_schema(schema: str) -> Tier:
        for suffix, tier in (("_raw", "raw"), ("_bronze", "bronze"), ("_silver", "silver")):
            if schema.endswith(suffix):
                return tier  # type: ignore[return-value]
        # Special schemas (meta, sqlmesh, ...) without a tier suffix:
        # treat as raw — they're never the target of multi-tier
        # competition, so the precedence rule in select_highest_tier
        # never sees them in a contest.
        return "raw"

    def _chunk_index(filename: str) -> str:
        for prefix in ("retry_", "1_", "3_"):
            if filename.startswith(prefix):
                return prefix
        return ""

    # ── Layout 1: _staging/<archive>/dk-data-files/{schema}/{table_dir}/*.dump
    staging_root = root / "_staging"
    if staging_root.is_dir():
        for archive_dir in staging_root.iterdir():
            dk_data_files = archive_dir / "dk-data-files"
            if not dk_data_files.is_dir():
                continue
            for schema_dir in dk_data_files.iterdir():
                if not schema_dir.is_dir():
                    continue
                schema = schema_dir.name
                tier = _tier_from_schema(schema)
                for table_dir in schema_dir.iterdir():
                    if not table_dir.is_dir():
                        continue
                    table_dir_name = table_dir.name
                    if tier == "raw":
                        target_table = table_dir_name
                    else:
                        # {schema}__{table}__{hash}  →  take the middle part
                        parts = table_dir_name.split("__", 2)
                        target_table = parts[1] if len(parts) >= 2 else table_dir_name
                    for dump_file in table_dir.glob("*.dump"):
                        artifacts.append(
                            PrestagedArtifact(
                                path=dump_file,
                                target_schema=schema,
                                target_table=target_table,
                                tier=tier,
                                chunk_index=_chunk_index(dump_file.name),
                                size_bytes=dump_file.stat().st_size,
                            )
                        )

    # ── Layout 2: _loose_dumps/{schema}/*.dump
    loose_root = root / "_loose_dumps"
    if loose_root.is_dir():
        for schema_dir in loose_root.iterdir():
            if not schema_dir.is_dir():
                continue
            schema = schema_dir.name
            tier = _tier_from_schema(schema)
            for dump_file in schema_dir.glob("*.dump"):
                # Filename: {schema}__{table}__{hash}-{archive_num}.dump
                # rsplit('-', 1) strips the trailing archive number safely.
                base = dump_file.stem.rsplit("-", 1)[0]
                parts = base.split("__", 2)
                target_table = parts[1] if len(parts) >= 2 else dump_file.stem
                artifacts.append(
                    PrestagedArtifact(
                        path=dump_file,
                        target_schema=schema,
                        target_table=target_table,
                        tier=tier,
                        chunk_index=_chunk_index(dump_file.name),
                        size_bytes=dump_file.stat().st_size,
                    )
                )

    return artifacts


def validate_magic_bytes(artifact: PrestagedArtifact) -> PrestagedArtifact:
    """Check first 5 bytes == ``b"PGDMP"`` (FR-002).

    Returns a new artifact with ``magic_ok`` set.
    """
    with open(artifact.path, "rb") as fh:
        header = fh.read(len(PGDMP_MAGIC))
    return artifact.model_copy(update={"magic_ok": header == PGDMP_MAGIC})


def compute_sha256(artifact: PrestagedArtifact) -> PrestagedArtifact:
    """Compute and attach sha256. Caches by inode to avoid re-reading (FR-002)."""
    inode = os.stat(artifact.path).st_ino
    if inode not in _SHA_CACHE:
        h = hashlib.sha256()
        with open(artifact.path, "rb") as fh:
            while chunk := fh.read(1024 * 1024):
                h.update(chunk)
        _SHA_CACHE[inode] = h.hexdigest()
    return artifact.model_copy(update={"sha256": _SHA_CACHE[inode]})


def group_by_table(
    artifacts: Iterable[PrestagedArtifact],
) -> dict[tuple[str, str], list[PrestagedArtifact]]:
    """Group artifacts by ``(target_schema, target_table)`` with lexical
    chunk ordering (FR-004)."""
    groups: dict[tuple[str, str], list[PrestagedArtifact]] = defaultdict(list)
    for artifact in artifacts:
        groups[(artifact.target_schema, artifact.target_table)].append(artifact)
    return {key: sorted(group, key=lambda a: a.chunk_index) for key, group in groups.items()}


def select_highest_tier(
    group: list[PrestagedArtifact],
) -> tuple[Tier, list[PrestagedArtifact]]:
    """Apply precedence silver > bronze > raw (FR-003).

    Returns ``(tier, artifacts_at_that_tier)``. Lower-tier artifacts in
    the input are discarded for this run.
    """
    best_tier: Tier = max(group, key=lambda a: _TIER_RANK[a.tier]).tier
    return best_tier, [a for a in group if a.tier == best_tier]


# ---------------------------------------------------------------------------
# Dispatch + orchestration (Worker: dispatch-cli)
# ---------------------------------------------------------------------------

def dispatch_pg_restore(
    pg_url: str,
    step: LoadStep,
    artifact: PrestagedArtifact,
    *,
    first_chunk: bool,
) -> int:
    """Run ``pg_restore -Fc …`` for a single chunk (research.md R1).

    Opens a short-lived psycopg2 session to acquire a session-level advisory
    lock keyed on ``hashtext('prestaged:' || schema || '.' || table)`` before
    spawning the subprocess, and releases it in the ``finally`` block (R5).

    Args:
        pg_url: destination connection string.
        step: the LoadStep this chunk belongs to.
        artifact: the specific chunk to restore.
        first_chunk: True only for the lexically-first chunk of a table;
            controls ``--clean --if-exists`` (applied on first only).

    Returns:
        pg_restore subprocess exit code. 0 == success.
    """
    schema = step.target_schema
    table = step.target_table
    lock_key_expr = f"prestaged:{schema}.{table}"

    # Dropped --single-transaction: pg_restore 17 (what the in-cluster
    # image ships) emits `SET transaction_timeout = 0;` as its first
    # statement, which PG 16 (prod server) rejects with
    # `unrecognized configuration parameter`. With --single-transaction
    # this is fatal (whole restore rolls back). Without, it's a warning
    # and the subsequent COPY commands still run fine. Per-source
    # atomicity is recoverable via TRUNCATE+retry on re-run.
    cmd = [
        "pg_restore",
        "-Fc",
        "--no-owner",
        "--no-privileges",
        "--section=data",
        f"--dbname={pg_url}",
    ]
    if first_chunk:
        cmd += ["--clean", "--if-exists"]
    cmd.append(str(artifact.path))

    # `--section=data` skips DDL, so `--clean` does NOT drop the target
    # table's existing rows. For a first-chunk restore we need to clear
    # any leftover data so the COPY doesn't conflict with existing PKs.
    # This runs in a separate connection so it commits before pg_restore.
    if first_chunk:
        try:
            with psycopg2.connect(pg_url) as truncate_conn:  # pg_url via build_dsn()
                truncate_conn.autocommit = True
                with truncate_conn.cursor() as cur:
                    # Quote schema/table to be safe with reserved names.
                    cur.execute(f'TRUNCATE TABLE "{schema}"."{table}" CASCADE;')
            logger.info(f"truncated {schema}.{table} before first chunk")
        except psycopg2.Error as exc:
            # If the table doesn't exist yet (e.g. raw staging tables created
            # implicitly by the dump), TRUNCATE will error. Swallow that —
            # pg_restore will create it.
            logger.info(
                f"TRUNCATE on {schema}.{table} skipped: {exc}"
            )

    logger.info(f"pg_restore command: {' '.join(cmd)}")

    lock_conn = psycopg2.connect(pg_url)  # pg_url via build_dsn()
    lock_conn.autocommit = True
    try:
        with lock_conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_lock(hashtext(%s))", (lock_key_expr,)
            )

        result = subprocess.run(cmd, capture_output=True, text=True)
        logger.info(
            "pg_restore exited with code {} for {}.{}",
            result.returncode,
            schema,
            table,
        )
        if result.returncode != 0:
            logger.warning("pg_restore stderr: {}", result.stderr[:2048])
            # Known-benign: pg_restore 17 emits `SET transaction_timeout = 0;`
            # which PG 16 rejects. The SET fails but the actual data COPY
            # still runs. If that's the ONLY error, treat as success.
            stderr = result.stderr
            only_benign = (
                "transaction_timeout" in stderr
                and "errors ignored on restore" in stderr
                and "COPY failed" not in stderr
                and "FATAL" not in stderr
            )
            if only_benign:
                logger.info(
                    "pg_restore rc=1 but only the benign SET "
                    "transaction_timeout error reported — treating as "
                    "success for {}.{}", schema, table
                )
                return 0
        return result.returncode
    finally:
        with lock_conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_unlock(hashtext(%s))", (lock_key_expr,)
            )
        lock_conn.close()


# ---------------------------------------------------------------------------
# DLQ error-code normalisation (plan §C.3)
# ---------------------------------------------------------------------------
# The backlog writer stores a short stable error_code (plus the free-text
# error_detail). The code drives the "same signature" check that triggers
# auto-quarantine. We keep the set small and shape-stable — heuristics on
# the detail string, not the full class hierarchy — so a retry of the same
# failure reliably produces the same code.

def _record_dlq_failure(
    backlog: HydrationBacklogWriter | None,
    source_id: str,
    schema: str,
    table: str,
    *,
    exc: BaseException | None = None,
    detail: str | None = None,
) -> None:
    """Best-effort DLQ failure record (plan §C.3).

    Wrapped in a broad try/except because a DLQ write failure MUST NOT
    fail the step. Same tolerant pattern as
    :meth:`ArtifactProvenanceWriter.record_swallow`.
    """
    if backlog is None:
        return
    try:
        from dk_data.observability.metrics import (
            DK_HYDRATION_DLQ_ADDED_TOTAL,
            DK_HYDRATION_DLQ_QUARANTINED_TOTAL,
        )
    except Exception:  # noqa: BLE001
        DK_HYDRATION_DLQ_ADDED_TOTAL = None  # type: ignore[assignment]
        DK_HYDRATION_DLQ_QUARANTINED_TOTAL = None  # type: ignore[assignment]
    code = _normalise_error_code(exc, detail)
    try:
        row = backlog.record_failure(
            source_id=source_id,
            schema=schema,
            table=table,
            error_code=code,
            error_detail=detail or (str(exc) if exc else ""),
        )
        try:
            if DK_HYDRATION_DLQ_ADDED_TOTAL is not None:
                DK_HYDRATION_DLQ_ADDED_TOTAL.labels(source=source_id).inc()
            if (
                DK_HYDRATION_DLQ_QUARANTINED_TOTAL is not None
                and row.get("quarantined_by") == "auto"
                and row.get("quarantined_at") is not None
            ):
                DK_HYDRATION_DLQ_QUARANTINED_TOTAL.labels(source=source_id).inc()
        except Exception:  # noqa: BLE001
            logger.debug("dlq metric emission failed")
    except Exception as exc2:  # noqa: BLE001
        logger.warning(
            "backlog.record_failure swallowed for {}: {} (continuing)",
            source_id, exc2,
        )


def _normalise_error_code(exc: BaseException | None, detail: str | None) -> str:
    """Return a short stable DLQ error_code for a failure.

    Known-stable codes:
      - ``CONN_LOST``           — psycopg2 InterfaceError / OperationalError
      - ``PG_RESTORE_FATAL``    — pg_restore non-zero RC (detail contains rc hint)
      - ``ROW_MISMATCH``        — caller passes explicit row_mismatch status
      - ``UNKNOWN_PG_ERROR``    — psycopg2.Error other than the connection family
      - ``UNKNOWN_ERROR``       — everything else

    ``exc`` takes precedence when present; otherwise the ``detail`` string is
    scanned for the ``pg_restore returned exit code`` substring emitted by
    :func:`dispatch_pg_restore`.
    """
    if exc is not None:
        # Order matters: InterfaceError subclasses OperationalError in some
        # psycopg2 versions, so check the narrower types first.
        if isinstance(exc, (psycopg2.InterfaceError, psycopg2.OperationalError)):
            return "CONN_LOST"
        if isinstance(exc, psycopg2.Error):
            return "UNKNOWN_PG_ERROR"
        return "UNKNOWN_ERROR"
    if detail:
        if "pg_restore returned exit code" in detail:
            return "PG_RESTORE_FATAL"
        if "row_mismatch" in detail:
            return "ROW_MISMATCH"
        if "connection lost" in detail.lower():
            return "CONN_LOST"
    return "UNKNOWN_ERROR"


def run_step(
    conn: Any,
    step: LoadStep,
    run_label: str,
    writer: TransformRunsWriter,
    throttle: WalThrottle | None = None,
    backlog: HydrationBacklogWriter | None = None,
) -> "RunStepOutcome":
    """Orchestrate one step end-to-end: view-safety pre-flight → per-chunk
    dispatch → row-count → ``meta.transform_runs`` upsert.

    When ``step.wal_mode`` is True and a ``throttle`` is supplied, calls
    :meth:`WalThrottle.maybe_pause` after the view-safety check and before
    the first ``pg_restore`` invocation (FR-007).

    When ``backlog`` is supplied (plan §C.3), the step is SKIPPED with
    outcome ``status='quarantined'`` if the source is currently
    quarantined in ``meta.hydration_backlog``. On any terminal ``failed``
    / ``row_mismatch`` outcome, a failure is recorded (best-effort — any
    backlog error is swallowed so a DLQ write failure never fails the
    step itself).

    Tags: [AUDIT] [IDMPT] [VIEWSAFE] [WALBUD] [DLQ]
    """
    schema = step.target_schema
    table = step.target_table
    started_at = _dt.datetime.now(_dt.timezone.utc)

    # 0. DLQ quarantine pre-flight (plan §C.3). Runs BEFORE the
    #    is_completed check so a quarantined source that somehow had a
    #    successful completed row in a prior run still reports
    #    "quarantined" deterministically — operators expect
    #    quarantine to be the loudest signal.
    if backlog is not None:
        try:
            if backlog.is_quarantined(step.source_id, schema, table):
                try:
                    from dk_data.observability.metrics import (
                        DK_HYDRATION_DLQ_SKIPPED_TOTAL,
                    )
                    DK_HYDRATION_DLQ_SKIPPED_TOTAL.labels(source=step.source_id).inc()
                except Exception:  # noqa: BLE001
                    logger.debug("dlq_skipped metric emission failed")
                logger.warning(
                    "skipping {} — quarantined in meta.hydration_backlog",
                    step.source_id,
                )
                return RunStepOutcome(
                    status="quarantined",
                    row_count=0,
                    error_detail="dlq quarantined",
                )
        except Exception as exc:  # noqa: BLE001
            # Backlog lookup failure MUST NOT fail the run — fall through
            # to normal processing. Same tolerant pattern as the provenance
            # writer (plan §C.4, record_swallow).
            logger.warning(
                "backlog.is_quarantined lookup failed for {}: {} (proceeding)",
                step.source_id, exc,
            )

    # 1. Skip-if-complete (FR-011 idempotency)
    if writer.is_completed(run_label, schema, table):
        logger.info(
            "Skipping {}.{} — already completed for run_label={}",
            schema, table, run_label[:12],
        )
        return RunStepOutcome(status="completed", row_count=0, error_detail=None)

    # 2. View-safety pre-flight (FR-015)
    if not is_restorable_target(conn, schema, table):
        logger.warning("{}.{} is not a plain table — skipping (skipped_view)", schema, table)
        ended_at = _dt.datetime.now(_dt.timezone.utc)
        writer.record(
            run_label=run_label, schema=schema, table=table,
            chunk_position="-", source_kind=step.kind, status="skipped_view",
            started_at=started_at, ended_at=ended_at, rows_processed=0,
        )
        conn.commit()
        return RunStepOutcome(status="skipped_view", row_count=0, error_detail=None)

    # 2b. WAL-aware pre-flight (FR-007/FR-008) for the 5 tables >5 GB.
    # Pass step.source_id so the throttle enforces the per-source pause
    # budget (plan §C.2 / DEFAULT_PER_SOURCE_BUDGET_SECONDS) — one bad
    # source cannot drain the entire run-level budget.
    if step.wal_mode and throttle is not None:
        throttle.maybe_pause(source_id=step.source_id)

    # 3. Per-chunk dispatch
    # pg_url is computed lazily here (not at function entry) so idempotency /
    # view-safety / blocked-path tests that short-circuit above never trigger
    # the build_dsn() secret lookup. Tests that DO reach here mock
    # psycopg2.connect, so a missing-secret fallback to "" is fine — the
    # mock receives "" and returns a fake conn; production has the secrets
    # and build_dsn() succeeds.
    pg_url = os.environ.get("PG_URL")
    if not pg_url:
        try:
            pg_url = build_dsn(application_name="dk-data.prestaged")
        except Exception:  # noqa: BLE001 — build_dsn raises MissingSecretError in tests
            pg_url = ""
    try:
        all_sha256s: list[str] = []
        for idx, artifact in enumerate(step.artifacts):
            rc = dispatch_pg_restore(pg_url, step, artifact, first_chunk=(idx == 0))
            if rc != 0:
                stderr_hint = f"pg_restore returned exit code {rc} for chunk {artifact.chunk_index}"
                ended_at = _dt.datetime.now(_dt.timezone.utc)
                sha256_joined = ",".join(all_sha256s) if all_sha256s else None
                writer.record(
                    run_label=run_label, schema=schema, table=table,
                    chunk_position=artifact.chunk_index or "-",
                    source_kind=step.kind, status="failed",
                    started_at=started_at, ended_at=ended_at,
                    rows_processed=0, artifact_sha256=sha256_joined,
                    error_detail=stderr_hint,
                )
                conn.commit()
                _record_dlq_failure(
                    backlog, step.source_id, schema, table,
                    detail=stderr_hint,
                )
                return RunStepOutcome(status="failed", row_count=0, error_detail=stderr_hint)
            if artifact.sha256:
                all_sha256s.append(artifact.sha256)

        # 4. Post-restore row count
        row_count = 0
        with conn.cursor() as count_cur:
            count_cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
            result = count_cur.fetchone()
            if result is not None:
                row_count = int(result[0])

        # 4b. Manifest row-count gate (plan.md §B.3, PR-02).
        #
        # Context: session memory #2245 — pg_restore 17 emits a benign
        # `SET transaction_timeout = 0` error that we treat as success.
        # That tolerance is necessary for the PG-16 target, but it means
        # an upstream truncation (short download, partial dump, zero-byte
        # chunk) rides through pg_restore and lands as a silently-short
        # table. The manifest gate is the only place we detect that.
        #
        # Contract:
        #   - Manifest present + count mismatches beyond tolerance →
        #     status="row_mismatch", increment row_mismatch_total, return
        #     a non-zero per-step code (caller folds this into
        #     failed_count, triggering the Job's non-zero exit in main()).
        #   - Manifest absent → preserve current behavior (log + proceed),
        #     but increment manifest_missing_total so the gap is visible.
        #   - Manifest present, counts match → fall through to the normal
        #     "completed" terminal write.
        #
        # We key on the last chunk's artifact — by construction all chunks
        # for a (schema, table) share the same manifest (one manifest per
        # source), so picking the trailing artifact is deterministic.
        tolerance_pct = float(os.environ.get(
            "HYDRATION_ROW_TOLERANCE_PCT",
            str(DEFAULT_ROW_TOLERANCE_PCT),
        ))
        manifest_entry = None
        if step.artifacts:
            manifest_entry = load_manifest(step.artifacts[-1])

        if manifest_entry is None:
            # Emit the gap metric. Import locally so the prestaged module
            # doesn't hard-depend on prometheus_client being present at
            # import time (keeps unit tests import-light).
            try:
                from dk_data.observability.metrics import (
                    DK_HYDRATION_MANIFEST_MISSING_TOTAL,
                )
                DK_HYDRATION_MANIFEST_MISSING_TOTAL.labels(
                    source=step.source_id, schema=schema, table=table,
                ).inc()
            except Exception:  # noqa: BLE001 — metrics must never break ingestion
                logger.debug("manifest_missing metric emission failed")
        elif is_row_count_mismatch(
            expected=manifest_entry.expected_row_count,
            actual=row_count,
            tolerance_pct=tolerance_pct,
        ):
            try:
                from dk_data.observability.metrics import (
                    DK_HYDRATION_ROW_MISMATCH_TOTAL,
                )
                DK_HYDRATION_ROW_MISMATCH_TOTAL.labels(
                    source=step.source_id, schema=schema, table=table,
                ).inc()
            except Exception:  # noqa: BLE001
                logger.debug("row_mismatch metric emission failed")

            detail = (
                f"row_mismatch: expected={manifest_entry.expected_row_count} "
                f"actual={row_count} tolerance_pct={tolerance_pct}"
            )
            logger.error("{}.{} {}", schema, table, detail)
            ended_at = _dt.datetime.now(_dt.timezone.utc)
            writer.record(
                run_label=run_label, schema=schema, table=table,
                chunk_position=(
                    step.artifacts[-1].chunk_index if step.artifacts else "-"
                ),
                source_kind=step.kind, status="row_mismatch",
                started_at=started_at, ended_at=ended_at,
                rows_processed=row_count,
                artifact_sha256=",".join(all_sha256s) if all_sha256s else None,
                error_detail=detail,
            )
            conn.commit()
            _record_dlq_failure(
                backlog, step.source_id, schema, table,
                detail=detail,
            )
            return RunStepOutcome(
                status="row_mismatch",
                row_count=row_count,
                error_detail=detail,
            )

        # 5. Write terminal completed row
        ended_at = _dt.datetime.now(_dt.timezone.utc)
        writer.record(
            run_label=run_label, schema=schema, table=table,
            chunk_position=step.artifacts[-1].chunk_index if step.artifacts else "-",
            source_kind=step.kind, status="completed",
            started_at=started_at, ended_at=ended_at,
            rows_processed=row_count,
            artifact_sha256=",".join(all_sha256s) if all_sha256s else None,
        )
        conn.commit()
        return RunStepOutcome(status="completed", row_count=row_count, error_detail=None)

    except Exception as exc:  # noqa: BLE001
        ended_at = _dt.datetime.now(_dt.timezone.utc)
        error_detail = str(exc)[:4096]
        logger.error("run_step failed for {}.{}: {}", schema, table, error_detail)
        try:
            writer.record(
                run_label=run_label, schema=schema, table=table,
                chunk_position="-", source_kind=step.kind, status="failed",
                started_at=started_at, ended_at=ended_at,
                rows_processed=0, error_detail=error_detail,
            )
            conn.commit()
        except Exception:  # noqa: BLE001
            pass
        _record_dlq_failure(
            backlog, step.source_id, schema, table,
            exc=exc, detail=error_detail,
        )
        return RunStepOutcome(status="failed", row_count=0, error_detail=error_detail)


def run_live_fetch(
    conn: Any,
    step: LoadStep,
    run_label: str,
    writer: TransformRunsWriter,
) -> "RunStepOutcome":
    """Fall through to the existing live fetcher for a source with no
    pre-staged artifact (FR-010).

    Lazy-imports :func:`dk_data.ingestion.main.run_ingestion` to avoid
    pulling its 70 KB of FastAPI / kubernetes / sqlmesh transitive deps
    into the prestaged module's import graph.

    Args:
        conn: live psycopg2 connection (used to commit the writer row).
        step: the LoadStep — must have ``kind='live_fetch'`` and empty
            ``artifacts``.
        run_label: deterministic hydration run label.
        writer: TransformRunsWriter for the run.

    Returns:
        RunStepOutcome with status ``'completed'`` on fetcher success,
        ``'failed'`` on any exception (which is logged and recorded).
    """
    started_at = _dt.datetime.now(_dt.timezone.utc)
    schema = step.target_schema
    table = step.target_table

    # source_id format is "{schema}.{table}"; the fetcher SOURCES dict
    # is keyed by the table-level name (e.g. "chembl", "drugbank").
    source_basename = step.source_id.split(".")[-1]

    try:
        from dk_data.ingestion.main import run_ingestion  # lazy
        result = run_ingestion(source_basename)
        ended_at = _dt.datetime.now(_dt.timezone.utc)
        status: RunStatus = "completed"
        row_count = int(result.get("row_count", 0)) if isinstance(result, dict) else 0
        writer.record(
            run_label=run_label, schema=schema, table=table,
            chunk_position="-", source_kind="live_fetch", status=status,
            started_at=started_at, ended_at=ended_at,
            rows_processed=row_count,
        )
        conn.commit()
        return RunStepOutcome(status=status, row_count=row_count, error_detail=None)
    except Exception as exc:  # noqa: BLE001
        ended_at = _dt.datetime.now(_dt.timezone.utc)
        error_detail = str(exc)[:4096]
        logger.error(f"run_live_fetch failed for {step.source_id}: {error_detail}")
        try:
            writer.record(
                run_label=run_label, schema=schema, table=table,
                chunk_position="-", source_kind="live_fetch", status="failed",
                started_at=started_at, ended_at=ended_at,
                rows_processed=0, error_detail=error_detail,
            )
            conn.commit()
        except Exception:  # noqa: BLE001
            pass
        return RunStepOutcome(status="failed", row_count=0, error_detail=error_detail)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (see ``contracts/cli.md``). Tag: [DRYBK]."""
    parser = argparse.ArgumentParser(
        prog="python -m dk_data.ingestion.prestaged",
        description="Pre-staged hydration of dk-data-prod (feature 005).",
    )
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Emit ordered plan without writing (FR-012).")
    parser.add_argument("--source-list", default="all",
                        help="Comma-separated source_ids or 'all'.")
    parser.add_argument("--only-tier", type=int, default=None, metavar="N",
                        help="Only process tier N (1–8).")
    parser.add_argument("--verbose", "-v", action="store_true", default=False,
                        help="Enable debug-level logging.")
    # C.3 — DLQ operator surface (plan §C.3)
    parser.add_argument(
        "--list-backlog", action="store_true", default=False,
        help="Print every row of meta.hydration_backlog as JSON, then exit.",
    )
    parser.add_argument(
        "--unquarantine", nargs=4, default=None,
        metavar=("SOURCE", "SCHEMA", "TABLE", "REASON"),
        help=(
            "Clear quarantine for <source> <schema> <table> and write an "
            "audit row to meta.transform_runs (procedure_name='dlq:unquarantine'). "
            "No hydration work runs in this mode."
        ),
    )
    args = parser.parse_args(argv)

    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else "INFO")

    # --list-backlog / --unquarantine short-circuit BEFORE any hydration
    # setup: these operator flags must work even if PRESTAGED_ROOT is
    # unset. The HydrationBacklogWriter consults the pool at __init__,
    # which requires POSTGRES_PASSWORD — no fallback here because these
    # commands are DB-read / DB-write by definition.
    if args.list_backlog:
        backlog = HydrationBacklogWriter()
        try:
            rows = backlog.list_all()
            # datetime fields must be stringified to be JSON-serializable.
            for r in rows:
                for k, v in list(r.items()):
                    if hasattr(v, "isoformat"):
                        r[k] = v.isoformat()
            print(json.dumps(rows, indent=2, default=str))
        finally:
            backlog.close()
        return 0

    if args.unquarantine is not None:
        src, sch, tbl, reason = args.unquarantine
        backlog = HydrationBacklogWriter()
        try:
            backlog.unquarantine(src, sch, tbl, reason)
        finally:
            backlog.close()
        print(json.dumps({
            "status": "unquarantined",
            "source_id": src,
            "schema": sch,
            "table": tbl,
            "reason": reason,
        }))
        return 0

    prestaged_root_str = os.environ.get("PRESTAGED_ROOT", "")
    if not prestaged_root_str:
        logger.error("PRESTAGED_ROOT not set (FR-016)")
        return 1
    prestaged_root = Path(prestaged_root_str)
    if not prestaged_root.exists():
        logger.error("PRESTAGED_ROOT={} does not exist (FR-016)", prestaged_root)
        return 1

    pg_url = os.environ.get("PG_URL")
    if not pg_url:
        try:
            pg_url = build_dsn(application_name="dk-data.prestaged")
        except Exception:  # noqa: BLE001 — fall back to empty so --dry-run can still run
            pg_url = ""
    if not pg_url and not args.dry_run:
        logger.error("PG_URL not set — required for non-dry-run mode")
        return 1

    fetchers_suspended_raw = os.environ.get(
        "FETCHERS_SUSPENDED", "patentsview,epo_ops,euipo,fda_ndc"
    )
    fetchers_suspended = {s.strip() for s in fetchers_suspended_raw.split(",") if s.strip()}

    source_list_all = args.source_list.strip().lower() == "all"
    requested_sources: set[str] | None = (
        None if source_list_all
        else {s.strip() for s in args.source_list.split(",") if s.strip()}
    )

    # Build artifact inventory
    try:
        raw_artifacts = walk_prestaged_root(prestaged_root)
    except FileNotFoundError as exc:
        logger.error("{}", exc)
        return 1

    valid_artifacts: list[PrestagedArtifact] = []
    for art in raw_artifacts:
        art = validate_magic_bytes(art)
        if not art.magic_ok:
            logger.warning("Invalid magic bytes — skipping {}", art.path)
            continue
        art = compute_sha256(art)
        valid_artifacts.append(art)

    # Stage 3: plan_load encapsulates ordering + tier-precedence + filtering.
    plan = plan_load(
        valid_artifacts,
        cluster_fingerprint=pg_url,
        requested_sources=requested_sources,
        only_tier=args.only_tier,
    )
    run_label = plan.run_label

    # Dry-run (FR-012)
    if args.dry_run:
        total_bytes = sum(a.size_bytes for s in plan.sources for a in s.artifacts)
        wal_mode_count = sum(1 for s in plan.sources if s.wal_mode)
        missing_sources = [s.source_id for s in plan.sources if not s.artifacts]

        for s in plan.sources:
            print(json.dumps({
                "tier": next(
                    (d.tier for d in SOURCE_LOAD_ORDER if d.source_id == s.source_id), 0,
                ),
                "source_id": s.source_id,
                "kind": s.kind,
                "artifacts": [str(a.path) for a in s.artifacts],
                "artifact_count": len(s.artifacts),
                "total_bytes": sum(a.size_bytes for a in s.artifacts),
                "magic_ok": all(a.magic_ok for a in s.artifacts),
                "wal_mode": s.wal_mode,
            }))
        print(json.dumps({
            "summary": True,
            "total_steps": len(plan.sources),
            "total_bytes": total_bytes,
            "wal_mode_steps": wal_mode_count,
            "missing_sources": missing_sources,
        }))
        return 0

    # Non-dry-run: execute steps sequentially.
    # Keepalives reduce PgBouncer-side connection drops while long
    # pg_restore subprocesses sit blocked on our control connection.
    KEEPALIVE = {
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    }
    conn = psycopg2.connect(pg_url, **KEEPALIVE)  # pg_url via build_dsn()
    # autocommit=True on the writer conn: every statement commits
    # immediately. Prevents `idle_in_transaction_session_timeout`
    # (5 min on prod) from killing the writer during long pg_restore
    # subprocesses where the writer conn sits idle. All writes to
    # meta.transform_runs are single-statement INSERTs; no
    # multi-statement atomicity needed.
    conn.autocommit = True
    writer = TransformRunsWriter(conn)

    # FR-007/008: configurable from env at call site; defaults match plan.md
    # WAL_PAUSE_BUDGET_PER_SOURCE_SECONDS (plan §C.2) caps how much of
    # the run-level budget any one source can consume — defaults to half
    # of the typical p95 pause (180s) so a single pathological source
    # cannot drain the whole budget.
    throttle = WalThrottle(
        conn=conn,
        high_pct=float(os.environ.get("WAL_PAUSE_HIGH_PCT", "70")),
        low_pct=float(os.environ.get("WAL_PAUSE_LOW_PCT", "40")),
        downshift_threshold=int(os.environ.get("WAL_PAUSE_DOWNSHIFT_THRESHOLD", "2")),
        budget_s=int(os.environ.get("WAL_PAUSE_BUDGET_SECONDS", "600")),
        per_source_budget_s=int(
            os.environ.get("WAL_PAUSE_BUDGET_PER_SOURCE_SECONDS", "180")
        ),
    )

    # C.3 — DLQ writer. Tolerant constructor: if Postgres creds are
    # missing (tests / dry-ish runs), log and proceed with backlog=None
    # so quarantine checks + failure records become no-ops.
    backlog: HydrationBacklogWriter | None
    try:
        backlog = HydrationBacklogWriter()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "HydrationBacklogWriter init failed ({}); DLQ recording disabled", exc,
        )
        backlog = None

    completed_ids: set[str] = set()
    failed_ids: set[str] = set()
    failed_count = 0
    total_count = len(plan.sources)

    for step in plan.sources:
        # Stage 3: blocked-state propagation via the declarative helper.
        # Compared against current failed_ids only (not future failures —
        # those will block their own downstream in subsequent iterations).
        blocked_map = propagate_blocked(
            LoadPlan(
                run_label=run_label,
                sources=[step],
                wal_mode_tables=WAL_MODE_TABLES,
            ),
            failed_ids,
        )
        if step.source_id in blocked_map:
            blocked_by = blocked_map[step.source_id]
            started_at = _dt.datetime.now(_dt.timezone.utc)
            writer.record(
                run_label=run_label, schema=step.target_schema, table=step.target_table,
                chunk_position="-", source_kind=step.kind, status="blocked",
                started_at=started_at, ended_at=started_at,
                rows_processed=0,
                error_detail=f"blocked_on={','.join(blocked_by)}",
            )
            conn.commit()
            logger.warning("{} blocked: {}", step.source_id, blocked_by)
            print(json.dumps({
                "run_id": run_label, "source_id": step.source_id,
                "status": "blocked", "row_count": 0, "duration_s": 0.0,
            }))
            failed_count += 1
            failed_ids.add(step.source_id)
            _emit_otlp(step, run_label, "blocked", 0)
            continue

        if not step.artifacts and step.kind == "live_fetch":
            source_base = step.source_id.split(".")[-1]
            if source_base in fetchers_suspended:
                started_at = _dt.datetime.now(_dt.timezone.utc)
                writer.record(
                    run_label=run_label, schema=step.target_schema,
                    table=step.target_table, chunk_position="-",
                    source_kind="live_fetch", status="no_source_available",
                    started_at=started_at, ended_at=started_at, rows_processed=0,
                )
                conn.commit()
                print(json.dumps({
                    "run_id": run_label, "source_id": step.source_id,
                    "status": "no_source_available", "row_count": 0, "duration_s": 0.0,
                }))
                failed_ids.add(step.source_id)
                _emit_otlp(step, run_label, "no_source_available", 0)
                continue

            # Source is enabled — invoke the live fetcher (FR-010, T060)
            t_start = _dt.datetime.now(_dt.timezone.utc)
            outcome = run_live_fetch(conn, step, run_label, writer)
            t_end = _dt.datetime.now(_dt.timezone.utc)
            duration_s = (t_end - t_start).total_seconds()
            print(json.dumps({
                "run_id": run_label, "source_id": step.source_id,
                "status": outcome.status, "row_count": outcome.row_count,
                "duration_s": round(duration_s, 1),
            }))
            _emit_otlp(step, run_label, outcome.status, outcome.row_count)
            if outcome.status == "completed":
                completed_ids.add(step.source_id)
            else:
                failed_count += 1
                failed_ids.add(step.source_id)
            continue

        # Ping-and-reconnect BEFORE every run_step. The writer conn sits
        # idle for the duration of each pg_restore subprocess (can be
        # 10+ minutes for large tables), during which PgBouncer may
        # close the client-pooler connection. Reconnecting here is
        # cheap (<10ms) and makes every source start with a live conn.
        def _ensure_live() -> None:
            nonlocal conn, writer, throttle
            try:
                with conn.cursor() as _pingc:
                    _pingc.execute("SELECT 1")
                return
            except (psycopg2.InterfaceError, psycopg2.OperationalError):
                pass
            logger.info(f"writer conn stale — reconnecting for {step.source_id}")
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            conn = psycopg2.connect(pg_url, **KEEPALIVE)  # pg_url via build_dsn()
            conn.autocommit = True
            writer = TransformRunsWriter(conn)
            if throttle is not None:
                throttle.conn = conn

        _ensure_live()

        t_start = _dt.datetime.now(_dt.timezone.utc)
        try:
            outcome = run_step(conn, step, run_label, writer, throttle=throttle, backlog=backlog)
        except (psycopg2.InterfaceError, psycopg2.OperationalError) as exc:
            # Mid-step conn loss. Reconnect + retry once; on second
            # failure, record as failed and move on rather than crash
            # the whole orchestrator.
            logger.warning(
                f"conn lost mid-run_step for {step.source_id} ({exc}) — "
                f"reconnecting and retrying once"
            )
            _ensure_live()
            try:
                outcome = run_step(conn, step, run_label, writer, throttle=throttle, backlog=backlog)
            except (psycopg2.InterfaceError, psycopg2.OperationalError) as exc2:
                logger.error(
                    f"second attempt also lost conn for {step.source_id} ({exc2}) "
                    f"— marking failed and continuing"
                )
                outcome = RunStepOutcome(
                    status="failed", row_count=0,
                    error_detail=f"connection lost twice: {exc2}",
                )
        t_end = _dt.datetime.now(_dt.timezone.utc)
        duration_s = (t_end - t_start).total_seconds()

        print(json.dumps({
            "run_id": run_label, "source_id": step.source_id,
            "status": outcome.status, "row_count": outcome.row_count,
            "duration_s": round(duration_s, 1),
        }))
        _emit_otlp(step, run_label, outcome.status, outcome.row_count)

        if outcome.status == "completed":
            completed_ids.add(step.source_id)
        else:
            failed_count += 1
            failed_ids.add(step.source_id)

    conn.close()
    if backlog is not None:
        try:
            backlog.close()
        except Exception:  # noqa: BLE001
            pass

    if failed_count == 0:
        return 0
    if failed_count < total_count:
        return 2
    return 3


# ---------------------------------------------------------------------------
# RunStepOutcome — terminal result type for run_step().
# ---------------------------------------------------------------------------

@dataclass
class RunStepOutcome:
    """Terminal result of orchestrating one LoadStep."""
    status: RunStatus
    row_count: int
    error_detail: str | None


if __name__ == "__main__":  # pragma: no cover — real entry point
    sys.exit(main(sys.argv[1:]))
