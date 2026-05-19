"""Tests for MCP data-tool adapters (issue #188).

Uses importlib to load MCP modules directly, bypassing the heavy
dk_data.services __init__ chain (which requires aiohttp, psycopg2, redis, etc.).
"""

import sys
import types
import importlib.util
from pathlib import Path

import json
from urllib.parse import unquote, urlparse, parse_qs

import httpx
import respx

# ---------------------------------------------------------------------------
# Direct module loader — imports MCP source files without triggering
# dk_data.services.__init__ (which pulls in the full service stack)
# ---------------------------------------------------------------------------
_SRC = Path(__file__).parent.parent / "src"

def _ensure_pkg(dotted: str):
    """Register empty package module stubs for every ancestor of dotted."""
    parts = dotted.split(".")
    for i in range(1, len(parts)):
        pkg = ".".join(parts[:i])
        if pkg not in sys.modules:
            m = types.ModuleType(pkg)
            m.__path__ = [str(_SRC / Path(*parts[:i]))]
            m.__package__ = pkg
            sys.modules[pkg] = m


def _load(dotted: str):
    """Load a dotted module path directly from src/ without package init chain."""
    _ensure_pkg(dotted)
    parts = dotted.split(".")
    path = _SRC / Path(*parts).with_suffix(".py")
    spec = importlib.util.spec_from_file_location(
        dotted, path,
        submodule_search_locations=[str(path.parent)],
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = ".".join(parts[:-1])
    sys.modules[dotted] = mod
    spec.loader.exec_module(mod)
    return mod

# ---------------------------------------------------------------------------
# Snapshot/restore guard (issue #415, WS3).
#
# The _load() mechanism RELIES on sys.modules being populated *during*
# exec_module so that relative imports inside the loaded files resolve
# (`from ..base_tool import BaseMCPTool`, `from .base import BaseAdapter`).
# But if those file-loaded copies and the _ensure_pkg() empty stubs are left
# in sys.modules after this file is collected, they shadow the canonical
# dk_data.services.mcp.* modules for every test file collected *afterwards*
# (the ~26 WS3 test_adapter_*.py files), producing a class-identity
# split-brain — exactly what made #421's CI red.
#
# So: snapshot the dk_data namespace, perform ALL loads (restore must NOT
# happen between _load() calls — later loads depend on earlier ones being in
# sys.modules), then restore the dk_data namespace to its pre-load state:
# keys absent before are removed; keys present before are reset to their
# original objects. This file keeps its own direct references (_fda,
# FdaDrugsTool, the local TOOL_REGISTRY, ...) so its own tests still pass;
# canonical sys.modules is left pristine for later-collected files.
# ---------------------------------------------------------------------------

def _dk_data_key(name: str) -> bool:
    return name == "dk_data" or name.startswith("dk_data")


# Snapshot ONLY the dk_data namespace (do not disturb pytest/respx/etc.).
_DK_SNAPSHOT = {
    name: mod for name, mod in sys.modules.items() if _dk_data_key(name)
}

try:
    # Load in dependency order (sys.modules must stay populated throughout).
    _base = _load("dk_data.services.mcp.base_tool")
    _fda = _load("dk_data.services.mcp.adapters.fda_drugs")
    _pdb = _load("dk_data.services.mcp.adapters.pdb_structures")
    _orcid = _load("dk_data.services.mcp.adapters.orcid")
    _cms = _load("dk_data.services.mcp.adapters.cms_part_d_spending")
    _hta = _load("dk_data.services.mcp.adapters.hta_decisions")
    _ema = _load("dk_data.services.mcp.adapters.ema")
    _cochrane = _load("dk_data.services.mcp.adapters.cochrane")
    _ttd = _load("dk_data.services.mcp.adapters.ttd")
finally:
    # Restore the dk_data namespace to its pre-load state.
    for _name in [n for n in sys.modules if _dk_data_key(n)]:
        if _name not in _DK_SNAPSHOT:
            del sys.modules[_name]
    for _name, _orig in _DK_SNAPSHOT.items():
        sys.modules[_name] = _orig

FdaDrugsTool = _fda.FdaDrugsTool
PdbStructuresTool = _pdb.PdbStructuresTool
OrcidTool = _orcid.OrcidTool
CmsPartDSpendingTool = _cms.CmsPartDSpendingTool
HtaDecisionsTool = _hta.HtaDecisionsTool
EmaTool = _ema.EmaTool
CochraneTool = _cochrane.CochraneTool
TtdTool = _ttd.TtdTool

TOOL_REGISTRY = {
    "fda-drugs-search": FdaDrugsTool(),
    "pdb-search": PdbStructuresTool(),
    "orcid-search": OrcidTool(),
    "cms-part-d-spending": CmsPartDSpendingTool(),
    "hta-decisions-search": HtaDecisionsTool(),
    "ema-search": EmaTool(),
    "cochrane-search": CochraneTool(),
    "ttd-search": TtdTool(),
}


DRUG = "imatinib"


# ---------------------------------------------------------------------------
# URL generation tests (no network)
# ---------------------------------------------------------------------------

class TestFdaDrugsUrl:
    def test_uses_search_param(self):
        url = FdaDrugsTool().build_url(DRUG)
        assert "search=" in url
        assert "query=" not in url

    def test_includes_drug_name(self):
        url = FdaDrugsTool().build_url(DRUG)
        assert DRUG in unquote(url)

    def test_includes_limit(self):
        url = FdaDrugsTool().build_url(DRUG)
        assert "limit=100" in url


class TestPdbStructuresUrl:
    def test_uses_json_param(self):
        url = PdbStructuresTool().build_url(DRUG)
        assert "json=" in url

    def test_json_is_valid(self):
        url = PdbStructuresTool().build_url(DRUG)
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        payload = json.loads(qs["json"][0])
        assert payload["query"]["parameters"]["value"] == DRUG
        assert payload["return_type"] == "entry"


class TestOrcidUrl:
    def test_uses_q_param(self):
        url = OrcidTool().build_url(DRUG)
        assert "?q=" in url
        assert "query=" not in url

    def test_includes_drug_name(self):
        url = OrcidTool().build_url(DRUG)
        assert DRUG in unquote(url)

    def test_accept_header(self):
        headers = OrcidTool().build_headers()
        assert headers.get("Accept") == "application/json"


class TestCmsPartDUrl:
    def test_uses_data_api_endpoint(self):
        url = CmsPartDSpendingTool().build_url(DRUG)
        assert "data-api/v1/dataset" in url
        assert "data.cms.gov" in url

    def test_includes_brand_name_filter(self):
        url = CmsPartDSpendingTool().build_url(DRUG)
        assert "Brnd_Name" in url
        assert DRUG in unquote(url)


class TestHtaDecisionsUrl:
    def test_uses_nice_api(self):
        url = HtaDecisionsTool().build_url(DRUG)
        assert "api.nice.org.uk" in url
        assert "?q=" in url

    def test_does_not_use_nice_website(self):
        url = HtaDecisionsTool().build_url(DRUG)
        assert "www.nice.org.uk" not in url


# ---------------------------------------------------------------------------
# Bulk-only / no-credentials adapters — synchronous error, no HTTP call
# Run with asyncio.run() to avoid pytest-asyncio dependency
# ---------------------------------------------------------------------------

def test_ema_returns_error_without_http_call():
    import asyncio
    result = asyncio.run(EmaTool().invoke(DRUG))
    assert result["tool"] == "ema-search"
    assert result["error"] is not None
    assert result["data"] is None
    assert result["status_code"] is None
    assert "no free public JSON API" in result["error"]


def test_cochrane_returns_error_without_http_call():
    import asyncio
    result = asyncio.run(CochraneTool().invoke(DRUG))
    assert result["tool"] == "cochrane-search"
    assert result["error"] is not None
    assert result["data"] is None
    assert "Wiley API key" in result["error"]


def test_ttd_returns_error_without_http_call():
    import asyncio
    result = asyncio.run(TtdTool().invoke(DRUG))
    assert result["tool"] == "ttd-search"
    assert result["error"] is not None
    assert result["data"] is None
    assert "bulk-only" in result["error"]


# ---------------------------------------------------------------------------
# base_tool: non-JSON content-type handling (B3 fix)
# ---------------------------------------------------------------------------

def test_base_tool_handles_html_response():
    """base_tool.invoke() should return a structured error for HTML responses."""
    import asyncio

    tool = FdaDrugsTool()
    url = tool.build_url(DRUG)

    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                content=b"<html>Not JSON</html>",
                headers={"content-type": "text/html; charset=utf-8"},
            )
        )
        result = asyncio.run(tool.invoke(DRUG))

    assert result.get("error") is not None
    assert "Non-JSON" in result["error"]["message"]
    assert result["data"] is None


def test_base_tool_parses_json_response():
    """base_tool.invoke() should parse JSON responses correctly."""
    import asyncio

    tool = FdaDrugsTool()
    url = tool.build_url(DRUG)

    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                json={"results": [{"drug_name": DRUG}]},
                headers={"content-type": "application/json"},
            )
        )
        result = asyncio.run(tool.invoke(DRUG))

    assert result.get("error") is None
    assert result["data"] == {"results": [{"drug_name": DRUG}]}
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Router registry
# ---------------------------------------------------------------------------

def test_tool_registry_contains_all_tools():
    expected = {
        "fda-drugs-search",
        "pdb-search",
        "orcid-search",
        "cms-part-d-spending",
        "hta-decisions-search",
        "ema-search",
        "cochrane-search",
        "ttd-search",
    }
    assert set(TOOL_REGISTRY.keys()) == expected


def test_tool_registry_has_eight_tools():
    assert len(TOOL_REGISTRY) == 8
