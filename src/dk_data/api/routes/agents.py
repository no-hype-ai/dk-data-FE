"""Agents API Router.

Feature: 019-cms-puf-platform-reconciliation
Task: T040

Provides:
- GET  /api/v1/agents                       — list all 7 agents with metadata
- POST /api/v1/agents/{agent_id}/run        — trigger agent run (202 Accepted, async)
- GET  /api/v1/agents/{agent_id}/runs       — list run history for an agent
- GET  /api/v1/agents/quarantine            — paginated quarantine records

Async execution: POST /run spawns a K8s Job via BackgroundTasks.
Returns 202 immediately; client polls GET /runs for completion using run_id.
Run history is read from meta.refresh_log.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from ..dependencies import get_db_pool

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

# Registry of all agents this feature provides.
# Each entry maps agent_id → metadata used by GET /agents.
AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "service_line_inference": {
        "agent_id": "service_line_inference",
        "display_name": "Service Line Inference",
        "description": "Infers clinical service lines per NPI from inpatient DRG mix",
        "module": "dk_data.agents.service_line_inference",
        "silver_table": "hcs_agents.service_lines",
        "default_limit": 50,
    },
    "idn_hierarchy": {
        "agent_id": "idn_hierarchy",
        "display_name": "IDN Hierarchy",
        "description": "Infers Integrated Delivery Network parent-child relationships from NPPES",
        "module": "dk_data.agents.idn_hierarchy",
        "silver_table": "hcs_agents.idn_hierarchy",
        "default_limit": 50,
    },
    "referral_network": {
        "agent_id": "referral_network",
        "display_name": "Referral Network",
        "description": "Maps physician referral patterns from CMS referring/ordering providers",
        "module": "dk_data.agents.referral_network",
        "silver_table": "hcs_agents.referral_network",
        "default_limit": 50,
    },
    "contact_verification": {
        "agent_id": "contact_verification",
        "display_name": "Contact Verification",
        "description": "Validates NPI contact information from NPPES",
        "module": "dk_data.agents.contact_verification",
        "silver_table": "hcs_agents.verified_contacts",
        "default_limit": 50,
    },
    "staffing_decomposition": {
        "agent_id": "staffing_decomposition",
        "display_name": "Staffing Decomposition",
        "description": "Decomposes cost report staffing data into clinical role categories",
        "module": "dk_data.agents.staffing_decomposition",
        "silver_table": "hcs_agents.staffing_decomposition",
        "default_limit": 50,
    },
    "equipment_inventory": {
        "agent_id": "equipment_inventory",
        "display_name": "Equipment Inventory",
        "description": "Infers medical equipment inventory from physician HCPCS procedure codes",
        "module": "dk_data.agents.equipment_inventory",
        "silver_table": "hcs_agents.equipment_inventory",
        "default_limit": 50,
    },
    "publication_evidence_extractor": {
        "agent_id": "publication_evidence_extractor",
        "display_name": "Publication Evidence Extractor",
        "description": "Extracts clinical trial endpoints from publication abstracts via LLM",
        "module": "dk_data.agents.publication_evidence_extractor",
        "silver_table": "mol_agents.publication_evidence_staging",
        "default_limit": 50,
    },
}


# ============================================================================
# Request / Response Models
# ============================================================================

class AgentInfo(BaseModel):
    agent_id: str
    display_name: str
    description: str
    silver_table: str
    default_limit: int


class AgentListResponse(BaseModel):
    agents: List[AgentInfo]
    total: int


class AgentRunRequest(BaseModel):
    limit: int = 50
    scope: Optional[str] = None


class AgentRunResponse(BaseModel):
    run_id: str
    agent_id: str
    status: str  # "queued"
    limit: int
    queued_at: str


class AgentRunRecord(BaseModel):
    run_id: Optional[str]
    source_name: str
    status: str
    records_fetched: Optional[int]
    records_inserted: Optional[int]
    refreshed_at: str
    error_message: Optional[str]


class AgentRunHistoryResponse(BaseModel):
    agent_id: str
    runs: List[AgentRunRecord]
    total: int


class QuarantineRecord(BaseModel):
    id: int
    agent_name: str
    record_id: str
    source_table: str
    confidence_score: Optional[float]
    failure_reason: Optional[str]
    created_at: str


class QuarantineResponse(BaseModel):
    records: List[QuarantineRecord]
    total: int
    page: int
    page_size: int


# ============================================================================
# Background task: spawn agent run
# ============================================================================

async def _run_agent_background(agent_id: str, run_id: str, limit: int, scope: Optional[str]) -> None:
    """Run agent asynchronously. Executed via FastAPI BackgroundTasks."""
    agent_meta = AGENT_REGISTRY[agent_id]
    module_path = agent_meta["module"]

    logger.info("agent_background_run_started", agent_id=agent_id, run_id=run_id, limit=limit)

    try:
        # Dynamic import and run to avoid circular imports
        import importlib
        module = importlib.import_module(module_path)
        agent_class = getattr(module, _get_agent_class_name(agent_id))
        agent = agent_class()
        result = await agent.run(scope=scope, limit=limit)

        logger.info(
            "agent_background_run_completed",
            agent_id=agent_id,
            run_id=run_id,
            records_processed=result.records_processed,
            records_written=result.records_written,
            status=result.status,
        )
    except Exception as e:
        logger.error("agent_background_run_failed", agent_id=agent_id, run_id=run_id, error=str(e))


def _get_agent_class_name(agent_id: str) -> str:
    """Convert agent_id snake_case to PascalCase class name."""
    return "".join(part.capitalize() for part in agent_id.split("_")) + "Agent"


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=AgentListResponse)
async def list_agents() -> AgentListResponse:
    """List all registered agents with metadata."""
    agents = [
        AgentInfo(
            agent_id=meta["agent_id"],
            display_name=meta["display_name"],
            description=meta["description"],
            silver_table=meta["silver_table"],
            default_limit=meta["default_limit"],
        )
        for meta in AGENT_REGISTRY.values()
    ]
    return AgentListResponse(agents=agents, total=len(agents))


@router.post("/{agent_id}/run", status_code=202, response_model=AgentRunResponse)
async def trigger_agent_run(
    agent_id: str,
    request: AgentRunRequest,
    background_tasks: BackgroundTasks,
) -> AgentRunResponse:
    """
    Trigger an agent run asynchronously.

    Returns 202 Accepted immediately. The agent runs in a background task.
    Poll GET /agents/{agent_id}/runs to check completion.
    """
    if agent_id not in AGENT_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' not found. Available agents: {list(AGENT_REGISTRY.keys())}"
        )

    run_id = str(uuid.uuid4())
    queued_at = datetime.now(timezone.utc).isoformat()

    background_tasks.add_task(
        _run_agent_background,
        agent_id=agent_id,
        run_id=run_id,
        limit=request.limit,
        scope=request.scope,
    )

    logger.info("agent_run_queued", agent_id=agent_id, run_id=run_id, limit=request.limit)

    return AgentRunResponse(
        run_id=run_id,
        agent_id=agent_id,
        status="queued",
        limit=request.limit,
        queued_at=queued_at,
    )


@router.get("/{agent_id}/runs", response_model=AgentRunHistoryResponse)
async def get_agent_run_history(
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db_pool=Depends(get_db_pool),
) -> AgentRunHistoryResponse:
    """List recent run history for an agent from meta.refresh_log."""
    if agent_id not in AGENT_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' not found."
        )

    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    rl.log_id::TEXT    AS run_id,
                    ds.source_name,
                    rl.status,
                    rl.records_fetched,
                    rl.records_inserted,
                    rl.refreshed_at::TEXT,
                    rl.error_message
                FROM meta.refresh_log rl
                JOIN meta.data_sources ds ON ds.source_id = rl.source_id
                WHERE ds.source_name = $1
                ORDER BY rl.refreshed_at DESC
                LIMIT $2
                """,
                agent_id,
                limit,
            )

        runs = [
            AgentRunRecord(
                run_id=row["run_id"],
                source_name=row["source_name"],
                status=row["status"],
                records_fetched=row["records_fetched"],
                records_inserted=row["records_inserted"],
                refreshed_at=row["refreshed_at"],
                error_message=row["error_message"],
            )
            for row in rows
        ]

        return AgentRunHistoryResponse(
            agent_id=agent_id,
            runs=runs,
            total=len(runs),
        )

    except Exception as e:
        logger.error("agent_run_history_failed", agent_id=agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch run history: {e}")


@router.get("/quarantine", response_model=QuarantineResponse)
async def get_quarantine(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    agent_name: Optional[str] = Query(default=None),
    db_pool=Depends(get_db_pool),
) -> QuarantineResponse:
    """
    Return paginated quarantine records from agents.agent_quarantine.

    Quarantine records are written by agents for records with confidence_score < 0.5
    or other processing failures.
    """
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    offset = (page - 1) * page_size

    try:
        async with db_pool.acquire() as conn:
            # Build query with optional agent filter
            where_clause = "WHERE agent_name = $3" if agent_name else ""
            params = [page_size, offset]
            count_params: list = []
            if agent_name:
                params.append(agent_name)
                count_params.append(agent_name)

            rows = await conn.fetch(
                f"""
                SELECT
                    id, agent_name, record_id, source_table,
                    confidence_score, failure_reason, created_at::TEXT
                FROM agents.agent_quarantine
                {where_clause}
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                *params,
            )

            count_row = await conn.fetchrow(
                f"""
                SELECT COUNT(*) AS total
                FROM agents.agent_quarantine
                {"WHERE agent_name = $1" if agent_name else ""}
                """,
                *count_params,
            )

        records = [
            QuarantineRecord(
                id=row["id"],
                agent_name=row["agent_name"],
                record_id=row["record_id"],
                source_table=row["source_table"],
                confidence_score=row["confidence_score"],
                failure_reason=row["failure_reason"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return QuarantineResponse(
            records=records,
            total=count_row["total"],
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error("quarantine_fetch_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch quarantine records: {e}")
