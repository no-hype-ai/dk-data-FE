"""MCP Data Retrieval Tools Router.

Feature: 015-assessment-dashboard-integration
Task: T063

Provides:
- GET /api/v1/mcp/tools — list all registered MCP tools
- POST /api/v1/mcp/tools/{tool_name}/invoke — invoke a specific tool
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from loguru import logger

from ...services.mcp.tool_registry import TOOL_REGISTRY, get_tools_by_tier
from ..dependencies import get_db_pool, get_current_user


router = APIRouter(prefix="/mcp", tags=["mcp"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ToolInfo(BaseModel):
    """Public info about an MCP tool."""
    name: str
    description: str
    tier: str
    input_schema: Dict[str, Any]


class ToolListResponse(BaseModel):
    """Response listing all available MCP tools."""
    tools: List[ToolInfo]
    total: int
    tiers: Dict[str, int]
    timestamp: str


class ToolInvokeRequest(BaseModel):
    """Request to invoke an MCP tool."""
    drug_name: str = Field(..., min_length=1, description="Drug/molecule name to search")
    molecule_id: Optional[str] = Field(None, description="Optional molecule UUID for scoping")


class ToolInvocationResponse(BaseModel):
    """Response from MCP tool invocation."""
    status: str
    request_id: Optional[str] = None
    source: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    raw_record_id: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[Dict[str, Any]] = None
    timestamp: str


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/tools", response_model=ToolListResponse)
async def list_tools(user: dict = Depends(get_current_user)):
    """List all available MCP data retrieval tools. Requires authentication."""
    tools = [
        ToolInfo(
            name=defn.name,
            description=defn.description,
            tier=defn.tier,
            input_schema=defn.input_schema,
        )
        for defn in TOOL_REGISTRY.values()
    ]

    tiers = {
        "direct_query": len(get_tools_by_tier("direct_query")),
        "fetch_filter": len(get_tools_by_tier("fetch_filter")),
        "supplementary": len(get_tools_by_tier("supplementary")),
    }

    return ToolListResponse(
        tools=tools,
        total=len(tools),
        tiers=tiers,
        timestamp=datetime.utcnow().isoformat(),
    )


@router.post("/tools/{tool_name}/invoke", response_model=ToolInvocationResponse)
async def invoke_tool(
    tool_name: str,
    body: ToolInvokeRequest,
    user: dict = Depends(get_current_user),
):
    """Invoke an MCP tool to fetch data from an external source.

    Requires analyst JWT authentication. Rate limited per source.
    """
    # Validate tool exists
    if tool_name not in TOOL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")

    tool_def = TOOL_REGISTRY[tool_name]

    try:
        # Lazy-import the adapter module
        import importlib
        adapter_mod = importlib.import_module(tool_def.adapter_module)
        adapter_cls = getattr(adapter_mod, "Adapter", None)

        if adapter_cls is None:
            raise HTTPException(
                status_code=501,
                detail=f"Adapter not fully implemented for tool: {tool_name}"
            )

        # Instantiate adapter and tool
        from ...services.mcp.base_tool import BaseMCPTool

        adapter = adapter_cls()
        pool = await get_db_pool()
        tool = BaseMCPTool(
            adapter=adapter,
            api_base_url=tool_def.api_base_url,
            db_pool=pool,
        )

        # Invoke
        result = await tool.invoke({
            "drug_name": body.drug_name,
            "molecule_id": body.molecule_id,
        })

        return ToolInvocationResponse(
            status=result.get("status", "error"),
            request_id=result.get("request_id"),
            source=result.get("source"),
            data=result.get("data"),
            raw_record_id=result.get("raw_record_id"),
            duration_ms=result.get("duration_ms"),
            error=result.get("error"),
            timestamp=result.get("timestamp", datetime.utcnow().isoformat()),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MCP tool invocation failed: {tool_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
