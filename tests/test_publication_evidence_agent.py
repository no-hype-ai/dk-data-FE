"""Tests for PublicationEvidenceExtractorAgent.

Feature: 019-cms-puf-platform-reconciliation
Task: T042

Tests use mocked LiteLLM proxy and mocked asyncpg pool — no real DB or LLM calls.
Verifies:
- Endpoint extraction writes to mol_agents.publication_evidence_staging (not live table)
- Duplicate content_hash in staging is skipped (ON CONFLICT DO NOTHING)
- Confidence < 0.5 goes to quarantine, not staging
- Confidence 0.5–0.79 sets needs_review = True in staging
- All LLM calls go through the configured LITELLM_PROXY_URL (openai SDK base_url)
- SQLMesh model promotes from staging; agent does NOT write to live table
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_agent(monkeypatch=None):
    """Build an agent with mocked env vars and patched asyncpg pool."""
    os.environ.setdefault("LITELLM_PROXY_URL", "http://litellm.infra.svc.cluster.local:4000")
    os.environ.setdefault("LITELLM_API_KEY", "test-key")
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

    from dk_data.agents.publication_evidence_extractor import PublicationEvidenceExtractorAgent
    return PublicationEvidenceExtractorAgent()


def _llm_response(
    endpoint_name="Overall Survival",
    endpoint_type="primary",
    hazard_ratio=0.72,
    p_value=0.001,
    response_rate=None,
    median_survival_months=24.5,
    sample_size=400,
    trial_nct_id="NCT12345678",
    confidence_score=0.90,
):
    return json.dumps({
        "endpoint_name": endpoint_name,
        "endpoint_type": endpoint_type,
        "hazard_ratio": hazard_ratio,
        "p_value": p_value,
        "response_rate": response_rate,
        "median_survival_months": median_survival_months,
        "sample_size": sample_size,
        "trial_nct_id": trial_nct_id,
        "confidence_score": confidence_score,
    })


def _sample_record(pmid=12345678):
    return {
        "id": str(pmid),
        "db_id": pmid,
        "pmid": pmid,
        "doi": f"10.1000/test{pmid}",
        "title": "A Phase III Trial of Drug X in Solid Tumors",
        "abstract": (
            "Background: Drug X was evaluated in 400 patients. "
            "Results: Median OS was 24.5 months (HR 0.72, p=0.001). "
            "Trial NCT12345678."
        ),
        "publication_date": "2024-01-15",
    }


def _mock_db_pool():
    """Return a mock asyncpg pool whose acquire() is a context manager."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)

    pool = AsyncMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    pool._conn = conn  # expose for assertion
    return pool


# ---------------------------------------------------------------------------
# Tests: LLM routing (all calls go through LITELLM_PROXY_URL)
# ---------------------------------------------------------------------------

class TestLLMRouting:
    """Verify all LLM calls go through the LiteLLM proxy (openai SDK base_url)."""

    def test_agent_uses_litellm_base_url(self):
        agent = _make_agent()
        client = agent._client
        # The client's base_url must match the LITELLM_PROXY_URL env var
        assert "litellm" in str(client.base_url).lower() or "4000" in str(client.base_url)

    def test_agent_does_not_import_anthropic(self):
        """No anthropic import in the publication evidence extractor module."""
        import dk_data.agents.publication_evidence_extractor as mod
        source_file = mod.__file__
        with open(source_file) as f:
            source = f.read()
        assert "import anthropic" not in source, (
            "publication_evidence_extractor.py must not import anthropic — "
            "LLM calls must route via LiteLLM proxy"
        )

    def test_base_agent_does_not_import_anthropic(self):
        import dk_data.agents.base_agent as mod
        source_file = mod.__file__
        with open(source_file) as f:
            lines = f.readlines()
        # Filter out comment/docstring lines; only check actual import statements
        import_lines = [
            l for l in lines
            if l.strip().startswith("import ") or l.strip().startswith("from ")
        ]
        assert not any("anthropic" in l for l in import_lines)


# ---------------------------------------------------------------------------
# Tests: staging table write (not live table)
# ---------------------------------------------------------------------------

class TestStagingWrite:
    """Verify agent writes to staging, never directly to live table."""

    def test_write_targets_staging_table(self):
        from dk_data.agents.publication_evidence_extractor import (
            SILVER_TABLE,
        )
        assert "staging" in SILVER_TABLE, (
            f"SILVER_TABLE must reference the staging table, got: {SILVER_TABLE}"
        )
        assert SILVER_TABLE == "mol_agents.publication_evidence_staging"

    def test_write_results_inserts_to_staging(self):
        """write_results() must INSERT into staging table, not live publication_evidence."""
        from dk_data.agents.base_agent import AgentResult

        agent = _make_agent()
        conn = AsyncMock()
        conn.execute = AsyncMock()

        pool = AsyncMock()
        pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        ))

        result = AgentResult(
            record_id="12345678",
            success=True,
            confidence_score=0.90,
            needs_review=False,
            output={
                "content_hash": "abc123",
                "molecule_id": None,
                "trial_nct_id": "NCT12345678",
                "pmid": 12345678,
                "doi": "10.1000/test",
                "endpoint_name": "Overall Survival",
                "endpoint_type": "primary",
                "hazard_ratio": 0.72,
                "p_value": 0.001,
                "response_rate": None,
                "median_survival_months": 24.5,
                "sample_size": 400,
                "confidence_score": 0.90,
                "needs_review": False,
                "agent_output": "{}",
            },
        )

        written = asyncio.run(
            agent.write_results([result], pool)
        )

        assert written == 1
        assert conn.execute.called
        # Verify INSERT targets publication_evidence_staging, not live table
        insert_sql = conn.execute.call_args[0][0]
        assert "publication_evidence_staging" in insert_sql
        assert "ON CONFLICT DO NOTHING" in insert_sql

    def test_write_results_skips_failed_records(self):
        """write_results() skips AgentResult(success=False) records."""
        from dk_data.agents.base_agent import AgentResult

        agent = _make_agent()
        conn = AsyncMock()
        conn.execute = AsyncMock()
        pool = AsyncMock()
        pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        ))

        failed = AgentResult(record_id="99", success=False, error="LLM timeout")

        written = asyncio.run(
            agent.write_results([failed], pool)
        )
        assert written == 0
        conn.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: deduplication (ON CONFLICT DO NOTHING)
# ---------------------------------------------------------------------------

class TestDeduplication:
    """Duplicate content_hash in staging is silently skipped."""

    def test_content_hash_computed_from_pmid_endpoint(self):
        from dk_data.agents.publication_evidence_extractor import _compute_content_hash
        import hashlib

        pmid = 12345678
        endpoint = "Overall Survival"
        expected = hashlib.md5((str(pmid) + endpoint).encode("utf-8")).hexdigest()
        assert _compute_content_hash(pmid, endpoint) == expected

    def test_same_pmid_endpoint_produces_same_hash(self):
        from dk_data.agents.publication_evidence_extractor import _compute_content_hash
        h1 = _compute_content_hash(11111, "PFS")
        h2 = _compute_content_hash(11111, "PFS")
        assert h1 == h2

    def test_different_endpoints_produce_different_hashes(self):
        from dk_data.agents.publication_evidence_extractor import _compute_content_hash
        h_os = _compute_content_hash(11111, "Overall Survival")
        h_pfs = _compute_content_hash(11111, "PFS")
        assert h_os != h_pfs


# ---------------------------------------------------------------------------
# Tests: confidence routing (quarantine vs staging vs needs_review)
# ---------------------------------------------------------------------------

class TestConfidenceRouting:
    """Verify confidence score routes records correctly."""

    def test_low_confidence_process_single_result_marks_not_success(self):
        """A record with no parseable JSON from LLM returns success=False."""
        agent = _make_agent()
        record = _sample_record()

        async def run():
            with patch.object(agent, "_call_llm_with_escalation", return_value=("invalid json", 0.3)):
                return await agent._process_single(record)

        result = asyncio.run(run())
        # JSON parse fails → success=False
        assert not result.success

    def test_high_confidence_sets_needs_review_false(self):
        """confidence >= 0.8 → needs_review = False in AgentResult."""
        agent = _make_agent()
        record = _sample_record()

        async def run():
            with patch.object(
                agent,
                "_call_llm_with_escalation",
                return_value=(_llm_response(confidence_score=0.95), 0.95),
            ):
                return await agent._process_single(record)

        result = asyncio.run(run())
        assert result.success
        assert result.confidence_score == 0.95
        assert result.needs_review is False

    def test_medium_confidence_sets_needs_review_true(self):
        """confidence 0.5–0.79 → needs_review = True in AgentResult."""
        agent = _make_agent()
        record = _sample_record()

        async def run():
            with patch.object(
                agent,
                "_call_llm_with_escalation",
                return_value=(_llm_response(confidence_score=0.65), 0.65),
            ):
                return await agent._process_single(record)

        result = asyncio.run(run())
        assert result.success
        assert result.needs_review is True

    def test_quarantine_called_for_low_confidence(self):
        """BaseAgent.run() calls _write_quarantine for results with confidence < 0.5."""
        agent = _make_agent()

        from dk_data.agents.base_agent import AgentResult

        low_conf_result = AgentResult(
            record_id="99",
            success=True,
            confidence_score=0.3,
            needs_review=True,
            output={
                "content_hash": "deadbeef",
                "molecule_id": None, "trial_nct_id": None,
                "pmid": 99, "doi": None,
                "endpoint_name": "Unknown Endpoint",
                "endpoint_type": "primary",
                "hazard_ratio": None, "p_value": None,
                "response_rate": None, "median_survival_months": None,
                "sample_size": None,
                "confidence_score": 0.3, "needs_review": True,
                "agent_output": "{}",
            },
        )

        quarantine_calls = []

        async def run():
            pool = _mock_db_pool()
            agent._db_pool = pool

            with patch.object(agent, "fetch_records", return_value=[_sample_record()]):
                with patch.object(agent, "_process_batch", return_value=[low_conf_result]):
                    with patch.object(agent, "write_results", return_value=0):
                        with patch.object(agent, "_write_quarantine", new_callable=AsyncMock) as mock_q:
                            await agent.run(scope=None, limit=1)
                            quarantine_calls.extend(mock_q.call_args_list)

        asyncio.run(run())
        # Low confidence record must route to quarantine
        assert len(quarantine_calls) >= 1


# ---------------------------------------------------------------------------
# Tests: batch processing — one failure doesn't abort the batch
# ---------------------------------------------------------------------------

class TestBatchProcessing:
    """_process_batch must not abort on single record failure."""

    def test_one_failed_record_does_not_abort_batch(self):
        """asyncio.gather with return_exceptions=True: a failure produces AgentResult(success=False)."""
        agent = _make_agent()

        records = [_sample_record(1), _sample_record(2), _sample_record(3)]

        call_count = 0

        async def fake_process_single(record):
            nonlocal call_count
            call_count += 1
            if record["pmid"] == 2:
                raise ValueError("Simulated LLM failure for record 2")
            from dk_data.agents.base_agent import AgentResult
            return AgentResult(
                record_id=str(record["pmid"]),
                success=True,
                confidence_score=0.9,
            )

        async def run():
            with patch.object(agent, "_process_single", side_effect=fake_process_single):
                return await agent._process_batch(records)

        results = asyncio.run(run())

        assert call_count == 3  # All 3 records attempted
        assert len(results) == 3
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 2
        assert len(failures) == 1
        assert failures[0].record_id == "2"


# ---------------------------------------------------------------------------
# Tests: _parse_confidence correctness
# ---------------------------------------------------------------------------

class TestParseConfidence:
    def test_parses_valid_json(self):
        agent = _make_agent()
        response = json.dumps({"endpoint_name": "OS", "confidence_score": 0.87})
        score = agent._parse_confidence(response)
        assert abs(score - 0.87) < 0.001

    def test_returns_zero_on_invalid_json(self):
        agent = _make_agent()
        score = agent._parse_confidence("not json at all")
        assert score == 0.0

    def test_regex_fallback_extracts_confidence(self):
        agent = _make_agent()
        partial = '... "confidence_score": 0.75 ...'
        score = agent._parse_confidence(partial)
        assert abs(score - 0.75) < 0.001


# ---------------------------------------------------------------------------
# Tests: SQLMesh staging-to-live separation
# ---------------------------------------------------------------------------

class TestStagingToLiveSeparation:
    """Agent must never write to mol_silver.publication_evidence (live table)."""

    def test_write_results_does_not_reference_live_table(self):
        """The INSERT SQL must not name the live table."""
        import inspect
        from dk_data.agents.publication_evidence_extractor import PublicationEvidenceExtractorAgent

        source = inspect.getsource(PublicationEvidenceExtractorAgent.write_results)
        # Live table name: publication_evidence (without _staging suffix)
        # Should NOT appear without the _staging suffix
        # The staging table IS allowed; the live table without suffix is not
        assert "publication_evidence_staging" in source
        # The live table should not be directly inserted into
        # (allow "publication_evidence" as part of "publication_evidence_staging")
        live_only = source.replace("publication_evidence_staging", "")
        assert "publication_evidence" not in live_only or "mol_silver.publication_evidence" not in live_only
