"""
Visualization Service.

Implements T109-T113: VisualizationService for D3.js, Cytoscape.js, Timeline.js formats.
"""

import math
from typing import Dict, List, Optional, Any
from loguru import logger

from ...models.competitive_graph import (
    CompetitiveLandscapeGraph,
    GraphLevel,
    CompetitiveDimension,
)
from ..external_apis.clinicaltrials_client import ClinicalTrialsClient
from ..external_apis.openfda_client import OpenFDAClient
from .global_regulatory_service import GlobalRegulatoryService, ApprovalStatus
from .lifecycle_service import LifecycleService, MilestoneType


class VisualizationService:
    """
    Service for converting data to visualization-ready formats.

    Supports multiple visualization libraries:
    - D3.js (force-directed graphs)
    - Cytoscape.js (network graphs)
    - Vis.js Timeline
    - Timeline.js
    - Recharts (waterfall/Gantt)
    """

    # Color schemes
    LEVEL_COLORS = {
        GraphLevel.CORE: "#3B82F6",      # Blue
        GraphLevel.N_PLUS_1: "#10B981",  # Green
        GraphLevel.N_PLUS_2: "#F59E0B",  # Amber
    }

    DIMENSION_COLORS = {
        CompetitiveDimension.INDICATION: "#8B5CF6",  # Purple
        CompetitiveDimension.MOA: "#EC4899",         # Pink
        CompetitiveDimension.TARGET: "#06B6D4",      # Cyan
        CompetitiveDimension.CLASS: "#84CC16",       # Lime
        CompetitiveDimension.STAGE: "#F97316",       # Orange
    }

    STATUS_COLORS = {
        "RECRUITING": "#10B981",
        "ACTIVE_NOT_RECRUITING": "#3B82F6",
        "COMPLETED": "#6B7280",
        "TERMINATED": "#EF4444",
        "WITHDRAWN": "#F59E0B",
        "SUSPENDED": "#F97316",
    }

    def __init__(
        self,
        lifecycle_service: Optional["LifecycleService"] = None,
        clinicaltrials_client: Optional["ClinicalTrialsClient"] = None,
        global_regulatory_service: Optional["GlobalRegulatoryService"] = None,
        openfda_client: Optional["OpenFDAClient"] = None,
    ):
        """Initialize visualization service with data sources."""
        self._lifecycle_service = lifecycle_service
        self._clinicaltrials_client = clinicaltrials_client
        self._global_regulatory_service = global_regulatory_service
        self._openfda_client = openfda_client

    def _get_lifecycle_service(self) -> "LifecycleService":
        """Lazy initialization of lifecycle service."""
        if self._lifecycle_service is None:
            self._lifecycle_service = LifecycleService()
        return self._lifecycle_service

    def _get_clinicaltrials_client(self) -> "ClinicalTrialsClient":
        """Lazy initialization of clinical trials client."""
        if self._clinicaltrials_client is None:
            self._clinicaltrials_client = ClinicalTrialsClient()
        return self._clinicaltrials_client

    def _get_global_regulatory_service(self) -> "GlobalRegulatoryService":
        """Lazy initialization of global regulatory service."""
        if self._global_regulatory_service is None:
            self._global_regulatory_service = GlobalRegulatoryService()
        return self._global_regulatory_service

    def _get_openfda_client(self) -> "OpenFDAClient":
        """Lazy initialization of OpenFDA client."""
        if self._openfda_client is None:
            self._openfda_client = OpenFDAClient()
        return self._openfda_client

    async def get_graph_visualization(
        self,
        molecule_id: str,
        format: str = "d3",
        layout: str = "force",
        depth: int = 2,
        min_score: float = 0.0,
        dimensions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Convert competitive graph to visualization format.

        Args:
            molecule_id: Core molecule ID
            format: Output format (d3, cytoscape)
            layout: Layout algorithm (force, hierarchical, circular)
            depth: Maximum depth to include
            min_score: Minimum edge score filter
            dimensions: Dimensions to include

        Returns:
            Visualization-ready data structure
        """
        # In production, this would load the graph from database
        # For now, return a placeholder structure

        if format == "d3":
            return self._to_d3_format(molecule_id, layout, depth, min_score, dimensions)
        elif format == "cytoscape":
            return self._to_cytoscape_format(molecule_id, layout, depth, min_score, dimensions)
        else:
            return self._to_d3_format(molecule_id, layout, depth, min_score, dimensions)

    def _to_d3_format(
        self,
        molecule_id: str,
        layout: str,
        depth: int,
        min_score: float,
        dimensions: Optional[List[str]],
    ) -> Dict[str, Any]:
        """Convert to D3.js force-directed graph format."""
        # Placeholder - would load real graph data
        nodes = [
            {
                "id": molecule_id,
                "label": "Core Molecule",
                "level": 0,
                "stage": "approved",
                "threat_score": 0,
                "color": self.LEVEL_COLORS[GraphLevel.CORE],
                "size": 30,
            }
        ]

        edges = []

        # Apply layout calculations
        if layout == "force":
            # D3 handles force layout client-side
            pass
        elif layout == "hierarchical":
            nodes = self._apply_hierarchical_layout(nodes)
        elif layout == "circular":
            nodes = self._apply_circular_layout(nodes)

        return {
            "nodes": nodes,
            "edges": edges,
            "layout": layout,
            "format": "d3",
            "core_id": molecule_id,
            "depth": depth,
            "metadata": {
                "min_score": min_score,
                "dimensions": dimensions,
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        }

    def _to_cytoscape_format(
        self,
        molecule_id: str,
        layout: str,
        depth: int,
        min_score: float,
        dimensions: Optional[List[str]],
    ) -> Dict[str, Any]:
        """Convert to Cytoscape.js format."""
        elements = []

        # Add core node
        elements.append({
            "data": {
                "id": molecule_id,
                "label": "Core Molecule",
                "level": 0,
                "stage": "approved",
                "threat_score": 0,
            },
            "classes": "core",
        })

        # Map layout to Cytoscape layout names
        cytoscape_layouts = {
            "force": "fcose",
            "hierarchical": "dagre",
            "circular": "circle",
        }

        return {
            "nodes": [e for e in elements if "source" not in e.get("data", {})],
            "edges": [e for e in elements if "source" in e.get("data", {})],
            "layout": cytoscape_layouts.get(layout, "fcose"),
            "format": "cytoscape",
            "core_id": molecule_id,
            "depth": depth,
            "metadata": {
                "min_score": min_score,
                "dimensions": dimensions,
            },
        }

    def _apply_hierarchical_layout(
        self, nodes: List[Dict]
    ) -> List[Dict]:
        """Apply hierarchical (tree) layout to nodes."""
        level_spacing = 150
        node_spacing = 100

        # Group by level
        by_level: Dict[int, List[Dict]] = {}
        for node in nodes:
            level = node.get("level", 0)
            if level not in by_level:
                by_level[level] = []
            by_level[level].append(node)

        # Position nodes
        for level, level_nodes in by_level.items():
            y = level * level_spacing
            total_width = (len(level_nodes) - 1) * node_spacing
            start_x = -total_width / 2

            for i, node in enumerate(level_nodes):
                node["x"] = start_x + i * node_spacing
                node["y"] = y

        return nodes

    def _apply_circular_layout(
        self, nodes: List[Dict]
    ) -> List[Dict]:
        """Apply circular layout with core at center."""
        center_x, center_y = 0, 0
        level_radius = {0: 0, 1: 150, 2: 300}

        # Group by level
        by_level: Dict[int, List[Dict]] = {}
        for node in nodes:
            level = node.get("level", 0)
            if level not in by_level:
                by_level[level] = []
            by_level[level].append(node)

        # Position nodes
        for level, level_nodes in by_level.items():
            radius = level_radius.get(level, 300)
            count = len(level_nodes)

            for i, node in enumerate(level_nodes):
                if radius == 0:
                    node["x"] = center_x
                    node["y"] = center_y
                else:
                    angle = (2 * math.pi * i) / count
                    node["x"] = center_x + radius * math.cos(angle)
                    node["y"] = center_y + radius * math.sin(angle)

        return nodes

    async def get_timeline_visualization(
        self,
        molecule_id: str,
        format: str = "vis-timeline",
        include_trials: bool = True,
        include_regulatory: bool = True,
        include_patents: bool = True,
        include_commercial: bool = False,
    ) -> Dict[str, Any]:
        """
        Convert lifecycle data to timeline format.

        Args:
            molecule_id: Molecule ID
            format: Output format (vis-timeline, timeline-js)
            include_*: Which event types to include

        Returns:
            Timeline-ready data structure
        """
        events = []
        groups = []
        min_date = None
        max_date = None

        # Define groups
        if include_trials:
            groups.append({
                "id": "trials",
                "content": "Clinical Trials",
                "className": "trials-group",
            })

        if include_regulatory:
            groups.append({
                "id": "regulatory",
                "content": "Regulatory",
                "className": "regulatory-group",
            })

        if include_patents:
            groups.append({
                "id": "patents",
                "content": "Patents",
                "className": "patents-group",
            })

        if include_commercial:
            groups.append({
                "id": "commercial",
                "content": "Commercial",
                "className": "commercial-group",
            })

        # Fetch real lifecycle data
        try:
            lifecycle_service = self._get_lifecycle_service()
            lifecycle = await lifecycle_service.get_lifecycle(molecule_id)

            # Process milestones into timeline events
            for i, milestone in enumerate(lifecycle.milestones):
                event_date = milestone.date.isoformat()

                # Track min/max dates for timeline bounds
                if min_date is None or milestone.date < min_date:
                    min_date = milestone.date
                if max_date is None or milestone.date > max_date:
                    max_date = milestone.date

                # Determine group based on milestone type
                group = "regulatory"
                class_name = "regulatory-event"

                if milestone.milestone_type in [MilestoneType.PHASE_START, MilestoneType.PHASE_COMPLETION]:
                    group = "trials"
                    class_name = "trials-event"
                elif milestone.milestone_type in [MilestoneType.PATENT_GRANT, MilestoneType.PATENT_EXPIRY]:
                    group = "patents"
                    class_name = "patents-event"
                elif milestone.milestone_type in [MilestoneType.FIRST_GENERIC, MilestoneType.MARKET_WITHDRAWAL]:
                    group = "commercial"
                    class_name = "commercial-event"

                # Only include if group is requested
                if (group == "trials" and not include_trials) or \
                   (group == "regulatory" and not include_regulatory) or \
                   (group == "patents" and not include_patents) or \
                   (group == "commercial" and not include_commercial):
                    continue

                events.append({
                    "id": f"milestone-{i}",
                    "start": event_date,
                    "content": milestone.description[:100] if len(milestone.description) > 100 else milestone.description,
                    "title": milestone.description,  # Full text on hover
                    "type": "point",
                    "group": group,
                    "className": class_name,
                    "milestone_type": milestone.milestone_type.value,
                    "source": milestone.source,
                    "confidence": milestone.confidence,
                })

        except Exception as e:
            logger.warning(f"Failed to fetch lifecycle data for timeline: {e}")
            # Return empty events on error

        # Calculate timeline bounds based on actual data
        if min_date and max_date:
            from datetime import timedelta
            # Add some padding around the dates
            min_bound = (min_date - timedelta(days=365)).isoformat()
            max_bound = (max_date + timedelta(days=365 * 2)).isoformat()
        else:
            min_bound = "2010-01-01"
            max_bound = "2030-12-31"

        options = {
            "min": min_bound,
            "max": max_bound,
            "zoomMin": 1000 * 60 * 60 * 24 * 30,  # 1 month
            "zoomMax": 1000 * 60 * 60 * 24 * 365 * 10,  # 10 years
        }

        return {
            "events": events,
            "groups": groups,
            "options": options,
            "molecule_id": molecule_id,
            "total_events": len(events),
        }

    async def get_trials_waterfall(
        self,
        molecule_id: str,
        group_by: str = "phase",
        status_filter: Optional[List[str]] = None,
        sort_by: str = "start_date",
    ) -> Dict[str, Any]:
        """
        Convert clinical trials data to waterfall/Gantt format.

        Args:
            molecule_id: Molecule ID
            group_by: Grouping field (phase, indication, status)
            status_filter: Filter by status
            sort_by: Sort field

        Returns:
            Waterfall chart data
        """
        items = []
        categories_set = set()

        # Fetch real clinical trials data
        try:
            ct_client = self._get_clinicaltrials_client()
            trials = await ct_client.search_by_drug(
                drug_name=molecule_id,
                active_only=False,  # Include all trials
                page_size=100
            )

            # Process trials into waterfall items
            for trial in trials:
                # Apply status filter if specified
                if status_filter:
                    if trial.overall_status.value not in status_filter:
                        continue

                # Determine category based on grouping
                if group_by == "phase":
                    category = trial.phase.value.replace("PHASE", "Phase ").replace("EARLY_", "Early ")
                elif group_by == "status":
                    category = trial.overall_status.value.replace("_", " ").title()
                elif group_by == "indication":
                    category = trial.conditions[0] if trial.conditions else "Unknown"
                else:
                    category = trial.phase.value

                categories_set.add(category)

                # Get start and end dates
                start_date = trial.start_date.isoformat() if trial.start_date else None
                end_date = trial.completion_date.isoformat() if trial.completion_date else None

                if not start_date:
                    continue  # Skip trials without start date

                items.append({
                    "id": trial.nct_id,
                    "title": trial.brief_title[:80] if len(trial.brief_title) > 80 else trial.brief_title,
                    "full_title": trial.brief_title,
                    "start": start_date,
                    "end": end_date,
                    "category": category,
                    "status": trial.overall_status.value,
                    "phase": trial.phase.value,
                    "enrollment": trial.enrollment,
                    "sponsor": trial.lead_sponsor.name if trial.lead_sponsor else None,
                    "conditions": trial.conditions[:3],  # First 3 conditions
                    "color": self.STATUS_COLORS.get(trial.overall_status.value, "#6B7280"),
                })

            # Sort items
            if sort_by == "start_date":
                items.sort(key=lambda x: x["start"] or "9999")
            elif sort_by == "end_date":
                items.sort(key=lambda x: x["end"] or "9999")
            elif sort_by == "phase":
                phase_order = {"EARLY_PHASE1": 0, "PHASE1": 1, "PHASE2": 2, "PHASE3": 3, "PHASE4": 4, "NA": 5}
                items.sort(key=lambda x: phase_order.get(x["phase"], 99))

        except Exception as e:
            logger.warning(f"Failed to fetch clinical trials for waterfall: {e}")

        # Define category order
        if group_by == "phase":
            categories = ["Early Phase 1", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "NA"]
            categories = [c for c in categories if c in categories_set]
        elif group_by == "status":
            categories = ["Recruiting", "Active Not Recruiting", "Enrolling By Invitation",
                         "Not Yet Recruiting", "Completed", "Terminated", "Withdrawn", "Suspended"]
            categories = [c for c in categories if c in categories_set]
        else:
            categories = sorted(list(categories_set))

        options = {
            "orientation": "horizontal",
            "colorScheme": self.STATUS_COLORS,
        }

        return {
            "items": items,
            "categories": categories,
            "options": options,
            "molecule_id": molecule_id,
            "total_trials": len(items),
            "group_by": group_by,
        }

    async def get_adverse_events_heatmap(
        self,
        molecule_id: str,
        molecule_name: str,
        top_n: int = 20,
        group_by: str = "soc",
    ) -> Dict[str, Any]:
        """
        Get adverse events data formatted for heatmap.

        Args:
            molecule_id: Molecule ID
            molecule_name: Molecule name for lookup
            top_n: Number of top events
            group_by: Grouping (soc, pt, outcome)

        Returns:
            Heatmap data structure
        """
        data = []
        rows = []

        # Fetch real adverse events from OpenFDA
        try:
            openfda_client = self._get_openfda_client()
            adverse_events = await openfda_client.get_adverse_events(
                drug_name=molecule_name,
                limit=500  # Get more events for aggregation
            )

            # Aggregate events by reaction
            reaction_stats: Dict[str, Dict[str, int]] = {}

            for event in adverse_events:
                for reaction in event.reactions:
                    if reaction not in reaction_stats:
                        reaction_stats[reaction] = {
                            "count": 0,
                            "serious": 0,
                            "death": 0,
                            "hospitalization": 0,
                        }

                    reaction_stats[reaction]["count"] += 1
                    if event.serious:
                        reaction_stats[reaction]["serious"] += 1
                    if event.serious_death:
                        reaction_stats[reaction]["death"] += 1
                    if event.serious_hospitalization:
                        reaction_stats[reaction]["hospitalization"] += 1

            # Sort by count and take top N
            sorted_reactions = sorted(
                reaction_stats.items(),
                key=lambda x: x[1]["count"],
                reverse=True
            )[:top_n]

            # Format data for heatmap
            for reaction, stats in sorted_reactions:
                rows.append(reaction)
                data.append({
                    "reaction": reaction,
                    "count": stats["count"],
                    "serious": stats["serious"],
                    "death": stats["death"],
                    "hospitalization": stats["hospitalization"],
                    "serious_rate": round(stats["serious"] / stats["count"] * 100, 1) if stats["count"] > 0 else 0,
                })

        except Exception as e:
            logger.warning(f"Failed to fetch adverse events for heatmap: {e}")

        return {
            "molecule_id": molecule_id,
            "molecule_name": molecule_name,
            "data": data,
            "categories": {
                "rows": rows,
                "columns": ["Count", "Serious", "Death", "Hospitalization"],
            },
            "color_scale": {
                "min": "#FEE2E2",
                "mid": "#F87171",
                "max": "#991B1B",
            },
            "group_by": group_by,
            "top_n": top_n,
            "total_events": len(data),
        }

    async def get_regulatory_map(
        self,
        molecule_id: str,
        molecule_name: str,
    ) -> Dict[str, Any]:
        """
        Get regulatory status by region for map visualization.

        Args:
            molecule_id: Molecule ID
            molecule_name: Molecule name

        Returns:
            Geographic data for map display
        """
        # Region coordinates for map display
        REGION_COORDINATES = {
            "US": {"lat": 37.0902, "lng": -95.7129, "name": "USA"},
            "EU": {"lat": 50.8503, "lng": 4.3517, "name": "European Union"},
            "Canada": {"lat": 56.1304, "lng": -106.3468, "name": "Canada"},
            "UK": {"lat": 55.3781, "lng": -3.4360, "name": "United Kingdom"},
            "Japan": {"lat": 36.2048, "lng": 138.2529, "name": "Japan"},
            "China": {"lat": 35.8617, "lng": 104.1954, "name": "China"},
        }

        STATUS_COLORS = {
            ApprovalStatus.APPROVED.value: "#10B981",      # Green
            ApprovalStatus.PENDING.value: "#F59E0B",       # Amber
            ApprovalStatus.UNDER_REVIEW.value: "#3B82F6",  # Blue
            ApprovalStatus.NOT_SUBMITTED.value: "#6B7280", # Gray
            ApprovalStatus.REFUSED.value: "#EF4444",       # Red
            ApprovalStatus.WITHDRAWN.value: "#EF4444",     # Red
        }

        regions = []

        # Fetch real regulatory data
        try:
            regulatory_service = self._get_global_regulatory_service()
            global_status = await regulatory_service.get_global_approval_status(
                molecule_name=molecule_name,
                molecule_id=molecule_id,
            )

            # Convert to map-friendly format
            for region_key, approval in global_status.regional_approvals.items():
                coords = REGION_COORDINATES.get(region_key, {})
                status = approval.status.value

                regions.append({
                    "region": coords.get("name", region_key),
                    "country_code": region_key,
                    "status": status,
                    "approval_date": approval.approval_date.isoformat() if approval.approval_date else None,
                    "brand_name": approval.brand_name,
                    "application_number": approval.application_number,
                    "coordinates": {
                        "lat": coords.get("lat", 0),
                        "lng": coords.get("lng", 0),
                    },
                    "color": STATUS_COLORS.get(status, "#6B7280"),
                    "source": approval.source,
                })

        except Exception as e:
            logger.warning(f"Failed to fetch regulatory data for map: {e}")
            # Return empty regions on error

        return {
            "molecule_id": molecule_id,
            "molecule_name": molecule_name,
            "regions": regions,
            "status_colors": {
                "approved": "#10B981",
                "pending": "#F59E0B",
                "under_review": "#3B82F6",
                "not_submitted": "#6B7280",
                "refused": "#EF4444",
                "withdrawn": "#EF4444",
            },
            "center": {"lat": 20, "lng": 0},
            "zoom": 2,
            "total_regions": len(regions),
            "approved_count": sum(1 for r in regions if r["status"] == "approved"),
        }

    async def get_competitive_radar(
        self,
        molecule_id: str,
        competitor_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Get competitive comparison data for radar chart.

        Args:
            molecule_id: Core molecule ID
            competitor_ids: List of competitor IDs

        Returns:
            Radar chart data
        """
        # Dimensions for comparison
        dimensions = [
            "Clinical Stage",
            "Safety Profile",
            "Patent Strength",
            "Market Presence",
            "Publications",
            "Regulatory Status",
        ]

        colors = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#06B6D4"]
        all_molecule_ids = [molecule_id] + competitor_ids[:5]  # Max 6 total

        molecules = []

        # Calculate scores for each molecule
        for i, mol_id in enumerate(all_molecule_ids):
            scores = {}

            try:
                # Get clinical stage score
                lifecycle_service = self._get_lifecycle_service()
                lifecycle = await lifecycle_service.get_lifecycle(mol_id)

                # Clinical stage: Phase 1=20, Phase 2=40, Phase 3=60, Approved=80, Marketed=100
                phase_scores = {
                    "discovery": 10, "preclinical": 15, "phase_1": 25,
                    "phase_2": 45, "phase_3": 65, "approved": 85, "marketed": 95
                }
                scores["Clinical Stage"] = phase_scores.get(lifecycle.current_phase.value, 50)

                # Regulatory status: based on number of approvals
                regulatory_service = self._get_global_regulatory_service()
                global_status = await regulatory_service.get_global_approval_status(mol_id)
                approved_count = global_status.total_approved_regions
                scores["Regulatory Status"] = min(approved_count * 30 + 10, 100)  # 10 base, +30 per region, max 100

                # Safety profile: based on adverse events (fewer = better)
                try:
                    openfda_client = self._get_openfda_client()
                    adverse_events = await openfda_client.get_adverse_events(mol_id, limit=100)
                    serious_count = sum(1 for e in adverse_events if e.serious)
                    # Fewer serious events = higher score
                    scores["Safety Profile"] = max(100 - serious_count, 20)
                except Exception:
                    scores["Safety Profile"] = 50  # Default

                # Market presence: based on whether approved and years on market
                if lifecycle.approval_date:
                    from datetime import date
                    years_on_market = (date.today() - lifecycle.approval_date).days / 365
                    scores["Market Presence"] = min(30 + years_on_market * 10, 100)
                else:
                    scores["Market Presence"] = 20

                # Patent strength and publications: estimate based on lifecycle
                # These would require additional data sources
                scores["Patent Strength"] = 60 if lifecycle.approval_date else 40
                scores["Publications"] = 50 + len(lifecycle.milestones) * 2  # Simple estimate

            except Exception as e:
                logger.warning(f"Failed to calculate scores for {mol_id}: {e}")
                # Use default scores on error
                scores = {d: 50 for d in dimensions}

            molecules.append({
                "id": mol_id,
                "name": mol_id if i > 0 else f"{mol_id} (Core)",
                "scores": scores,
                "color": colors[i % len(colors)],
                "is_core": i == 0,
            })

        return {
            "dimensions": dimensions,
            "molecules": molecules,
            "max_value": 100,
            "options": {
                "showLegend": True,
                "showTooltip": True,
            },
            "core_molecule": molecule_id,
            "competitor_count": len(competitor_ids),
        }

    def graph_to_d3(self, graph: CompetitiveLandscapeGraph) -> Dict[str, Any]:
        """Convert CompetitiveLandscapeGraph to D3.js format."""
        nodes = []
        links = []

        for node in graph.nodes.values():
            nodes.append({
                "id": node.id,
                "label": node.name,
                "level": node.level.value,
                "stage": node.development_stage.value,
                "threat_score": node.threat_score,
                "color": self.LEVEL_COLORS.get(node.level, "#6B7280"),
                "size": 30 if node.level == GraphLevel.CORE else 20,
                "moa": node.mechanism_of_action,
                "sponsor": node.sponsor,
            })

        for edge in graph.edges:
            links.append({
                "source": edge.source_id,
                "target": edge.target_id,
                "score": edge.score,
                "dimension": edge.dimension.value,
                "color": self.DIMENSION_COLORS.get(edge.dimension, "#6B7280"),
                "width": max(1, edge.score * 5),
            })

        return {
            "nodes": nodes,
            "links": links,
            "core_id": graph.core_molecule_id,
            "depth": graph.depth,
        }

    def graph_to_cytoscape(self, graph: CompetitiveLandscapeGraph) -> Dict[str, Any]:
        """Convert CompetitiveLandscapeGraph to Cytoscape.js format."""
        elements = []

        for node in graph.nodes.values():
            elements.append({
                "data": {
                    "id": node.id,
                    "label": node.name,
                    "level": node.level.value,
                    "stage": node.development_stage.value,
                    "threat_score": node.threat_score,
                },
                "classes": f"level-{node.level.value}",
            })

        for edge in graph.edges:
            elements.append({
                "data": {
                    "id": f"{edge.source_id}-{edge.target_id}-{edge.dimension.value}",
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "score": edge.score,
                    "dimension": edge.dimension.value,
                },
                "classes": f"dimension-{edge.dimension.value}",
            })

        return {
            "elements": elements,
            "core_id": graph.core_molecule_id,
            "depth": graph.depth,
        }
