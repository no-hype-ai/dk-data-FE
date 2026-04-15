"""Tests for src/dk_data/ingestion/load_order.py.

Stage 3 (T042-T044) of the 005-prestaged-hydration feature. Pure tests —
no DB, no filesystem reads beyond what Pydantic does internally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dk_data.ingestion.load_order import (
    OUT_OF_SCOPE_SCHEMA_PREFIXES,
    SOURCE_LOAD_ORDER,
    SourceDescriptor,
    plan_load,
    propagate_blocked,
)
from dk_data.ingestion.prestaged_types import LoadPlan, PrestagedArtifact


def _make_artifact(
    schema: str,
    table: str,
    *,
    tier: str = "raw",
    chunk_index: str = "",
    sha256: str = "0" * 64,
) -> PrestagedArtifact:
    """Construct a minimally-valid PrestagedArtifact for tests."""
    return PrestagedArtifact(
        path=Path(f"/tmp/{schema}__{table}{chunk_index}.dump"),
        target_schema=schema,
        target_table=table,
        tier=tier,  # type: ignore[arg-type]
        chunk_index=chunk_index,
        size_bytes=42,
        sha256=sha256,
        magic_ok=True,
    )


# ---------------------------------------------------------------------------
# T042: full inventory produces 8 tiers in declared order
# ---------------------------------------------------------------------------


def test_plan_load_preserves_declared_order_and_all_tiers() -> None:
    """When every descriptor receives an artifact, plan_load emits one
    step per (in-scope) descriptor in the same order as
    SOURCE_LOAD_ORDER, and every tier 1..8 is represented (modulo the
    out-of-scope filter for tier 8 ind_/ip_)."""
    artifacts = [
        _make_artifact(d.schema, d.table, tier=_tier_for_schema(d.schema))
        for d in SOURCE_LOAD_ORDER
        if not _is_out_of_scope(d.schema)
    ]

    plan = plan_load(artifacts, cluster_fingerprint="testhost:5432/dkdata")

    # Same length and same order as the in-scope subset of the descriptor list
    in_scope_ids = [
        d.source_id for d in SOURCE_LOAD_ORDER if not _is_out_of_scope(d.schema)
    ]
    plan_ids = [s.source_id for s in plan.sources]
    assert plan_ids == in_scope_ids, (
        "plan_load must preserve the declared SOURCE_LOAD_ORDER for in-scope "
        "descriptors"
    )

    # Out-of-scope must not appear at all
    for s in plan.sources:
        assert not _is_out_of_scope(s.target_schema), (
            f"out-of-scope source leaked into plan: {s.source_id}"
        )

    # Tiers 1-7 must all be represented (tier 8 is gold via SQLMesh; the
    # only tier-8 descriptors are ind_gold + ip_gold + mol_gold_ext.* —
    # the first two are filtered, mol_gold_ext.* are kept)
    tiers_present = {d.tier for d in SOURCE_LOAD_ORDER if d.source_id in plan_ids}
    assert tiers_present >= {1, 2, 3, 4, 5, 6, 7}, (
        f"missing tiers in plan: {sorted({1,2,3,4,5,6,7,8} - tiers_present)}"
    )

    # Run label is deterministic
    plan2 = plan_load(artifacts, cluster_fingerprint="testhost:5432/dkdata")
    assert plan.run_label == plan2.run_label


def test_plan_load_marks_missing_artifacts_as_live_fetch() -> None:
    """When a descriptor has no artifact, the step is still emitted with
    ``kind='live_fetch'`` so the orchestrator can fall through to the
    fetcher path (FR-010)."""
    artifacts: list[PrestagedArtifact] = []  # nothing discovered
    plan = plan_load(artifacts, cluster_fingerprint="testhost:5432/dkdata")

    in_scope = [d for d in SOURCE_LOAD_ORDER if not _is_out_of_scope(d.schema)]
    assert len(plan.sources) == len(in_scope)
    assert all(s.kind == "live_fetch" for s in plan.sources)
    assert all(s.artifacts == [] for s in plan.sources)


# ---------------------------------------------------------------------------
# T043: missing hub blocks dependent spokes
# ---------------------------------------------------------------------------


def test_propagate_blocked_transitively_marks_descendants() -> None:
    """If `mol_raw.chembl` fails, `mol_bronze.chembl_activities`
    (which depends on it) must be blocked, and any future descendants
    of that bronze step must also be blocked transitively."""
    descriptors = [
        SourceDescriptor("mol_raw.chembl", "mol_raw", "chembl", 2),
        SourceDescriptor(
            "mol_bronze.chembl_activities",
            "mol_bronze",
            "chembl_activities",
            3,
            depends_on=["mol_raw.chembl"],
        ),
        SourceDescriptor(
            "mol_silver.molecules",
            "mol_silver",
            "molecules",
            4,
            depends_on=["mol_bronze.chembl_activities"],
        ),
        SourceDescriptor(
            "mol_raw.unrelated", "mol_raw", "unrelated", 2,
        ),  # not in any failure chain
    ]
    plan = plan_load(
        artifacts=[],
        cluster_fingerprint="t:1/d",
        descriptors=descriptors,
    )

    blocked = propagate_blocked(plan, failed_source_ids={"mol_raw.chembl"})

    assert "mol_bronze.chembl_activities" in blocked
    assert blocked["mol_bronze.chembl_activities"] == ["mol_raw.chembl"]
    assert "mol_silver.molecules" in blocked, (
        "transitive descendant must also be blocked"
    )
    assert blocked["mol_silver.molecules"] == ["mol_bronze.chembl_activities"]
    assert "mol_raw.unrelated" not in blocked
    # The original failed source is not itself in the blocked dict — it
    # already has its own terminal state (failed, not blocked).
    assert "mol_raw.chembl" not in blocked


def test_propagate_blocked_empty_when_no_failures() -> None:
    """No failures → empty blocked dict."""
    blocked = propagate_blocked(
        plan_load([], cluster_fingerprint="t:1/d"),
        failed_source_ids=set(),
    )
    assert blocked == {}


# ---------------------------------------------------------------------------
# T044: silver dump suppresses lower-tier dumps for the same (schema, table)
# ---------------------------------------------------------------------------


def test_silver_dump_suppresses_lower_tiers_for_same_table() -> None:
    """When a (schema, table) pair has artifacts at multiple tiers,
    plan_load picks the highest tier and discards the rest (FR-003)."""
    descriptors = [
        SourceDescriptor("mol_silver.molecules", "mol_silver", "molecules", 4),
    ]

    raw_a = _make_artifact("mol_silver", "molecules", tier="raw", sha256="r" * 64)
    bronze_a = _make_artifact("mol_silver", "molecules", tier="bronze", sha256="b" * 64)
    silver_a = _make_artifact("mol_silver", "molecules", tier="silver", sha256="s" * 64)

    plan = plan_load(
        [raw_a, bronze_a, silver_a],
        cluster_fingerprint="t:1/d",
        descriptors=descriptors,
    )

    assert len(plan.sources) == 1
    step = plan.sources[0]
    assert step.tier == "silver"
    assert len(step.artifacts) == 1
    assert step.artifacts[0].sha256 == "s" * 64, (
        "silver artifact must win over bronze and raw"
    )


def test_bronze_wins_when_no_silver_for_same_table() -> None:
    """With no silver dump, bronze beats raw."""
    descriptors = [
        SourceDescriptor("mol_raw.pubchem", "mol_raw", "pubchem", 2),
        SourceDescriptor(
            "mol_bronze.pubchem", "mol_bronze", "pubchem", 3,
            depends_on=["mol_raw.pubchem"],
        ),
    ]
    # Single (schema, table) intentionally — both go to mol_bronze.pubchem
    raw_a = _make_artifact("mol_bronze", "pubchem", tier="raw", sha256="r" * 64)
    bronze_a = _make_artifact("mol_bronze", "pubchem", tier="bronze", sha256="b" * 64)

    plan = plan_load(
        [raw_a, bronze_a],
        cluster_fingerprint="t:1/d",
        descriptors=descriptors,
    )

    bronze_step = next(s for s in plan.sources if s.target_schema == "mol_bronze")
    assert bronze_step.tier == "bronze"
    assert bronze_step.artifacts[0].sha256 == "b" * 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tier_for_schema(schema: str) -> str:
    if schema.endswith("_raw"):
        return "raw"
    if schema.endswith("_bronze"):
        return "bronze"
    if schema.endswith("_silver"):
        return "silver"
    # Catch-all for meta + sqlmesh + gold; treat as raw for fixture purposes.
    return "raw"


def _is_out_of_scope(schema: str) -> bool:
    return any(schema.startswith(p) for p in OUT_OF_SCOPE_SCHEMA_PREFIXES)
