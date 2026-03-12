"""Tests for EquipmentInventoryAgent.

Feature: 016-cms-puf-datasource-integration
Task: T094
"""

import os
from unittest.mock import patch

import pytest


class TestEquipmentInventoryAgent:

    @patch.dict(os.environ, {"LITELLM_BASE_URL": "http://test:8000", "LITELLM_API_KEY": "test"})
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_agent_class_exists(self, mock_pg, mock_openai):
        from dk_data.agents.equipment_inventory import EquipmentInventoryAgent
        agent = EquipmentInventoryAgent()
        assert agent.AGENT_NAME == "equipment_inventory"

    @patch.dict(os.environ, {"LITELLM_BASE_URL": "http://test:8000", "LITELLM_API_KEY": "test"})
    @patch("dk_data.agents.base_agent.OpenAI")
    @patch("dk_data.agents.base_agent.psycopg2")
    def test_no_anthropic_import(self, mock_pg, mock_openai):
        import inspect
        from dk_data.agents import equipment_inventory
        source = inspect.getsource(equipment_inventory)
        assert "import anthropic" not in source
