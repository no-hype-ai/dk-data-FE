"""Tests for pipeline tools registry and unified data tools gateway.

Feature: 015-assessment-dashboard-integration (pipeline), 016-cms-puf (data-tools)
Task: T078

Tests verify:
- Pipeline registry: 26 molecule/IP tools
- Data tools registry: 54 tools (26 molecule + 20 CMS queryable + 8 CMS bulk-only)
- Data tools router endpoints
- Response models
"""

class TestToolRegistry:
    """Verify pipeline tool registry has all 26 tools."""

    def test_registry_has_26_tools(self):
        from dk_data.services.pipeline.tool_registry import TOOL_REGISTRY
        assert len(TOOL_REGISTRY) == 26

    def test_tier_1_has_19_tools(self):
        from dk_data.services.pipeline.tool_registry import get_tools_by_tier
        assert len(get_tools_by_tier("direct_query")) == 19

    def test_tier_2_has_5_tools(self):
        from dk_data.services.pipeline.tool_registry import get_tools_by_tier
        assert len(get_tools_by_tier("fetch_filter")) == 5

    def test_tier_3_has_2_tools(self):
        from dk_data.services.pipeline.tool_registry import get_tools_by_tier
        assert len(get_tools_by_tier("supplementary")) == 2

    def test_cms_tools_removed(self):
        """CMS tools removed in 016-cms-puf — data served via PostgREST gold views."""
        from dk_data.services.pipeline.tool_registry import TOOL_REGISTRY
        for name in ("cms-inpatient-search", "cms-hospital-info-search", "cms-cost-reports-search"):
            assert name not in TOOL_REGISTRY, f"{name} should be removed"

    def test_all_tools_have_required_fields(self):
        from dk_data.services.pipeline.tool_registry import TOOL_REGISTRY
        for name, defn in TOOL_REGISTRY.items():
            assert defn.name == name, f"Tool name mismatch: {name}"
            assert defn.description, f"Missing description: {name}"
            assert defn.tier in ("direct_query", "fetch_filter", "supplementary"), f"Invalid tier: {name}"
            assert defn.raw_table, f"Missing raw_table: {name}"
            assert defn.raw_schema in ("mol_raw", "raw"), f"Invalid raw_schema: {name}"
            assert defn.adapter_module, f"Missing adapter_module: {name}"
            assert defn.api_base_url, f"Missing api_base_url: {name}"
            assert defn.input_schema, f"Missing input_schema: {name}"

    def test_mol_raw_sources(self):
        """Molecule-specific sources use mol_raw schema."""
        from dk_data.services.pipeline.tool_registry import TOOL_REGISTRY
        mol_raw_tools = [
            "clinicaltrials-search", "chembl-search", "openfda-faers-search",
            "openfda-labels-search", "drugbank-search", "pubchem-search",
            "openalex-search", "uniprot-search",
        ]
        for name in mol_raw_tools:
            assert TOOL_REGISTRY[name].raw_schema == "mol_raw", f"{name} should use mol_raw"

    def test_raw_sources(self):
        """IP/regulatory sources use raw schema."""
        from dk_data.services.pipeline.tool_registry import TOOL_REGISTRY
        raw_tools = [
            "pubmed-search", "ema-search", "hta-decisions-search",
            "sec-edgar-search", "who-icd-search", "pdb-search",
        ]
        for name in raw_tools:
            assert TOOL_REGISTRY[name].raw_schema == "raw", f"{name} should use raw"


class TestDataToolsRegistry:
    """Verify unified data tools registry has correct tool counts."""

    def test_registry_has_54_tools(self):
        from dk_data.services.data_tools.tool_registry import TOOL_REGISTRY
        assert len(TOOL_REGISTRY) == 54

    def test_molecule_category_has_26_tools(self):
        from dk_data.services.data_tools.tool_registry import get_tools_by_category
        assert len(get_tools_by_category("molecule")) == 26

    def test_cms_queryable_has_20_tools(self):
        from dk_data.services.data_tools.tool_registry import get_tools_by_category
        assert len(get_tools_by_category("cms_queryable")) == 20

    def test_cms_bulk_only_has_8_tools(self):
        from dk_data.services.data_tools.tool_registry import get_tools_by_category
        assert len(get_tools_by_category("cms_bulk_only")) == 8

    def test_all_tools_have_required_fields(self):
        from dk_data.services.data_tools.tool_registry import TOOL_REGISTRY
        for name, defn in TOOL_REGISTRY.items():
            assert defn.name == name, f"Tool name mismatch: {name}"
            assert defn.description, f"Missing description: {name}"
            assert defn.category in ("molecule", "cms_queryable", "cms_bulk_only"), f"Invalid category: {name}"
            assert defn.supported_query_keys, f"Missing supported_query_keys: {name}"
            assert defn.adapter_module, f"Missing adapter_module: {name}"

    def test_cms_queryable_tools_have_local_check(self):
        from dk_data.services.data_tools.tool_registry import get_tools_by_category
        for name, defn in get_tools_by_category("cms_queryable").items():
            assert defn.local_check is not None, f"CMS queryable tool {name} missing local_check"
            assert defn.local_check.gold_schema, f"{name} missing gold_schema"
            assert defn.local_check.gold_table, f"{name} missing gold_table"

    def test_bulk_only_tools_not_external(self):
        from dk_data.services.data_tools.tool_registry import get_tools_by_category
        for name, defn in get_tools_by_category("cms_bulk_only").items():
            assert not defn.external_api_available, f"Bulk-only tool {name} should not have external API"

    def test_provider_network_in_registry(self):
        from dk_data.services.data_tools.tool_registry import TOOL_REGISTRY
        assert "cms-provider-network" in TOOL_REGISTRY
        defn = TOOL_REGISTRY["cms-provider-network"]
        assert defn.local_check.gold_table == "cms_provider_network"
        assert defn.local_check.silver_table == "cms_referral_edges"


class TestDataToolsRouter:
    """Verify data-tools router endpoint structure."""

    def test_list_endpoint_exists(self):
        from dk_data.api.routes.data_tools import router
        routes = [r.path for r in router.routes]
        assert "/data-tools" in routes

    def test_backfill_endpoint_exists(self):
        from dk_data.api.routes.data_tools import router
        routes = [r.path for r in router.routes]
        assert "/data-tools/{source}/backfill" in routes

    def test_meta_endpoint_exists(self):
        from dk_data.api.routes.data_tools import router
        routes = [r.path for r in router.routes]
        assert "/data-tools/{source}/meta" in routes

    def test_router_prefix(self):
        from dk_data.api.routes.data_tools import router
        assert router.prefix == "/data-tools"

    def test_no_query_endpoint(self):
        """Reads go directly to PostgREST — no /query proxy."""
        from dk_data.api.routes.data_tools import router
        routes = [r.path for r in router.routes]
        assert "/data-tools/{source}/query" not in routes


class TestBackfillResponse:
    """Verify backfill response model matches contract."""

    def test_backfilled_response(self):
        from dk_data.api.routes.data_tools import BackfillResponse
        resp = BackfillResponse(
            status="backfilled",
            request_id="abc-123",
            source="cms-pecos",
            record_count=5,
            raw_record_id="raw-456",
            external_api_available=True,
            duration_ms=1200,
            postgrest_view="gold.cms_provider_360",
            postgrest_key="npi",
            message="Data fetched and transform triggered. Re-query PostgREST for results.",
            timestamp="2026-03-12T10:00:00",
        )
        assert resp.status == "backfilled"
        assert resp.postgrest_view == "gold.cms_provider_360"
        assert resp.postgrest_key == "npi"

    def test_not_available_response(self):
        from dk_data.api.routes.data_tools import BackfillResponse
        resp = BackfillResponse(
            status="not_available",
            request_id="abc-123",
            source="cms-nppes",
            external_api_available=False,
            postgrest_view="gold.cms_nppes",
            postgrest_key="npi",
            timestamp="2026-03-12T10:00:00",
        )
        assert resp.status == "not_available"
        assert not resp.external_api_available

    def test_error_response(self):
        from dk_data.api.routes.data_tools import BackfillResponse
        resp = BackfillResponse(
            status="error",
            request_id="abc-123",
            source="cms-pecos",
            error={"code": "rate_limited", "message": "Rate limit exceeded", "status_code": 429},
            timestamp="2026-03-12T10:00:00",
        )
        assert resp.status == "error"
        assert resp.error["code"] == "rate_limited"


class TestDataToolListIncludesPostgRESTMapping:
    """Verify the list endpoint returns PostgREST view mappings."""

    def test_tools_have_postgrest_view(self):
        from dk_data.api.routes.data_tools import DataToolInfo
        info = DataToolInfo(
            name="cms-pecos",
            description="test",
            category="cms_queryable",
            supported_query_keys=["npi"],
            external_api_available=True,
            tier="direct_query",
            postgrest_view="gold.cms_provider_360",
            postgrest_key="npi",
        )
        assert info.postgrest_view == "gold.cms_provider_360"
        assert info.postgrest_key == "npi"


class TestBaseMCPTool:
    """Verify base tool error response structure."""

    def test_error_response_format(self):
        from dk_data.services.pipeline.base_tool import BaseMCPTool
        from dk_data.services.pipeline.adapters.base import BaseAdapter

        class DummyAdapter(BaseAdapter):
            @property
            def source_name(self): return "test"
            @property
            def raw_table(self): return "test"
            @property
            def raw_schema(self): return "raw"
            def normalize(self, api_response): return api_response

        tool = BaseMCPTool(DummyAdapter(), "http://test.example.com")
        result = tool._error_response("req-1", "timeout", "Timed out", 408)
        assert result["status"] == "error"
        assert result["error"]["code"] == "timeout"
        assert result["error"]["status_code"] == 408
        assert result["request_id"] == "req-1"


class TestPostgRESTClient:
    """Verify PostgREST client construction."""

    def test_default_url(self):
        from dk_data.services.data_tools.postgrest_client import PostgRESTClient
        client = PostgRESTClient()
        assert "postgrest" in client.base_url
        assert "3000" in client.base_url

    def test_custom_url(self):
        from dk_data.services.data_tools.postgrest_client import PostgRESTClient
        client = PostgRESTClient(base_url="http://localhost:3333")
        assert client.base_url == "http://localhost:3333"

    def test_jwt_token_forwarding(self):
        from dk_data.services.data_tools.postgrest_client import PostgRESTClient
        client = PostgRESTClient(jwt_token="test-token-123")
        assert client._headers["Authorization"] == "Bearer test-token-123"

    def test_no_token_no_auth_header(self):
        from dk_data.services.data_tools.postgrest_client import PostgRESTClient
        client = PostgRESTClient()
        assert "Authorization" not in client._headers


class TestJWTAuth:
    """Verify JWT auth dependency."""

    def test_no_token_returns_system_user(self):
        import asyncio
        from dk_data.api.dependencies import get_jwt_user
        result = asyncio.run(get_jwt_user(authorization=None))
        assert result["role"] == "api_user"
        assert result["authenticated"] is False

    def test_invalid_token_raises(self):
        import asyncio
        import os
        os.environ["JWT_SECRET"] = "a" * 32
        from dk_data.api.dependencies import get_jwt_user
        try:
            asyncio.run(get_jwt_user(authorization="Bearer invalid"))
            assert False, "Should have raised"
        except Exception:
            pass  # Expected
        finally:
            os.environ.pop("JWT_SECRET", None)
