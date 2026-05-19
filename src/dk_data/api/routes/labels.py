"""Drug label preview endpoints — FDA and EMA.

Slim, consumer-friendly label lookup. DB-first against local raw tables;
FDA falls back to live OpenFDA API. Both return URL-only previews so
downstream platforms can embed the official PDF directly.

Routes:
    GET /api/v1/labels/fda?drug_name=adalimumab
    GET /api/v1/labels/ema?drug_name=ranibizumab
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..dependencies import get_db_pool
from ...services.mcp.adapters.ema_labels import Adapter as EmaLabelsAdapter
from ...services.mcp.adapters.openfda_labels import Adapter as OpenFDALabelsAdapter

router = APIRouter(prefix="/labels", tags=["labels"])

_fda_adapter = OpenFDALabelsAdapter()
_ema_adapter = EmaLabelsAdapter()


class FDALabel(BaseModel):
    brand_name: str | None
    generic_name: str | None
    pdf_url: str | None
    boxed_warning: str | None


class EMALabel(BaseModel):
    medicine_name: str | None
    active_substance: str | None
    smpc_pdf_url: str | None


class FDALabelResponse(BaseModel):
    source: str  # "openfda_local" | "openfda"
    results: list[FDALabel]


class EMALabelResponse(BaseModel):
    source: str  # "ema_cache" | "ema_smpc_pdf"
    results: list[EMALabel]


@router.get("/fda", response_model=FDALabelResponse)
async def search_fda_label(
    drug_name: str = Query(..., min_length=1, description="Generic or brand name"),
    db_pool: Any = Depends(get_db_pool),
) -> FDALabelResponse:
    """FDA SPL label preview. DB-first against mol_raw.openfda_labels with OpenFDA API fallback."""
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database pool unavailable")

    result = await _fda_adapter.db_query(drug_name, db_pool)
    if not result or not result.get("results"):
        raise HTTPException(status_code=404, detail=f"No FDA label found for '{drug_name}'")
    return FDALabelResponse(**result)


@router.get("/ema", response_model=EMALabelResponse)
async def search_ema_label(
    drug_name: str = Query(..., min_length=1, description="Generic, brand, INN, or active substance"),
    db_pool: Any = Depends(get_db_pool),
) -> EMALabelResponse:
    """EMA SmPC label preview. Cache-first; lazily derives SmPC PDF URL from mol_raw.ema."""
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database pool unavailable")

    result = await _ema_adapter.db_query(drug_name, db_pool)
    if not result or not result.get("results"):
        raise HTTPException(status_code=404, detail=f"No EMA label found for '{drug_name}'")
    return EMALabelResponse(**result)
