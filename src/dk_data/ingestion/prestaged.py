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
    OUT_OF_SCOPE_SCHEMA_PREFIXES,
    SOURCE_LOAD_ORDER,
    WAL_MODE_TABLES,
    plan_load,
    propagate_blocked,
)
from dk_data.ingestion.prestaged_safety import is_restorable_target
from dk_data.ingestion.prestaged_types import (
    PGDMP_MAGIC,
    LoadPlan,
    LoadStep,
    PrestagedArtifact,
    RunStatus,
    SourceKind,
    Tier,
    compute_run_id,
)
from dk_data.ingestion.transform_runs_writer import TransformRunsWriter
from dk_data.ingestion.wal_throttle import WalThrottle

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
        raise ValueError(f"Cannot derive tier from schema name: {schema!r}")

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

    cmd = [
        "pg_restore",
        "-Fc",
        "--no-owner",
        "--no-privileges",
        "--single-transaction",
        "--section=data",
        f"--dbname={pg_url}",
    ]
    if first_chunk:
        cmd += ["--clean", "--if-exists"]
    cmd.append(str(artifact.path))

    logger.info("pg_restore command: {}", " ".join(cmd))

    lock_conn = psycopg2.connect(pg_url)
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
        return result.returncode
    finally:
        with lock_conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_unlock(hashtext(%s))", (lock_key_expr,)
            )
        lock_conn.close()


def run_step(
    conn: Any,
    step: LoadStep,
    run_label: str,
    writer: TransformRunsWriter,
    throttle: WalThrottle | None = None,
) -> "RunStepOutcome":
    """Orchestrate one step end-to-end: view-safety pre-flight → per-chunk
    dispatch → row-count → ``meta.transform_runs`` upsert.

    When ``step.wal_mode`` is True and a ``throttle`` is supplied, calls
    :meth:`WalThrottle.maybe_pause` after the view-safety check and before
    the first ``pg_restore`` invocation (FR-007).

    Tags: [AUDIT] [IDMPT] [VIEWSAFE] [WALBUD]
    """
    pg_url = os.environ.get("PG_URL", "")
    schema = step.target_schema
    table = step.target_table
    started_at = _dt.datetime.now(_dt.timezone.utc)

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

    # 2b. WAL-aware pre-flight (FR-007/FR-008) for the 5 tables >5 GB
    if step.wal_mode and throttle is not None:
        throttle.maybe_pause()

    # 3. Per-chunk dispatch
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
    args = parser.parse_args(argv)

    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else "INFO")

    prestaged_root_str = os.environ.get("PRESTAGED_ROOT", "")
    if not prestaged_root_str:
        logger.error("PRESTAGED_ROOT not set (FR-016)")
        return 1
    prestaged_root = Path(prestaged_root_str)
    if not prestaged_root.exists():
        logger.error("PRESTAGED_ROOT={} does not exist (FR-016)", prestaged_root)
        return 1

    pg_url = os.environ.get("PG_URL", "")
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

    # Non-dry-run: execute steps sequentially
    conn = psycopg2.connect(pg_url)
    conn.autocommit = False
    writer = TransformRunsWriter(conn)

    # FR-007/008: configurable from env at call site; defaults match plan.md
    throttle = WalThrottle(
        conn=conn,
        high_pct=float(os.environ.get("WAL_PAUSE_HIGH_PCT", "70")),
        low_pct=float(os.environ.get("WAL_PAUSE_LOW_PCT", "40")),
        downshift_threshold=int(os.environ.get("WAL_PAUSE_DOWNSHIFT_THRESHOLD", "2")),
        budget_s=int(os.environ.get("WAL_PAUSE_BUDGET_SECONDS", "600")),
    )

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

        t_start = _dt.datetime.now(_dt.timezone.utc)
        outcome = run_step(conn, step, run_label, writer, throttle=throttle)
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
