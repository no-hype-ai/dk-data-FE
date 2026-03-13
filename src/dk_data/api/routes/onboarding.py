"""
User & Molecule Onboarding API routes.

Implements:
- T187: POST /api/v1/onboarding/user - User onboarding
- T188: POST /api/v1/onboarding/molecules - Molecule tracking setup
- Molecule onboarding endpoints for data platform

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import UUID, uuid4
from loguru import logger

from ...services.ground_truth.onboarding_service import (
    UserOnboardingService,
    DataOnboardingPipeline,
)
from ...models.application.onboarding import (
    OnboardingRequest,
    OnboardingStatus,
    IdentifierInput,
)


router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# Request Models
class UserOnboardRequest(BaseModel):
    """Request to onboard a new user."""
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(default="analyst")
    organization: Optional[str] = None
    therapeutic_areas: Optional[List[str]] = None


class MoleculeTrackingRequest(BaseModel):
    """Request to set up molecule tracking."""
    user_id: str
    molecules: List[Dict[str, str]] = Field(
        ...,
        min_length=1,
        description="List of {molecule_id, molecule_name}"
    )
    alert_types: Optional[List[str]] = None
    notification_frequency: str = Field(default="daily")


class PipelineStartRequest(BaseModel):
    """Request to start data onboarding pipeline."""
    molecule_id: str
    molecule_name: str
    data_sources: Optional[List[str]] = None


# Response Models
class UserOnboardResponse(BaseModel):
    """Response for user onboarding."""
    success: bool
    user_id: str
    name: str
    email: str
    role: str
    onboarding_status: str
    suggested_molecules: List[Dict[str, Any]]
    timestamp: str


class MoleculeTrackingResponse(BaseModel):
    """Response for molecule tracking setup."""
    success: bool
    user_id: str
    tracked_count: int
    trackers: List[Dict[str, Any]]
    timestamp: str


class PipelineStatusResponse(BaseModel):
    """Response for pipeline status."""
    success: bool
    job_id: str
    molecule_id: str
    current_stage: str
    progress_percent: float
    stages_completed: List[str]
    stages_pending: List[str]
    errors: List[str]
    timestamp: str


# Service instances
_onboarding_service: Optional[UserOnboardingService] = None
_pipeline_service: Optional[DataOnboardingPipeline] = None


def get_onboarding_service() -> UserOnboardingService:
    global _onboarding_service
    if _onboarding_service is None:
        _onboarding_service = UserOnboardingService()
    return _onboarding_service


def get_pipeline_service() -> DataOnboardingPipeline:
    global _pipeline_service
    if _pipeline_service is None:
        _pipeline_service = DataOnboardingPipeline()
    return _pipeline_service


@router.post("/user", response_model=UserOnboardResponse)
async def onboard_user(request: UserOnboardRequest):
    """
    Onboard a new user with role-based setup.

    Creates user profile with default preferences based on role
    and returns suggested molecules for tracking.
    """
    try:
        service = get_onboarding_service()

        profile = await service.onboard_user(
            email=request.email,
            name=request.name,
            role=request.role,
            organization=request.organization,
            therapeutic_areas=request.therapeutic_areas,
        )

        # Get suggested molecules
        suggestions = await service.suggest_molecules(
            therapeutic_areas=profile.therapeutic_areas,
            limit=10,
        )

        return UserOnboardResponse(
            success=True,
            user_id=profile.user_id,
            name=profile.name,
            email=profile.email,
            role=profile.role.value,
            onboarding_status=profile.onboarding_status.value,
            suggested_molecules=suggestions,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"Error onboarding user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/molecules", response_model=MoleculeTrackingResponse)
async def setup_molecule_tracking(request: MoleculeTrackingRequest):
    """
    Set up molecule tracking for a user.

    Configures which molecules to track and alert preferences.
    """
    try:
        service = get_onboarding_service()

        trackers = await service.setup_molecule_tracking(
            user_id=request.user_id,
            molecules=request.molecules,
            alert_types=request.alert_types,
            notification_frequency=request.notification_frequency,
        )

        return MoleculeTrackingResponse(
            success=True,
            user_id=request.user_id,
            tracked_count=len(trackers),
            trackers=[t.to_dict() for t in trackers],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting up molecule tracking: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}")
async def get_user_profile(user_id: str):
    """
    Get user profile and tracking configuration.
    """
    try:
        service = get_onboarding_service()

        profile = await service.get_user_profile(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        trackers = await service.get_tracked_molecules(user_id)

        return {
            "success": True,
            "profile": profile.to_dict(),
            "tracked_molecules": [t.to_dict() for t in trackers],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggestions")
async def get_molecule_suggestions(
    therapeutic_areas: str = Query(..., description="Comma-separated therapeutic areas"),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Get molecule suggestions based on therapeutic areas.
    """
    try:
        service = get_onboarding_service()
        tas = [ta.strip() for ta in therapeutic_areas.split(",")]

        suggestions = await service.suggest_molecules(
            therapeutic_areas=tas,
            limit=limit,
        )

        return {
            "success": True,
            "therapeutic_areas": tas,
            "suggestions_count": len(suggestions),
            "suggestions": suggestions,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/start", response_model=PipelineStatusResponse)
async def start_data_pipeline(request: PipelineStartRequest):
    """
    Start data onboarding pipeline for a molecule.

    Runs 7-step pipeline: ingest, normalize, dedupe, enrich, validate, index, serve.
    """
    try:
        service = get_pipeline_service()

        status = await service.start_pipeline(
            molecule_id=request.molecule_id,
            molecule_name=request.molecule_name,
            data_sources=request.data_sources,
        )

        return PipelineStatusResponse(
            success=True,
            job_id=status.job_id,
            molecule_id=status.molecule_id,
            current_stage=status.current_stage.value,
            progress_percent=status.progress_percent,
            stages_completed=status.stages_completed,
            stages_pending=status.stages_pending,
            errors=status.errors,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"Error starting pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/{job_id}", response_model=PipelineStatusResponse)
async def get_pipeline_status(job_id: str):
    """
    Get status of a data onboarding pipeline job.
    """
    try:
        service = get_pipeline_service()

        status = await service.get_pipeline_status(job_id)
        if not status:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        return PipelineStatusResponse(
            success=True,
            job_id=status.job_id,
            molecule_id=status.molecule_id,
            current_stage=status.current_stage.value,
            progress_percent=status.progress_percent,
            stages_completed=status.stages_completed,
            stages_pending=status.stages_pending,
            errors=status.errors,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pipeline status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline")
async def list_pipeline_jobs(
    molecule_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """
    List data onboarding pipeline jobs.
    """
    try:
        service = get_pipeline_service()

        jobs = await service.list_jobs(molecule_id=molecule_id)

        return {
            "success": True,
            "jobs_count": len(jobs[:limit]),
            "jobs": [j.to_dict() for j in jobs[:limit]],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error listing pipeline jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Molecule Onboarding Endpoints (MoleculeOnboardingService)
# =============================================================================

# Request models for molecule onboarding
class MoleculeIdentifier(BaseModel):
    """Single identifier for molecule resolution."""
    identifier_type: str = Field(
        ...,
        description="Type: inchi_key, chembl_id, drugbank_id, pubchem_cid, cas_number, unii, name, research_code"
    )
    identifier_value: str = Field(..., description="The identifier value")


class MoleculeOnboardRequest(BaseModel):
    """Request to onboard a molecule to the platform."""
    identifiers: List[MoleculeIdentifier] = Field(
        ...,
        min_length=1,
        description="List of identifiers (at least one required)"
    )
    requested_sources: Optional[List[str]] = Field(
        None,
        description="Specific sources to fetch (null = all configured sources)"
    )
    skip_enrichment: bool = Field(
        False,
        description="Skip data enrichment (resolve only)"
    )
    indication: Optional[str] = Field(
        None,
        description="Primary indication/therapeutic area"
    )


class BulkMoleculeOnboardRequest(BaseModel):
    """Request to onboard multiple molecules."""
    molecules: List[MoleculeOnboardRequest] = Field(..., min_length=1, max_length=100)
    continue_on_error: bool = Field(True, description="Continue if individual molecules fail")


class MoleculeOnboardResponse(BaseModel):
    """Response for molecule onboarding."""
    request_id: str
    status: str
    molecule_id: Optional[str] = None
    canonical_name: Optional[str] = None
    inchi_key: Optional[str] = None
    confidence: Optional[float] = None
    data_sources_fetched: List[str] = []
    matched_identifiers: Dict[str, str] = {}
    unmatched_identifiers: List[str] = []
    potential_matches: List[Dict[str, Any]] = []
    error_message: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class BulkMoleculeOnboardResponse(BaseModel):
    """Response for bulk molecule onboarding."""
    batch_id: str
    total_requested: int
    successful: int
    failed: int
    pending: int
    results: List[MoleculeOnboardResponse]
    errors: List[Dict[str, Any]] = []
    created_at: str


# Service factory for MoleculeOnboardingService
_molecule_onboarding_service = None


async def get_molecule_onboarding_service():
    """Get or create MoleculeOnboardingService instance."""
    global _molecule_onboarding_service

    if _molecule_onboarding_service is None:
        try:
            from ...api.dependencies import get_db_pool
            from ...services.data_platform.molecule_onboarding import MoleculeOnboardingService
            from ...services.data_platform.identifier_resolver import IdentifierResolver
            from ...services.data_platform.raw_ingestion import RawIngestionService
            from ...services.data_platform.gold_aggregation import GoldAggregationService

            pool = await get_db_pool()
            if pool is None:
                return None

            # Initialize resolver
            resolver = IdentifierResolver(pool)

            # Initialize raw ingestion service
            raw_service = RawIngestionService(pool)

            # Initialize gold service
            gold_service = GoldAggregationService(pool)

            # Try to use BulletproofTransformer if available
            try:
                from ...services.data_platform.bulletproof_transformer import BulletproofTransformer
                transformer = BulletproofTransformer(pool)
                await transformer.initialize()
                _molecule_onboarding_service = MoleculeOnboardingService(
                    db_pool=pool,
                    identifier_resolver=resolver,
                    raw_ingestion_service=raw_service,
                    gold_aggregation_service=gold_service,
                    bulletproof_transformer=transformer
                )
            except ImportError:
                # Fallback to legacy services
                from ...services.data_platform.bronze_ingestion import BronzeIngestionService
                from ...services.data_platform.silver_transformation import SilverTransformationService

                bronze_service = BronzeIngestionService(pool)
                silver_service = SilverTransformationService(pool)

                _molecule_onboarding_service = MoleculeOnboardingService(
                    db_pool=pool,
                    identifier_resolver=resolver,
                    raw_ingestion_service=raw_service,
                    bronze_ingestion_service=bronze_service,
                    silver_transformation_service=silver_service,
                    gold_aggregation_service=gold_service,
                )

            logger.info("MoleculeOnboardingService initialized")
        except Exception as e:
            logger.error(f"Failed to initialize MoleculeOnboardingService: {e}")
            return None

    return _molecule_onboarding_service


@router.post("/molecule", response_model=MoleculeOnboardResponse)
async def onboard_molecule(
    request: MoleculeOnboardRequest,
    user_id: str = Query("system", description="User ID for audit"),
):
    """
    Onboard a single molecule to the DK Data Platform.

    Workflow:
    1. RESOLVING: Resolve identifiers to canonical InChI Key
    2. INGESTING: Fetch raw data from configured sources
    3. ENRICHING: Transform through Bronze → Silver → Gold
    4. COMPLETED: Return enriched molecule profile

    If resolution confidence < 0.8, returns NEEDS_REVIEW status with potential matches.
    """
    try:
        service = await get_molecule_onboarding_service()
        if service is None:
            raise HTTPException(status_code=503, detail="Molecule onboarding service unavailable")

        # Convert request to internal format
        identifiers = [
            IdentifierInput(
                identifier_type=i.identifier_type,
                identifier_value=i.identifier_value
            )
            for i in request.identifiers
        ]

        onboarding_request = OnboardingRequest(
            identifiers=identifiers,
            requested_sources=request.requested_sources,
            skip_enrichment=request.skip_enrichment,
        )

        result = await service.onboard_molecule(
            request=onboarding_request,
            user_id=UUID(user_id) if user_id != "system" else uuid4()
        )

        return MoleculeOnboardResponse(
            request_id=str(result.request_id),
            status=result.status.value,
            molecule_id=str(result.molecule_id) if result.molecule_id else None,
            canonical_name=result.canonical_name,
            inchi_key=result.resolution_result.inchi_key if result.resolution_result else None,
            confidence=result.resolution_result.confidence if result.resolution_result else None,
            data_sources_fetched=result.data_sources_fetched or [],
            matched_identifiers=result.resolution_result.matched_identifiers if result.resolution_result else {},
            unmatched_identifiers=result.resolution_result.unmatched_identifiers if result.resolution_result else [],
            potential_matches=result.resolution_result.potential_matches if result.resolution_result else [],
            error_message=result.error_message,
            created_at=result.created_at.isoformat() if result.created_at else datetime.now(timezone.utc).isoformat(),
            completed_at=result.completed_at.isoformat() if result.completed_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Molecule onboarding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/molecule/bulk", response_model=BulkMoleculeOnboardResponse)
async def onboard_molecules_bulk(
    request: BulkMoleculeOnboardRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Query("system", description="User ID for audit"),
):
    """
    Onboard multiple molecules in batch.

    Processes up to 100 molecules. For larger batches, use the async endpoint.
    """
    try:
        service = await get_molecule_onboarding_service()
        if service is None:
            raise HTTPException(status_code=503, detail="Molecule onboarding service unavailable")

        batch_id = uuid4()
        created_at = datetime.now(timezone.utc)
        results = []
        errors = []

        for idx, mol_request in enumerate(request.molecules):
            try:
                identifiers = [
                    IdentifierInput(
                        identifier_type=i.identifier_type,
                        identifier_value=i.identifier_value
                    )
                    for i in mol_request.identifiers
                ]

                onboarding_request = OnboardingRequest(
                    identifiers=identifiers,
                    requested_sources=mol_request.requested_sources,
                    skip_enrichment=mol_request.skip_enrichment,
                )

                result = await service.onboard_molecule(
                    request=onboarding_request,
                    user_id=UUID(user_id) if user_id != "system" else uuid4()
                )

                results.append(MoleculeOnboardResponse(
                    request_id=str(result.request_id),
                    status=result.status.value,
                    molecule_id=str(result.molecule_id) if result.molecule_id else None,
                    canonical_name=result.canonical_name,
                    inchi_key=result.resolution_result.inchi_key if result.resolution_result else None,
                    confidence=result.resolution_result.confidence if result.resolution_result else None,
                    data_sources_fetched=result.data_sources_fetched or [],
                    matched_identifiers=result.resolution_result.matched_identifiers if result.resolution_result else {},
                    unmatched_identifiers=result.resolution_result.unmatched_identifiers if result.resolution_result else [],
                    potential_matches=[],
                    error_message=result.error_message,
                    created_at=result.created_at.isoformat() if result.created_at else created_at.isoformat(),
                    completed_at=result.completed_at.isoformat() if result.completed_at else None,
                ))
            except Exception as e:
                if not request.continue_on_error:
                    raise
                errors.append({
                    'index': idx,
                    'identifiers': [i.model_dump() for i in mol_request.identifiers],
                    'error': str(e)
                })

        successful = sum(1 for r in results if r.status == 'completed')
        failed = sum(1 for r in results if r.status == 'failed') + len(errors)
        pending = sum(1 for r in results if r.status in ['pending', 'needs_review'])

        return BulkMoleculeOnboardResponse(
            batch_id=str(batch_id),
            total_requested=len(request.molecules),
            successful=successful,
            failed=failed,
            pending=pending,
            results=results,
            errors=errors,
            created_at=created_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk molecule onboarding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/molecule/{request_id}", response_model=MoleculeOnboardResponse)
async def get_molecule_onboarding_status(request_id: str):
    """
    Get the status of a molecule onboarding request.
    """
    try:
        service = await get_molecule_onboarding_service()
        if service is None:
            raise HTTPException(status_code=503, detail="Molecule onboarding service unavailable")

        result = await service.get_onboarding_status(UUID(request_id))
        if not result:
            raise HTTPException(status_code=404, detail=f"Request {request_id} not found")

        return MoleculeOnboardResponse(
            request_id=str(result.request_id),
            status=result.status.value,
            molecule_id=str(result.molecule_id) if result.molecule_id else None,
            canonical_name=result.canonical_name,
            error_message=result.error_message,
            created_at=result.created_at.isoformat() if result.created_at else datetime.now(timezone.utc).isoformat(),
            completed_at=result.completed_at.isoformat() if result.completed_at else None,
            data_sources_fetched=[],
            matched_identifiers={},
            unmatched_identifiers=[],
            potential_matches=[],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting onboarding status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/molecule/{request_id}/approve")
async def approve_molecule_resolution(
    request_id: str,
    molecule_id: str = Query(..., description="Selected molecule ID from potential matches"),
    user_id: str = Query("system", description="User ID for audit"),
):
    """
    Approve a molecule resolution when status is NEEDS_REVIEW.

    Use this when the automated resolution returned multiple potential matches
    and manual selection is required.
    """
    try:
        service = await get_molecule_onboarding_service()
        if service is None:
            raise HTTPException(status_code=503, detail="Molecule onboarding service unavailable")

        # Get current status
        current = await service.get_onboarding_status(UUID(request_id))
        if not current:
            raise HTTPException(status_code=404, detail=f"Request {request_id} not found")

        if current.status != OnboardingStatus.NEEDS_REVIEW:
            raise HTTPException(
                status_code=400,
                detail=f"Request is not in NEEDS_REVIEW status (current: {current.status.value})"
            )

        # Log approval and complete onboarding
        from ...api.dependencies import get_db_pool
        pool = await get_db_pool()

        async with pool.acquire() as conn:
            # Log approval
            await conn.execute("""
                INSERT INTO application.onboarding_audit_log
                (id, request_id, user_id, action, status, details)
                VALUES ($1, $2, $3, 'resolution_approved', 'completed', $4)
            """, uuid4(), UUID(request_id), UUID(user_id) if user_id != "system" else uuid4(),
            {'selected_molecule_id': molecule_id})

        return {
            "success": True,
            "request_id": request_id,
            "molecule_id": molecule_id,
            "status": "completed",
            "message": "Resolution approved and molecule linked",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving resolution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/molecule/resolve")
async def resolve_molecule_identifier(
    identifier: str = Query(..., description="Identifier value to resolve"),
    identifier_type: Optional[str] = Query(None, description="Type hint (auto-detected if not provided)"),
):
    """
    Quick resolve endpoint to look up a molecule by identifier.

    Returns the canonical molecule if found, or potential matches for review.
    Does NOT trigger full onboarding - use POST /molecule for that.
    """
    try:
        from ...api.dependencies import get_db_pool
        from ...services.data_platform.identifier_resolver import IdentifierResolver

        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        resolver = IdentifierResolver(pool)

        result = await resolver.resolve(
            identifier_type=identifier_type or 'auto',
            identifier_value=identifier
        )

        return {
            "success": True,
            "query": identifier,
            "query_type": identifier_type or result.get('detected_type', 'unknown'),
            "resolved": result.get('resolved', False),
            "molecule_id": str(result.get('molecule_id')) if result.get('molecule_id') else None,
            "inchi_key": result.get('inchi_key'),
            "canonical_name": result.get('canonical_name'),
            "confidence": result.get('confidence', 0),
            "potential_matches": result.get('potential_matches', [])[:10],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error resolving identifier: {e}")
        raise HTTPException(status_code=500, detail=str(e))
