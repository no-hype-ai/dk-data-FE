"""
Competitive Graph Data Models.

Models for representing N+2 competitive landscape graphs,
including nodes, edges, and the complete graph structure.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class GraphLevel(Enum):
    """Level in the competitive graph hierarchy."""

    CORE = 0      # N - The core molecule being analyzed
    N_PLUS_1 = 1  # N+1 - Direct competitors
    N_PLUS_2 = 2  # N+2 - Competitors' competitors


class CompetitiveDimension(str, Enum):
    """Dimensions along which molecules can compete."""

    INDICATION = "indication"   # Same disease/condition
    MOA = "moa"                # Same mechanism of action
    TARGET = "target"          # Same molecular target
    CLASS = "class"            # Same ATC drug class
    STAGE = "stage"            # Same development phase
    STRUCTURE = "structure"    # Structural similarity


class DevelopmentStage(str, Enum):
    """Drug development stages. Tuple = (serialized value, ordinal rank).

    `rank` orders stages by progression. Ties allowed (APPROVED == MARKETED).
    WITHDRAWN/DISCONTINUED rank 0 so they're treated as non-competing.
    """

    PRECLINICAL  = ("preclinical",  0)
    PHASE_1      = ("phase_1",      1)
    PHASE_1_2    = ("phase_1_2",    2)
    PHASE_2      = ("phase_2",      3)
    PHASE_2_3    = ("phase_2_3",    4)
    PHASE_3      = ("phase_3",      5)
    SUBMITTED    = ("submitted",    6)
    APPROVED     = ("approved",     7)
    MARKETED     = ("marketed",     7)
    WITHDRAWN    = ("withdrawn",    0)
    DISCONTINUED = ("discontinued", 0)

    def __new__(cls, value: str, rank: int):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.rank = rank
        return obj


@dataclass
class CompetitiveNode:
    """
    A node in the competitive landscape graph.

    Represents a molecule with its key attributes for competitive analysis.
    """

    # Core identifiers
    id: str  # Internal unique ID
    name: str  # Primary name (INN or brand)
    generic_name: Optional[str] = None  # INN/generic name
    brand_names: List[str] = field(default_factory=list)  # Brand/trade names
    drugbank_id: Optional[str] = None
    inchi_key: Optional[str] = None
    chembl_id: Optional[str] = None

    # Competitive attributes
    development_stage: DevelopmentStage = DevelopmentStage.PRECLINICAL
    mechanism_of_action: Optional[str] = None
    primary_indication: Optional[str] = None
    secondary_indications: List[str] = field(default_factory=list)
    atc_codes: List[str] = field(default_factory=list)
    targets: List[str] = field(default_factory=list)

    # Graph metadata
    level: GraphLevel = GraphLevel.CORE
    discovered_via: List[str] = field(default_factory=list)  # How this node was found

    # Company info
    sponsor: Optional[str] = None
    originator: Optional[str] = None

    # Scores
    threat_score: float = 0.0  # Overall competitive threat score
    data_coverage: float = 0.0  # Data sufficiency score

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Additional data
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CompetitiveNode):
            return False
        return self.id == other.id

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "generic_name": self.generic_name,
            "brand_names": self.brand_names,
            "drugbank_id": self.drugbank_id,
            "inchi_key": self.inchi_key,
            "chembl_id": self.chembl_id,
            "development_stage": self.development_stage.value,
            "mechanism_of_action": self.mechanism_of_action,
            "primary_indication": self.primary_indication,
            "secondary_indications": self.secondary_indications,
            "atc_codes": self.atc_codes,
            "targets": self.targets,
            "level": self.level.value,
            "discovered_via": self.discovered_via,
            "sponsor": self.sponsor,
            "originator": self.originator,
            "threat_score": self.threat_score,
            "data_coverage": self.data_coverage,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompetitiveNode":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            generic_name=data.get("generic_name"),
            brand_names=data.get("brand_names", []),
            drugbank_id=data.get("drugbank_id"),
            inchi_key=data.get("inchi_key"),
            chembl_id=data.get("chembl_id"),
            development_stage=DevelopmentStage(data.get("development_stage", "preclinical")),
            mechanism_of_action=data.get("mechanism_of_action"),
            primary_indication=data.get("primary_indication"),
            secondary_indications=data.get("secondary_indications", []),
            atc_codes=data.get("atc_codes", []),
            targets=data.get("targets", []),
            level=GraphLevel(data.get("level", 0)),
            discovered_via=data.get("discovered_via", []),
            sponsor=data.get("sponsor"),
            originator=data.get("originator"),
            threat_score=data.get("threat_score", 0.0),
            data_coverage=data.get("data_coverage", 0.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CompetitiveEdge:
    """
    An edge in the competitive landscape graph.

    Represents a competitive relationship between two molecules.
    """

    source_id: str  # Source molecule ID
    target_id: str  # Target molecule ID

    # Relationship attributes
    dimension: CompetitiveDimension  # What dimension this competition is on
    score: float  # Competitive score (0-1)
    confidence: float = 1.0  # Confidence in this relationship

    # Discovery metadata
    discovered_via: Optional[str] = None  # How this edge was discovered
    evidence: List[str] = field(default_factory=list)  # Supporting evidence

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __hash__(self) -> int:
        return hash((self.source_id, self.target_id, self.dimension))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CompetitiveEdge):
            return False
        return (
            self.source_id == other.source_id
            and self.target_id == other.target_id
            and self.dimension == other.dimension
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "dimension": self.dimension.value,
            "score": self.score,
            "confidence": self.confidence,
            "discovered_via": self.discovered_via,
            "evidence": self.evidence,
        }


@dataclass
class CompetitiveLandscapeGraph:
    """
    Complete competitive landscape graph for a molecule.

    Contains all nodes (N, N+1, N+2) and edges representing
    competitive relationships.
    """

    # Core molecule
    core_molecule_id: str
    core_molecule: Optional[CompetitiveNode] = None

    # Graph data
    nodes: Dict[str, CompetitiveNode] = field(default_factory=dict)
    edges: List[CompetitiveEdge] = field(default_factory=list)

    # Deduplication tracking
    _seen_ids: Set[str] = field(default_factory=set, repr=False)

    # Build metadata
    depth: int = 2  # Max depth (1 = N+1 only, 2 = N+2)
    built_at: datetime = field(default_factory=datetime.utcnow)
    build_time_ms: int = 0

    # Filters applied
    min_score: float = 0.0
    dimensions_included: List[CompetitiveDimension] = field(
        default_factory=lambda: list(CompetitiveDimension)
    )

    def add_node(
        self,
        node: CompetitiveNode,
        allow_level_promotion: bool = True
    ) -> bool:
        """
        Add a node to the graph with deduplication.

        Args:
            node: The node to add
            allow_level_promotion: If True, promote to closer level if duplicate

        Returns:
            True if node was added or promoted, False if blocked
        """
        # Block circular reference (core molecule appearing in N+1 or N+2)
        if node.id == self.core_molecule_id and node.level != GraphLevel.CORE:
            return False

        # Check for duplicates
        if node.id in self.nodes:
            existing = self.nodes[node.id]

            # Level promotion: closer level wins
            if allow_level_promotion and node.level.value < existing.level.value:
                # Promote to closer level, merge discovery paths
                existing.level = node.level
                existing.discovered_via.extend(node.discovered_via)
                return True

            # Already exists at same or closer level
            # Merge discovery paths
            existing.discovered_via.extend(node.discovered_via)
            return False

        # Add new node
        self.nodes[node.id] = node
        self._seen_ids.add(node.id)
        return True

    def add_edge(
        self,
        edge: CompetitiveEdge,
        min_score: Optional[float] = None
    ) -> bool:
        """
        Add an edge to the graph.

        Args:
            edge: The edge to add
            min_score: Minimum score threshold (uses graph default if None)

        Returns:
            True if edge was added, False if blocked
        """
        threshold = min_score if min_score is not None else self.min_score

        # Check score threshold
        if edge.score < threshold:
            return False

        # Check both nodes exist
        if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
            return False

        # Check dimension is included
        if edge.dimension not in self.dimensions_included:
            return False

        # Check for duplicate edge
        for existing in self.edges:
            if existing == edge:
                # Update score if higher
                if edge.score > existing.score:
                    existing.score = edge.score
                return False

        self.edges.append(edge)
        return True

    def get_nodes_at_level(self, level: GraphLevel) -> List[CompetitiveNode]:
        """Get all nodes at a specific level."""
        return [n for n in self.nodes.values() if n.level == level]

    def get_edges_for_node(self, node_id: str) -> List[CompetitiveEdge]:
        """Get all edges connected to a node."""
        return [
            e for e in self.edges
            if e.source_id == node_id or e.target_id == node_id
        ]

    def get_competitors(
        self,
        level: Optional[GraphLevel] = None,
        min_score: float = 0.0
    ) -> List[CompetitiveNode]:
        """
        Get competitor nodes, optionally filtered.

        Args:
            level: Filter by level (None = all levels except CORE)
            min_score: Minimum threat score

        Returns:
            List of competitor nodes
        """
        competitors = []
        for node in self.nodes.values():
            if node.level == GraphLevel.CORE:
                continue
            if level is not None and node.level != level:
                continue
            if node.threat_score >= min_score:
                competitors.append(node)

        return sorted(competitors, key=lambda n: n.threat_score, reverse=True)

    def to_visualization_format(self, layout: str = "force") -> Dict[str, Any]:
        """
        Convert graph to D3.js/Cytoscape.js compatible format.

        Args:
            layout: Layout algorithm hint (force, hierarchical, circular)

        Returns:
            Dictionary with nodes and edges arrays
        """
        vis_nodes = []
        for node in self.nodes.values():
            vis_nodes.append({
                "id": node.id,
                "label": node.name,
                "generic_name": node.generic_name,
                "brand_names": node.brand_names,
                "level": node.level.value,
                "stage": node.development_stage.value,
                "threat_score": node.threat_score,
                "sponsor": node.sponsor,
                "moa": node.mechanism_of_action,
            })

        vis_edges = []
        for edge in self.edges:
            vis_edges.append({
                "source": edge.source_id,
                "target": edge.target_id,
                "score": edge.score,
                "dimension": edge.dimension.value,
            })

        return {
            "nodes": vis_nodes,
            "edges": vis_edges,
            "layout": layout,
            "core_id": self.core_molecule_id,
            "depth": self.depth,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "core_molecule_id": self.core_molecule_id,
            "core_molecule": self.core_molecule.to_dict() if self.core_molecule else None,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "depth": self.depth,
            "built_at": self.built_at.isoformat(),
            "build_time_ms": self.build_time_ms,
            "min_score": self.min_score,
            "dimensions_included": [d.value for d in self.dimensions_included],
            "stats": {
                "total_nodes": len(self.nodes),
                "n_plus_1_count": len(self.get_nodes_at_level(GraphLevel.N_PLUS_1)),
                "n_plus_2_count": len(self.get_nodes_at_level(GraphLevel.N_PLUS_2)),
                "total_edges": len(self.edges),
            },
        }


@dataclass
class ThreatAssessment:
    """Assessment of competitive threat from a specific competitor."""

    competitor_id: str
    competitor_name: str
    threat_level: str  # critical, high, medium, low
    time_horizon: str  # imminent, near_term, long_term
    overall_score: float

    # Breakdown by dimension
    dimension_scores: Dict[CompetitiveDimension, float] = field(default_factory=dict)

    # Factors contributing to threat
    factors: List[str] = field(default_factory=list)

    # Recommended actions
    monitoring_actions: List[str] = field(default_factory=list)

    # Evidence
    evidence: List[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "competitor_id": self.competitor_id,
            "competitor_name": self.competitor_name,
            "threat_level": self.threat_level,
            "time_horizon": self.time_horizon,
            "overall_score": self.overall_score,
            "dimension_scores": {k.value: v for k, v in self.dimension_scores.items()},
            "factors": self.factors,
            "monitoring_actions": self.monitoring_actions,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }
