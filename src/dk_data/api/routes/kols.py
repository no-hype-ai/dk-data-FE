"""
KOL and Patient Advocacy API routes.

Implements:
- T161: GET /api/v1/kols/{therapeutic_area}
- T162: GET /api/v1/kols/{kol_id}/network
- T163: GET /api/v1/advocacy/{indication}
- T164: GET /api/v1/advocacy/{molecule_id}/sentiment
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger

from ...services.ground_truth.kol_service import (
    KOLIntelligenceService,
    PatientAdvocacyService,
)


router = APIRouter(prefix="/kols", tags=["kols"])


# Response Models
class KOLListResponse(BaseModel):
    """KOL list response."""
    success: bool
    therapeutic_area: str
    kols_count: int
    kols: List[Dict[str, Any]]
    timestamp: str


class KOLNetworkResponse(BaseModel):
    """KOL network response."""
    success: bool
    center_kol: Dict[str, Any]
    network_size: int
    connections: List[Dict[str, Any]]
    connected_kols: List[Dict[str, Any]]
    timestamp: str


class AdvocacyResponse(BaseModel):
    """Advocacy groups response."""
    success: bool
    indication: str
    groups_count: int
    groups: List[Dict[str, Any]]
    timestamp: str


# Service instances
_kol_service: Optional[KOLIntelligenceService] = None
_advocacy_service: Optional[PatientAdvocacyService] = None


def get_kol_service() -> KOLIntelligenceService:
    global _kol_service
    if _kol_service is None:
        _kol_service = KOLIntelligenceService()
    return _kol_service


def get_advocacy_service() -> PatientAdvocacyService:
    global _advocacy_service
    if _advocacy_service is None:
        _advocacy_service = PatientAdvocacyService()
    return _advocacy_service


@router.get("/{therapeutic_area}", response_model=KOLListResponse)
async def get_kols_by_therapeutic_area(
    therapeutic_area: str,
    indication: Optional[str] = Query(None, description="Specific indication"),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get Key Opinion Leaders in a therapeutic area.

    Returns ranked list of KOLs based on publications, citations, and influence.
    """
    try:
        service = get_kol_service()

        kols = await service.identify_kols(
            therapeutic_area=therapeutic_area,
            indication=indication,
            limit=limit,
        )

        return KOLListResponse(
            success=True,
            therapeutic_area=therapeutic_area,
            kols_count=len(kols),
            kols=[kol.to_dict() for kol in kols],
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error getting KOLs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drug/{drug_name}")
async def get_kols_for_drug(
    drug_name: str,
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get KOLs who have published about or investigated a drug.
    """
    try:
        service = get_kol_service()
        kols = await service.get_kols_for_drug(drug_name, limit=limit)

        return {
            "success": True,
            "drug_name": drug_name,
            "kols_count": len(kols),
            "kols": [kol.to_dict() for kol in kols],
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting KOLs for drug: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile/{kol_id}/network", response_model=KOLNetworkResponse)
async def get_kol_network(
    kol_id: str,
    depth: int = Query(1, ge=1, le=2, description="Network depth"),
):
    """
    Get network of collaborators for a KOL.

    Returns co-authors, co-investigators, and connection strengths.
    """
    try:
        service = get_kol_service()

        network = await service.get_kol_network(kol_id, depth=depth)

        return KOLNetworkResponse(
            success=True,
            center_kol=network.center_kol.to_dict(),
            network_size=network.network_size,
            connections=[
                {
                    "from": c.from_kol_id,
                    "to": c.to_kol_id,
                    "type": c.connection_type,
                    "strength": c.strength,
                    "shared_publications": c.shared_publications,
                }
                for c in network.connections
            ],
            connected_kols=[kol.to_dict() for kol in network.connected_kols],
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error getting KOL network: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Advocacy routes
advocacy_router = APIRouter(prefix="/advocacy", tags=["advocacy"])


@advocacy_router.get("/{indication}", response_model=AdvocacyResponse)
async def get_advocacy_groups(
    indication: str,
    therapeutic_area: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Find patient advocacy groups for an indication.
    """
    try:
        service = get_advocacy_service()

        groups = await service.find_advocacy_groups(
            indication=indication,
            therapeutic_area=therapeutic_area,
            limit=limit,
        )

        return AdvocacyResponse(
            success=True,
            indication=indication,
            groups_count=len(groups),
            groups=[g.to_dict() for g in groups],
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error getting advocacy groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@advocacy_router.get("/molecule/{molecule_id}/sentiment")
async def get_advocacy_sentiment(
    molecule_id: str,
    molecule_name: Optional[str] = Query(None),
):
    """
    Analyze patient advocacy sentiment towards a drug.
    """
    try:
        service = get_advocacy_service()
        name = molecule_name or molecule_id.replace("_", " ")

        sentiment = await service.get_advocacy_sentiment(name)

        return {
            "success": True,
            **sentiment,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting sentiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Include advocacy router
router.include_router(advocacy_router)
