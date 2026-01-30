"""
Visualization API Routes.

Implements T114-T118: Visualization endpoints for D3.js, Cytoscape.js, Timeline.js.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from loguru import logger

from ...services.ground_truth.visualization_service import VisualizationService


router = APIRouter(prefix="/api/v1/visualize", tags=["visualize"])


# Response Models
class VisualizationNode(BaseModel):
    """Node for visualization."""
    id: str
    label: str
    level: int
    stage: str
    threat_score: float
    sponsor: Optional[str]
    moa: Optional[str]
    x: Optional[float] = None
    y: Optional[float] = None
    color: Optional[str] = None
    size: Optional[float] = None


class VisualizationEdge(BaseModel):
    """Edge for visualization."""
    source: str
    target: str
    score: float
    dimension: str
    color: Optional[str] = None
    width: Optional[float] = None


class GraphVisualizationResponse(BaseModel):
    """Graph visualization response."""
    nodes: List[dict]
    edges: List[dict]
    layout: str
    format: str
    core_id: str
    depth: int
    metadata: dict


class TimelineEvent(BaseModel):
    """Timeline event."""
    id: str
    start: str
    end: Optional[str]
    content: str
    type: str
    group: Optional[str]
    className: Optional[str]


class TimelineGroup(BaseModel):
    """Timeline group."""
    id: str
    content: str
    className: Optional[str]


class TimelineVisualizationResponse(BaseModel):
    """Timeline visualization response."""
    events: List[dict]
    groups: List[dict]
    options: dict


class WaterfallItem(BaseModel):
    """Waterfall chart item."""
    id: str
    name: str
    start_date: str
    end_date: Optional[str]
    status: str
    phase: str
    color: str


class WaterfallVisualizationResponse(BaseModel):
    """Waterfall chart response."""
    items: List[dict]
    categories: List[str]
    options: dict


# Dependency
def get_visualization_service() -> VisualizationService:
    """Get visualization service instance."""
    return VisualizationService()


@router.get("/graph/{molecule_id}", response_model=GraphVisualizationResponse)
async def get_graph_visualization(
    molecule_id: str,
    format: str = Query(default="d3", description="Output format: d3, cytoscape"),
    layout: str = Query(default="force", description="Layout: force, hierarchical, circular"),
    depth: int = Query(default=2, ge=1, le=2, description="Graph depth to display"),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0, description="Minimum edge score"),
    dimensions: Optional[List[str]] = Query(default=None, description="Dimensions to include"),
):
    """
    Get competitive graph in visualization-ready format.

    **Output Formats:**
    - **d3**: D3.js force-directed graph format with nodes and links arrays
    - **cytoscape**: Cytoscape.js format with elements array

    **Layout Options:**
    - **force**: Force-directed layout (nodes repel, edges attract)
    - **hierarchical**: Tree-like layout with core at top
    - **circular**: Circular layout with core at center

    **Filters:**
    - **depth**: Show only N (0), N+1 (1), or include N+2 (2)
    - **min_score**: Filter edges by minimum competitive score
    - **dimensions**: Filter by specific competitive dimensions
    """
    logger.info(f"Getting graph visualization for {molecule_id}")

    try:
        service = get_visualization_service()
        result = await service.get_graph_visualization(
            molecule_id=molecule_id,
            format=format,
            layout=layout,
            depth=depth,
            min_score=min_score,
            dimensions=dimensions,
        )

        return GraphVisualizationResponse(
            nodes=result["nodes"],
            edges=result["edges"],
            layout=result["layout"],
            format=result["format"],
            core_id=result["core_id"],
            depth=result["depth"],
            metadata=result.get("metadata", {}),
        )

    except Exception as e:
        logger.error(f"Graph visualization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline/{molecule_id}", response_model=TimelineVisualizationResponse)
async def get_timeline_visualization(
    molecule_id: str,
    format: str = Query(default="vis-timeline", description="Format: vis-timeline, timeline-js"),
    include_trials: bool = Query(default=True, description="Include clinical trials"),
    include_regulatory: bool = Query(default=True, description="Include regulatory events"),
    include_patents: bool = Query(default=True, description="Include patent events"),
    include_commercial: bool = Query(default=False, description="Include commercial events"),
):
    """
    Get molecule lifecycle as timeline visualization.

    **Output Formats:**
    - **vis-timeline**: Vis.js Timeline format
    - **timeline-js**: Timeline.js format

    **Event Types:**
    - **trials**: Clinical trial start/end dates, phase transitions
    - **regulatory**: Approval dates, label changes, safety updates
    - **patents**: Patent grants, expirations, exclusivity periods
    - **commercial**: Launch dates, generic entry, market events

    Events are grouped by type for organized display.
    """
    logger.info(f"Getting timeline visualization for {molecule_id}")

    try:
        service = get_visualization_service()
        result = await service.get_timeline_visualization(
            molecule_id=molecule_id,
            format=format,
            include_trials=include_trials,
            include_regulatory=include_regulatory,
            include_patents=include_patents,
            include_commercial=include_commercial,
        )

        return TimelineVisualizationResponse(
            events=result["events"],
            groups=result["groups"],
            options=result.get("options", {}),
        )

    except Exception as e:
        logger.error(f"Timeline visualization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trials/{molecule_id}", response_model=WaterfallVisualizationResponse)
async def get_trials_waterfall(
    molecule_id: str,
    group_by: str = Query(default="phase", description="Group by: phase, indication, status"),
    status: Optional[List[str]] = Query(default=None, description="Filter by status"),
    sort_by: str = Query(default="start_date", description="Sort by: start_date, phase, status"),
):
    """
    Get clinical trials as waterfall chart visualization.

    Returns trial data formatted for Gantt/waterfall chart display.

    **Grouping Options:**
    - **phase**: Group by clinical phase (Phase 1, 2, 3)
    - **indication**: Group by therapeutic indication
    - **status**: Group by trial status (recruiting, completed, etc.)

    Each trial includes:
    - Start and end dates
    - Phase and status
    - Color coding by status
    """
    logger.info(f"Getting trials waterfall for {molecule_id}")

    try:
        service = get_visualization_service()
        result = await service.get_trials_waterfall(
            molecule_id=molecule_id,
            group_by=group_by,
            status_filter=status,
            sort_by=sort_by,
        )

        return WaterfallVisualizationResponse(
            items=result["items"],
            categories=result["categories"],
            options=result.get("options", {}),
        )

    except Exception as e:
        logger.error(f"Trials waterfall failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/heatmap/{molecule_id}")
async def get_adverse_events_heatmap(
    molecule_id: str,
    molecule_name: str = Query(..., description="Molecule name for lookup"),
    top_n: int = Query(default=20, ge=5, le=100, description="Top N adverse events"),
    group_by: str = Query(default="soc", description="Group by: soc, pt, outcome"),
):
    """
    Get adverse events data formatted for heatmap visualization.

    Returns FAERS adverse event data organized for heatmap display.

    **Grouping Options:**
    - **soc**: Group by System Organ Class
    - **pt**: Group by Preferred Term
    - **outcome**: Group by patient outcome

    Data includes:
    - Event counts by category
    - Relative frequencies
    - Color intensity mapping
    """
    logger.info(f"Getting AE heatmap for {molecule_name}")

    try:
        service = get_visualization_service()
        result = await service.get_adverse_events_heatmap(
            molecule_id=molecule_id,
            molecule_name=molecule_name,
            top_n=top_n,
            group_by=group_by,
        )

        return result

    except Exception as e:
        logger.error(f"AE heatmap failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/map/{molecule_id}")
async def get_regulatory_map(
    molecule_id: str,
    molecule_name: str = Query(..., description="Molecule name for lookup"),
):
    """
    Get regulatory approval data formatted for world map visualization.

    Returns approval status by country/region for geographic display.

    Includes:
    - Approval status by region (approved, pending, not submitted)
    - Approval dates where available
    - Geographic coordinates for map plotting
    """
    logger.info(f"Getting regulatory map for {molecule_name}")

    try:
        service = get_visualization_service()
        result = await service.get_regulatory_map(
            molecule_id=molecule_id,
            molecule_name=molecule_name,
        )

        return result

    except Exception as e:
        logger.error(f"Regulatory map failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/radar/{molecule_id}")
async def get_competitive_radar(
    molecule_id: str,
    competitor_ids: List[str] = Query(..., description="Competitor molecule IDs"),
):
    """
    Get competitive comparison as radar chart data.

    Compares the target molecule against competitors across dimensions:
    - Clinical Development Stage
    - Safety Profile
    - Patent Strength
    - Market Presence
    - Publication Volume
    - Regulatory Status

    Returns normalized scores (0-100) for each dimension per molecule.
    """
    logger.info(f"Getting competitive radar for {molecule_id}")

    try:
        service = get_visualization_service()
        result = await service.get_competitive_radar(
            molecule_id=molecule_id,
            competitor_ids=competitor_ids,
        )

        return result

    except Exception as e:
        logger.error(f"Competitive radar failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
