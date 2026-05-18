"""FastAPI router for MCP data-tool endpoints.

Mounts at: /api/v1/mcp-tools
Endpoint:  POST /api/v1/mcp-tools/{tool}/invoke

Prefix is /mcp-tools (not /data-tools) to avoid shadowing the ingestion
data-tools gateway router (routes/data_tools.py) which also uses /data-tools.
Both routers previously shared the same prefix, causing POST /{tool}/invoke
to be silently shadowed by data_tools since it registers first.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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

router = APIRouter(prefix="/mcp-tools", tags=["mcp-data-tools"])

# Registry maps URL slug → adapter instance
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
async def invoke_tool(tool: str, request: InvokeRequest) -> InvokeResponse:
    """Invoke a named data-tool adapter with a drug name.

    Returns normalised data from the upstream API, or a structured error
    for tools that are bulk-only or require credentials.
    """
    if tool not in TOOL_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Tool '{tool}' not found.",
                "available_tools": list(TOOL_REGISTRY.keys()),
            },
        )

    adapter = TOOL_REGISTRY[tool]
    try:
        result = await adapter.invoke(request.drug_name)
        return InvokeResponse(
            tool=tool,
            data=result.get("data"),
            error=result.get("error"),
            status_code=result.get("status_code"),
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": f"Upstream API returned {exc.response.status_code}",
                "tool": tool,
            },
        ) from exc
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail={"error": "Upstream API timed out", "tool": tool},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"error": str(exc), "tool": tool},
        ) from exc
