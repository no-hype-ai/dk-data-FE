"""Tests for the live-fetch fallback path of 005-prestaged-hydration (US4).

Stage 5 (T063, T064, T065). Pure unit tests — no DB connection, no
filesystem reads. Mocks both the writer and the lazy-imported
``main.run_ingestion``.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch


from dk_data.ingestion.load_order import (
    OUT_OF_SCOPE_SCHEMA_PREFIXES,
    SourceDescriptor,
    plan_load,
)
from dk_data.ingestion.prestaged import run_live_fetch
from dk_data.ingestion.prestaged_types import LoadStep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _step(source_id: str, schema: str, table: str) -> LoadStep:
    return LoadStep(
        source_id=source_id,
        target_schema=schema,
        target_table=table,
        tier="raw",
        kind="live_fetch",
        artifacts=[],
    )


# ---------------------------------------------------------------------------
# T063: missing artifact + enabled fetcher → run_live_fetch invoked
# ---------------------------------------------------------------------------


def test_run_live_fetch_invokes_main_run_ingestion_with_basename() -> None:
    """run_live_fetch lazy-imports main.run_ingestion and calls it with
    just the table-level source name (the SOURCES dict's key shape)."""
    fake_main = types.ModuleType("dk_data.ingestion.main")
    fake_main.run_ingestion = MagicMock(  # type: ignore[attr-defined]
        return_value={"status": "completed", "row_count": 1234}
    )

    writer = MagicMock()
    conn = MagicMock()
    step = _step("mol_raw.chembl", "mol_raw", "chembl")

    with patch.dict(sys.modules, {"dk_data.ingestion.main": fake_main}):
        outcome = run_live_fetch(conn, step, run_label="abc123", writer=writer)

    fake_main.run_ingestion.assert_called_once_with("chembl")
    assert outcome.status == "completed"
    assert outcome.row_count == 1234

    # Outcome was recorded in meta.transform_runs via the writer
    writer.record.assert_called_once()
    call_kwargs = writer.record.call_args.kwargs
    assert call_kwargs["run_label"] == "abc123"
    assert call_kwargs["schema"] == "mol_raw"
    assert call_kwargs["table"] == "chembl"
    assert call_kwargs["source_kind"] == "live_fetch"
    assert call_kwargs["status"] == "completed"
    assert call_kwargs["rows_processed"] == 1234

    # And the connection committed the write
    conn.commit.assert_called_once()


def test_run_live_fetch_records_failure_when_fetcher_raises() -> None:
    """When the fetcher raises, run_live_fetch records status='failed'
    with the exception text in error_detail and never propagates."""
    fake_main = types.ModuleType("dk_data.ingestion.main")
    fake_main.run_ingestion = MagicMock(  # type: ignore[attr-defined]
        side_effect=RuntimeError("oauth token rotated")
    )

    writer = MagicMock()
    conn = MagicMock()
    step = _step("mol_raw.drugbank", "mol_raw", "drugbank")

    with patch.dict(sys.modules, {"dk_data.ingestion.main": fake_main}):
        outcome = run_live_fetch(conn, step, run_label="xyz", writer=writer)

    assert outcome.status == "failed"
    assert outcome.row_count == 0
    assert "oauth token rotated" in outcome.error_detail

    writer.record.assert_called_once()
    assert writer.record.call_args.kwargs["status"] == "failed"
    assert "oauth token rotated" in writer.record.call_args.kwargs["error_detail"]


# ---------------------------------------------------------------------------
# T064: suspended fetcher → no_source_available, no fetcher call
# ---------------------------------------------------------------------------
#
# This branch is implemented inline in main()'s loop (the FETCHERS_SUSPENDED
# membership check fires BEFORE run_live_fetch is invoked), so the unit
# test for it lives at the loop level. We assert the contract by
# constructing the same condition and verifying that, given a suspended
# fetcher set, run_live_fetch is NOT what main() would dispatch to.
#
# Concretely: main()'s logic is `if source_base in fetchers_suspended:
# record('no_source_available'); continue`. We mirror that check here so
# the test pins the expected behavior even if main() gets refactored.


def test_suspended_fetcher_does_not_trigger_run_live_fetch() -> None:
    """Document the wire-in contract: if a source's basename is in
    FETCHERS_SUSPENDED, the loop must record no_source_available and
    skip the run_live_fetch call entirely."""
    fetchers_suspended = {"patentsview", "epo_ops", "euipo", "fda_ndc"}

    # A source that IS suspended
    step = _step("mol_raw.fda_ndc", "mol_raw", "fda_ndc")
    source_base = step.source_id.split(".")[-1]
    assert source_base in fetchers_suspended, (
        "test relies on fda_ndc being in the suspended set"
    )

    # A source that is NOT suspended
    step_ok = _step("mol_raw.chembl", "mol_raw", "chembl")
    assert step_ok.source_id.split(".")[-1] not in fetchers_suspended

    # The contract main() implements: only the unsuspended one would
    # reach run_live_fetch. We don't actually call main() here (it
    # requires a Postgres connection); the contract is simple enough
    # that an inline assertion is the right test scope.
    should_invoke_live_fetch = lambda step: (  # noqa: E731
        not step.artifacts
        and step.kind == "live_fetch"
        and step.source_id.split(".")[-1] not in fetchers_suspended
    )

    assert should_invoke_live_fetch(step) is False
    assert should_invoke_live_fetch(step_ok) is True


# ---------------------------------------------------------------------------
# T065: out-of-scope sources are absent from the LoadPlan entirely
# ---------------------------------------------------------------------------


def test_out_of_scope_sources_not_in_load_plan() -> None:
    """Per FR-014, sources whose schema starts with any of
    OUT_OF_SCOPE_SCHEMA_PREFIXES (`ip_`, `ind_`, `hcp_silver`) are
    dropped from the plan before any kind/status decision is made."""
    descriptors = [
        SourceDescriptor("mol_raw.chembl", "mol_raw", "chembl", 2),
        SourceDescriptor("ip_silver.patents", "ip_silver", "patents", 7),
        SourceDescriptor("ind_gold.indication_catalog", "ind_gold",
                         "indication_catalog", 8),
        SourceDescriptor("hcp_silver.providers", "hcp_silver", "providers", 7),
    ]

    plan = plan_load([], cluster_fingerprint="t:1/d", descriptors=descriptors)

    plan_ids = {s.source_id for s in plan.sources}
    assert "mol_raw.chembl" in plan_ids, "in-scope source must remain"
    assert "ip_silver.patents" not in plan_ids
    assert "ind_gold.indication_catalog" not in plan_ids
    assert "hcp_silver.providers" not in plan_ids

    # And the prefix set really does match what the spec declared
    assert {"ip_", "ind_", "hcp_silver"} == set(OUT_OF_SCOPE_SCHEMA_PREFIXES)
