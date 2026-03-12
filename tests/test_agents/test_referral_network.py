"""Tests for ReferralNetworkAgent.

Feature: 016-cms-puf-datasource-integration
Task: T091
"""

import os
from unittest.mock import patch

import pytest  # noqa: F401 — pytest fixture/marker discovery


class TestReferralNetworkAgent:

    @patch.dict(os.environ, {"LITELLM_BASE_URL": "http://test:8000", "LITELLM_API_KEY": "test"})
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_agent_class_exists(self, mock_pg, mock_openai):
        from dk_data.agents.referral_network import ReferralNetworkAgent
        agent = ReferralNetworkAgent()
        assert agent.AGENT_NAME == "referral_network"

    @patch.dict(os.environ, {"LITELLM_BASE_URL": "http://test:8000", "LITELLM_API_KEY": "test"})
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_no_anthropic_import(self, mock_pg, mock_openai):
        import inspect
        from dk_data.agents import referral_network
        source = inspect.getsource(referral_network)
        assert "import anthropic" not in source
