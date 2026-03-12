"""Tests for ServiceLineInferenceAgent.

Feature: 016-cms-puf-datasource-integration
Task: T089
"""

import os
from unittest.mock import patch, MagicMock

import pytest


class TestServiceLineInferenceAgent:
    """Verify service line inference agent."""

    @patch.dict(os.environ, {
        "LITELLM_BASE_URL": "http://test:8000",
        "LITELLM_API_KEY": "test",
    })
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_agent_class_exists(self, mock_pg, mock_openai):
        from dk_data.agents.service_line_inference import ServiceLineInferenceAgent
        agent = ServiceLineInferenceAgent()
        assert agent.AGENT_NAME == "service_line_inference"

    @patch.dict(os.environ, {
        "LITELLM_BASE_URL": "http://test:8000",
        "LITELLM_API_KEY": "test",
    })
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_uses_litellm_not_anthropic(self, mock_pg, mock_openai):
        import inspect
        from dk_data.agents import service_line_inference
        source = inspect.getsource(service_line_inference)
        assert "import anthropic" not in source
        assert "from anthropic" not in source

    @patch.dict(os.environ, {
        "LITELLM_BASE_URL": "http://test:8000",
        "LITELLM_API_KEY": "test",
    })
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_execute_returns_agent_result(self, mock_pg, mock_openai):
        from dk_data.agents.service_line_inference import ServiceLineInferenceAgent
        from dk_data.agents.base_agent import AgentResult

        agent = ServiceLineInferenceAgent()
        # Mock LLM response
        agent.call_llm = MagicMock(return_value={
            "results": [
                {"drg_code": "001", "service_line": "Cardiology", "confidence": 0.95}
            ]
        })

        batch = [{"drg_code": "001", "drg_description": "Heart transplant"}]
        result = agent.execute(batch)
        assert isinstance(result, AgentResult)
