"""Types for the 005-prestaged-hydration feature.

Pydantic models for PrestagedArtifact / LoadStep / LoadPlan and the
deterministic run_id helper from research.md R4.

Every public type is strict — `extra="forbid"` and no Any. [TYPED]
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["raw", "bronze", "silver"]
SourceKind = Literal["pg_dump", "bronze_ready", "raw_csv", "live_fetch"]
RunStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "blocked",
    "skipped_view",
    "no_source_available",
]

PGDMP_MAGIC = b"PGDMP"


class PrestagedArtifact(BaseModel):
    """One `.dump` file on disk, post-discovery + validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: Path
    target_schema: str
    target_table: str
    tier: Tier
    chunk_index: str = Field(
        default="",
        description=(
            "File prefix: '1', '3', 'retry', or '' for single-file. "
            "Lexical order determines dispatch order within a table."
        ),
    )
    size_bytes: int = Field(ge=0)
    sha256: str | None = None
    magic_ok: bool = False


class LoadStep(BaseModel):
    """One unit of work in a LoadPlan — restore all chunks for one table,
    or fall through to live-fetch, or skip entirely."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_schema: str
    target_table: str
    tier: Tier
    kind: SourceKind
    artifacts: list[PrestagedArtifact] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    wal_mode: bool = False


class LoadPlan(BaseModel):
    """The full ordered execution plan for one hydration run."""

    model_config = ConfigDict(extra="forbid")

    run_label: str = Field(
        description=(
            "Deterministic sha256 hex digest — same inventory + same cluster "
            "produces the same run_label across invocations (FR-011)."
        )
    )
    sources: list[LoadStep]
    wal_mode_tables: frozenset[tuple[str, str]] = Field(default_factory=frozenset)


def compute_run_id(
    artifact_sha256s: list[str],
    cluster_fingerprint: str,
) -> str:
    """Deterministic identifier per research.md R4.

    Args:
        artifact_sha256s: every artifact's sha256 (any order — sorted internally).
        cluster_fingerprint: stable identifier for the target cluster,
            e.g. ``f"{pg_host}:{pg_port}/{pg_database}"``.

    Returns:
        Lowercase 64-character hex digest.

    Guarantee: same inputs ⇒ same output, regardless of order of
    ``artifact_sha256s``. This is what lets FR-011 work: a re-run with
    the same inventory against the same cluster computes the same
    ``run_label`` and skips every row already marked ``completed`` in
    ``meta.transform_runs``.
    """
    joined = "\n".join(sorted(artifact_sha256s)) + "\n" + cluster_fingerprint
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
