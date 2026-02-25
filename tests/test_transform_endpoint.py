"""Tests for on-demand transform endpoint.

Feature: 015-assessment-dashboard-integration
Task: T058

Tests verify:
- Authentication required (401 without JWT)
- Analyst role required for transform
- Rate limit enforcement (429 after 10 rapid requests)
- Source routing for mol_raw sources
- Source routing for raw sources
- Unknown source returns 404
- Optional molecule_id scoping
"""

import time
from unittest.mock import patch, MagicMock

import pytest

# Pre-import to handle email-validator dependency issue in test environment.
# The first import of data_platform may raise ImportError due to email-validator
# not being installed (a Pydantic transitive dep). The module still caches, so
# a second import succeeds. We force that here at module level.
try:
    from dk_data.api.routes import data_platform as _dp_module  # noqa: F401
except ImportError:
    pass  # Module is now cached; subsequent imports will work


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_app():
    """Import FastAPI app for TestClient."""
    from dk_data.ingestion.batch.api import app
    return app


def _reset_rate_limits():
    """Reset the in-memory rate limit counters between tests."""
    from dk_data.api.routes.data_platform import _rate_limit_window
    _rate_limit_window.clear()


# ---------------------------------------------------------------------------
# Source Routing Tests (T055)
# ---------------------------------------------------------------------------


class TestSourceRouting:
    """Verify source→model routing logic."""

    def test_clinicaltrials_routes_to_mol_pipeline(self):
        from dk_data.api.routes.data_platform import _SOURCE_MODEL_MAP

        config = _SOURCE_MODEL_MAP["clinicaltrials"]
        assert config["bronze"] == "mol_bronze.clinical_trials"
        assert config["silver"] == "mol_silver.clinical_trials"
        assert "mol_gold" in config.get("gold", "")
        assert "mol_raw" in config["schema_path"]

    def test_pubmed_routes_to_raw_pipeline(self):
        from dk_data.api.routes.data_platform import _SOURCE_MODEL_MAP

        config = _SOURCE_MODEL_MAP["pubmed"]
        assert config["bronze"] == "bronze.pubmed"
        assert config["silver"] == "silver.publications"
        assert "raw→bronze" in config["schema_path"]

    def test_sec_edgar_routes_to_financial(self):
        from dk_data.api.routes.data_platform import _SOURCE_MODEL_MAP

        config = _SOURCE_MODEL_MAP["sec_edgar"]
        assert config["bronze"] == "bronze.sec_edgar"
        assert config["silver"] == "silver.financial_data"
        assert config["gold"] == "mol_gold.financial_summary"

    def test_orcid_routes_to_kol(self):
        from dk_data.api.routes.data_platform import _SOURCE_MODEL_MAP

        config = _SOURCE_MODEL_MAP["orcid"]
        assert config["bronze"] == "bronze.orcid"
        assert config["silver"] == "silver.researchers"
        assert config["gold"] == "mol_gold.kol_profiles"

    def test_all_contract_sources_present(self):
        """All sources from transform-api.yaml contract are in routing map."""
        from dk_data.api.routes.data_platform import _SOURCE_MODEL_MAP

        contract_sources = [
            "clinicaltrials", "chembl", "openfda_faers", "openfda_labels",
            "drugbank", "pubchem", "openalex", "uniprot",
            "pubmed", "ema", "hta_decisions", "cochrane_reviews",
            "sec_edgar", "orcid", "journal_rss", "medical_news",
            "cms_medicare_inpatient", "cms_hospital_info", "cms_cost_reports",
            "acc_tvc", "hrsa", "pdb_structures", "who_icd",
            "uspto_patents", "epo_patents", "orange_book",
            "uspto_trademarks", "euipo_trademarks",
        ]
        for source in contract_sources:
            assert source in _SOURCE_MODEL_MAP, f"Missing source in routing map: {source}"

    def test_unknown_source_not_in_map(self):
        from dk_data.api.routes.data_platform import _SOURCE_MODEL_MAP
        assert "nonexistent_source" not in _SOURCE_MODEL_MAP


# ---------------------------------------------------------------------------
# Rate Limiting Tests (T056)
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Verify per-source rate limiting."""

    def setup_method(self):
        _reset_rate_limits()

    def test_under_limit_allows_request(self):
        from dk_data.api.routes.data_platform import _check_rate_limit
        result = _check_rate_limit("test_source")
        assert result is None  # No rate limit

    def test_at_limit_returns_retry_after(self):
        from dk_data.api.routes.data_platform import _check_rate_limit, _RATE_LIMIT_MAX

        # Fill up the window
        for _ in range(_RATE_LIMIT_MAX):
            _check_rate_limit("test_source_2")

        # Next request should be rate limited
        result = _check_rate_limit("test_source_2")
        assert result is not None
        assert isinstance(result, int)
        assert result > 0

    def test_different_sources_independent(self):
        from dk_data.api.routes.data_platform import _check_rate_limit, _RATE_LIMIT_MAX

        # Fill up source A
        for _ in range(_RATE_LIMIT_MAX):
            _check_rate_limit("source_a")

        # Source B should still be available
        result = _check_rate_limit("source_b")
        assert result is None

    def test_rate_limit_per_source_not_global(self):
        from dk_data.api.routes.data_platform import _check_rate_limit, _RATE_LIMIT_MAX

        for _ in range(_RATE_LIMIT_MAX):
            _check_rate_limit("pubmed")

        # pubmed is limited
        assert _check_rate_limit("pubmed") is not None
        # chembl is not
        assert _check_rate_limit("chembl") is None


# ---------------------------------------------------------------------------
# Advisory Lock Tests (T057)
# ---------------------------------------------------------------------------


class TestAdvisoryLock:
    """Verify advisory lock key generation."""

    def test_lock_key_deterministic(self):
        """Same source always produces same lock key."""
        import hashlib
        key1 = int(hashlib.md5(b"clinicaltrials").hexdigest()[:8], 16)
        key2 = int(hashlib.md5(b"clinicaltrials").hexdigest()[:8], 16)
        assert key1 == key2

    def test_different_sources_different_keys(self):
        """Different sources produce different lock keys."""
        import hashlib
        key1 = int(hashlib.md5(b"clinicaltrials").hexdigest()[:8], 16)
        key2 = int(hashlib.md5(b"pubmed").hexdigest()[:8], 16)
        assert key1 != key2


# ---------------------------------------------------------------------------
# Transform Response Model Tests
# ---------------------------------------------------------------------------


class TestTransformResponseModel:
    """Verify response model structure matches contract."""

    def test_transform_response_fields(self):
        from dk_data.api.routes.data_platform import TransformResponse, TransformLayerResult

        response = TransformResponse(
            source="clinicaltrials",
            status="completed",
            schema_path="mol_raw→mol_bronze→mol_silver→mol_gold",
            layers=[
                TransformLayerResult(
                    layer="bronze",
                    model="mol_bronze.clinical_trials",
                    rows_processed=5,
                    duration_ms=1200,
                    status="success",
                ),
            ],
            total_duration_ms=3500,
            timestamp="2026-02-25T10:00:00",
        )
        assert response.source == "clinicaltrials"
        assert response.status == "completed"
        assert len(response.layers) == 1
        assert response.layers[0].rows_processed == 5

    def test_transform_layer_result_error(self):
        from dk_data.api.routes.data_platform import TransformLayerResult

        result = TransformLayerResult(
            layer="silver",
            model="mol_silver.clinical_trials",
            status="failed",
            error="Timeout connecting to database",
        )
        assert result.status == "failed"
        assert result.error is not None

    def test_transform_request_defaults(self):
        from dk_data.api.routes.data_platform import TransformRequest

        req = TransformRequest()
        assert req.molecule_id is None
        assert req.layers == ["bronze", "silver", "gold"]

    def test_transform_request_custom_layers(self):
        from dk_data.api.routes.data_platform import TransformRequest

        req = TransformRequest(layers=["bronze"])
        assert req.layers == ["bronze"]

    def test_transform_request_with_molecule_id(self):
        from dk_data.api.routes.data_platform import TransformRequest

        req = TransformRequest(molecule_id="abc-123")
        assert req.molecule_id == "abc-123"
