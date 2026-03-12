"""Agent Trigger & Quarantine Router.

Feature: 016-cms-puf-datasource-integration
Tasks: T085, T088

Provides:
- POST /api/v1/agents/{agent_name}/run — trigger agent execution
- GET /api/v1/agents/quarantine — list quarantined records
- POST /api/v1/agents/quarantine/{id}/resolve — resolve a quarantined record
"""

import importlib
import os
from datetime import datetime
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from loguru import logger


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


def _get_db_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB", "dk_data"),
    )


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
async def trigger_agent(agent_name: str):
    """Trigger an agent execution. Runs synchronously."""
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
        agent.run()

        return AgentRunResponse(
            agent_name=agent_name,
            status="completed",
            message=f"Agent {agent_name} executed successfully",
            timestamp=datetime.utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent {agent_name} execution failed: {e}")
        return AgentRunResponse(
            agent_name=agent_name,
            status="failed",
            message=str(e),
            timestamp=datetime.utcnow().isoformat(),
        )


@router.get("/quarantine", response_model=QuarantineListResponse)
async def list_quarantine(
    agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    status: str = Query("PENDING", description="Filter by status"),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
):
    """List quarantined records for review."""
    try:
        conn = _get_db_conn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT id, agent_name, execution_id, record_data, reason,
                   confidence_score, status, created_at, resolved_at, resolved_by
            FROM meta.agent_quarantine
            WHERE status = %s
        """
        params: list[Any] = [status]

        if agent_name:
            query += " AND agent_name = %s"
            params.append(agent_name)

        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Get total count
        count_query = "SELECT COUNT(*) FROM meta.agent_quarantine WHERE status = %s"
        count_params: list[Any] = [status]
        if agent_name:
            count_query += " AND agent_name = %s"
            count_params.append(agent_name)

        cursor.execute(count_query, count_params)
        total = cursor.fetchone()["count"]

        cursor.close()
        conn.close()

        return QuarantineListResponse(
            records=[QuarantineRecord(**row) for row in rows],
            total=total,
        )

    except Exception as e:
        logger.error(f"Error listing quarantine: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quarantine/{record_id}/resolve", response_model=ResolveResponse)
async def resolve_quarantine(record_id: int, body: ResolveRequest):
    """Resolve a quarantined record (accept or reject)."""
    if body.action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'accept' or 'reject'")

    try:
        conn = _get_db_conn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Verify record exists and is PENDING
        cursor.execute(
            "SELECT id, status FROM meta.agent_quarantine WHERE id = %s",
            (record_id,),
        )
        row = cursor.fetchone()

        if not row:
            cursor.close()
            conn.close()
            raise HTTPException(status_code=404, detail=f"Quarantine record not found: {record_id}")

        if row["status"] != "PENDING":
            cursor.close()
            conn.close()
            raise HTTPException(status_code=400, detail=f"Record already resolved: {row['status']}")

        new_status = "ACCEPTED" if body.action == "accept" else "REJECTED"

        cursor.execute(
            """UPDATE meta.agent_quarantine
            SET status = %s, resolved_at = NOW(), resolved_by = %s
            WHERE id = %s""",
            (new_status, body.resolved_by, record_id),
        )
        conn.commit()
        cursor.close()
        conn.close()

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
