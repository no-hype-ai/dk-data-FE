"""
DK Molecule Data Platform API Routes.

Implements REST endpoints for:
- Molecule search and resolution
- Entity resolution queue management
- Pipeline status and metrics
- Data ingestion triggers

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from loguru import logger

# Import services (will be injected via dependency)
from ...services.data_platform import (
    ResolutionQueueService,
)
from ..dependencies import get_db_pool, get_gold_service, get_resolver_service

router = APIRouter(prefix="/data-platform", tags=["data-platform"])


# ============================================================================
# Request/Response Models
# ============================================================================

class MoleculeSearchRequest(BaseModel):
    """Request for molecule search."""
    query: str = Field(..., min_length=2, description="Search query (molecule name)")
    threshold: float = Field(0.3, ge=0.0, le=1.0, description="Similarity threshold")
    limit: int = Field(20, ge=1, le=100, description="Maximum results")


class MoleculeSearchResult(BaseModel):
    """Single molecule search result."""
    molecule_id: str
    inchi_key: Optional[str]
    canonical_name: str
    similarity: float
    match_type: str


class MoleculeSearchResponse(BaseModel):
    """Response for molecule search."""
    success: bool
    query: str
    results: List[MoleculeSearchResult]
    count: int
    timestamp: str


class IdentifierResolutionRequest(BaseModel):
    """Request for identifier resolution."""
    identifier: str = Field(..., min_length=1, description="Identifier to resolve")
    identifier_type: Optional[str] = Field(None, description="Type hint (auto-detected if not provided)")


class IdentifierResolutionResponse(BaseModel):
    """Response for identifier resolution."""
    success: bool
    identifier: str
    detected_type: str
    molecule_id: Optional[str]
    inchi_key: Optional[str]
    canonical_name: Optional[str]
    confidence: float
    match_type: str
    needs_review: bool
    resolution_path: List[str]
    timestamp: str


class MoleculeProfileResponse(BaseModel):
    """Complete molecule profile response."""
    success: bool
    molecule_id: str
    inchi_key: Optional[str]
    canonical_name: str
    canonical_smiles: Optional[str]
    molecular_formula: Optional[str]
    molecular_weight: Optional[float]
    molecule_type: Optional[str]
    development_status: Optional[str]
    max_phase: Optional[int]
    therapeutic_areas: Optional[List[str]]
    mechanism_of_action: Optional[str]

    # Cross-references
    drugbank_id: Optional[str]
    chembl_id: Optional[str]
    pubchem_cid: Optional[int]
    unii: Optional[str]
    cas_number: Optional[str]

    # Aggregated counts
    total_trials: int = 0
    active_trials: int = 0
    total_adverse_reports: int = 0
    serious_adverse_reports: int = 0
    has_boxed_warning: bool = False
    target_count: int = 0
    publication_count: int = 0

    aliases: Optional[List[str]]
    data_sources: Optional[List[str]]
    timestamp: str


class SafetySignalsResponse(BaseModel):
    """Safety signals response."""
    success: bool
    molecule_id: str
    canonical_name: str
    total_reports: int
    serious_reports: int
    death_reports: int
    top_adverse_events: Optional[List[Dict[str, Any]]]
    boxed_warning: Optional[str]
    first_report_date: Optional[str]
    last_report_date: Optional[str]
    timestamp: str


class QueueItemResponse(BaseModel):
    """Resolution queue item response."""
    id: str
    molecule_id: Optional[str]
    original_identifier: str
    identifier_type: str
    confidence_score: float
    candidate_matches: List[Dict[str, Any]]
    status: str
    priority: str
    created_at: str


class QueueListResponse(BaseModel):
    """Resolution queue list response."""
    success: bool
    items: List[QueueItemResponse]
    total_count: int
    timestamp: str


class QueueActionRequest(BaseModel):
    """Request for queue action."""
    action: str = Field(..., description="approve, reject, or merge")
    reviewed_by: str = Field(..., min_length=1, description="Reviewer username")
    notes: Optional[str] = None
    merge_target_id: Optional[str] = None  # Required for merge action
    delete_molecule: bool = False  # For reject action


class QueueActionResponse(BaseModel):
    """Response for queue action."""
    success: bool
    item_id: str
    action: str
    message: str
    timestamp: str


class QueueStatsResponse(BaseModel):
    """Resolution queue statistics."""
    success: bool
    pending_count: int
    pending_by_priority: Dict[str, int]
    approved_today: int
    rejected_today: int
    merged_today: int
    avg_resolution_time_hours: float
    timestamp: str


class PipelineStatusResponse(BaseModel):
    """Data pipeline status response."""
    success: bool
    molecules: Dict[str, int]
    trials: Dict[str, int]
    adverse_events: Dict[str, int]
    last_refresh: Optional[str]
    timestamp: str


class IngestionTriggerResponse(BaseModel):
    """Response for ingestion trigger."""
    success: bool
    message: str
    job_id: Optional[str]
    timestamp: str


# ============================================================================
# Molecule Search & Resolution Endpoints
# ============================================================================

@router.get("/molecules/search", response_model=MoleculeSearchResponse)
async def search_molecules(
    query: str = Query(..., min_length=2, description="Search query"),
    threshold: float = Query(0.3, ge=0.0, le=1.0, description="Similarity threshold"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results")
):
    """
    Search for molecules by name using fuzzy matching.

    Uses PostgreSQL pg_trgm extension for trigram similarity matching.
    Returns molecules sorted by similarity score.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return MoleculeSearchResponse(
                success=False,
                query=query,
                results=[],
                count=0,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        results = []
        async with pool.acquire() as conn:
            # Search in drug_name_resolver table using trigram similarity
            rows = await conn.fetch("""
                SELECT DISTINCT ON (inchi_key)
                    COALESCE(inchi_key, chembl_id, drugbank_id)::text as molecule_id,
                    inchi_key,
                    drug_name as canonical_name,
                    similarity(LOWER(drug_name_normalized), LOWER($1)) as similarity
                FROM drug_name_resolver
                WHERE similarity(LOWER(drug_name_normalized), LOWER($1)) > $2
                   OR LOWER(drug_name_normalized) LIKE LOWER($3)
                ORDER BY inchi_key, similarity(LOWER(drug_name_normalized), LOWER($1)) DESC
                LIMIT $4
            """, query, threshold, f'%{query}%', limit)

            for row in rows:
                results.append(MoleculeSearchResult(
                    molecule_id=row['molecule_id'] or 'Unknown',
                    inchi_key=row['inchi_key'],
                    canonical_name=row['canonical_name'] or 'Unknown',
                    similarity=float(row['similarity']) if row['similarity'] else 0.0,
                    match_type='fuzzy' if float(row['similarity'] or 0) < 1.0 else 'exact'
                ))

        return MoleculeSearchResponse(
            success=True,
            query=query,
            results=results,
            count=len(results),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Molecule search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resolve", response_model=IdentifierResolutionResponse)
async def resolve_identifier(request: IdentifierResolutionRequest):
    """
    Resolve any molecule identifier to a canonical molecule.

    Supports:
    - InChI Key
    - SMILES
    - ChEMBL ID
    - DrugBank ID
    - PubChem CID
    - UNII
    - CAS Number
    - Molecule names (with fuzzy matching)

    Auto-detects identifier type if not provided.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return IdentifierResolutionResponse(
                success=False,
                identifier=request.identifier,
                detected_type="unknown",
                molecule_id=None,
                inchi_key=None,
                canonical_name=None,
                confidence=0.0,
                match_type="none",
                needs_review=True,
                resolution_path=["database_unavailable"],
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        # Try to get resolver service
        resolver = await get_resolver_service()
        if resolver:
            result = await resolver.resolve(request.identifier, request.identifier_type)
            return IdentifierResolutionResponse(
                success=result.success,
                identifier=request.identifier,
                detected_type=result.identifier_type.value if result.identifier_type else "unknown",
                molecule_id=str(result.molecule_id) if result.molecule_id else None,
                inchi_key=result.inchi_key,
                canonical_name=result.canonical_name,
                confidence=result.confidence,
                match_type=result.match_type,
                needs_review=result.needs_review,
                resolution_path=result.resolution_path,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        # Fallback: direct database lookup
        async with pool.acquire() as conn:
            identifier = request.identifier.strip()
            resolution_path = ["direct_lookup"]

            # Try to detect identifier type
            detected_type = request.identifier_type or "name"

            # Check if it's an InChI Key pattern
            if len(identifier) == 27 and '-' in identifier:
                detected_type = "inchi_key"
                resolution_path.append("inchi_key_pattern")

            # Check if it matches common ID patterns
            if identifier.upper().startswith("CHEMBL"):
                detected_type = "chembl_id"
            elif identifier.upper().startswith("DB"):
                detected_type = "drugbank_id"
            elif identifier.isdigit():
                detected_type = "pubchem_cid"

            # Search in molecules table
            mol = await conn.fetchrow("""
                SELECT
                    m.id::text as molecule_id,
                    m.inchi_key,
                    m.canonical_name,
                    m.needs_review
                FROM silver.molecules m
                WHERE m.inchi_key = $1
                   OR LOWER(m.canonical_name) = LOWER($1)
                   OR EXISTS (
                       SELECT 1 FROM silver.identifier_mappings im
                       WHERE im.molecule_id = m.id AND im.identifier_value = $1
                   )
                LIMIT 1
            """, identifier)

            if mol:
                resolution_path.append("found_in_molecules")
                return IdentifierResolutionResponse(
                    success=True,
                    identifier=request.identifier,
                    detected_type=detected_type,
                    molecule_id=mol['molecule_id'],
                    inchi_key=mol['inchi_key'],
                    canonical_name=mol['canonical_name'],
                    confidence=1.0 if mol['inchi_key'] == identifier else 0.9,
                    match_type="exact" if mol['inchi_key'] == identifier else "name",
                    needs_review=mol['needs_review'],
                    resolution_path=resolution_path,
                    timestamp=datetime.now(timezone.utc).isoformat()
                )

            # Try fuzzy name match
            fuzzy_match = await conn.fetchrow("""
                SELECT
                    m.id::text as molecule_id,
                    m.inchi_key,
                    m.canonical_name,
                    m.needs_review,
                    similarity(LOWER(m.canonical_name), LOWER($1)) as sim
                FROM silver.molecules m
                WHERE similarity(LOWER(m.canonical_name), LOWER($1)) > 0.3
                ORDER BY sim DESC
                LIMIT 1
            """, identifier)

            if fuzzy_match and fuzzy_match['sim'] > 0.5:
                resolution_path.append("fuzzy_match")
                return IdentifierResolutionResponse(
                    success=True,
                    identifier=request.identifier,
                    detected_type="name",
                    molecule_id=fuzzy_match['molecule_id'],
                    inchi_key=fuzzy_match['inchi_key'],
                    canonical_name=fuzzy_match['canonical_name'],
                    confidence=float(fuzzy_match['sim']),
                    match_type="fuzzy",
                    needs_review=True,
                    resolution_path=resolution_path,
                    timestamp=datetime.now(timezone.utc).isoformat()
                )

            # No match found
            resolution_path.append("no_match")
            return IdentifierResolutionResponse(
                success=False,
                identifier=request.identifier,
                detected_type=detected_type,
                molecule_id=None,
                inchi_key=None,
                canonical_name=None,
                confidence=0.0,
                match_type="none",
                needs_review=True,
                resolution_path=resolution_path,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

    except Exception as e:
        logger.error(f"Identifier resolution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/molecules/{molecule_id}", response_model=MoleculeProfileResponse)
async def get_molecule_profile(molecule_id: str):
    """
    Get complete molecule profile from Gold layer.

    Returns aggregated data including:
    - Basic properties (structure, formula, weight)
    - Cross-references (DrugBank, ChEMBL, PubChem, etc.)
    - Clinical trial counts
    - Safety signal summaries
    - Development status
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Get molecule from silver.molecules with identifiers - using medallion architecture
            mol = await conn.fetchrow("""
                SELECT
                    m.id::text as molecule_id,
                    m.canonical_name,
                    m.canonical_smiles,
                    m.inchi_key,
                    m.molecular_formula,
                    m.molecular_weight,
                    (SELECT identifier_value FROM silver.identifier_mappings WHERE molecule_id = m.id AND identifier_type = 'chembl_id' LIMIT 1) as chembl_id,
                    (SELECT identifier_value FROM silver.identifier_mappings WHERE molecule_id = m.id AND identifier_type = 'drugbank_id' LIMIT 1) as drugbank_id,
                    (SELECT identifier_value FROM silver.identifier_mappings WHERE molecule_id = m.id AND identifier_type = 'pubchem_cid' LIMIT 1) as pubchem_cid
                FROM silver.molecules m
                WHERE m.id::text = $1 OR m.inchi_key = $1
                   OR EXISTS (SELECT 1 FROM silver.identifier_mappings im WHERE im.molecule_id = m.id AND im.identifier_value = $1)
                LIMIT 1
            """, molecule_id)

            if not mol:
                raise HTTPException(status_code=404, detail="Molecule not found")

            # Get trial counts - using medallion architecture
            trial_counts = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE UPPER(status) IN ('RECRUITING', 'ACTIVE, NOT RECRUITING')) as active
                FROM silver.clinical_trials
                WHERE molecule_id = $1::uuid OR LOWER(interventions::text) LIKE LOWER($2)
            """, mol["molecule_id"], f'%{mol["canonical_name"]}%') if mol["canonical_name"] else {"total": 0, "active": 0}

            # Get adverse event counts - using medallion architecture
            ae_counts = await conn.fetchrow("""
                SELECT
                    COALESCE(SUM(report_count), 0) as total,
                    COALESCE(SUM(serious_count), 0) as serious
                FROM silver.adverse_events
                WHERE molecule_id = $1::uuid
            """, mol["molecule_id"]) or {"total": 0, "serious": 0}

            # Get publication count from molecule_publications junction table
            pub_count = await conn.fetchval("""
                SELECT COUNT(*) FROM silver.molecule_publications
                WHERE molecule_id = $1::uuid
            """, mol["molecule_id"]) or 0

            return MoleculeProfileResponse(
                success=True,
                molecule_id=mol['molecule_id'],
                inchi_key=mol['inchi_key'],
                canonical_name=mol['canonical_name'] or 'Unknown',
                canonical_smiles=mol['canonical_smiles'],
                molecular_formula=mol['molecular_formula'],
                molecular_weight=float(mol['molecular_weight']) if mol['molecular_weight'] else None,
                molecule_type=None,
                development_status=None,
                max_phase=None,
                therapeutic_areas=None,
                mechanism_of_action=None,
                drugbank_id=mol['drugbank_id'],
                chembl_id=mol['chembl_id'],
                pubchem_cid=mol['pubchem_cid'],
                unii=None,
                cas_number=None,
                total_trials=trial_counts['total'] if trial_counts else 0,
                active_trials=trial_counts['active'] if trial_counts else 0,
                total_adverse_reports=ae_counts['total'] if ae_counts else 0,
                serious_adverse_reports=ae_counts['serious'] if ae_counts else 0,
                has_boxed_warning=False,
                target_count=0,
                publication_count=pub_count,
                aliases=None,
                data_sources=['compounds'],
                timestamp=datetime.now(timezone.utc).isoformat()
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get molecule profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/molecules/{molecule_id}/safety", response_model=SafetySignalsResponse)
async def get_safety_signals(molecule_id: str):
    """
    Get aggregated safety signals for a molecule.

    Includes:
    - FAERS adverse event counts
    - Top adverse events by frequency
    - Boxed warning text (if applicable)
    - PRR/ROR signal metrics
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Get molecule first
            mol = await conn.fetchrow("""
                SELECT id, canonical_name, inchi_key
                FROM silver.molecules
                WHERE id::text = $1 OR inchi_key = $1
                LIMIT 1
            """, molecule_id)

            if not mol:
                raise HTTPException(status_code=404, detail="Molecule not found")

            mol_id = mol['id']

            # Get adverse event counts from silver layer
            ae_counts = await conn.fetchrow("""
                SELECT
                    COALESCE(SUM(report_count), 0) as total_reports,
                    COALESCE(SUM(serious_count), 0) as serious_reports,
                    COALESCE(SUM(death_count), 0) as death_reports,
                    MIN(first_report_date) as first_report,
                    MAX(last_report_date) as last_report
                FROM silver.adverse_events
                WHERE molecule_id = $1
            """, mol_id)

            # Get top adverse events
            top_events = await conn.fetch("""
                SELECT
                    event_term,
                    report_count,
                    serious_count,
                    prr_score,
                    ror_score
                FROM silver.adverse_events
                WHERE molecule_id = $1
                ORDER BY report_count DESC
                LIMIT 10
            """, mol_id)

            top_adverse_events = [
                {
                    "event_term": row['event_term'],
                    "report_count": row['report_count'],
                    "serious_count": row['serious_count'],
                    "prr_score": float(row['prr_score']) if row['prr_score'] else None,
                    "ror_score": float(row['ror_score']) if row['ror_score'] else None,
                }
                for row in top_events
            ] if top_events else None

            # Get boxed warning from drug labels
            boxed_warning = await conn.fetchval("""
                SELECT boxed_warning
                FROM silver.drug_labels
                WHERE molecule_id = $1 AND boxed_warning IS NOT NULL
                LIMIT 1
            """, mol_id)

            return SafetySignalsResponse(
                success=True,
                molecule_id=str(mol_id),
                canonical_name=mol['canonical_name'] or 'Unknown',
                total_reports=ae_counts['total_reports'] or 0 if ae_counts else 0,
                serious_reports=ae_counts['serious_reports'] or 0 if ae_counts else 0,
                death_reports=ae_counts['death_reports'] or 0 if ae_counts else 0,
                top_adverse_events=top_adverse_events,
                boxed_warning=boxed_warning,
                first_report_date=ae_counts['first_report'].isoformat() if ae_counts and ae_counts['first_report'] else None,
                last_report_date=ae_counts['last_report'].isoformat() if ae_counts and ae_counts['last_report'] else None,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get safety signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Resolution Queue Endpoints
# ============================================================================

@router.get("/resolution-queue", response_model=QueueListResponse)
async def list_resolution_queue(
    priority: Optional[str] = Query(None, description="Filter by priority: high, medium, low"),
    identifier_type: Optional[str] = Query(None, description="Filter by identifier type"),
    limit: int = Query(50, ge=1, le=200, description="Maximum items"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """
    List pending items in the resolution queue.

    Items are sorted by confidence score (descending) and creation date.
    Higher priority items (confidence 0.5-0.8) are likely correct and
    should be reviewed first.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return QueueListResponse(
                success=False,
                items=[],
                total_count=0,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        # Build query conditions
        conditions = ["status = 'pending'"]
        params = []
        param_idx = 1

        if priority:
            priority_ranges = {
                'high': (0.5, 0.8),
                'medium': (0.3, 0.5),
                'low': (0.0, 0.3)
            }
            if priority in priority_ranges:
                low, high = priority_ranges[priority]
                conditions.append(f"confidence_score >= ${param_idx} AND confidence_score < ${param_idx + 1}")
                params.extend([low, high])
                param_idx += 2

        if identifier_type:
            conditions.append(f"identifier_type = ${param_idx}")
            params.append(identifier_type)
            param_idx += 1

        async with pool.acquire() as conn:
            # Get total count
            count_query = f"""
                SELECT COUNT(*) FROM silver.resolution_queue
                WHERE {' AND '.join(conditions)}
            """
            total_count = await conn.fetchval(count_query, *params) or 0

            # Get items
            params.extend([limit, offset])
            query = f"""
                SELECT
                    rq.id::text,
                    rq.molecule_id::text,
                    rq.original_identifier,
                    rq.identifier_type,
                    rq.confidence_score,
                    rq.candidate_inchi_keys,
                    rq.status,
                    rq.created_at,
                    m.canonical_name AS molecule_name
                FROM silver.resolution_queue rq
                LEFT JOIN silver.molecules m ON rq.molecule_id = m.id
                WHERE {' AND '.join(conditions)}
                ORDER BY rq.confidence_score DESC, rq.created_at ASC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            rows = await conn.fetch(query, *params)

            items = []
            for row in rows:
                conf = float(row['confidence_score'])
                if conf >= 0.5:
                    item_priority = 'high'
                elif conf >= 0.3:
                    item_priority = 'medium'
                else:
                    item_priority = 'low'

                candidates = row['candidate_inchi_keys']
                if isinstance(candidates, str):
                    import json
                    candidates = json.loads(candidates)

                items.append(QueueItemResponse(
                    id=row['id'],
                    molecule_id=row['molecule_id'],
                    original_identifier=row['original_identifier'],
                    identifier_type=row['identifier_type'],
                    confidence_score=conf,
                    candidate_matches=candidates or [],
                    status=row['status'],
                    priority=item_priority,
                    created_at=row['created_at'].isoformat() if row['created_at'] else ''
                ))

        return QueueListResponse(
            success=True,
            items=items,
            total_count=total_count,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to list resolution queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resolution-queue/stats", response_model=QueueStatsResponse)
async def get_queue_stats():
    """
    Get resolution queue statistics.

    Returns:
    - Pending counts by priority
    - Today's resolution counts
    - Average resolution time
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return QueueStatsResponse(
                success=False,
                pending_count=0,
                pending_by_priority={"high": 0, "medium": 0, "low": 0},
                approved_today=0,
                rejected_today=0,
                merged_today=0,
                avg_resolution_time_hours=0.0,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        async with pool.acquire() as conn:
            try:
                # Get pending counts by priority (using spec-defined ranges)
                pending_stats = await conn.fetchrow("""
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE confidence_score >= 0.5 AND confidence_score < 0.8) AS high,
                        COUNT(*) FILTER (WHERE confidence_score >= 0.3 AND confidence_score < 0.5) AS medium,
                        COUNT(*) FILTER (WHERE confidence_score < 0.3) AS low
                    FROM silver.resolution_queue
                    WHERE status = 'pending'
                """)

                # Get today's resolution counts
                today_stats = await conn.fetchrow("""
                    SELECT
                        COUNT(*) FILTER (WHERE resolution_action = 'approve') AS approved,
                        COUNT(*) FILTER (WHERE resolution_action = 'reject') AS rejected,
                        COUNT(*) FILTER (WHERE resolution_action = 'merge') AS merged
                    FROM silver.resolution_queue
                    WHERE reviewed_at >= CURRENT_DATE
                """)

                # Get average resolution time (last 30 days)
                avg_time = await conn.fetchval("""
                    SELECT AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at)) / 3600)
                    FROM silver.resolution_queue
                    WHERE reviewed_at IS NOT NULL
                      AND reviewed_at >= NOW() - INTERVAL '30 days'
                """)

                return QueueStatsResponse(
                    success=True,
                    pending_count=pending_stats['total'] or 0,
                    pending_by_priority={
                        "high": pending_stats['high'] or 0,
                        "medium": pending_stats['medium'] or 0,
                        "low": pending_stats['low'] or 0
                    },
                    approved_today=today_stats['approved'] or 0,
                    rejected_today=today_stats['rejected'] or 0,
                    merged_today=today_stats['merged'] or 0,
                    avg_resolution_time_hours=float(avg_time) if avg_time else 0.0,
                    timestamp=datetime.now(timezone.utc).isoformat()
                )

            except Exception as table_err:
                logger.warning(f"Resolution queue table may not exist: {table_err}")
                return QueueStatsResponse(
                    success=True,
                    pending_count=0,
                    pending_by_priority={"high": 0, "medium": 0, "low": 0},
                    approved_today=0,
                    rejected_today=0,
                    merged_today=0,
                    avg_resolution_time_hours=0.0,
                    timestamp=datetime.now(timezone.utc).isoformat()
                )

    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resolution-queue/{item_id}", response_model=QueueItemResponse)
async def get_queue_item(item_id: str):
    """Get a single resolution queue item."""
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    rq.id::text,
                    rq.molecule_id::text,
                    rq.original_identifier,
                    rq.identifier_type,
                    rq.confidence_score,
                    rq.candidate_inchi_keys,
                    rq.status,
                    rq.created_at,
                    m.canonical_name AS molecule_name
                FROM silver.resolution_queue rq
                LEFT JOIN silver.molecules m ON rq.molecule_id = m.id
                WHERE rq.id = $1::uuid
            """, item_id)

            if not row:
                raise HTTPException(status_code=404, detail="Queue item not found")

            conf = float(row['confidence_score'])
            if conf >= 0.5:
                item_priority = 'high'
            elif conf >= 0.3:
                item_priority = 'medium'
            else:
                item_priority = 'low'

            candidates = row['candidate_inchi_keys']
            if isinstance(candidates, str):
                import json
                candidates = json.loads(candidates)

            return QueueItemResponse(
                id=row['id'],
                molecule_id=row['molecule_id'],
                original_identifier=row['original_identifier'],
                identifier_type=row['identifier_type'],
                confidence_score=conf,
                candidate_matches=candidates or [],
                status=row['status'],
                priority=item_priority,
                created_at=row['created_at'].isoformat() if row['created_at'] else ''
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get queue item: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resolution-queue/{item_id}/action", response_model=QueueActionResponse)
async def perform_queue_action(item_id: str, request: QueueActionRequest):
    """
    Perform an action on a resolution queue item.

    Actions:
    - approve: Confirm resolution, promote to Gold layer
    - reject: Mark as incorrect, optionally delete molecule
    - merge: Merge with another molecule (requires merge_target_id)
    """
    try:
        if request.action not in ["approve", "reject", "merge"]:
            raise HTTPException(status_code=400, detail="Invalid action")

        if request.action == "merge" and not request.merge_target_id:
            raise HTTPException(status_code=400, detail="merge_target_id required for merge action")

        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        queue_service = ResolutionQueueService(pool)

        if request.action == "approve":
            success = await queue_service.approve(
                item_id=item_id,
                reviewed_by=request.reviewed_by,
                notes=request.notes
            )
            message = "Resolution approved, molecule promoted to Gold layer" if success else "Failed to approve"

        elif request.action == "reject":
            success = await queue_service.reject(
                item_id=item_id,
                reviewed_by=request.reviewed_by,
                notes=request.notes,
                delete_molecule=request.delete_molecule
            )
            if request.delete_molecule:
                message = "Resolution rejected, molecule deleted" if success else "Failed to reject"
            else:
                message = "Resolution rejected, molecule remains quarantined" if success else "Failed to reject"

        elif request.action == "merge":
            success = await queue_service.merge(
                item_id=item_id,
                target_molecule_id=request.merge_target_id,
                reviewed_by=request.reviewed_by,
                notes=request.notes
            )
            message = f"Molecule merged into {request.merge_target_id}" if success else "Failed to merge"

        if not success:
            raise HTTPException(status_code=400, detail=message)

        return QueueActionResponse(
            success=True,
            item_id=item_id,
            action=request.action,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to perform queue action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BulkApproveRequest(BaseModel):
    """Request for bulk approve."""
    item_ids: List[str]
    reviewed_by: str


@router.post("/resolution-queue/bulk-approve", response_model=Dict[str, Any])
async def bulk_approve_queue_items(request: BulkApproveRequest):
    """Bulk approve multiple resolution queue items."""
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        results = {}
        approved_count = 0

        async with pool.acquire() as conn:
            for item_id in request.item_ids:
                try:
                    # Update resolution queue item status
                    result = await conn.execute("""
                        UPDATE silver.resolution_queue
                        SET status = 'approved',
                            reviewed_by = $1,
                            reviewed_at = NOW(),
                            updated_at = NOW()
                        WHERE id = $2::uuid AND status = 'pending'
                    """, request.reviewed_by, item_id)

                    # Check if any row was updated
                    if result and 'UPDATE 1' in result:
                        results[item_id] = True
                        approved_count += 1

                        # Promote molecule to Gold layer by setting needs_review = FALSE
                        await conn.execute("""
                            UPDATE silver.molecules
                            SET needs_review = FALSE,
                                updated_at = NOW()
                            WHERE id = (
                                SELECT molecule_id FROM silver.resolution_queue WHERE id = $1::uuid
                            )
                        """, item_id)
                    else:
                        results[item_id] = False
                except Exception as e:
                    logger.warning(f"Failed to approve item {item_id}: {e}")
                    results[item_id] = False

        return {
            "success": True,
            "approved_count": approved_count,
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to bulk approve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resolution-queue/{item_id}/potential-duplicates")
async def find_potential_duplicates(
    item_id: str,
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Similarity threshold")
):
    """
    Find potential duplicate molecules for a queue item.

    Used during merge workflow to identify existing molecules
    that might be duplicates of the quarantined item.

    Returns molecules with similar names using trigram similarity.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Get the queue item and its molecule
            item = await conn.fetchrow("""
                SELECT rq.molecule_id, m.canonical_name, m.inchi_key
                FROM silver.resolution_queue rq
                LEFT JOIN silver.molecules m ON rq.molecule_id = m.id
                WHERE rq.id = $1::uuid
            """, item_id)

            if not item:
                raise HTTPException(status_code=404, detail="Queue item not found")

            if not item['canonical_name']:
                return {
                    "success": True,
                    "item_id": item_id,
                    "duplicates": [],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            # Find similar molecules using trigram similarity
            rows = await conn.fetch("""
                SELECT
                    m.id::text AS molecule_id,
                    m.canonical_name,
                    m.inchi_key,
                    m.data_sources,
                    m.development_status,
                    similarity(lower(m.canonical_name), lower($1)) AS name_similarity
                FROM silver.molecules m
                WHERE m.id != $2::uuid
                  AND m.needs_review = FALSE
                  AND similarity(lower(m.canonical_name), lower($1)) > $3
                ORDER BY name_similarity DESC
                LIMIT 10
            """, item['canonical_name'], item['molecule_id'], threshold)

            duplicates = [
                {
                    "molecule_id": row['molecule_id'],
                    "canonical_name": row['canonical_name'],
                    "inchi_key": row['inchi_key'],
                    "data_sources": row['data_sources'],
                    "development_status": row['development_status'],
                    "similarity": float(row['name_similarity'])
                }
                for row in rows
            ]

            return {
                "success": True,
                "item_id": item_id,
                "duplicates": duplicates,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to find potential duplicates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Pipeline Status & Ingestion Endpoints
# ============================================================================

@router.get("/status", response_model=PipelineStatusResponse)
async def get_pipeline_status():
    """
    Get current data pipeline status and statistics.

    Returns counts for:
    - Molecules (total, published, quarantined)
    - Clinical trials (total, active)
    - Adverse events (molecules with events, total reports)
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return PipelineStatusResponse(
                success=False,
                molecules={"total": 0, "published": 0, "quarantined": 0},
                trials={"total": 0, "active": 0},
                adverse_events={"molecules_with_events": 0, "total_reports": 0},
                last_refresh=None,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        async with pool.acquire() as conn:
            # Get molecule counts - using medallion architecture
            mol_total = await conn.fetchval("SELECT COUNT(*) FROM silver.molecules") or 0
            mol_with_ids = await conn.fetchval(
                "SELECT COUNT(*) FROM silver.molecules WHERE canonical_smiles IS NOT NULL AND inchi_key IS NOT NULL"
            ) or 0

            # Get trial counts - using medallion architecture
            trials_total = await conn.fetchval("SELECT COUNT(*) FROM silver.clinical_trials") or 0
            trials_active = await conn.fetchval("""
                SELECT COUNT(*) FROM silver.clinical_trials
                WHERE UPPER(status) IN ('RECRUITING', 'ACTIVE, NOT RECRUITING', 'ENROLLING BY INVITATION')
            """) or 0

            # Get adverse event counts - dynamically from silver layer
            ae_molecules = await conn.fetchval(
                "SELECT COUNT(DISTINCT molecule_id) FROM silver.adverse_events"
            ) or 0
            ae_reports = await conn.fetchval(
                "SELECT COALESCE(SUM(report_count), 0) FROM silver.adverse_events"
            ) or 0

        return PipelineStatusResponse(
            success=True,
            molecules={
                "total": mol_total,
                "published": mol_with_ids,
                "quarantined": mol_total - mol_with_ids
            },
            trials={
                "total": trials_total,
                "active": trials_active
            },
            adverse_events={
                "molecules_with_events": ae_molecules,
                "total_reports": ae_reports
            },
            last_refresh=datetime.now(timezone.utc).isoformat(),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to get pipeline status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh/gold", response_model=IngestionTriggerResponse)
async def trigger_gold_refresh(background_tasks: BackgroundTasks):
    """
    Trigger a Gold layer refresh.

    Updates all pre-aggregated views and computed metrics.
    Runs asynchronously in the background.
    """
    try:
        from uuid import uuid4

        job_id = str(uuid4())

        async def run_gold_refresh():
            try:
                gold_service = await get_gold_service()
                if gold_service:
                    await gold_service.refresh_all()
                    logger.info(f"Gold refresh job {job_id} completed")
            except Exception as e:
                logger.error(f"Gold refresh job {job_id} failed: {e}")

        background_tasks.add_task(run_gold_refresh)

        return IngestionTriggerResponse(
            success=True,
            message="Gold layer refresh initiated",
            job_id=job_id,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to trigger Gold refresh: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest/{source}", response_model=IngestionTriggerResponse)
async def trigger_source_ingestion(
    source: str,
    background_tasks: BackgroundTasks
):
    """
    Trigger ingestion for a specific data source.

    Supports all registered sources from the database (raw.sync_schedules).
    """
    pool = await get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Check database for registered sources (fully dynamic)
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM raw.sync_schedules WHERE source = $1",
            source
        )
        if not exists:
            # Get available sources for error message
            available = await conn.fetch(
                "SELECT source FROM raw.sync_schedules WHERE enabled = true ORDER BY source"
            )
            available_sources = [r['source'] for r in available]
            raise HTTPException(
                status_code=404,
                detail=f"Source '{source}' not found. Available sources: {', '.join(available_sources)}"
            )

    try:
        from uuid import uuid4
        from ...services.data_platform.sync_runner import run_pipeline

        job_id = str(uuid4())

        async def run_ingestion():
            try:
                result = await run_pipeline(
                    sources=[source],
                    tier='manual',
                    full_refresh=False,
                    skip_raw=False,
                    skip_bronze=False,
                    skip_silver=False,
                    skip_gold=False,
                )
                logger.info(f"Ingestion job {job_id} completed: {result['status']}")
            except Exception as e:
                logger.error(f"Ingestion job {job_id} failed: {e}")

        background_tasks.add_task(run_ingestion)

        return IngestionTriggerResponse(
            success=True,
            message=f"Ingestion triggered for {source}",
            job_id=job_id,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to trigger {source} ingestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/run", response_model=IngestionTriggerResponse)
async def trigger_full_pipeline(
    background_tasks: BackgroundTasks,
    tier: str = Query("manual", description="Sync tier: daily, weekly, monthly, manual, on_demand"),
    transform_only: bool = Query(False, description="Skip API fetching, only transform existing data"),
):
    """
    Trigger a full pipeline run.

    This runs the complete Raw → Bronze → Silver → Gold pipeline.
    Use transform_only=true to process existing data without fetching from APIs.
    Sources are loaded dynamically from raw.sync_schedules based on tier.
    """
    try:
        from uuid import uuid4
        from ...services.data_platform.sync_runner import run_pipeline

        job_id = str(uuid4())

        # Load sources dynamically from database based on tier
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            if tier == 'manual':
                # For manual, get all enabled sources
                rows = await conn.fetch(
                    "SELECT source FROM raw.sync_schedules WHERE enabled = true ORDER BY priority DESC"
                )
            else:
                # Get sources for specific tier
                rows = await conn.fetch(
                    "SELECT source FROM raw.sync_schedules WHERE tier = $1 AND enabled = true ORDER BY priority DESC",
                    tier
                )
            sources = [r['source'] for r in rows]

        if not sources:
            raise HTTPException(
                status_code=400,
                detail=f"No enabled sources found for tier '{tier}'. Configure sources in raw.sync_schedules."
            )

        async def run_full_pipeline():
            try:
                result = await run_pipeline(
                    sources=sources,
                    tier=tier,
                    full_refresh=False,
                    skip_raw=transform_only,
                    skip_bronze=False,
                    skip_silver=False,
                    skip_gold=False,
                )
                logger.info(f"Pipeline job {job_id} completed: {result['status']}")
            except Exception as e:
                logger.error(f"Pipeline job {job_id} failed: {e}")

        background_tasks.add_task(run_full_pipeline)

        return IngestionTriggerResponse(
            success=True,
            message=f"Full pipeline triggered (tier={tier}, transform_only={transform_only})",
            job_id=job_id,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to trigger pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Competitive Intelligence Endpoints
# ============================================================================

@router.get("/competitive-landscape")
async def get_competitive_landscape(
    therapeutic_area: Optional[str] = Query(None, description="Filter by therapeutic area"),
    mechanism: Optional[str] = Query(None, description="Filter by mechanism of action"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results")
):
    """
    Get competitive landscape data.

    Returns molecules in active development with:
    - Phase distribution
    - Active trial counts
    - Sponsor information
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return {
                "success": False,
                "results": [],
                "count": 0,
                "filters": {"therapeutic_area": therapeutic_area, "mechanism": mechanism},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        async with pool.acquire() as conn:
            # Build dynamic query with optional filters
            query = """
                SELECT
                    molecule_id::text,
                    inchi_key,
                    canonical_name,
                    therapeutic_areas,
                    mechanism_of_action,
                    development_status,
                    max_phase,
                    active_trials,
                    phase_distribution,
                    indications,
                    sponsors
                FROM gold.competitive_landscape
                WHERE 1=1
            """
            params = []
            param_idx = 1

            if therapeutic_area:
                query += f" AND therapeutic_areas::text ILIKE ${param_idx}"
                params.append(f'%{therapeutic_area}%')
                param_idx += 1

            if mechanism:
                query += f" AND mechanism_of_action ILIKE ${param_idx}"
                params.append(f'%{mechanism}%')
                param_idx += 1

            query += f" ORDER BY COALESCE(active_trials, 0) DESC, max_phase DESC NULLS LAST LIMIT ${param_idx}"
            params.append(limit)

            try:
                rows = await conn.fetch(query, *params)
                results = []
                for row in rows:
                    results.append({
                        "molecule_id": row['molecule_id'],
                        "inchi_key": row['inchi_key'],
                        "canonical_name": row['canonical_name'],
                        "therapeutic_areas": row['therapeutic_areas'],
                        "mechanism_of_action": row['mechanism_of_action'],
                        "development_status": row['development_status'],
                        "max_phase": row['max_phase'],
                        "active_trials": row['active_trials'],
                        "phase_distribution": row['phase_distribution'],
                        "indications": row['indications'],
                        "sponsors": row['sponsors'],
                    })
            except Exception as e:
                logger.warning(f"Gold view query failed, trying fallback: {e}")
                # Fallback to silver layer if gold view doesn't exist
                rows = await conn.fetch("""
                    SELECT
                        m.id::text as molecule_id,
                        m.inchi_key,
                        m.canonical_name,
                        m.therapeutic_areas,
                        m.mechanism_of_action,
                        m.development_status,
                        m.max_phase,
                        COUNT(DISTINCT ct.nct_id) FILTER (
                            WHERE ct.status IN ('Recruiting', 'Active, not recruiting')
                        ) as active_trials
                    FROM silver.molecules m
                    LEFT JOIN silver.clinical_trials ct ON m.id = ct.molecule_id
                    WHERE m.needs_review = FALSE
                      AND m.development_status IN ('phase_1', 'phase_2', 'phase_3', 'approved')
                    GROUP BY m.id
                    ORDER BY active_trials DESC, m.max_phase DESC NULLS LAST
                    LIMIT $1
                """, limit)
                results = [dict(row) for row in rows]

        return {
            "success": True,
            "results": results,
            "count": len(results),
            "filters": {
                "therapeutic_area": therapeutic_area,
                "mechanism": mechanism
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get competitive landscape: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company-pipeline/{company}")
async def get_company_pipeline(
    company: str,
    phase: Optional[str] = Query(None, description="Filter by phase"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results")
):
    """
    Get pipeline for a specific company.

    Returns all molecules being developed by the company with:
    - Development status
    - Trial information
    - Indications
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return {
                "success": False,
                "company": company,
                "pipeline": [],
                "count": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        async with pool.acquire() as conn:
            # Build dynamic query with optional phase filter
            query = """
                SELECT
                    company,
                    molecule_id::text,
                    inchi_key,
                    canonical_name,
                    development_status,
                    phase,
                    trial_status,
                    indications,
                    trial_count,
                    latest_trial_start
                FROM gold.company_pipeline
                WHERE LOWER(company) LIKE LOWER($1)
            """
            params = [f'%{company}%']
            param_idx = 2

            if phase:
                query += f" AND LOWER(phase) LIKE LOWER(${param_idx})"
                params.append(f'%{phase}%')
                param_idx += 1

            query += f" ORDER BY trial_count DESC, latest_trial_start DESC NULLS LAST LIMIT ${param_idx}"
            params.append(limit)

            try:
                rows = await conn.fetch(query, *params)
                pipeline = []
                for row in rows:
                    pipeline.append({
                        "company": row['company'],
                        "molecule_id": row['molecule_id'],
                        "inchi_key": row['inchi_key'],
                        "canonical_name": row['canonical_name'],
                        "development_status": row['development_status'],
                        "phase": row['phase'],
                        "trial_status": row['trial_status'],
                        "indications": row['indications'],
                        "trial_count": row['trial_count'],
                        "latest_trial_start": row['latest_trial_start'].isoformat() if row['latest_trial_start'] else None,
                    })
            except Exception as e:
                logger.warning(f"Gold view query failed, trying fallback: {e}")
                # Fallback to silver layer
                rows = await conn.fetch("""
                    SELECT
                        ct.sponsor as company,
                        m.id::text as molecule_id,
                        m.inchi_key,
                        m.canonical_name,
                        m.development_status,
                        ct.phase,
                        ct.status as trial_status,
                        ct.conditions as indications,
                        COUNT(DISTINCT ct.nct_id) as trial_count,
                        MAX(ct.start_date) as latest_trial_start
                    FROM silver.clinical_trials ct
                    JOIN silver.molecules m ON ct.molecule_id = m.id
                    WHERE m.needs_review = FALSE
                      AND LOWER(ct.sponsor) LIKE LOWER($1)
                    GROUP BY ct.sponsor, m.id, m.inchi_key, m.canonical_name, m.development_status, ct.phase, ct.status, ct.conditions
                    ORDER BY trial_count DESC
                    LIMIT $2
                """, f'%{company}%', limit)
                pipeline = []
                for row in rows:
                    pipeline.append({
                        "company": row['company'],
                        "molecule_id": row['molecule_id'],
                        "inchi_key": row['inchi_key'],
                        "canonical_name": row['canonical_name'],
                        "development_status": row['development_status'],
                        "phase": row['phase'],
                        "trial_status": row['trial_status'],
                        "indications": row['indications'],
                        "trial_count": row['trial_count'],
                        "latest_trial_start": row['latest_trial_start'].isoformat() if row['latest_trial_start'] else None,
                    })

        return {
            "success": True,
            "company": company,
            "pipeline": pipeline,
            "count": len(pipeline),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get company pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/molecules/{molecule_id}/evidence")
async def get_lifecycle_evidence(
    molecule_id: str,
    evidence_type: Optional[str] = Query(None, description="Filter by type: clinical_trial, drug_label"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results")
):
    """
    Get lifecycle evidence for a molecule.

    Returns supporting evidence for lifecycle stage detection:
    - Clinical trials
    - Drug labels
    - Regulatory milestones
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return {
                "success": False,
                "molecule_id": molecule_id,
                "evidence": [],
                "count": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        async with pool.acquire() as conn:
            # Build query with optional type filter
            query = """
                SELECT
                    molecule_id::text,
                    inchi_key,
                    canonical_name,
                    evidence_type,
                    evidence_id,
                    evidence_title,
                    evidence_detail,
                    evidence_status,
                    evidence_source,
                    evidence_date,
                    evidence_url
                FROM gold.lifecycle_evidence
                WHERE molecule_id::text = $1 OR inchi_key = $1
            """
            params = [molecule_id]
            param_idx = 2

            if evidence_type:
                query += f" AND evidence_type = ${param_idx}"
                params.append(evidence_type)
                param_idx += 1

            query += f" ORDER BY evidence_date DESC NULLS LAST LIMIT ${param_idx}"
            params.append(limit)

            try:
                rows = await conn.fetch(query, *params)
                evidence = []
                for row in rows:
                    evidence.append({
                        "molecule_id": row['molecule_id'],
                        "inchi_key": row['inchi_key'],
                        "canonical_name": row['canonical_name'],
                        "evidence_type": row['evidence_type'],
                        "evidence_id": row['evidence_id'],
                        "evidence_title": row['evidence_title'],
                        "evidence_detail": row['evidence_detail'],
                        "evidence_status": row['evidence_status'],
                        "evidence_source": row['evidence_source'],
                        "evidence_date": row['evidence_date'].isoformat() if row['evidence_date'] else None,
                        "evidence_url": row['evidence_url'],
                    })
            except Exception as e:
                logger.warning(f"Gold view query failed, trying fallback: {e}")
                # Fallback: query clinical trials and drug labels directly
                evidence = []

                # Get molecule ID first
                mol = await conn.fetchrow("""
                    SELECT id FROM silver.molecules
                    WHERE id::text = $1 OR inchi_key = $1
                    LIMIT 1
                """, molecule_id)

                if mol:
                    mol_id = mol['id']

                    # Get clinical trial evidence
                    if not evidence_type or evidence_type == 'clinical_trial':
                        trials = await conn.fetch("""
                            SELECT
                                nct_id as evidence_id,
                                brief_title as evidence_title,
                                phase as evidence_detail,
                                overall_status as evidence_status,
                                'ClinicalTrials.gov' as evidence_source,
                                start_date as evidence_date
                            FROM silver.clinical_trials
                            WHERE molecule_id = $1
                            ORDER BY start_date DESC NULLS LAST
                            LIMIT $2
                        """, mol_id, limit)

                        for row in trials:
                            evidence.append({
                                "molecule_id": molecule_id,
                                "evidence_type": "clinical_trial",
                                "evidence_id": row['evidence_id'],
                                "evidence_title": row['evidence_title'],
                                "evidence_detail": row['evidence_detail'],
                                "evidence_status": row['evidence_status'],
                                "evidence_source": row['evidence_source'],
                                "evidence_date": row['evidence_date'].isoformat() if row['evidence_date'] else None,
                                "evidence_url": f"https://clinicaltrials.gov/study/{row['evidence_id']}",
                            })

                    # Get drug label evidence
                    if not evidence_type or evidence_type == 'drug_label':
                        labels = await conn.fetch("""
                            SELECT
                                set_id as evidence_id,
                                COALESCE(brand_name, generic_name) as evidence_title,
                                product_type as evidence_detail,
                                CASE WHEN boxed_warning IS NOT NULL THEN 'Has Boxed Warning' ELSE 'Active' END as evidence_status,
                                'DailyMed' as evidence_source,
                                effective_date as evidence_date
                            FROM silver.drug_labels
                            WHERE molecule_id = $1
                            ORDER BY effective_date DESC NULLS LAST
                            LIMIT $2
                        """, mol_id, limit)

                        for row in labels:
                            evidence.append({
                                "molecule_id": molecule_id,
                                "evidence_type": "drug_label",
                                "evidence_id": row['evidence_id'],
                                "evidence_title": row['evidence_title'],
                                "evidence_detail": row['evidence_detail'],
                                "evidence_status": row['evidence_status'],
                                "evidence_source": row['evidence_source'],
                                "evidence_date": row['evidence_date'].isoformat() if row['evidence_date'] else None,
                                "evidence_url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={row['evidence_id']}",
                            })

        return {
            "success": True,
            "molecule_id": molecule_id,
            "evidence": evidence,
            "count": len(evidence),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get lifecycle evidence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Gold Layer Aggregation Endpoints
# ============================================================================

class GoldMoleculeProfileItem(BaseModel):
    """Gold layer molecule profile item."""
    molecule_id: str
    inchi_key: Optional[str]
    canonical_name: str
    canonical_smiles: Optional[str]
    molecular_weight: Optional[float]
    development_status: Optional[str]
    max_phase: Optional[int]
    therapeutic_areas: Optional[List[str]]
    mechanism_of_action: Optional[str]
    active_trials: int = 0
    total_adverse_reports: int = 0
    has_boxed_warning: bool = False
    data_sources: List[str] = []


class GoldMoleculeProfilesResponse(BaseModel):
    """Gold layer molecule profiles response."""
    success: bool
    profiles: List[GoldMoleculeProfileItem]
    total_count: int
    page: int
    page_size: int
    timestamp: str


class GoldSafetySignalItem(BaseModel):
    """Gold layer safety signal item."""
    molecule_id: str
    canonical_name: str
    inchi_key: Optional[str]
    total_reports: int
    serious_reports: int
    death_reports: int
    has_boxed_warning: bool
    top_event: Optional[str]
    signal_score: Optional[float]


class GoldSafetySignalsResponse(BaseModel):
    """Gold layer safety signals response."""
    success: bool
    signals: List[GoldSafetySignalItem]
    total_count: int
    timestamp: str


class GoldLifecycleStageItem(BaseModel):
    """Gold layer lifecycle stage item."""
    molecule_id: str
    canonical_name: str
    inchi_key: Optional[str]
    current_stage: str
    stage_entered_date: Optional[str]
    previous_stage: Optional[str]
    days_in_current_stage: Optional[int]
    next_expected_stage: Optional[str]


class GoldLifecycleStagesResponse(BaseModel):
    """Gold layer lifecycle stages response."""
    success: bool
    molecules: List[GoldLifecycleStageItem]
    stage_distribution: Dict[str, int]
    total_count: int
    timestamp: str


@router.get("/gold/molecule-profiles", response_model=GoldMoleculeProfilesResponse)
async def list_gold_molecule_profiles(
    development_status: Optional[str] = Query(None, description="Filter by status: preclinical, phase_1, phase_2, phase_3, approved, withdrawn"),
    therapeutic_area: Optional[str] = Query(None, description="Filter by therapeutic area"),
    has_trials: Optional[bool] = Query(None, description="Filter to molecules with active trials"),
    min_adverse_reports: Optional[int] = Query(None, ge=0, description="Minimum adverse event reports"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Results per page")
):
    """
    List aggregated molecule profiles from Gold layer.

    Returns pre-computed profiles with:
    - Basic properties and identifiers
    - Development status and max phase
    - Active trial counts
    - Adverse event summaries
    - Data source coverage
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return GoldMoleculeProfilesResponse(
                success=False,
                profiles=[],
                total_count=0,
                page=page,
                page_size=page_size,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        async with pool.acquire() as conn:
            # Build query with filters
            conditions = ["needs_review = FALSE"]
            params = []
            param_idx = 1

            if development_status:
                conditions.append(f"development_status = ${param_idx}")
                params.append(development_status)
                param_idx += 1

            if therapeutic_area:
                conditions.append(f"therapeutic_areas::text ILIKE ${param_idx}")
                params.append(f'%{therapeutic_area}%')
                param_idx += 1

            where_clause = " AND ".join(conditions)

            # Get total count
            count_query = f"SELECT COUNT(*) FROM silver.molecules WHERE {where_clause}"
            total_count = await conn.fetchval(count_query, *params) or 0

            # Get profiles with aggregated data
            offset = (page - 1) * page_size
            params.extend([page_size, offset])

            query = f"""
                SELECT
                    m.id::text as molecule_id,
                    m.inchi_key,
                    m.canonical_name,
                    m.canonical_smiles,
                    m.molecular_weight,
                    m.development_status,
                    m.max_phase,
                    m.therapeutic_areas,
                    m.mechanism_of_action,
                    m.data_sources,
                    COALESCE(trial_counts.active_trials, 0) as active_trials,
                    COALESCE(ae_counts.total_reports, 0) as total_adverse_reports,
                    COALESCE(label_info.has_boxed_warning, FALSE) as has_boxed_warning
                FROM silver.molecules m
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) FILTER (
                        WHERE status IN ('Recruiting', 'Active, not recruiting', 'Enrolling by invitation')
                    ) as active_trials
                    FROM silver.clinical_trials
                    WHERE molecule_id = m.id
                ) trial_counts ON TRUE
                LEFT JOIN LATERAL (
                    SELECT COALESCE(SUM(report_count), 0) as total_reports
                    FROM silver.adverse_events
                    WHERE molecule_id = m.id
                ) ae_counts ON TRUE
                LEFT JOIN LATERAL (
                    SELECT EXISTS(
                        SELECT 1 FROM silver.drug_labels
                        WHERE molecule_id = m.id AND boxed_warning IS NOT NULL
                    ) as has_boxed_warning
                ) label_info ON TRUE
                WHERE {where_clause}
            """

            # Add has_trials filter if specified
            if has_trials is not None:
                if has_trials:
                    query += " AND COALESCE(trial_counts.active_trials, 0) > 0"
                else:
                    query += " AND COALESCE(trial_counts.active_trials, 0) = 0"

            # Add min_adverse_reports filter if specified
            if min_adverse_reports is not None:
                query += f" AND COALESCE(ae_counts.total_reports, 0) >= ${param_idx}"
                params.insert(-2, min_adverse_reports)  # Insert before limit and offset
                param_idx += 1

            query += f" ORDER BY COALESCE(trial_counts.active_trials, 0) DESC, m.canonical_name LIMIT ${param_idx - 1} OFFSET ${param_idx}"

            try:
                rows = await conn.fetch(query, *params)
            except Exception as e:
                logger.warning(f"Complex query failed, using fallback: {e}")
                # Simpler fallback query
                rows = await conn.fetch(f"""
                    SELECT
                        m.id::text as molecule_id,
                        m.inchi_key,
                        m.canonical_name,
                        m.canonical_smiles,
                        m.molecular_weight,
                        m.development_status,
                        m.max_phase,
                        m.therapeutic_areas,
                        m.mechanism_of_action,
                        m.data_sources,
                        0 as active_trials,
                        0 as total_adverse_reports,
                        FALSE as has_boxed_warning
                    FROM silver.molecules m
                    WHERE {where_clause}
                    ORDER BY m.canonical_name
                    LIMIT $1 OFFSET $2
                """, page_size, offset)

            profiles = []
            for row in rows:
                profiles.append(GoldMoleculeProfileItem(
                    molecule_id=row['molecule_id'],
                    inchi_key=row['inchi_key'],
                    canonical_name=row['canonical_name'] or 'Unknown',
                    canonical_smiles=row['canonical_smiles'],
                    molecular_weight=float(row['molecular_weight']) if row['molecular_weight'] else None,
                    development_status=row['development_status'],
                    max_phase=row['max_phase'],
                    therapeutic_areas=row['therapeutic_areas'],
                    mechanism_of_action=row['mechanism_of_action'],
                    active_trials=row['active_trials'] or 0,
                    total_adverse_reports=row['total_adverse_reports'] or 0,
                    has_boxed_warning=row['has_boxed_warning'] or False,
                    data_sources=row['data_sources'] or [],
                ))

        return GoldMoleculeProfilesResponse(
            success=True,
            profiles=profiles,
            total_count=total_count,
            page=page,
            page_size=page_size,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to list gold molecule profiles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gold/safety-signals", response_model=GoldSafetySignalsResponse)
async def list_gold_safety_signals(
    min_reports: int = Query(10, ge=0, description="Minimum total reports"),
    serious_only: bool = Query(False, description="Only show molecules with serious events"),
    boxed_warning_only: bool = Query(False, description="Only show molecules with boxed warnings"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results")
):
    """
    List aggregated safety signals from Gold layer.

    Returns molecules with significant safety data:
    - Total and serious adverse event counts
    - Death report counts
    - Boxed warning status
    - Top adverse event term
    - Computed signal score
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return GoldSafetySignalsResponse(
                success=False,
                signals=[],
                total_count=0,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        async with pool.acquire() as conn:
            # Try gold view first
            try:
                rows = await conn.fetch("""
                    SELECT
                        molecule_id::text,
                        canonical_name,
                        inchi_key,
                        total_reports,
                        serious_reports,
                        death_reports,
                        has_boxed_warning,
                        top_event,
                        signal_score
                    FROM gold.safety_signals
                    WHERE total_reports >= $1
                      AND ($2 = FALSE OR serious_reports > 0)
                      AND ($3 = FALSE OR has_boxed_warning = TRUE)
                    ORDER BY signal_score DESC NULLS LAST, total_reports DESC
                    LIMIT $4
                """, min_reports, serious_only, boxed_warning_only, limit)
            except Exception as e:
                logger.warning(f"Gold view query failed, using fallback: {e}")
                # Fallback: aggregate from silver layer
                rows = await conn.fetch("""
                    SELECT
                        m.id::text as molecule_id,
                        m.canonical_name,
                        m.inchi_key,
                        COALESCE(SUM(ae.report_count), 0) as total_reports,
                        COALESCE(SUM(ae.serious_count), 0) as serious_reports,
                        COALESCE(SUM(ae.death_count), 0) as death_reports,
                        EXISTS(
                            SELECT 1 FROM silver.drug_labels dl
                            WHERE dl.molecule_id = m.id AND dl.boxed_warning IS NOT NULL
                        ) as has_boxed_warning,
                        (
                            SELECT event_term FROM silver.adverse_events
                            WHERE molecule_id = m.id
                            ORDER BY report_count DESC
                            LIMIT 1
                        ) as top_event,
                        -- Simple signal score: weighted combination
                        (COALESCE(SUM(ae.serious_count), 0) * 2.0 + COALESCE(SUM(ae.death_count), 0) * 5.0) /
                            NULLIF(COALESCE(SUM(ae.report_count), 1), 0) as signal_score
                    FROM silver.molecules m
                    LEFT JOIN silver.adverse_events ae ON ae.molecule_id = m.id
                    WHERE m.needs_review = FALSE
                    GROUP BY m.id, m.canonical_name, m.inchi_key
                    HAVING COALESCE(SUM(ae.report_count), 0) >= $1
                       AND ($2 = FALSE OR COALESCE(SUM(ae.serious_count), 0) > 0)
                       AND ($3 = FALSE OR EXISTS(
                           SELECT 1 FROM silver.drug_labels dl
                           WHERE dl.molecule_id = m.id AND dl.boxed_warning IS NOT NULL
                       ))
                    ORDER BY signal_score DESC NULLS LAST, total_reports DESC
                    LIMIT $4
                """, min_reports, serious_only, boxed_warning_only, limit)

            signals = []
            for row in rows:
                signals.append(GoldSafetySignalItem(
                    molecule_id=row['molecule_id'],
                    canonical_name=row['canonical_name'] or 'Unknown',
                    inchi_key=row['inchi_key'],
                    total_reports=row['total_reports'] or 0,
                    serious_reports=row['serious_reports'] or 0,
                    death_reports=row['death_reports'] or 0,
                    has_boxed_warning=row['has_boxed_warning'] or False,
                    top_event=row['top_event'],
                    signal_score=float(row['signal_score']) if row['signal_score'] else None,
                ))

        return GoldSafetySignalsResponse(
            success=True,
            signals=signals,
            total_count=len(signals),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to list gold safety signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gold/lifecycle-stages", response_model=GoldLifecycleStagesResponse)
async def list_gold_lifecycle_stages(
    stage: Optional[str] = Query(None, description="Filter by stage: discovery, preclinical, phase_1, phase_2, phase_3, approved, withdrawn"),
    recent_transitions: bool = Query(False, description="Only show molecules with recent stage transitions (last 90 days)"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results")
):
    """
    List molecule lifecycle stages from Gold layer.

    Returns molecules with lifecycle progression data:
    - Current development stage
    - Stage entry date
    - Previous stage
    - Days in current stage
    - Predicted next stage
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return GoldLifecycleStagesResponse(
                success=False,
                molecules=[],
                stage_distribution={},
                total_count=0,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        async with pool.acquire() as conn:
            # Build conditions
            conditions = ["m.needs_review = FALSE"]
            params = []
            param_idx = 1

            if stage:
                conditions.append(f"m.development_status = ${param_idx}")
                params.append(stage)
                param_idx += 1

            " AND ".join(conditions)

            # Try gold view first
            try:
                query = """
                    SELECT
                        molecule_id::text,
                        canonical_name,
                        inchi_key,
                        current_stage,
                        stage_entered_date,
                        previous_stage,
                        days_in_current_stage,
                        next_expected_stage
                    FROM gold.lifecycle_stages
                    WHERE 1=1
                """
                if stage:
                    query += f" AND current_stage = ${param_idx - 1}"
                if recent_transitions:
                    query += " AND stage_entered_date >= NOW() - INTERVAL '90 days'"

                query += " ORDER BY stage_entered_date DESC NULLS LAST LIMIT $" + str(param_idx)
                params.append(limit)

                rows = await conn.fetch(query, *params)
            except Exception as e:
                logger.warning(f"Gold view query failed, using fallback: {e}")
                # Fallback: derive from silver layer
                params = []
                param_idx = 1
                fallback_conditions = ["m.needs_review = FALSE", "m.development_status IS NOT NULL"]

                if stage:
                    fallback_conditions.append(f"m.development_status = ${param_idx}")
                    params.append(stage)
                    param_idx += 1

                params.append(limit)
                rows = await conn.fetch(f"""
                    SELECT
                        m.id::text as molecule_id,
                        m.canonical_name,
                        m.inchi_key,
                        m.development_status as current_stage,
                        m.updated_at as stage_entered_date,
                        NULL as previous_stage,
                        EXTRACT(DAY FROM NOW() - m.updated_at)::int as days_in_current_stage,
                        CASE m.development_status
                            WHEN 'discovery' THEN 'preclinical'
                            WHEN 'preclinical' THEN 'phase_1'
                            WHEN 'phase_1' THEN 'phase_2'
                            WHEN 'phase_2' THEN 'phase_3'
                            WHEN 'phase_3' THEN 'approved'
                            ELSE NULL
                        END as next_expected_stage
                    FROM silver.molecules m
                    WHERE {' AND '.join(fallback_conditions)}
                    ORDER BY m.updated_at DESC NULLS LAST
                    LIMIT ${param_idx}
                """, *params)

            molecules = []
            for row in rows:
                molecules.append(GoldLifecycleStageItem(
                    molecule_id=row['molecule_id'],
                    canonical_name=row['canonical_name'] or 'Unknown',
                    inchi_key=row['inchi_key'],
                    current_stage=row['current_stage'] or 'unknown',
                    stage_entered_date=row['stage_entered_date'].isoformat() if row['stage_entered_date'] else None,
                    previous_stage=row['previous_stage'],
                    days_in_current_stage=row['days_in_current_stage'],
                    next_expected_stage=row['next_expected_stage'],
                ))

            # Get stage distribution
            stage_dist = await conn.fetch("""
                SELECT development_status as stage, COUNT(*) as count
                FROM silver.molecules
                WHERE needs_review = FALSE AND development_status IS NOT NULL
                GROUP BY development_status
                ORDER BY count DESC
            """)

            stage_distribution = {row['stage']: row['count'] for row in stage_dist}

        return GoldLifecycleStagesResponse(
            success=True,
            molecules=molecules,
            stage_distribution=stage_distribution,
            total_count=len(molecules),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to list gold lifecycle stages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gold/data-quality")
async def get_gold_data_quality():
    """
    Get data quality metrics for the Gold layer.

    Returns:
    - Completeness metrics by field
    - Source coverage statistics
    - Resolution quality metrics
    - Freshness indicators
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return {
                "success": False,
                "metrics": {},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        async with pool.acquire() as conn:
            # Get molecule completeness metrics
            mol_metrics = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_molecules,
                    COUNT(*) FILTER (WHERE needs_review = FALSE) as published_molecules,
                    COUNT(*) FILTER (WHERE needs_review = TRUE) as quarantined_molecules,
                    COUNT(*) FILTER (WHERE inchi_key IS NOT NULL) as has_inchi_key,
                    COUNT(*) FILTER (WHERE canonical_smiles IS NOT NULL) as has_smiles,
                    COUNT(*) FILTER (WHERE molecular_weight IS NOT NULL) as has_mol_weight,
                    COUNT(*) FILTER (WHERE development_status IS NOT NULL) as has_dev_status,
                    COUNT(*) FILTER (WHERE therapeutic_areas IS NOT NULL AND ARRAY_LENGTH(therapeutic_areas, 1) > 0) as has_therapeutic_areas,
                    COUNT(*) FILTER (WHERE mechanism_of_action IS NOT NULL) as has_moa,
                    COUNT(*) FILTER (WHERE data_sources IS NOT NULL AND ARRAY_LENGTH(data_sources, 1) > 1) as multi_source
                FROM silver.molecules
            """)

            # Get source coverage
            source_coverage = await conn.fetch("""
                SELECT
                    UNNEST(data_sources) as source,
                    COUNT(*) as molecule_count
                FROM silver.molecules
                WHERE needs_review = FALSE
                GROUP BY UNNEST(data_sources)
                ORDER BY molecule_count DESC
            """)

            # Get trial linking stats
            trial_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_trials,
                    COUNT(*) FILTER (WHERE molecule_id IS NOT NULL) as linked_trials,
                    COUNT(DISTINCT molecule_id) as molecules_with_trials
                FROM silver.clinical_trials
            """)

            # Get adverse event linking stats
            ae_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_ae_records,
                    COUNT(*) FILTER (WHERE molecule_id IS NOT NULL) as linked_ae_records,
                    COUNT(DISTINCT molecule_id) as molecules_with_ae
                FROM silver.adverse_events
            """)

            # Get resolution queue stats
            queue_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_reviews,
                    COUNT(*) FILTER (WHERE status = 'approved') as approved_total,
                    COUNT(*) FILTER (WHERE status = 'rejected') as rejected_total
                FROM silver.resolution_queue
            """)

            total_mols = mol_metrics['total_molecules'] or 1  # Avoid division by zero

            return {
                "success": True,
                "metrics": {
                    "molecules": {
                        "total": mol_metrics['total_molecules'],
                        "published": mol_metrics['published_molecules'],
                        "quarantined": mol_metrics['quarantined_molecules'],
                        "publication_rate": round(mol_metrics['published_molecules'] / total_mols * 100, 1),
                    },
                    "completeness": {
                        "inchi_key": round(mol_metrics['has_inchi_key'] / total_mols * 100, 1),
                        "smiles": round(mol_metrics['has_smiles'] / total_mols * 100, 1),
                        "molecular_weight": round(mol_metrics['has_mol_weight'] / total_mols * 100, 1),
                        "development_status": round(mol_metrics['has_dev_status'] / total_mols * 100, 1),
                        "therapeutic_areas": round(mol_metrics['has_therapeutic_areas'] / total_mols * 100, 1),
                        "mechanism_of_action": round(mol_metrics['has_moa'] / total_mols * 100, 1),
                    },
                    "source_coverage": {
                        "multi_source_molecules": mol_metrics['multi_source'],
                        "multi_source_rate": round(mol_metrics['multi_source'] / total_mols * 100, 1),
                        "by_source": {row['source']: row['molecule_count'] for row in source_coverage},
                    },
                    "entity_linking": {
                        "clinical_trials": {
                            "total": trial_stats['total_trials'] if trial_stats else 0,
                            "linked": trial_stats['linked_trials'] if trial_stats else 0,
                            "link_rate": round(
                                (trial_stats['linked_trials'] or 0) / max(trial_stats['total_trials'] or 1, 1) * 100, 1
                            ) if trial_stats else 0,
                            "molecules_with_trials": trial_stats['molecules_with_trials'] if trial_stats else 0,
                        },
                        "adverse_events": {
                            "total": ae_stats['total_ae_records'] if ae_stats else 0,
                            "linked": ae_stats['linked_ae_records'] if ae_stats else 0,
                            "link_rate": round(
                                (ae_stats['linked_ae_records'] or 0) / max(ae_stats['total_ae_records'] or 1, 1) * 100, 1
                            ) if ae_stats else 0,
                            "molecules_with_ae": ae_stats['molecules_with_ae'] if ae_stats else 0,
                        },
                    },
                    "resolution_queue": {
                        "pending": queue_stats['pending_reviews'] if queue_stats else 0,
                        "approved_total": queue_stats['approved_total'] if queue_stats else 0,
                        "rejected_total": queue_stats['rejected_total'] if queue_stats else 0,
                    },
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    except Exception as e:
        logger.error(f"Failed to get data quality metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Scheduler Status & Control Endpoints
# ============================================================================

class ScheduleStatusResponse(BaseModel):
    """Sync schedule status response."""
    success: bool
    schedules: List[Dict[str, Any]]
    scheduler_running: bool
    timestamp: str


class JobHistoryResponse(BaseModel):
    """Job history response."""
    success: bool
    jobs: List[Dict[str, Any]]
    total_count: int
    timestamp: str


@router.get("/scheduler/status", response_model=ScheduleStatusResponse)
async def get_scheduler_status():
    """
    Get current sync scheduler status.

    Returns:
    - All configured schedules with last_run and next_run times
    - Whether the scheduler container is running
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return ScheduleStatusResponse(
                success=False,
                schedules=[],
                scheduler_running=False,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    source,
                    tier,
                    cron_expression,
                    priority,
                    enabled,
                    last_run,
                    next_run,
                    options,
                    updated_at
                FROM raw.sync_schedules
                ORDER BY
                    CASE tier
                        WHEN 'daily' THEN 1
                        WHEN 'weekly' THEN 2
                        WHEN 'monthly' THEN 3
                        ELSE 4
                    END,
                    source
            """)

            schedules = []
            for row in rows:
                schedules.append({
                    "source": row['source'],
                    "tier": row['tier'],
                    "cron_expression": row['cron_expression'],
                    "priority": row['priority'],
                    "enabled": row['enabled'],
                    "last_run": row['last_run'].isoformat() if row['last_run'] else None,
                    "next_run": row['next_run'].isoformat() if row['next_run'] else None,
                    "options": row['options'],
                    "updated_at": row['updated_at'].isoformat() if row['updated_at'] else None,
                })

        # Check if scheduler is active (has run recently)
        scheduler_running = any(
            s.get('last_run') or s.get('next_run')
            for s in schedules
        )

        return ScheduleStatusResponse(
            success=True,
            schedules=schedules,
            scheduler_running=scheduler_running,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/jobs", response_model=JobHistoryResponse)
async def get_job_history(
    source: Optional[str] = Query(None, description="Filter by source"),
    status: Optional[str] = Query(None, description="Filter by status: pending, processing, completed, failed"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """
    Get ingestion job history.

    Returns recent pipeline job executions with status and metrics.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            return JobHistoryResponse(
                success=False,
                jobs=[],
                total_count=0,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        async with pool.acquire() as conn:
            # Build query with filters
            conditions = []
            params = []
            param_idx = 1

            if source:
                conditions.append(f"source = ${param_idx}")
                params.append(source)
                param_idx += 1

            if status:
                conditions.append(f"status = ${param_idx}")
                params.append(status)
                param_idx += 1

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            # Get total count
            count_query = f"SELECT COUNT(*) FROM raw.ingestion_jobs {where_clause}"
            total_count = await conn.fetchval(count_query, *params) or 0

            # Get jobs
            params.extend([limit, offset])
            query = f"""
                SELECT
                    job_id::text,
                    source,
                    status,
                    priority,
                    started_at,
                    completed_at,
                    records_processed,
                    error_message,
                    error_details,
                    created_at
                FROM raw.ingestion_jobs
                {where_clause}
                ORDER BY started_at DESC NULLS LAST, created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            rows = await conn.fetch(query, *params)

            jobs = []
            for row in rows:
                duration = None
                if row['started_at'] and row['completed_at']:
                    duration = (row['completed_at'] - row['started_at']).total_seconds()

                jobs.append({
                    "job_id": row['job_id'],
                    "source": row['source'],
                    "status": row['status'],
                    "priority": row['priority'],
                    "started_at": row['started_at'].isoformat() if row['started_at'] else None,
                    "completed_at": row['completed_at'].isoformat() if row['completed_at'] else None,
                    "duration_seconds": duration,
                    "records_processed": row['records_processed'],
                    "error_message": row['error_message'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                })

        return JobHistoryResponse(
            success=True,
            jobs=jobs,
            total_count=total_count,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to get job history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/trigger/{tier}", response_model=IngestionTriggerResponse)
async def trigger_tier_sync(
    tier: str,
    background_tasks: BackgroundTasks
):
    """
    Manually trigger a tier sync.

    Tiers are loaded dynamically from raw.sync_schedules.
    Standard tiers: daily, weekly, monthly, on_demand
    """
    pool = await get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Load sources dynamically from database
    async with pool.acquire() as conn:
        # Validate tier exists
        valid_tiers = await conn.fetch(
            "SELECT DISTINCT tier FROM raw.sync_schedules WHERE tier IS NOT NULL"
        )
        valid_tier_names = [r['tier'] for r in valid_tiers]

        if tier not in valid_tier_names:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tier. Must be one of: {', '.join(valid_tier_names)}"
            )

        # Get sources for this tier
        rows = await conn.fetch(
            "SELECT source FROM raw.sync_schedules WHERE tier = $1 AND enabled = true ORDER BY priority DESC",
            tier
        )
        sources = [r['source'] for r in rows]

    if not sources:
        raise HTTPException(
            status_code=400,
            detail=f"No enabled sources found for tier '{tier}'"
        )

    try:
        from uuid import uuid4
        from ...services.data_platform.sync_runner import run_pipeline

        job_id = str(uuid4())

        async def run_tier_sync():
            try:
                result = await run_pipeline(
                    sources=sources,
                    tier=tier,
                    full_refresh=False,
                    skip_raw=False,
                    skip_bronze=False,
                    skip_silver=False,
                    skip_gold=False,
                )
                logger.info(f"Tier sync job {job_id} completed: {result['status']}")
            except Exception as e:
                logger.error(f"Tier sync job {job_id} failed: {e}")

        background_tasks.add_task(run_tier_sync)

        return IngestionTriggerResponse(
            success=True,
            message=f"Tier '{tier}' sync triggered for sources: {', '.join(sources)}",
            job_id=job_id,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to trigger tier sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/scheduler/schedule/{source}")
async def update_schedule(
    source: str,
    enabled: Optional[bool] = Query(None, description="Enable/disable schedule"),
    tier: Optional[str] = Query(None, description="Change tier: daily, weekly, monthly"),
    cron_expression: Optional[str] = Query(None, description="Custom cron expression"),
    priority: Optional[str] = Query(None, description="Priority: critical, high, normal, low")
):
    """
    Update a sync schedule configuration.

    Allows modifying:
    - Enable/disable specific source syncs
    - Change tier (daily/weekly/monthly)
    - Set custom cron expression
    - Adjust priority
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        # Validate inputs
        valid_tiers = ['daily', 'weekly', 'monthly', 'on_demand']
        valid_priorities = ['critical', 'high', 'normal', 'low']

        if tier and tier not in valid_tiers:
            raise HTTPException(status_code=400, detail=f"Invalid tier. Must be one of: {valid_tiers}")
        if priority and priority not in valid_priorities:
            raise HTTPException(status_code=400, detail=f"Invalid priority. Must be one of: {valid_priorities}")

        async with pool.acquire() as conn:
            # Check if source exists
            exists = await conn.fetchval(
                "SELECT 1 FROM raw.sync_schedules WHERE source = $1",
                source
            )

            if not exists:
                raise HTTPException(status_code=404, detail=f"Schedule not found for source: {source}")

            # Build update query
            updates = []
            params = []
            param_idx = 1

            if enabled is not None:
                updates.append(f"enabled = ${param_idx}")
                params.append(enabled)
                param_idx += 1

            if tier:
                updates.append(f"tier = ${param_idx}")
                params.append(tier)
                param_idx += 1

            if cron_expression:
                updates.append(f"cron_expression = ${param_idx}")
                params.append(cron_expression)
                param_idx += 1

            if priority:
                updates.append(f"priority = ${param_idx}")
                params.append(priority)
                param_idx += 1

            if not updates:
                raise HTTPException(status_code=400, detail="No updates provided")

            updates.append("updated_at = NOW()")
            params.append(source)

            query = f"""
                UPDATE raw.sync_schedules
                SET {', '.join(updates)}
                WHERE source = ${param_idx}
                RETURNING source, tier, cron_expression, priority, enabled
            """

            row = await conn.fetchrow(query, *params)

            return {
                "success": True,
                "message": f"Schedule updated for {source}",
                "schedule": {
                    "source": row['source'],
                    "tier": row['tier'],
                    "cron_expression": row['cron_expression'],
                    "priority": row['priority'],
                    "enabled": row['enabled'],
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DYNAMIC ONBOARDING ENDPOINTS
# Zero-code data source onboarding with SQLMesh integration
# ============================================================================

class SourceRegistrationRequest(BaseModel):
    """Request to register a new data source."""
    source_name: str = Field(..., description="Unique name for the source")
    source_table: str = Field(..., description="Bronze table name (e.g., 'bronze.new_source')")
    column_mappings: Dict[str, str] = Field(
        ...,
        description="Bronze -> Silver column mappings",
        examples=[{"inchi_key": "inchi_key", "drug_name": "canonical_name"}],
    )
    identifier_mappings: Optional[Dict[str, str]] = Field(
        None,
        description="Identifier extraction rules",
        examples=[{"drugbank_id": "drugbank_id"}],
    )
    name_mappings: Optional[Dict[str, str]] = Field(
        None,
        description="Name extraction rules",
        examples=[{"generic": "name", "synonyms": "synonyms"}],
    )
    source_precedence: int = Field(
        10,
        description="Priority (lower = higher)",
        ge=1,
        le=100
    )
    dedup_strategy: str = Field(
        "inchi_key",
        description="Deduplication strategy",
        pattern="^(inchi_key|identifier_match|name_fuzzy|composite)$"
    )
    generate_models: bool = Field(
        True,
        description="Whether to generate SQLMesh models"
    )


class SourceRegistrationResponse(BaseModel):
    """Response from source registration."""
    success: bool
    source_name: str
    message: str
    models_generated: Optional[List[str]] = None


class DynamicTransformationRequest(BaseModel):
    """Request to run transformation."""
    source_name: Optional[str] = Field(
        None,
        description="Source to transform (None = all sources)"
    )
    batch_size: Optional[int] = Field(
        None,
        description="Override batch size",
        ge=100,
        le=10000
    )
    dry_run: bool = Field(
        False,
        description="If True, don't commit changes"
    )


class DynamicTransformationResponse(BaseModel):
    """Response from transformation."""
    source_name: str
    records_processed: int
    records_inserted: int
    records_updated: int
    records_linked: int
    identifiers_extracted: int
    names_extracted: int
    duration_seconds: float
    success: bool
    errors: List[str] = []


class SchemaDetectionRequest(BaseModel):
    """Request for schema detection from samples."""
    source_name: str
    sample_data: List[Dict[str, Any]] = Field(
        ...,
        description="Sample JSON records from the API",
        min_length=1,
        max_length=100
    )
    flatten_depth: int = Field(2, description="Max depth to flatten nested JSON")


class SchemaDetectionResponse(BaseModel):
    """Response from schema detection."""
    source_name: str
    detected_columns: List[Dict[str, Any]]
    suggested_primary_key: Optional[str]
    suggested_indexes: List[str]
    create_table_sql: str


class ModelGenerationRequest(BaseModel):
    """Request to generate SQLMesh models."""
    source_name: Optional[str] = Field(
        None,
        description="Source to generate models for (None = all)"
    )
    regenerate_all: bool = Field(
        False,
        description="Force regeneration of all models"
    )


class ModelGenerationResponse(BaseModel):
    """Response from model generation."""
    models_generated: int
    models: List[Dict[str, str]]
    message: str


class SourceStatusResponse(BaseModel):
    """Status of a data source."""
    source_name: str
    enabled: bool
    source_table: str
    target_table: str
    source_precedence: int
    last_run_at: Optional[datetime]
    last_run_records: Optional[int]
    models_generated: List[str]


async def get_dynamic_transformation_service():
    """Get DynamicSilverTransformation instance."""
    from ...services.data_platform.dynamic_silver_transformation import DynamicSilverTransformation
    pool = await get_db_pool()
    if pool is None:
        return None
    return DynamicSilverTransformation(pool)


async def get_sqlmesh_model_generator():
    """Get SQLMeshModelGenerator instance."""
    from ...services.data_platform.sqlmesh_model_generator import SQLMeshModelGenerator
    pool = await get_db_pool()
    if pool is None:
        return None
    return SQLMeshModelGenerator(pool)


@router.post("/sources/register", response_model=SourceRegistrationResponse, tags=["dynamic-onboarding"])
async def register_data_source(
    request: SourceRegistrationRequest,
    transformation_service = Depends(get_dynamic_transformation_service)
):
    """
    Register a new data source for transformation.

    This endpoint enables zero-code onboarding of new data sources:
    1. Stores transformation rules in the database
    2. Optionally generates SQLMesh models
    3. Makes the source ready for transformation

    After registration, call POST /transform to run the transformation.
    """
    if transformation_service is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    success, message = await transformation_service.register_new_source(
        source_name=request.source_name,
        source_table=request.source_table,
        column_mappings=request.column_mappings,
        identifier_mappings=request.identifier_mappings,
        name_mappings=request.name_mappings,
        source_precedence=request.source_precedence,
        dedup_strategy=request.dedup_strategy,
        generate_models=request.generate_models
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Extract model paths from message if generated
    models_generated = None
    if request.generate_models and "models:" in message:
        import re
        match = re.search(r'\[(.*?)\]', message)
        if match:
            models_generated = [m.strip().strip("'") for m in match.group(1).split(",")]

    return SourceRegistrationResponse(
        success=True,
        source_name=request.source_name,
        message=message,
        models_generated=models_generated
    )


@router.post("/dynamic-transform", response_model=List[DynamicTransformationResponse], tags=["dynamic-onboarding"])
async def run_dynamic_transformation(
    request: DynamicTransformationRequest,
    transformation_service = Depends(get_dynamic_transformation_service)
):
    """
    Run Bronze -> Silver transformation.

    If source_name is provided, transforms only that source.
    Otherwise, transforms all enabled sources in precedence order.
    """
    if transformation_service is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if request.source_name:
        result = await transformation_service.transform_source(
            source_name=request.source_name,
            batch_size=request.batch_size,
            dry_run=request.dry_run
        )
        results = [result]
    else:
        results = await transformation_service.transform_all_sources(
            dry_run=request.dry_run
        )

    return [
        DynamicTransformationResponse(
            source_name=r.source_name,
            records_processed=r.records_processed,
            records_inserted=r.records_inserted,
            records_updated=r.records_updated,
            records_linked=r.records_linked,
            identifiers_extracted=r.identifiers_extracted,
            names_extracted=r.names_extracted,
            duration_seconds=r.duration_seconds,
            success=r.success,
            errors=r.errors
        )
        for r in results
    ]


@router.post("/schema/detect", response_model=SchemaDetectionResponse, tags=["dynamic-onboarding"])
async def detect_schema(request: SchemaDetectionRequest):
    """
    Detect schema from sample JSON data.

    Provide sample API responses and get back:
    - Detected columns with PostgreSQL types
    - Suggested primary key
    - Suggested indexes
    - CREATE TABLE SQL
    """
    from ...services.data_platform.schema_detector import SchemaDetector
    from ...services.data_platform.table_generator import TableGenerator

    pool = await get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    detector = SchemaDetector()
    table_generator = TableGenerator(pool)

    # Detect schema
    schema = detector.detect_schema(
        request.sample_data,
        table_name=request.source_name,
        max_flatten_depth=request.flatten_depth
    )

    # Generate CREATE TABLE SQL
    create_sql = table_generator._generate_create_table_sql(
        request.source_name,
        schema,
        schema_name="bronze"
    )

    return SchemaDetectionResponse(
        source_name=request.source_name,
        detected_columns=[
            {
                "name": col.name,
                "type": col.pg_type.value,
                "nullable": col.nullable,
                "is_unique": col.is_unique
            }
            for col in schema.columns
        ],
        suggested_primary_key=schema.primary_key,
        suggested_indexes=schema.suggested_indexes,
        create_table_sql=create_sql
    )


@router.post("/models/generate", response_model=ModelGenerationResponse, tags=["dynamic-onboarding"])
async def generate_models(
    request: ModelGenerationRequest,
    model_generator = Depends(get_sqlmesh_model_generator)
):
    """
    Generate SQLMesh models from transformation rules.

    If source_name is provided, generates models only for that source.
    Otherwise, generates models for all sources.
    """
    if model_generator is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if request.regenerate_all or request.source_name:
        models = await model_generator.generate_all_models(
            source_name=request.source_name
        )
    else:
        models = await model_generator.regenerate_if_needed()

    return ModelGenerationResponse(
        models_generated=len(models),
        models=[
            {"name": m.model_name, "path": m.file_path}
            for m in models
        ],
        message=f"Generated {len(models)} SQLMesh models"
    )


@router.get("/transformation-sources", response_model=List[SourceStatusResponse], tags=["dynamic-onboarding"])
async def list_transformation_sources(enabled_only: bool = True):
    """
    List all registered data sources for dynamic transformation.
    """
    pool = await get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with pool.acquire() as conn:
        query = """
            SELECT
                r.source_name,
                r.enabled,
                r.source_table,
                r.target_table,
                r.source_precedence,
                r.last_run_at,
                r.last_run_records,
                COALESCE(
                    array_agg(m.model_name) FILTER (WHERE m.model_name IS NOT NULL),
                    ARRAY[]::text[]
                ) AS models_generated
            FROM raw.silver_transformation_rules r
            LEFT JOIN raw.generated_sqlmesh_models m ON m.source_rule_id = r.id
        """
        if enabled_only:
            query += " WHERE r.enabled = true"
        query += " GROUP BY r.id ORDER BY r.source_precedence ASC"

        rows = await conn.fetch(query)

    return [
        SourceStatusResponse(
            source_name=row['source_name'],
            enabled=row['enabled'],
            source_table=row['source_table'],
            target_table=row['target_table'],
            source_precedence=row['source_precedence'],
            last_run_at=row['last_run_at'],
            last_run_records=row['last_run_records'],
            models_generated=row['models_generated']
        )
        for row in rows
    ]


@router.get("/transformation-sources/{source_name}", response_model=SourceStatusResponse, tags=["dynamic-onboarding"])
async def get_transformation_source(source_name: str):
    """
    Get details for a specific data source.
    """
    pool = await get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                r.source_name,
                r.enabled,
                r.source_table,
                r.target_table,
                r.source_precedence,
                r.last_run_at,
                r.last_run_records,
                COALESCE(
                    array_agg(m.model_name) FILTER (WHERE m.model_name IS NOT NULL),
                    ARRAY[]::text[]
                ) AS models_generated
            FROM raw.silver_transformation_rules r
            LEFT JOIN raw.generated_sqlmesh_models m ON m.source_rule_id = r.id
            WHERE r.source_name = $1
            GROUP BY r.id
        """, source_name)

    if not row:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_name}")

    return SourceStatusResponse(
        source_name=row['source_name'],
        enabled=row['enabled'],
        source_table=row['source_table'],
        target_table=row['target_table'],
        source_precedence=row['source_precedence'],
        last_run_at=row['last_run_at'],
        last_run_records=row['last_run_records'],
        models_generated=row['models_generated']
    )


@router.delete("/transformation-sources/{source_name}", tags=["dynamic-onboarding"])
async def disable_transformation_source(source_name: str):
    """
    Disable a data source (soft delete).
    """
    pool = await get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE raw.silver_transformation_rules
            SET enabled = false, updated_at = NOW()
            WHERE source_name = $1
        """, source_name)

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail=f"Source not found: {source_name}")

    return {"message": f"Source '{source_name}' disabled"}


@router.post("/transformation-sources/{source_name}/enable", tags=["dynamic-onboarding"])
async def enable_transformation_source(source_name: str):
    """
    Re-enable a disabled data source.
    """
    pool = await get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE raw.silver_transformation_rules
            SET enabled = true, updated_at = NOW()
            WHERE source_name = $1
        """, source_name)

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail=f"Source not found: {source_name}")

    return {"message": f"Source '{source_name}' enabled"}


# ============================================================================
# On-Demand Transform Endpoint (015-assessment-dashboard-integration)
# T054-T057: POST /transform-raw/{source}
# ============================================================================

import collections  # noqa: E402
import time as _time  # noqa: E402
import hashlib  # noqa: E402


class TransformRequest(BaseModel):
    """Request body for on-demand transform."""
    molecule_id: Optional[str] = Field(None, description="Optional - scope transform to this molecule")
    layers: List[str] = Field(
        default=["bronze", "silver", "gold"],
        description="Which layers to process"
    )


class TransformLayerResult(BaseModel):
    """Result for a single layer transform."""
    layer: str
    model: str
    rows_processed: int = 0
    duration_ms: int = 0
    status: str = "success"
    error: Optional[str] = None


class TransformResponse(BaseModel):
    """Response from on-demand transform."""
    source: str
    status: str
    schema_path: Optional[str] = None
    layers: List[TransformLayerResult]
    total_duration_ms: int
    timestamp: str


# Source → model routing map (T055)
# Maps source name to its pipeline models (bronze, silver, gold)
# mol_raw sources go through mol_bronze → mol_silver → mol_gold
# raw sources go through bronze → silver → gold
_SOURCE_MODEL_MAP: Dict[str, Dict[str, str]] = {
    # mol_raw sources
    "clinicaltrials": {
        "bronze": "mol_bronze.clinical_trials",
        "silver": "mol_silver.clinical_trials",
        "gold": "mol_gold.molecule_profiles_agg",
        "schema_path": "mol_raw→mol_bronze→mol_silver→mol_gold",
    },
    "chembl": {
        "bronze": "mol_bronze.chembl_molecules",
        "silver": "mol_silver.molecules_from_bronze",
        "gold": "mol_gold.molecule_profiles_agg",
        "schema_path": "mol_raw→mol_bronze→mol_silver→mol_gold",
    },
    "openfda_faers": {
        "bronze": "mol_bronze.openfda_faers",
        "silver": "mol_silver.adverse_events",
        "gold": "mol_gold.safety_signals_agg",
        "schema_path": "mol_raw→mol_bronze→mol_silver→mol_gold",
    },
    "openfda_labels": {
        "bronze": "mol_bronze.openfda_labels",
        "silver": "mol_silver.drug_labels",
        "gold": "mol_gold.molecule_profiles_agg",
        "schema_path": "mol_raw→mol_bronze→mol_silver→mol_gold",
    },
    "drugbank": {
        "bronze": "mol_bronze.chembl_molecules",
        "silver": "mol_silver.molecules_from_bronze",
        "gold": "mol_gold.molecule_profiles_agg",
        "schema_path": "mol_raw→mol_bronze→mol_silver→mol_gold",
    },
    "pubchem": {
        "bronze": "mol_bronze.pubchem_compounds",
        "silver": "mol_silver.molecules_from_bronze",
        "gold": "mol_gold.molecule_profiles_agg",
        "schema_path": "mol_raw→mol_bronze→mol_silver→mol_gold",
    },
    "openalex": {
        "bronze": "bronze.openalex",
        "silver": "silver.publications",
        "schema_path": "raw→bronze→silver→gold",
    },
    "uniprot": {
        "bronze": "bronze.uniprot",
        "silver": "silver.targets",
        "schema_path": "raw→bronze→silver→gold",
    },
    # raw (IP) sources
    "pubmed": {
        "bronze": "bronze.pubmed",
        "silver": "silver.publications",
        "schema_path": "raw→bronze→silver→gold",
    },
    "ema": {
        "bronze": "bronze.ema",
        "silver": "silver.regulatory_decisions",
        "gold": "mol_gold.regulatory_timeline",
        "schema_path": "raw→bronze→silver→gold",
    },
    "hta_decisions": {
        "bronze": "bronze.hta_decisions",
        "silver": "silver.regulatory_decisions",
        "gold": "mol_gold.regulatory_timeline",
        "schema_path": "raw→bronze→silver→gold",
    },
    "cochrane_reviews": {
        "bronze": "bronze.cochrane_reviews",
        "silver": "silver.publications",
        "schema_path": "raw→bronze→silver→gold",
    },
    "sec_edgar": {
        "bronze": "bronze.sec_edgar",
        "silver": "silver.financial_data",
        "gold": "mol_gold.financial_summary",
        "schema_path": "raw→bronze→silver→gold",
    },
    "orcid": {
        "bronze": "bronze.orcid",
        "silver": "silver.researchers",
        "gold": "mol_gold.kol_profiles",
        "schema_path": "raw→bronze→silver→gold",
    },
    "journal_rss": {
        "bronze": "bronze.journal_rss",
        "silver": "silver.publications",
        "schema_path": "raw→bronze→silver→gold",
    },
    "medical_news": {
        "bronze": "bronze.medical_news",
        "silver": "silver.news_signals",
        "gold": "mol_gold.advocacy_sentiment",
        "schema_path": "raw→bronze→silver→gold",
    },
    "cms_medicare_inpatient": {
        "bronze": "bronze.cms_inpatient",
        "silver": "silver.healthcare_facilities",
        "schema_path": "raw→bronze→silver→gold",
    },
    "cms_hospital_info": {
        "bronze": "bronze.cms_hospital_info",
        "silver": "silver.healthcare_facilities",
        "schema_path": "raw→bronze→silver→gold",
    },
    "cms_cost_reports": {
        "bronze": "bronze.cms_cost_reports",
        "silver": "silver.healthcare_facilities",
        "schema_path": "raw→bronze→silver→gold",
    },
    "acc_tvc": {
        "bronze": "bronze.acc_tvc",
        "silver": "silver.healthcare_facilities",
        "schema_path": "raw→bronze→silver→gold",
    },
    "hrsa": {
        "bronze": "bronze.hrsa",
        "silver": "silver.healthcare_facilities",
        "schema_path": "raw→bronze→silver→gold",
    },
    "pdb_structures": {
        "bronze": "bronze.pdb_structures",
        "silver": "silver.targets",
        "schema_path": "raw→bronze→silver→gold",
    },
    "who_icd": {
        "bronze": "bronze.who_icd",
        "silver": "silver.icd_codes",
        "schema_path": "raw→bronze→silver→gold",
    },
    "uspto_patents": {
        "bronze": "bronze.uspto_patents",
        "silver": "silver.patents",
        "gold": "gold.molecule_profile",
        "schema_path": "raw→bronze→silver→gold",
    },
    "epo_patents": {
        "bronze": "bronze.epo_patents",
        "silver": "silver.patents",
        "gold": "gold.molecule_profile",
        "schema_path": "raw→bronze→silver→gold",
    },
    "orange_book": {
        "bronze": "bronze.orange_book",
        "silver": "silver.patents",
        "gold": "gold.molecule_profile",
        "schema_path": "raw→bronze→silver→gold",
    },
    "uspto_trademarks": {
        "bronze": "bronze.uspto_trademarks",
        "silver": "silver.trademarks",
        "gold": "gold.molecule_profile",
        "schema_path": "raw→bronze→silver→gold",
    },
    "euipo_trademarks": {
        "bronze": "bronze.euipo_trademarks",
        "silver": "silver.trademarks",
        "gold": "gold.molecule_profile",
        "schema_path": "raw→bronze→silver→gold",
    },
}


# Rate limiting (T056): in-memory per-source counters
_rate_limit_window: Dict[str, list] = collections.defaultdict(list)
_RATE_LIMIT_MAX = 10  # requests per minute per source
_RATE_LIMIT_WINDOW_SECONDS = 60


def _check_rate_limit(source: str) -> Optional[int]:
    """Check rate limit for a source. Returns retry_after seconds if limited, None if OK."""
    now = _time.time()
    window = _rate_limit_window[source]
    # Prune old entries
    _rate_limit_window[source] = [t for t in window if now - t < _RATE_LIMIT_WINDOW_SECONDS]
    window = _rate_limit_window[source]

    if len(window) >= _RATE_LIMIT_MAX:
        oldest = min(window)
        retry_after = int(_RATE_LIMIT_WINDOW_SECONDS - (now - oldest)) + 1
        return max(retry_after, 1)
    # Record this request
    _rate_limit_window[source].append(now)
    return None


async def _acquire_advisory_lock(conn, source: str) -> bool:
    """Attempt to acquire a PostgreSQL advisory lock for the source. Returns True if acquired."""
    lock_key = int(hashlib.md5(source.encode()).hexdigest()[:8], 16)
    result = await conn.fetchval("SELECT pg_try_advisory_xact_lock($1)", lock_key)
    return result is True


async def _run_transform_model(model_name: str) -> dict:
    """Run a single SQLMesh model transform. Returns result dict."""
    try:
        from ...ingestion.transform_molecules import transform_model
        result = transform_model(model_name)
        return result
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@router.post("/transform-raw/{source}", tags=["on-demand-transform"])
async def trigger_on_demand_transform(
    source: str,
    body: Optional[TransformRequest] = None,
):
    """
    Trigger on-demand raw → bronze → silver → gold transformation for a specific source.

    Uses same SQLMesh models as the daily batch pipeline.
    Rate limited to 10 requests/minute/source.
    Advisory locks prevent concurrent execution with batch transforms.
    """
    # Validate source exists in routing map
    if source not in _SOURCE_MODEL_MAP:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source}")

    # Rate limit check (T056)
    retry_after = _check_rate_limit(source)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for source '{source}'",
            headers={"Retry-After": str(retry_after)},
        )

    source_config = _SOURCE_MODEL_MAP[source]
    schema_path = source_config.get("schema_path", "unknown")
    requested_layers = (body.layers if body else ["bronze", "silver", "gold"])

    start_total = _time.time()
    layer_results: List[TransformLayerResult] = []
    overall_status = "completed"

    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        # Advisory lock check (T057)
        async with pool.acquire() as conn:
            lock_acquired = await _acquire_advisory_lock(conn, source)
            if not lock_acquired:
                raise HTTPException(
                    status_code=409,
                    detail=f"Concurrent transform in progress for source '{source}'",
                    headers={"Retry-After": "60"},
                )

            # Process each layer sequentially (bronze → silver → gold)
            for layer in ["bronze", "silver", "gold"]:
                if layer not in requested_layers:
                    continue

                model_name = source_config.get(layer)
                if model_name is None:
                    layer_results.append(TransformLayerResult(
                        layer=layer, model="none", status="skipped",
                    ))
                    continue

                layer_start = _time.time()
                result = await _run_transform_model(model_name)
                layer_duration = int((_time.time() - layer_start) * 1000)

                layer_status = result.get("status", "failed")
                rows = result.get("success_count", 0)

                layer_results.append(TransformLayerResult(
                    layer=layer,
                    model=model_name,
                    rows_processed=rows,
                    duration_ms=layer_duration,
                    status=layer_status,
                    error=result.get("error"),
                ))

                if layer_status == "failed":
                    overall_status = "partial"

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transform failed for source {source}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    total_duration = int((_time.time() - start_total) * 1000)

    # Check if any rows were processed
    total_rows = sum(lr.rows_processed for lr in layer_results)
    if total_rows == 0 and overall_status == "completed":
        overall_status = "no_rows"

    return TransformResponse(
        source=source,
        status=overall_status,
        schema_path=schema_path,
        layers=layer_results,
        total_duration_ms=total_duration,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
