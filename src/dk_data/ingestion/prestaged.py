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

import sys
from pathlib import Path
from typing import Iterable

from dk_data.ingestion.prestaged_types import (
    LoadPlan,
    LoadStep,
    PrestagedArtifact,
    SourceKind,
    Tier,
)


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
    raise NotImplementedError("Stage 2 worker: discovery-validate")


def validate_magic_bytes(artifact: PrestagedArtifact) -> PrestagedArtifact:
    """Check first 5 bytes == ``b"PGDMP"`` (FR-002).

    Returns a new artifact with ``magic_ok`` set.
    """
    raise NotImplementedError("Stage 2 worker: discovery-validate")


def compute_sha256(artifact: PrestagedArtifact) -> PrestagedArtifact:
    """Compute and attach sha256. Caches by inode to avoid re-reading (FR-002)."""
    raise NotImplementedError("Stage 2 worker: discovery-validate")


def group_by_table(
    artifacts: Iterable[PrestagedArtifact],
) -> dict[tuple[str, str], list[PrestagedArtifact]]:
    """Group artifacts by ``(target_schema, target_table)`` with lexical
    chunk ordering (FR-004)."""
    raise NotImplementedError("Stage 2 worker: discovery-validate")


def select_highest_tier(
    group: list[PrestagedArtifact],
) -> tuple[Tier, list[PrestagedArtifact]]:
    """Apply precedence silver > bronze > raw (FR-003).

    Returns ``(tier, artifacts_at_that_tier)``. Lower-tier artifacts in
    the input are discarded for this run.
    """
    raise NotImplementedError("Stage 2 worker: discovery-validate")


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
