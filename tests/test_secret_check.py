"""Tests for secret validation module.

Feature: 012-platform-hardening (US5)
"""

from unittest.mock import patch

import pytest

from dk_data.ingestion.utils.secret_check import validate_secrets


class TestValidateSecrets:
    """Tests for validate_secrets function."""

    def test_all_required_present(self):
        env = {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "secret",
            "POSTGRES_DB": "dk_data",
        }
        with patch.dict("os.environ", env, clear=True):
            result = validate_secrets()

        assert result["valid"] is True
        assert result["missing_required"] == []
        assert len(result["present"]) >= 5

    def test_missing_required_secret(self):
        env = {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            # Missing POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
        }
        with patch.dict("os.environ", env, clear=True):
            result = validate_secrets()

        assert result["valid"] is False
        assert "POSTGRES_USER" in result["missing_required"]
        assert "POSTGRES_PASSWORD" in result["missing_required"]
        assert "POSTGRES_DB" in result["missing_required"]

    def test_empty_value_treated_as_missing(self):
        env = {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "",
            "POSTGRES_PASSWORD": "secret",
            "POSTGRES_DB": "dk_data",
        }
        with patch.dict("os.environ", env, clear=True):
            result = validate_secrets()

        assert result["valid"] is False
        assert "POSTGRES_USER" in result["missing_required"]

    def test_whitespace_only_treated_as_missing(self):
        env = {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "  ",
            "POSTGRES_PASSWORD": "secret",
            "POSTGRES_DB": "dk_data",
        }
        with patch.dict("os.environ", env, clear=True):
            result = validate_secrets()

        assert result["valid"] is False
        assert "POSTGRES_USER" in result["missing_required"]

    def test_optional_secrets_tracked(self):
        env = {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "secret",
            "POSTGRES_DB": "dk_data",
            "NCBI_API_KEY": "test_key",
        }
        with patch.dict("os.environ", env, clear=True):
            result = validate_secrets()

        assert result["valid"] is True
        assert "NCBI_API_KEY" in result["present"]
        assert "DRUGBANK_API_KEY" in result["missing_optional"]

    def test_custom_secret_lists(self):
        required = [("MY_SECRET", "Test secret")]
        optional = [("MY_OPTIONAL", "Optional test")]

        env = {"MY_SECRET": "value"}
        with patch.dict("os.environ", env, clear=True):
            result = validate_secrets(required=required, optional=optional)

        assert result["valid"] is True
        assert "MY_SECRET" in result["present"]
        assert "MY_OPTIONAL" in result["missing_optional"]

    def test_no_secrets_at_all(self):
        with patch.dict("os.environ", {}, clear=True):
            result = validate_secrets()

        assert result["valid"] is False
        assert len(result["missing_required"]) == 5
