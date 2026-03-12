"""Data Tools Gateway — backfill service for PostgREST cold-start.

Reads go directly to PostgREST (the agent's primary API). This gateway
only handles what PostgREST can't: on-demand external fetch, raw insert,
and transform triggering when PostgREST views are empty.

Agent workflow:
  1. Agent → PostgREST (read gold view)    ← fast, JWT-authed, cached
  2. Empty? → Agent → gateway /backfill    ← rate-limited external fetch
  3. Agent → PostgREST again               ← now has fresh data

Endpoints:
  GET  /data-tools                       — List all tools + PostgREST view mappings
  POST /data-tools/{source}/backfill     — Trigger external fetch + transform
  GET  /data-tools/{source}/meta         — Freshness info via PostgREST
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from loguru import logger

from ...services.data_tools.tool_registry import (
    TOOL_REGISTRY,
    get_tools_by_category,
)
from ...services.data_tools.postgrest_client import PostgRESTClient
from ..dependencies import get_db_pool, get_jwt_user


router = APIRouter(prefix="/data-tools", tags=["data-tools"])


# ============================================================================
# Request/Response Models
# ============================================================================

class DataToolInfo(BaseModel):
    """Public info about a data tool, including its PostgREST view."""
    name: str
    description: str
    category: str
    supported_query_keys: List[str]
    external_api_available: bool
    tier: str
    postgrest_view: Optional[str] = None  # e.g. "gold.cms_provider_360"
    postgrest_key: Optional[str] = None   # e.g. "npi"


class DataToolListResponse(BaseModel):
    """Response listing all available data tools."""
    tools: List[DataToolInfo]
    total: int
    categories: Dict[str, int]
    postgrest_base_url: str
    timestamp: str


class BackfillRequest(BaseModel):
    """Request to trigger an external fetch + backfill for a source."""
    drug_name: Optional[str] = Field(None, description="Drug/molecule name")
    npi: Optional[str] = Field(None, description="National Provider Identifier")
    ccn: Optional[str] = Field(None, description="CMS Certification Number")
    ndc: Optional[str] = Field(None, description="National Drug Code")
    state: Optional[str] = Field(None, description="Two-letter state code")
    county: Optional[str] = Field(None, description="County name")
    hcpcs_code: Optional[str] = Field(None, description="HCPCS procedure code")
    molecule_id: Optional[str] = Field(None, description="Internal molecule UUID")
    filters: Optional[Dict[str, str]] = Field(None, description="Source-specific extra filters")
    limit: int = Field(100, ge=1, le=1000, description="Max records for external fetch")


class BackfillResponse(BaseModel):
    """Response from a backfill trigger."""
    status: str                            # "backfilled", "not_available", "error"
    request_id: str
    source: str
    record_count: int = 0
    raw_record_id: Optional[str] = None
    external_api_available: bool = True
    duration_ms: Optional[int] = None
    postgrest_view: Optional[str] = None   # where to re-query after backfill
    postgrest_key: Optional[str] = None
    transform_status: Optional[str] = None  # "completed", "partial", "failed", "pending"
    transform_error: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    timestamp: str


class DataToolMetaResponse(BaseModel):
    """Freshness and metadata for a data source."""
    source: str
    category: str
    external_api_available: bool
    supported_query_keys: List[str]
    postgrest_view: Optional[str] = None
    postgrest_key: Optional[str] = None
    gold: Optional[Dict[str, Any]] = None
    silver: Optional[Dict[str, Any]] = None
    timestamp: str


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=DataToolListResponse)
async def list_data_tools(
    user: dict = Depends(get_jwt_user),
):
    """List all tools with their PostgREST view mappings.

    Agents use this to discover which PostgREST view to query for each
    source, and which key column to filter on.
    """
    from ...services.data_tools.postgrest_client import _postgrest_base_url

    tools = []
    for defn in TOOL_REGISTRY.values():
        lc = defn.local_check
        tools.append(DataToolInfo(
            name=defn.name,
            description=defn.description,
            category=defn.category,
            supported_query_keys=defn.supported_query_keys,
            external_api_available=defn.external_api_available,
            tier=defn.tier,
            postgrest_view=f"{lc.gold_schema}.{lc.gold_table}" if lc else None,
            postgrest_key=lc.gold_key_column if lc else None,
        ))

    categories = {
        cat: len(get_tools_by_category(cat))
        for cat in ("molecule", "cms_queryable", "cms_bulk_only")
    }

    return DataToolListResponse(
        tools=tools,
        total=len(tools),
        categories=categories,
        postgrest_base_url=_postgrest_base_url(),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/{source}/backfill", response_model=BackfillResponse)
async def backfill_source(
    source: str,
    body: BackfillRequest,
    user: dict = Depends(get_jwt_user),
):
    """Trigger an external fetch + transform for a source.

    Call this ONLY when PostgREST returned empty. This endpoint:
    1. Rate-limits the external API call
    2. Fetches from the external API via the source adapter
    3. Inserts into the raw table
    4. Triggers the transform pipeline (raw → bronze → silver → gold)
    5. Returns status so the agent can re-query PostgREST

    For bulk-only sources, returns 409 (no external API available).
    """
    if source not in TOOL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown data tool: {source}")

    import time
    import uuid

    tool_def = TOOL_REGISTRY[source]
    start_time = time.monotonic()
    request_id = str(uuid.uuid4())
    lc = tool_def.local_check

    from ...observability.metrics import record_cms_backfill_request

    # Bulk-only sources cannot be backfilled
    if not tool_def.external_api_available:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        record_cms_backfill_request(tool_def.name, "not_available")
        return BackfillResponse(
            status="not_available",
            request_id=request_id,
            source=tool_def.name,
            external_api_available=False,
            duration_ms=duration_ms,
            postgrest_view=f"{lc.gold_schema}.{lc.gold_table}" if lc else None,
            postgrest_key=lc.gold_key_column if lc else None,
            message="Bulk-loaded source. Data available after next scheduled ingestion.",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    try:
        # Extract query keys
        provided_keys = _extract_query_keys(tool_def.supported_query_keys, body)
        if not provided_keys:
            raise HTTPException(
                status_code=400,
                detail=f"No supported query keys provided. Accepts: {tool_def.supported_query_keys}",
            )

        # External fetch + raw insert + transform
        pool = await get_db_pool()
        from ...services.data_tools.base_tool import BaseDataTool
        tool = BaseDataTool(tool_def=tool_def, db_pool=pool)

        params = body.model_dump(exclude_none=True)
        result = await tool._invoke_external(request_id, params, provided_keys)

        duration_ms = int((time.monotonic() - start_time) * 1000)

        if result.get("status") == "success":
            transform_status = result.get("transform_status", "skipped")
            transform_error = result.get("transform_error")

            if transform_status == "completed":
                message = "Data fetched and transform completed. Re-query PostgREST for results."
            elif transform_status == "pending":
                message = "Data fetched and stored in raw. Gold views update on next scheduled refresh."
            elif transform_status == "partial":
                message = "Data fetched. Bronze transform succeeded but silver/gold refresh had errors."
            else:
                message = "Data fetched and stored in raw. Transform may require manual refresh."

            record_cms_backfill_request(tool_def.name, "backfilled")
            return BackfillResponse(
                status="backfilled",
                request_id=request_id,
                source=tool_def.name,
                record_count=result.get("record_count", 0),
                raw_record_id=result.get("raw_record_id"),
                external_api_available=True,
                duration_ms=duration_ms,
                postgrest_view=f"{lc.gold_schema}.{lc.gold_table}" if lc else None,
                postgrest_key=lc.gold_key_column if lc else None,
                transform_status=transform_status,
                transform_error=transform_error,
                message=message,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # External fetch failed
        record_cms_backfill_request(tool_def.name, "error")
        return BackfillResponse(
            status="error",
            request_id=request_id,
            source=tool_def.name,
            external_api_available=True,
            duration_ms=duration_ms,
            error=result.get("error"),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backfill failed for {source}: {e}")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        record_cms_backfill_request(source, "error")
        return BackfillResponse(
            status="error",
            request_id=request_id,
            source=source,
            error={"code": "internal_error", "message": str(e), "status_code": 500},
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


@router.get("/{source}/meta", response_model=DataToolMetaResponse)
async def get_data_tool_meta(
    source: str,
    user: dict = Depends(get_jwt_user),
):
    """Get freshness info and metadata for a data source via PostgREST."""
    if source not in TOOL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown data tool: {source}")

    tool_def = TOOL_REGISTRY[source]
    pgrst = PostgRESTClient(jwt_token=user.get("raw_token"))
    lc = tool_def.local_check

    gold_info = None
    silver_info = None

    if lc:
        gold_info = await pgrst.get_freshness(lc.gold_schema, lc.gold_table)
        if lc.silver_schema and lc.silver_table:
            silver_info = await pgrst.get_freshness(lc.silver_schema, lc.silver_table)

    return DataToolMetaResponse(
        source=tool_def.name,
        category=tool_def.category,
        external_api_available=tool_def.external_api_available,
        supported_query_keys=tool_def.supported_query_keys,
        postgrest_view=f"{lc.gold_schema}.{lc.gold_table}" if lc else None,
        postgrest_key=lc.gold_key_column if lc else None,
        gold=gold_info,
        silver=silver_info,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ============================================================================
# Helpers
# ============================================================================

def _extract_query_keys(supported_keys: List[str], body: BackfillRequest) -> Dict[str, str]:
    """Extract provided query keys that match the tool's supported keys."""
    result = {}
    params = body.model_dump(exclude_none=True)
    for key in supported_keys:
        value = params.get(key)
        if value:
            result[key] = str(value)
    return result
