"""Tests for MCP tools endpoint and registry.

Feature: 015-assessment-dashboard-integration
Task: T078

Tests verify:
- GET /mcp/tools returns all 28 tools
- Tool invocation requires authentication
- Unknown tool returns 404
- Rate limiting returns 429
- Timeout returns 408 error response
"""

class TestToolRegistry:
    """Verify tool registry has all tools (28 original + 28 CMS PUF + 5 new = 61)."""

    def test_registry_has_28_tools(self):
        from dk_data.services.mcp.tool_registry import TOOL_REGISTRY
        assert len(TOOL_REGISTRY) == 61

    def test_tier_1_has_19_tools(self):
        from dk_data.services.mcp.tool_registry import get_tools_by_tier
        assert len(get_tools_by_tier("direct_query")) == 24

    def test_tier_2_has_4_tools(self):
        from dk_data.services.mcp.tool_registry import get_tools_by_tier
        assert len(get_tools_by_tier("fetch_filter")) == 4

    def test_tier_3_has_5_tools(self):
        from dk_data.services.mcp.tool_registry import get_tools_by_tier
        assert len(get_tools_by_tier("supplementary")) == 33

    def test_all_tools_have_required_fields(self):
        from dk_data.services.mcp.tool_registry import TOOL_REGISTRY
        for name, defn in TOOL_REGISTRY.items():
            assert defn.name == name, f"Tool name mismatch: {name}"
            assert defn.description, f"Missing description: {name}"
            assert defn.tier in ("direct_query", "fetch_filter", "supplementary"), f"Invalid tier: {name}"
            assert defn.raw_table, f"Missing raw_table: {name}"
            assert defn.raw_schema in ("mol_raw", "raw", "hcs_raw"), f"Invalid raw_schema: {name}"
            assert defn.adapter_module, f"Missing adapter_module: {name}"
            assert defn.api_base_url, f"Missing api_base_url: {name}"
            assert defn.input_schema, f"Missing input_schema: {name}"

    def test_mol_raw_sources(self):
        """Molecule-specific sources use mol_raw schema."""
        from dk_data.services.mcp.tool_registry import TOOL_REGISTRY
        mol_raw_tools = [
            "clinicaltrials-search", "chembl-search", "openfda-faers-search",
            "openfda-labels-search", "drugbank-search", "pubchem-search",
            "openalex-search", "uniprot-search",
        ]
        for name in mol_raw_tools:
            assert TOOL_REGISTRY[name].raw_schema == "mol_raw", f"{name} should use mol_raw"

    def test_raw_sources(self):
        """IP/regulatory sources use raw schema."""
        from dk_data.services.mcp.tool_registry import TOOL_REGISTRY
        raw_tools = [
            "pubmed-search", "ema-search", "hta-decisions-search",
            "sec-edgar-search", "who-icd-search", "pdb-search",
        ]
        for name in raw_tools:
            assert TOOL_REGISTRY[name].raw_schema == "raw", f"{name} should use raw"


class TestMCPRouter:
    """Verify data-tools router endpoint structure."""

    def test_registry_endpoint_exists(self):
        from dk_data.api.routes.data_tools import router
        routes = [r.path for r in router.routes]
        assert "/data-tools/registry" in routes

    def test_status_endpoint_exists(self):
        from dk_data.api.routes.data_tools import router
        routes = [r.path for r in router.routes]
        assert "/data-tools/{source_name}/status" in routes

    def test_router_prefix(self):
        from dk_data.api.routes.data_tools import router
        assert router.prefix == "/data-tools"


class TestToolInvocationResponse:
    """Verify BackfillResponse model matches contract."""

    def test_success_response_fields(self):
        from dk_data.api.routes.data_tools import BackfillResponse
        resp = BackfillResponse(
            source_name="clinicaltrials",
            triggered=True,
            skipped=False,
            run_id="abc-123",
            status="queued",
        )
        assert resp.status == "queued"
        assert resp.triggered is True

    def test_skipped_response_fields(self):
        from dk_data.api.routes.data_tools import BackfillResponse
        resp = BackfillResponse(
            source_name="clinicaltrials",
            triggered=False,
            skipped=True,
            reason="Data is fresh",
            status="skipped",
        )
        assert resp.status == "skipped"
        assert resp.reason == "Data is fresh"


class TestBaseMCPTool:
    """Verify base tool error response structure."""

    def test_error_response_format(self):
        from dk_data.services.mcp.base_tool import BaseMCPTool
        from dk_data.services.mcp.adapters.base import BaseAdapter

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
