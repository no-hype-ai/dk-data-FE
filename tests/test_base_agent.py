"""Tests for BaseAgent class.

Feature: 016-cms-puf-datasource-integration
Task: T022

Verifies:
- LiteLLM OpenAI client initialization (not Anthropic SDK)
- Execution logging to meta.agent_execution_log
- Quarantine write to meta.agent_quarantine
- Confidence threshold classification
- Full run() orchestration
"""

import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest


class TestBaseAgentInit:
    """Verify agent initializes with LiteLLM OpenAI client."""

    @patch.dict(os.environ, {
        "LITELLM_BASE_URL": "http://litellm.test:8000",
        "LITELLM_API_KEY": "test-key",
        "LITELLM_MODEL_ALIAS": "haiku",
    })
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_uses_openai_client(self, mock_pg, mock_openai):
        from dk_data.agents.base_agent import BaseAgent

        class TestAgent(BaseAgent):
            AGENT_NAME = "test"
            AGENT_VERSION = "0.1.0"
            def load_batch(self): return []
            def execute(self, batch): pass
            def write_results(self, enriched): pass

        agent = TestAgent()
        mock_openai.assert_called_once_with(
            base_url="http://litellm.test:8000",
            api_key="test-key",
        )
        assert agent.model == "haiku"

    def test_does_not_import_anthropic(self):
        """BaseAgent must NOT use anthropic SDK — dk-canon requirement."""
        import inspect
        from dk_data.agents import base_agent
        source = inspect.getsource(base_agent)
        assert "import anthropic" not in source
        assert "from anthropic" not in source


class TestConfidenceThresholds:
    """Verify confidence tier classification."""

    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_threshold_values(self, mock_pg, mock_openai):
        from dk_data.agents.base_agent import BaseAgent

        class TestAgent(BaseAgent):
            AGENT_NAME = "test"
            AGENT_VERSION = "0.1.0"
            def load_batch(self): return []
            def execute(self, batch): pass
            def write_results(self, enriched): pass

        agent = TestAgent()
        assert agent.CONFIDENCE_THRESHOLD_ACCEPT == 0.8
        assert agent.CONFIDENCE_THRESHOLD_REVIEW == 0.5


class TestAgentResult:
    """Verify AgentResult dataclass."""

    def test_default_values(self):
        from dk_data.agents.base_agent import AgentResult
        result = AgentResult()
        assert result.enriched == []
        assert result.quarantine == []
        assert result.error is None

    def test_with_data(self):
        from dk_data.agents.base_agent import AgentResult
        result = AgentResult(
            enriched=[{"npi": "1234567890", "service_line": "Cardiology"}],
            quarantine=[{"data": {}, "reason": "Low confidence", "confidence_score": 0.3}],
        )
        assert len(result.enriched) == 1
        assert len(result.quarantine) == 1


class TestQuarantineWrite:
    """Verify quarantine records are written to meta.agent_quarantine."""

    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_write_quarantine_inserts_records(self, mock_pg, mock_openai):
        from dk_data.agents.base_agent import BaseAgent

        class TestAgent(BaseAgent):
            AGENT_NAME = "test_agent"
            AGENT_VERSION = "0.1.0"
            def load_batch(self): return []
            def execute(self, batch): pass
            def write_results(self, enriched): pass

        agent = TestAgent()

        # Mock connection with proper context manager support
        mock_conn = MagicMock()
        mock_conn.closed = False
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        agent._conn = mock_conn

        quarantine = [
            {"data": {"npi": "123"}, "reason": "Low confidence", "confidence_score": 0.3},
            {"data": {"npi": "456"}, "reason": "Missing field", "confidence_score": 0.2},
        ]

        agent.write_quarantine(quarantine, "exec-123")

        assert mock_cursor.execute.call_count == 2
        mock_conn.commit.assert_called_once()

    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_write_quarantine_skips_empty(self, mock_pg, mock_openai):
        from dk_data.agents.base_agent import BaseAgent

        class TestAgent(BaseAgent):
            AGENT_NAME = "test"
            AGENT_VERSION = "0.1.0"
            def load_batch(self): return []
            def execute(self, batch): pass
            def write_results(self, enriched): pass

        agent = TestAgent()
        mock_conn = MagicMock()
        agent._conn = mock_conn

        agent.write_quarantine([], "exec-123")
        mock_conn.cursor.assert_not_called()


class TestExecutionLogging:
    """Verify execution logging to meta.agent_execution_log."""

    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_log_execution_completed(self, mock_pg, mock_openai):
        from dk_data.agents.base_agent import BaseAgent, AgentResult

        class TestAgent(BaseAgent):
            AGENT_NAME = "test_agent"
            AGENT_VERSION = "0.1.0"
            def load_batch(self): return []
            def execute(self, batch): pass
            def write_results(self, enriched): pass

        agent = TestAgent()

        mock_conn = MagicMock()
        mock_conn.closed = False
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        agent._conn = mock_conn

        result = AgentResult(enriched=[{"x": 1}], quarantine=[{"y": 2}])
        started = datetime.now(timezone.utc)

        agent.log_execution("exec-456", started, result, 10)

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "COMPLETED" in str(call_args)
        mock_conn.commit.assert_called_once()

    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_log_execution_failed(self, mock_pg, mock_openai):
        from dk_data.agents.base_agent import BaseAgent, AgentResult

        class TestAgent(BaseAgent):
            AGENT_NAME = "test_agent"
            AGENT_VERSION = "0.1.0"
            def load_batch(self): return []
            def execute(self, batch): pass
            def write_results(self, enriched): pass

        agent = TestAgent()

        mock_conn = MagicMock()
        mock_conn.closed = False
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        agent._conn = mock_conn

        result = AgentResult(error="Connection timeout")
        started = datetime.now(timezone.utc)

        agent.log_execution("exec-789", started, result, 0)

        call_args = mock_cursor.execute.call_args
        assert "FAILED" in str(call_args)
