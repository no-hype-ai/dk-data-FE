"""FastAPI router for MCP data-tool endpoints.

Mounts at: /api/v1/data-tools
Endpoint:  POST /api/v1/data-tools/{tool}/invoke

Dispatch order (registry-driven, DB-first):
  1. If a ToolDefinition exists with a built Adapter and a live db_pool,
     call adapter.db_query() first:
       - returns dict  → serve from DB (no HTTP call).
       - returns None  → fall through to HTTP.
       - raises        → return 502 {"stage": "db_query"} (not a miss).
  2. HTTP fallthrough via the BaseMCPTool.invoke() path.
  3. Neither available → 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from . import tool_registry as _tr
from .dispatch import dispatch_invoke

from .adapters import (
    CmsPartDSpendingTool,
    CochraneTool,
    EmaTool,
    FdaDrugsTool,
    HtaDecisionsTool,
    OpenFDALabelsTool,
    OrcidTool,
    PdbStructuresTool,
    TtdTool,
)

router = APIRouter(prefix="/data-tools", tags=["data-tools"])

# HTTP-first registry: slug → BaseMCPTool instance (9 built adapters)
TOOL_REGISTRY = {
    "fda-drugs-search": FdaDrugsTool(),
    "pdb-search": PdbStructuresTool(),
    "orcid-search": OrcidTool(),
    "cms-part-d-spending": CmsPartDSpendingTool(),
    "hta-decisions-search": HtaDecisionsTool(),
    "ema-search": EmaTool(),
    "cochrane-search": CochraneTool(),
    "ttd-search": TtdTool(),
    "openfda-labels-search": OpenFDALabelsTool(),
}


class InvokeRequest(BaseModel):
    drug_name: str


class InvokeResponse(BaseModel):
    tool: str
    data: object | None = None
    error: str | None = None
    status_code: int | None = None


@router.get("/")
async def list_tools() -> dict:
    """List all registered data-tool adapters."""
    return {"tools": list(TOOL_REGISTRY.keys()), "count": len(TOOL_REGISTRY)}


@router.post("/{tool}/invoke", response_model=InvokeResponse)
async def invoke_tool(tool: str, body: InvokeRequest, request: Request) -> InvokeResponse:
    """Invoke a named data-tool adapter with a drug name.

    DB-first: attempts warehouse lookup via BaseAdapter.db_query() before
    making any outbound HTTP call. A DB error surfaces as 502 — it is NOT
    silently treated as a cache miss.
    """
    db_pool = getattr(request.app.state, "db_pool", None)

    result = await dispatch_invoke(
        slug=tool,
        drug_name=body.drug_name,
        db_pool=db_pool,
        http_tool_registry=TOOL_REGISTRY,
        tool_definition_registry=_tr.TOOL_REGISTRY,
    )

    return InvokeResponse(
        tool=result["tool"],
        data=result.get("data"),
        error=result.get("error"),
        status_code=result.get("status_code"),
    )
