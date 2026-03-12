"""Tests for IDNHierarchyAgent.

Feature: 016-cms-puf-datasource-integration
Task: T090
"""

import os
from unittest.mock import patch, MagicMock  # noqa: F401 — MagicMock used in future agent mock tests

import pytest  # noqa: F401 — pytest fixture/marker discovery


class TestIDNHierarchyAgent:

    @patch.dict(os.environ, {"LITELLM_BASE_URL": "http://test:8000", "LITELLM_API_KEY": "test"})
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_agent_class_exists(self, mock_pg, mock_openai):
        from dk_data.agents.idn_hierarchy import IDNHierarchyAgent
        agent = IDNHierarchyAgent()
        assert agent.AGENT_NAME == "idn_hierarchy"

    @patch.dict(os.environ, {"LITELLM_BASE_URL": "http://test:8000", "LITELLM_API_KEY": "test"})
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_no_anthropic_import(self, mock_pg, mock_openai):
        import inspect
        from dk_data.agents import idn_hierarchy
        source = inspect.getsource(idn_hierarchy)
        assert "import anthropic" not in source
