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

import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from dk_data.ingestion.prestaged_types import (
    PGDMP_MAGIC,
    LoadPlan,
    LoadStep,
    PrestagedArtifact,
    SourceKind,
    Tier,
)

# Module-level inode → sha256 cache; avoids re-reading the same file twice
# within a single process (FR-002 performance note).
_SHA_CACHE: dict[int, str] = {}

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

    Args:
        pg_url: destination connection string.
        step: the LoadStep this chunk belongs to.
        artifact: the specific chunk to restore.
        first_chunk: True only for the lexically-first chunk of a table;
            controls ``--clean --if-exists`` (applied on first only).

    Returns:
        pg_restore subprocess exit code. 0 == success.
    """
    raise NotImplementedError("Stage 2 worker: dispatch-cli")


def run_step(pg_url: str, step: LoadStep, run_label: str) -> RunStepOutcome:  # type: ignore[name-defined]
    """Orchestrate one step end-to-end: view-safety pre-flight → per-chunk
    dispatch → row-count → ``meta.transform_runs`` upsert.

    The single public orchestration unit for a LoadStep. Returns an
    outcome object with the terminal status and row count.
    """
    raise NotImplementedError("Stage 2 worker: dispatch-cli")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (see ``contracts/cli.md``).

    Flags: ``--dry-run``, ``--source-list``, ``--only-tier``, ``--verbose``.
    Returns process exit code.
    """
    raise NotImplementedError("Stage 2 worker: dispatch-cli")


# ---------------------------------------------------------------------------
# Forward-declared return type — filled by Stage 2 worker dispatch-cli.
# Kept here so skeleton imports resolve cleanly.
# ---------------------------------------------------------------------------

class RunStepOutcome:
    """Placeholder. dispatch-cli worker replaces this with a real
    dataclass carrying ``status``, ``row_count``, ``error_detail``."""


if __name__ == "__main__":  # pragma: no cover — real entry point
    sys.exit(main(sys.argv[1:]))
