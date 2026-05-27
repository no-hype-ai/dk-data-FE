"""Competitor-search endpoint — composed across ChEMBL, ClinicalTrials.gov,
OpenFDA, and DrugBank.

Mirrors the dk-data invoke envelope (`status / request_id / source / data /
duration_ms / error / timestamp`) so platform consumers can treat this like
any other /data-tools/{tool}/invoke call, even though the underlying
implementation fans out across multiple sources rather than a single
adapter.

Route:
    POST /api/v1/data-tools/competitor-search/invoke
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..dependencies import get_db_pool
from ...services.competitor_search import CompetitorSearchService

router = APIRouter(prefix="/data-tools/competitor-search", tags=["competitor-search"])

_service = CompetitorSearchService()


# ──────────────────────────── Request models ────────────────────────────────


class IndicationInput(BaseModel):
    name: str = Field(..., min_length=1)
    status: str | None = Field(None, description="e.g. 'Approved', 'Phase 3'")


class CompetitorSearchRequest(BaseModel):
    molecule_name: str = Field(..., min_length=1)
    indications: list[IndicationInput] = Field(..., min_length=1)
    brand_name: str | None = None
    mechanism_of_action: str | None = None
    limit: int = Field(default=10, ge=1, le=25)


# ──────────────────────────── Response models ───────────────────────────────


class CompetitorResult(BaseModel):
    molecule: str
    brand: str | None = None
    manufacturer: str | None = None
    mechanism: str | None = None
    shared_indications: list[str] = Field(default_factory=list)
    approval_status: str | None = None
    evidence: list[str] = Field(default_factory=list)


class CompetitorSearchData(BaseModel):
    source: str = "composed"
    results: list[CompetitorResult]


class CompetitorSearchResponse(BaseModel):
    status: str
    request_id: str
    source: str = "competitor-search"
    data: CompetitorSearchData
    duration_ms: int
    error: dict[str, Any] | None = None
    timestamp: str


# ─────────────────────────────── Endpoint ───────────────────────────────────


@router.post("/invoke", response_model=CompetitorSearchResponse)
async def invoke_competitor_search(
    request: CompetitorSearchRequest,
    db_pool: Any = Depends(get_db_pool),
) -> CompetitorSearchResponse:
    """Find competing molecules by shared target / MOA / indication."""
    t0 = time.monotonic()
    request_id = str(uuid.uuid4())

    try:
        results = await _service.find_competitors(
            molecule_name=request.molecule_name,
            indications=[ind.model_dump() for ind in request.indications],
            brand_name=request.brand_name,
            mechanism_of_action=request.mechanism_of_action,
            limit=request.limit,
            db_pool=db_pool,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Competitor search failed: {e}"
        )

    duration_ms = int((time.monotonic() - t0) * 1000)
    return CompetitorSearchResponse(
        status="success",
        request_id=request_id,
        source="competitor-search",
        data=CompetitorSearchData(
            source="composed",
            results=[CompetitorResult(**r) for r in results],
        ),
        duration_ms=duration_ms,
        error=None,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
