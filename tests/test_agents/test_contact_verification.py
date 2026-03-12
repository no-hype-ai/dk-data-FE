"""Tests for ContactVerificationAgent.

Feature: 016-cms-puf-datasource-integration
Task: T092
"""

import os
from unittest.mock import patch

import pytest


class TestContactVerificationAgent:

    @patch.dict(os.environ, {"LITELLM_BASE_URL": "http://test:8000", "LITELLM_API_KEY": "test"})
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_agent_class_exists(self, mock_pg, mock_openai):
        from dk_data.agents.contact_verification import ContactVerificationAgent
        agent = ContactVerificationAgent()
        assert agent.AGENT_NAME == "contact_verification"

    @patch.dict(os.environ, {"LITELLM_BASE_URL": "http://test:8000", "LITELLM_API_KEY": "test"})
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_no_anthropic_import(self, mock_pg, mock_openai):
        import inspect
        from dk_data.agents import contact_verification
        source = inspect.getsource(contact_verification)
        assert "import anthropic" not in source
