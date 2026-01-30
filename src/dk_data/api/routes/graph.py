"""
Competitive Graph API Routes.

Implements T039-T040: Graph build and competitors endpoints.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from loguru import logger

from ...models.competitive_graph import (
    CompetitiveDimension,
    GraphLevel,
)
from ...services.ground_truth.competitive_graph_service import (
    CompetitiveGraphService,
    GraphBuildConfig,
)


router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


# Request/Response Models
class GraphBuildRequest(BaseModel):
    """Request to build a competitive graph."""
    molecule_id: str = Field(..., description="Unique molecule identifier")
    molecule_name: str = Field(..., description="Molecule name for lookups")
    depth: int = Field(default=1, ge=1, le=2, description="Graph depth (1=N+1, 2=N+2)")
    min_score: float = Field(default=0.1, ge=0.0, le=1.0, description="Minimum competitive score")
    dimensions: Optional[List[str]] = Field(
        default=None,
        description="Dimensions to include (indication, moa, target, class)"
    )
    include_preclinical: bool = Field(default=False, description="Include preclinical drugs")
    core_node_data: Optional[dict] = Field(default=None, description="Pre-populated core node data")


class GraphBuildResponse(BaseModel):
    """Response from graph build."""
    core_molecule_id: str
    nodes: dict
    edges: list
    stats: dict
    depth: int
    build_time_ms: int


class CompetitorResponse(BaseModel):
    """Competitor information."""
    id: str
    name: str
    level: int
    development_stage: str
    mechanism_of_action: Optional[str]
    primary_indication: Optional[str]
    sponsor: Optional[str]
    threat_score: float
    discovered_via: List[str]


class CompetitorsListResponse(BaseModel):
    """List of competitors."""
    molecule_id: str
    competitors: List[CompetitorResponse]
    total_count: int
    n_plus_1_count: int
    n_plus_2_count: int


# Dependency
def get_graph_service() -> CompetitiveGraphService:
    """Get competitive graph service instance."""
    return CompetitiveGraphService()


@router.post("/build", response_model=GraphBuildResponse)
async def build_graph(request: GraphBuildRequest):
    """
    Build a competitive landscape graph for a molecule.

    This endpoint discovers competitors across multiple dimensions:
    - **Indication**: Same disease/condition (from ClinicalTrials.gov)
    - **MOA**: Same mechanism of action (from OpenFDA)
    - **Target**: Same molecular target (from RxNorm)
    - **Class**: Same ATC drug class (from OpenFDA)

    The graph is built to the specified depth:
    - depth=1: N+1 competitors only (direct competitors)
    - depth=2: N+1 and N+2 competitors (competitors' competitors)

    Returns the complete graph with nodes, edges, and statistics.
    """
    logger.info(f"Building graph for {request.molecule_name} (depth={request.depth})")

    # Parse dimensions
    dimensions = None
    if request.dimensions:
        dimensions = []
        for d in request.dimensions:
            try:
                dimensions.append(CompetitiveDimension(d))
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid dimension: {d}. Valid: indication, moa, target, class"
                )

    # Build config
    config = GraphBuildConfig(
        depth=request.depth,
        min_score=request.min_score,
        dimensions=dimensions or [
            CompetitiveDimension.INDICATION,
            CompetitiveDimension.MOA,
            CompetitiveDimension.TARGET,
        ],
        include_preclinical=request.include_preclinical,
    )

    try:
        service = get_graph_service()
        graph = await service.build_graph(
            molecule_id=request.molecule_id,
            molecule_name=request.molecule_name,
            config=config,
            core_node_data=request.core_node_data,
        )

        result = graph.to_dict()

        return GraphBuildResponse(
            core_molecule_id=result["core_molecule_id"],
            nodes=result["nodes"],
            edges=result["edges"],
            stats=result["stats"],
            depth=result["depth"],
            build_time_ms=result["build_time_ms"],
        )

    except Exception as e:
        logger.error(f"Graph build failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{molecule_id}/competitors", response_model=CompetitorsListResponse)
async def get_competitors(
    molecule_id: str,
    level: Optional[int] = Query(default=None, ge=1, le=2, description="Filter by level (1=N+1, 2=N+2)"),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0, description="Minimum threat score"),
    limit: Optional[int] = Query(default=None, ge=1, le=500, description="Maximum results"),
):
    """
    Get competitors for a molecule.

    Returns competitors discovered in a previously built graph.
    Results are sorted by threat score (highest first).

    **Filters:**
    - **level**: Filter by graph level (1=N+1 direct, 2=N+2 indirect)
    - **min_score**: Filter by minimum threat score (0-1)
    - **limit**: Maximum number of results
    """
    logger.info(f"Getting competitors for {molecule_id}")

    try:
        service = get_graph_service()

        # Parse level
        graph_level = None
        if level == 1:
            graph_level = GraphLevel.N_PLUS_1
        elif level == 2:
            graph_level = GraphLevel.N_PLUS_2

        # Get competitors from database via service
        competitors = await service.get_competitors(
            molecule_id=molecule_id,
            level=graph_level,
            min_score=min_score,
        )

        # Apply limit
        if limit:
            competitors = competitors[:limit]

        # Convert to response format
        competitor_responses = [
            CompetitorResponse(
                id=c.get("id", ""),
                name=c.get("name", ""),
                level=c.get("level", 1),
                development_stage=c.get("development_stage", "unknown"),
                mechanism_of_action=c.get("mechanism_of_action"),
                primary_indication=c.get("primary_indication"),
                sponsor=c.get("sponsor"),
                threat_score=c.get("threat_score", 0.0),
                discovered_via=c.get("discovered_via", []),
            )
            for c in competitors
        ]

        return CompetitorsListResponse(
            molecule_id=molecule_id,
            competitors=competitor_responses,
            total_count=len(competitor_responses),
            n_plus_1_count=sum(1 for c in competitor_responses if c.level == 1),
            n_plus_2_count=sum(1 for c in competitor_responses if c.level == 2),
        )

    except Exception as e:
        logger.error(f"Get competitors failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{molecule_id}/visualization")
async def get_graph_visualization(
    molecule_id: str,
    layout: str = Query(default="force", description="Layout: force, hierarchical, circular"),
    format: str = Query(default="d3", description="Format: d3, cytoscape"),
):
    """
    Get graph data in visualization-ready format.

    Returns the competitive graph formatted for visualization libraries:
    - **d3**: D3.js force-directed graph format
    - **cytoscape**: Cytoscape.js format

    **Layout options:**
    - **force**: Force-directed layout (default)
    - **hierarchical**: Tree-like layout by level
    - **circular**: Circular layout with core at center
    """
    logger.info(f"Getting visualization for {molecule_id}")

    try:
        service = get_graph_service()

        # Get competitors from the service
        competitors = await service.get_competitors(
            molecule_id=molecule_id,
            level=None,
            min_score=0.0,
        )

        # Build nodes and edges for visualization
        nodes = []
        edges = []

        # Add core molecule as central node
        nodes.append({
            "id": molecule_id,
            "label": molecule_id,
            "type": "core",
            "level": 0,
            "x": 0,
            "y": 0,
        })

        # Add competitor nodes and edges
        for i, comp in enumerate(competitors):
            comp_id = comp.get("id", f"comp_{i}")
            comp_level = comp.get("level", 1)

            # Calculate position based on layout
            if layout == "circular":
                import math
                angle = (2 * math.pi * i) / max(len(competitors), 1)
                radius = 100 * comp_level
                x = radius * math.cos(angle)
                y = radius * math.sin(angle)
            elif layout == "hierarchical":
                x = (i % 5 - 2) * 150
                y = comp_level * 150
            else:  # force layout - positions computed by client
                x = None
                y = None

            nodes.append({
                "id": comp_id,
                "label": comp.get("name", comp_id),
                "type": "competitor",
                "level": comp_level,
                "development_stage": comp.get("development_stage"),
                "threat_score": comp.get("threat_score", 0),
                "x": x,
                "y": y,
            })

            # Add edge from core (or parent) to competitor
            edges.append({
                "source": molecule_id,
                "target": comp_id,
                "type": "competes_with",
                "discovered_via": comp.get("discovered_via", []),
            })

        # Format for cytoscape if requested
        if format == "cytoscape":
            return {
                "elements": {
                    "nodes": [{"data": n} for n in nodes],
                    "edges": [{"data": e} for e in edges],
                },
                "layout": {"name": layout},
                "core_id": molecule_id,
            }

        # Default D3 format
        return {
            "nodes": nodes,
            "links": edges,  # D3 uses "links"
            "layout": layout,
            "format": format,
            "core_id": molecule_id,
        }

    except Exception as e:
        logger.error(f"Graph visualization failed: {e}")
        # Return empty graph on error
        return {
            "nodes": [{"id": molecule_id, "label": molecule_id, "type": "core", "level": 0}],
            "links": [] if format == "d3" else None,
            "edges": [] if format != "d3" else None,
            "layout": layout,
            "format": format,
            "core_id": molecule_id,
        }


@router.post("/{molecule_id}/refresh")
async def refresh_graph(
    molecule_id: str,
    molecule_name: str = Query(..., description="Molecule name for lookups"),
    depth: int = Query(default=1, ge=1, le=2, description="Graph depth"),
):
    """
    Refresh the competitive graph with latest data.

    Re-runs competitor discovery with latest data from all sources.
    Returns the updated graph.
    """
    logger.info(f"Refreshing graph for {molecule_id}")

    config = GraphBuildConfig(depth=depth)

    try:
        service = get_graph_service()
        graph = await service.build_graph(
            molecule_id=molecule_id,
            molecule_name=molecule_name,
            config=config,
        )

        return graph.to_dict()

    except Exception as e:
        logger.error(f"Graph refresh failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
