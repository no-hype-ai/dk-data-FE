"""Data Tools Gateway Router.

Feature: 019-cms-puf-platform-reconciliation
Task: T047

Provides:
- GET  /api/v1/data-tools/registry          — list all registered tools with freshness metadata
- POST /api/v1/data-tools/backfill          — trigger a source refresh (with freshness check)
- GET  /api/v1/data-tools/{source_name}/status — freshness status for a single source

Caching:
- GET /registry: Redis TTL=60s
- GET /{source_name}/status: per-source TTL (3600s CMS bulk, 300s API)

Freshness check: uses DataFreshnessMonitor.is_fresh() which reads meta.data_sources.
Only sources tracked in meta.data_sources are available via this endpoint.
Sources tracked only in meta.ingestion_jobs return 404.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies import get_db_pool
from ...services.mcp.tool_registry import TOOL_REGISTRY
from ...observability.metrics import record_cms_backfill, _is_cms_source

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/data-tools", tags=["data-tools"])

# Default freshness thresholds (hours) by source type
FRESHNESS_THRESHOLDS: Dict[str, int] = {
    "cms_bulk_file": 720,       # 30 days
    "api_incremental": 24,      # 24 hours
    "api_static": 168,          # 7 days
}

# Redis TTLs (seconds)
REGISTRY_CACHE_TTL = 60
STATUS_CACHE_TTL_BULK = 3600
STATUS_CACHE_TTL_API = 300


# ============================================================================
# Helper: lazy Redis client
# ============================================================================

def _get_redis_client():
    """Get Redis client. Returns None if Redis unavailable."""
    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://redis.infra.svc.cluster.local:6379/0")
        return redis.from_url(redis_url, decode_responses=True, socket_timeout=1)
    except Exception:
        return None


# ============================================================================
# Request / Response Models
# ============================================================================

class ToolRegistryEntry(BaseModel):
    name: str
    description: str
    tier: str
    raw_table: str
    raw_schema: str
    source_name: str  # Corresponding meta.data_sources key
    last_refresh: Optional[str] = None
    last_refresh_status: Optional[str] = None


class RegistryResponse(BaseModel):
    tools: List[ToolRegistryEntry]
    total: int
    cached: bool
    generated_at: str


class BackfillRequest(BaseModel):
    source_name: str
    force: bool = False  # If True, skip freshness check and always trigger


class BackfillResponse(BaseModel):
    source_name: str
    triggered: bool
    skipped: bool
    reason: Optional[str] = None
    run_id: Optional[str] = None
    status: str  # "queued" | "skipped" | "error"


class SourceStatusResponse(BaseModel):
    source_name: str
    is_fresh: bool
    last_successful_refresh: Optional[str]
    last_refresh_status: Optional[str]
    max_age_hours: int
    cached: bool


# ============================================================================
# Helper: convert TOOL_REGISTRY name → meta.data_sources source_name
# ============================================================================

def _tool_name_to_source_name(tool_name: str) -> str:
    """Convert hyphenated tool name to underscore source_name (SOURCES dict key)."""
    return tool_name.replace("-", "_")


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/registry", response_model=RegistryResponse)
async def get_registry(db_pool=Depends(get_db_pool)) -> RegistryResponse:
    """
    List all registered tools with freshness metadata.

    Response is cached in Redis for 60 seconds to prevent unbounded DB queries.
    """
    cache_key = "data_tools:registry"
    redis_client = _get_redis_client()

    # Check cache
    if redis_client is not None:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                data["cached"] = True
                return RegistryResponse(**data)
        except Exception as e:
            logger.warning("redis_cache_miss", error=str(e))

    # Build registry from TOOL_REGISTRY
    tools = []
    source_names = [_tool_name_to_source_name(name) for name in TOOL_REGISTRY.keys()]

    # Fetch last_refresh for all sources in one query
    freshness_map: Dict[str, Dict[str, Any]] = {}
    if db_pool is not None:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT source_name, last_successful_refresh, last_refresh_status
                    FROM meta.data_sources
                    WHERE source_name = ANY($1::text[])
                    """,
                    source_names,
                )
                for row in rows:
                    freshness_map[row["source_name"]] = {
                        "last_refresh": row["last_successful_refresh"].isoformat() if row["last_successful_refresh"] else None,
                        "last_refresh_status": row["last_refresh_status"],
                    }
        except Exception as e:
            logger.warning("registry_freshness_fetch_failed", error=str(e))

    for tool_name, tool_def in TOOL_REGISTRY.items():
        source_name = _tool_name_to_source_name(tool_name)
        freshness = freshness_map.get(source_name, {})
        tools.append(ToolRegistryEntry(
            name=tool_def.name,
            description=tool_def.description,
            tier=tool_def.tier,
            raw_table=tool_def.raw_table,
            raw_schema=tool_def.raw_schema,
            source_name=source_name,
            last_refresh=freshness.get("last_refresh"),
            last_refresh_status=freshness.get("last_refresh_status"),
        ))

    response_data = {
        "tools": [t.model_dump() for t in tools],
        "total": len(tools),
        "cached": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Store in cache
    if redis_client is not None:
        try:
            redis_client.setex(cache_key, REGISTRY_CACHE_TTL, json.dumps(response_data))
        except Exception as e:
            logger.warning("redis_cache_write_failed", error=str(e))

    return RegistryResponse(**response_data)


@router.post("/backfill", response_model=BackfillResponse)
async def trigger_backfill(
    request: BackfillRequest,
    background_tasks: BackgroundTasks,
    db_pool=Depends(get_db_pool),
) -> BackfillResponse:
    """
    Trigger a source refresh.

    If force=False (default), checks freshness first and skips if data is recent.
    If force=True, triggers unconditionally.

    Returns 202 Accepted if fetch is queued; 200 with skipped=True if data is fresh.
    Only sources tracked in meta.data_sources are available.
    Returns 404 if source_name not in meta.data_sources.
    Returns 409 if a backfill is already running for this source.
    """
    source_name = request.source_name

    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Verify source exists in meta.data_sources
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT source_id, source_type, last_refresh_status FROM meta.data_sources WHERE source_name = $1 AND is_active = TRUE",
            source_name,
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source '{source_name}' not found in meta.data_sources. "
                   "Sources tracked only in meta.ingestion_jobs are not available via this endpoint."
        )

    # Check for in-progress backfill (409 Conflict)
    lock_key = f"data_tools:backfill_lock:{source_name}"
    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            if redis_client.exists(lock_key):
                raise HTTPException(
                    status_code=409,
                    detail=f"Backfill for '{source_name}' is already running."
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Redis unavailable — proceed without lock

    # Check freshness unless force=True
    if not request.force:
        source_type = row["source_type"] or "cms_bulk_file"
        max_age_hours = FRESHNESS_THRESHOLDS.get(source_type, 720)

        from ...services.data_platform.data_freshness_monitor import DataFreshnessMonitor
        monitor = DataFreshnessMonitor(db_pool=db_pool)
        fresh = await monitor.is_fresh(source_name, max_age_hours=max_age_hours)

        if fresh:
            return BackfillResponse(
                source_name=source_name,
                triggered=False,
                skipped=True,
                reason=f"Data is fresh (within {max_age_hours}h threshold)",
                status="skipped",
            )

    # Acquire lock and queue backfill
    import uuid
    run_id = str(uuid.uuid4())

    if redis_client is not None:
        try:
            redis_client.setex(lock_key, 3600, run_id)  # Auto-expire after 1h
        except Exception:
            pass

    background_tasks.add_task(_backfill_source, source_name, run_id, db_pool)

    if _is_cms_source(source_name):
        record_cms_backfill(source_name, "queued")
    logger.info("backfill_queued", source_name=source_name, run_id=run_id)

    return BackfillResponse(
        source_name=source_name,
        triggered=True,
        skipped=False,
        run_id=run_id,
        status="queued",
    )


async def _backfill_source(source_name: str, run_id: str, db_pool) -> None:
    """Background task: invoke run_ingestion for source_name."""
    try:
        from ...ingestion.main import run_ingestion
        result = run_ingestion(source_name)
        outcome = result.get("status", "unknown")
        logger.info(
            "backfill_completed",
            source_name=source_name,
            run_id=run_id,
            status=outcome,
        )
        if _is_cms_source(source_name):
            record_cms_backfill(source_name, outcome if outcome in ("success", "skipped") else "error")
    except Exception as e:
        logger.error("backfill_failed", source_name=source_name, run_id=run_id, error=str(e))
        if _is_cms_source(source_name):
            record_cms_backfill(source_name, "error")
    finally:
        # Release lock
        redis_client = _get_redis_client()
        if redis_client is not None:
            try:
                redis_client.delete(f"data_tools:backfill_lock:{source_name}")
            except Exception:
                pass


@router.get("/{source_name}/status", response_model=SourceStatusResponse)
async def get_source_status(
    source_name: str,
    db_pool=Depends(get_db_pool),
) -> SourceStatusResponse:
    """
    Get freshness status for a single source.

    Response is cached per source_name:
    - CMS bulk sources: TTL=3600s
    - API sources: TTL=300s
    """
    cache_key = f"data_tools:status:{source_name}"
    redis_client = _get_redis_client()

    if redis_client is not None:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                data["cached"] = True
                return SourceStatusResponse(**data)
        except Exception:
            pass

    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT source_name, source_type, last_successful_refresh, last_refresh_status
            FROM meta.data_sources
            WHERE source_name = $1 AND is_active = TRUE
            """,
            source_name,
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source '{source_name}' not found in meta.data_sources."
        )

    source_type = row["source_type"] or "cms_bulk_file"
    max_age_hours = FRESHNESS_THRESHOLDS.get(source_type, 720)

    from ...services.data_platform.data_freshness_monitor import DataFreshnessMonitor
    monitor = DataFreshnessMonitor(db_pool=db_pool)
    fresh = await monitor.is_fresh(source_name, max_age_hours=max_age_hours)

    last_refresh = row["last_successful_refresh"]
    response_data = {
        "source_name": source_name,
        "is_fresh": fresh,
        "last_successful_refresh": last_refresh.isoformat() if last_refresh else None,
        "last_refresh_status": row["last_refresh_status"],
        "max_age_hours": max_age_hours,
        "cached": False,
    }

    # Cache with source-type TTL
    ttl = STATUS_CACHE_TTL_API if source_type == "api_incremental" else STATUS_CACHE_TTL_BULK
    if redis_client is not None:
        try:
            redis_client.setex(cache_key, ttl, json.dumps(response_data))
        except Exception:
            pass

    return SourceStatusResponse(**response_data)
