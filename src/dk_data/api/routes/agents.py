"""Agent Trigger & Quarantine Router.

Feature: 016-cms-puf-datasource-integration
Tasks: T085, T088

Provides:
- POST /api/v1/agents/{agent_name}/run — trigger agent execution (background)
- GET /api/v1/agents/quarantine — list quarantined records
- POST /api/v1/agents/quarantine/{id}/resolve — resolve a quarantined record
"""

import asyncio
import importlib
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from loguru import logger

from ..dependencies import get_db_connection, get_jwt_user


router = APIRouter(prefix="/agents", tags=["agents"])

# Known agent modules — maps agent_name to importable module path
AGENT_REGISTRY = {
    "service_line_inference": "dk_data.agents.service_line_inference",
    "idn_hierarchy": "dk_data.agents.idn_hierarchy",
    "referral_network": "dk_data.agents.referral_network",
    "contact_verification": "dk_data.agents.contact_verification",
    "staffing_decomposition": "dk_data.agents.staffing_decomposition",
    "equipment_inventory": "dk_data.agents.equipment_inventory",
}


# ── Request/Response Models ──────────────────────────────────────────────────

class AgentRunResponse(BaseModel):
    agent_name: str
    status: str
    message: str
    timestamp: str


class QuarantineRecord(BaseModel):
    id: int
    agent_name: str
    execution_id: str
    record_data: dict[str, Any]
    reason: str
    confidence_score: float
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


class QuarantineListResponse(BaseModel):
    records: list[QuarantineRecord]
    total: int


class ResolveRequest(BaseModel):
    action: str  # "accept" or "reject"
    resolved_by: str = "api_user"


class ResolveResponse(BaseModel):
    id: int
    status: str
    message: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/{agent_name}/run", response_model=AgentRunResponse)
async def trigger_agent(
    agent_name: str,
    user: dict = Depends(get_jwt_user),
):
    """Trigger an agent execution in a background thread.

    The agent is dispatched to a thread pool so the FastAPI event loop
    is not blocked by synchronous DB + LLM calls.
    """
    if agent_name not in AGENT_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent: {agent_name}. Available: {list(AGENT_REGISTRY.keys())}",
        )

    module_path = AGENT_REGISTRY[agent_name]

    try:
        mod = importlib.import_module(module_path)
        agent_cls = None
        # Find the agent class (subclass naming convention: *Agent)
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and hasattr(attr, "run")
                and hasattr(attr, "AGENT_NAME")
                and attr_name != "BaseAgent"
            ):
                agent_cls = attr
                break

        if agent_cls is None:
            raise HTTPException(status_code=501, detail=f"No agent class found in {module_path}")

        agent = agent_cls()
        # Run the synchronous agent.run() in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, agent.run)

        return AgentRunResponse(
            agent_name=agent_name,
            status="completed",
            message=f"Agent {agent_name} executed successfully",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent {agent_name} execution failed: {e}")
        return AgentRunResponse(
            agent_name=agent_name,
            status="failed",
            message=str(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


@router.get("/quarantine", response_model=QuarantineListResponse)
async def list_quarantine(
    agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    status: str = Query("PENDING", description="Filter by status"),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_jwt_user),
    conn=Depends(get_db_connection),
):
    """List quarantined records for review."""
    try:
        query = """
            SELECT id, agent_name, execution_id, record_data, reason,
                   confidence_score, status, created_at, resolved_at, resolved_by
            FROM meta.ops_agent_quarantine
            WHERE status = $1
        """
        params: list[Any] = [status]
        idx = 2

        if agent_name:
            query += f" AND agent_name = ${idx}"
            params.append(agent_name)
            idx += 1

        query += f" ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)

        # Get total count
        count_query = "SELECT COUNT(*) FROM meta.ops_agent_quarantine WHERE status = $1"
        count_params: list[Any] = [status]
        if agent_name:
            count_query += " AND agent_name = $2"
            count_params.append(agent_name)

        total = await conn.fetchval(count_query, *count_params)

        return QuarantineListResponse(
            records=[QuarantineRecord(**dict(row)) for row in rows],
            total=total,
        )

    except Exception as e:
        logger.error(f"Error listing quarantine: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quarantine/{record_id}/resolve", response_model=ResolveResponse)
async def resolve_quarantine(
    record_id: int,
    body: ResolveRequest,
    user: dict = Depends(get_jwt_user),
    conn=Depends(get_db_connection),
):
    """Resolve a quarantined record (accept or reject)."""
    if body.action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'accept' or 'reject'")

    try:
        # Verify record exists and is PENDING
        row = await conn.fetchrow(
            "SELECT id, status FROM meta.ops_agent_quarantine WHERE id = $1",
            record_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail=f"Quarantine record not found: {record_id}")

        if row["status"] != "PENDING":
            raise HTTPException(status_code=400, detail=f"Record already resolved: {row['status']}")

        new_status = "ACCEPTED" if body.action == "accept" else "REJECTED"

        await conn.execute(
            """UPDATE meta.ops_agent_quarantine
            SET status = $1, resolved_at = NOW(), resolved_by = $2
            WHERE id = $3""",
            new_status, body.resolved_by, record_id,
        )

        return ResolveResponse(
            id=record_id,
            status=new_status,
            message=f"Record {record_id} {body.action}ed",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving quarantine {record_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
