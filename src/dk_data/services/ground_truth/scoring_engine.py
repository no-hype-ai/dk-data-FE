"""
Competitive Threat Scoring Engine.

Calculates competitive threat scores using configurable weights from
scoring_config.yaml. Supports:
- Multi-dimensional scoring (indication, MOA, target, class, stage)
- Therapeutic area-specific weight overrides
- Time horizon estimation
- Threat level categorization
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import yaml
from loguru import logger

from ...models.competitive_graph import (
    CompetitiveDimension,
    CompetitiveEdge,
    CompetitiveLandscapeGraph,
    CompetitiveNode,
    DevelopmentStage,
    ThreatAssessment,
)


class ThreatLevel(str, Enum):
    """Threat level categories."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TimeHorizon(str, Enum):
    """Time horizon for competitive threat."""

    IMMINENT = "imminent"      # < 6 months
    NEAR_TERM = "near_term"    # < 18 months
    LONG_TERM = "long_term"    # < 36 months
    VERY_LONG = "very_long"    # > 36 months


@dataclass
class ScoringConfig:
    """Configuration loaded from scoring_config.yaml."""

    # Dimension weights
    dimension_weights: Dict[str, float] = field(default_factory=lambda: {
        "indication": 0.30,
        "moa": 0.25,
        "target": 0.20,
        "class": 0.15,
        "stage": 0.10,
    })

    # Therapeutic area overrides
    therapeutic_area_overrides: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Phase weights
    phase_weights: Dict[str, float] = field(default_factory=lambda: {
        "preclinical": 0.05,
        "phase_1": 0.10,
        "phase_1_2": 0.20,
        "phase_2": 0.30,
        "phase_2_3": 0.45,
        "phase_3": 0.60,
        "submitted": 0.80,
        "approved": 1.00,
        "marketed": 1.00,
        "withdrawn": 0.00,
        "discontinued": 0.00,
    })

    # Threat thresholds
    threat_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "critical": 0.70,
        "high": 0.50,
        "medium": 0.30,
        "low": 0.00,
    })

    # Time horizon thresholds (months)
    time_horizon_months: Dict[str, int] = field(default_factory=lambda: {
        "imminent": 6,
        "near_term": 18,
        "long_term": 36,
    })

    # Similarity thresholds
    tanimoto_min: float = 0.40
    indication_overlap_min: float = 0.20
    target_overlap_min: float = 0.30

    # Score aggregation
    aggregation_method: str = "weighted_average"
    secondary_boost: float = 0.05  # Boost for each additional dimension


class ScoringEngine:
    """
    Calculates competitive threat scores.

    Usage:
        engine = ScoringEngine()
        await engine.initialize()

        # Score a single competitor
        assessment = engine.assess_threat(
            core_node=core,
            competitor_node=competitor,
            edges=edges_between_them,
        )

        # Score entire graph
        assessments = engine.score_graph(graph)
    """

    def __init__(self, config: Optional[ScoringConfig] = None):
        self.config = config or ScoringConfig()
        self._config_loaded = False

    async def initialize(self) -> None:
        """Load configuration from YAML file."""
        await self._load_config()

    async def _load_config(self) -> None:
        """Load scoring configuration from YAML file."""
        try:
            config_path = os.path.join(
                os.path.dirname(__file__),
                "../../../config/scoring_config.yaml"
            )
            with open(config_path, "r") as f:
                yaml_config = yaml.safe_load(f)

            # Parse dimension weights
            dims = yaml_config.get("competitive_dimensions", {})
            if "default" in dims:
                self.config.dimension_weights = dims["default"]
            if "therapeutic_area_overrides" in dims:
                self.config.therapeutic_area_overrides = dims["therapeutic_area_overrides"]

            # Parse phase weights
            if "phase_weights" in yaml_config:
                self.config.phase_weights = yaml_config["phase_weights"]

            # Parse threat thresholds
            if "threat_thresholds" in yaml_config:
                self.config.threat_thresholds = yaml_config["threat_thresholds"]

            # Parse time horizon
            if "time_horizon" in yaml_config:
                self.config.time_horizon_months = yaml_config["time_horizon"]

            # Parse similarity thresholds
            sim = yaml_config.get("similarity", {})
            if "tanimoto" in sim:
                self.config.tanimoto_min = sim["tanimoto"].get("min_threshold", 0.40)
            if "indication_overlap" in sim:
                self.config.indication_overlap_min = sim["indication_overlap"].get("min_threshold", 0.20)
            if "target_overlap" in sim:
                self.config.target_overlap_min = sim["target_overlap"].get("min_threshold", 0.30)

            # Parse aggregation settings
            agg = yaml_config.get("score_aggregation", {})
            if "method" in agg:
                self.config.aggregation_method = agg["method"]
            mult = agg.get("multiple_relationships", {})
            if "secondary_boost" in mult:
                self.config.secondary_boost = mult["secondary_boost"]

            self._config_loaded = True
            logger.info("Loaded scoring configuration")

        except Exception as e:
            logger.warning(f"Could not load scoring config: {e}, using defaults")

    def get_dimension_weights(
        self,
        therapeutic_area: Optional[str] = None
    ) -> Dict[str, float]:
        """Get dimension weights, with optional therapeutic area override."""
        if therapeutic_area and therapeutic_area in self.config.therapeutic_area_overrides:
            return self.config.therapeutic_area_overrides[therapeutic_area]
        return self.config.dimension_weights

    def get_phase_weight(self, stage: DevelopmentStage) -> float:
        """Get weight for a development stage."""
        return self.config.phase_weights.get(stage.value, 0.5)

    def calculate_dimension_score(
        self,
        dimension: CompetitiveDimension,
        edges: List[CompetitiveEdge],
        competitor_stage: DevelopmentStage,
    ) -> float:
        """
        Calculate score for a single competitive dimension.

        Args:
            dimension: The competitive dimension
            edges: Edges representing this dimension's relationship
            competitor_stage: Development stage of the competitor

        Returns:
            Score between 0 and 1
        """
        if not edges:
            return 0.0

        # Get max edge score for this dimension
        dimension_edges = [e for e in edges if e.dimension == dimension]
        if not dimension_edges:
            return 0.0

        max_edge_score = max(e.score for e in dimension_edges)

        # Apply phase weighting
        phase_weight = self.get_phase_weight(competitor_stage)

        # Dimension-specific scoring formulas (from inference_rules.yaml)
        if dimension == CompetitiveDimension.INDICATION:
            # 0.30 * indication_overlap + 0.70 * phase_weight
            return 0.30 * max_edge_score + 0.70 * phase_weight
        elif dimension == CompetitiveDimension.MOA:
            # 0.40 * moa_similarity + 0.60 * phase_weight
            return 0.40 * max_edge_score + 0.60 * phase_weight
        elif dimension == CompetitiveDimension.TARGET:
            # 0.35 * target_overlap + 0.65 * phase_weight
            return 0.35 * max_edge_score + 0.65 * phase_weight
        elif dimension == CompetitiveDimension.CLASS:
            # 0.25 * class_similarity + 0.75 * phase_weight
            return 0.25 * max_edge_score + 0.75 * phase_weight
        elif dimension == CompetitiveDimension.STRUCTURE:
            # 0.20 * tanimoto + 0.80 * phase_weight
            return 0.20 * max_edge_score + 0.80 * phase_weight
        else:
            return max_edge_score * phase_weight

    def calculate_overall_score(
        self,
        dimension_scores: Dict[CompetitiveDimension, float],
        therapeutic_area: Optional[str] = None,
    ) -> float:
        """
        Calculate overall threat score from dimension scores.

        Args:
            dimension_scores: Scores by dimension
            therapeutic_area: Optional therapeutic area for weight overrides

        Returns:
            Overall score between 0 and 1
        """
        weights = self.get_dimension_weights(therapeutic_area)

        if self.config.aggregation_method == "max":
            return max(dimension_scores.values()) if dimension_scores else 0.0

        elif self.config.aggregation_method == "sum_capped":
            total = sum(dimension_scores.values())
            return min(1.0, total)

        else:  # weighted_average (default)
            weighted_sum = 0.0
            weight_sum = 0.0

            for dimension, score in dimension_scores.items():
                dim_key = dimension.value
                weight = weights.get(dim_key, 0.1)
                weighted_sum += score * weight
                weight_sum += weight

            if weight_sum == 0:
                return 0.0

            base_score = weighted_sum / weight_sum

            # Apply secondary boost for multiple dimensions
            num_dimensions = len([s for s in dimension_scores.values() if s > 0])
            if num_dimensions > 1:
                boost = (num_dimensions - 1) * self.config.secondary_boost
                base_score = min(1.0, base_score + boost)

            return base_score

    def determine_threat_level(self, score: float) -> ThreatLevel:
        """Determine threat level from score."""
        thresholds = self.config.threat_thresholds

        if score >= thresholds.get("critical", 0.70):
            return ThreatLevel.CRITICAL
        elif score >= thresholds.get("high", 0.50):
            return ThreatLevel.HIGH
        elif score >= thresholds.get("medium", 0.30):
            return ThreatLevel.MEDIUM
        else:
            return ThreatLevel.LOW

    def estimate_time_horizon(
        self,
        competitor_stage: DevelopmentStage,
    ) -> TimeHorizon:
        """
        Estimate time horizon for competitive threat.

        Based on typical development timelines by phase.
        """
        # Typical months to approval by stage
        months_to_approval = {
            DevelopmentStage.APPROVED: 0,
            DevelopmentStage.MARKETED: 0,
            DevelopmentStage.SUBMITTED: 6,
            DevelopmentStage.PHASE_3: 24,
            DevelopmentStage.PHASE_2_3: 30,
            DevelopmentStage.PHASE_2: 48,
            DevelopmentStage.PHASE_1_2: 54,
            DevelopmentStage.PHASE_1: 60,
            DevelopmentStage.PRECLINICAL: 84,
            DevelopmentStage.WITHDRAWN: 999,
            DevelopmentStage.DISCONTINUED: 999,
        }

        months = months_to_approval.get(competitor_stage, 60)
        thresholds = self.config.time_horizon_months

        if months <= thresholds.get("imminent", 6):
            return TimeHorizon.IMMINENT
        elif months <= thresholds.get("near_term", 18):
            return TimeHorizon.NEAR_TERM
        elif months <= thresholds.get("long_term", 36):
            return TimeHorizon.LONG_TERM
        else:
            return TimeHorizon.VERY_LONG

    def assess_threat(
        self,
        core_node: CompetitiveNode,
        competitor_node: CompetitiveNode,
        edges: List[CompetitiveEdge],
        therapeutic_area: Optional[str] = None,
    ) -> ThreatAssessment:
        """
        Generate a complete threat assessment for a competitor.

        Args:
            core_node: The core molecule being analyzed
            competitor_node: The competitor to assess
            edges: All edges between core and competitor
            therapeutic_area: Therapeutic area for weight overrides

        Returns:
            ThreatAssessment with scores and recommendations
        """
        # Calculate dimension scores
        dimension_scores: Dict[CompetitiveDimension, float] = {}
        for dimension in CompetitiveDimension:
            score = self.calculate_dimension_score(
                dimension=dimension,
                edges=edges,
                competitor_stage=competitor_node.development_stage,
            )
            if score > 0:
                dimension_scores[dimension] = score

        # Calculate overall score
        overall_score = self.calculate_overall_score(
            dimension_scores,
            therapeutic_area=therapeutic_area,
        )

        # Determine threat level and time horizon
        threat_level = self.determine_threat_level(overall_score)
        time_horizon = self.estimate_time_horizon(competitor_node.development_stage)

        # Generate factors contributing to threat
        factors = self._generate_threat_factors(
            competitor_node,
            dimension_scores,
            edges,
        )

        # Generate monitoring recommendations
        monitoring_actions = self._generate_monitoring_actions(
            threat_level,
            time_horizon,
            competitor_node,
        )

        # Gather evidence
        evidence = []
        for edge in edges:
            evidence.extend(edge.evidence)

        return ThreatAssessment(
            competitor_id=competitor_node.id,
            competitor_name=competitor_node.name,
            threat_level=threat_level.value,
            time_horizon=time_horizon.value,
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            factors=factors,
            monitoring_actions=monitoring_actions,
            evidence=evidence,
            confidence=min(e.confidence for e in edges) if edges else 1.0,
        )

    def _generate_threat_factors(
        self,
        competitor: CompetitiveNode,
        dimension_scores: Dict[CompetitiveDimension, float],
        edges: List[CompetitiveEdge],
    ) -> List[str]:
        """Generate human-readable threat factors."""
        factors = []

        # Stage-based factors
        if competitor.development_stage in [DevelopmentStage.APPROVED, DevelopmentStage.MARKETED]:
            factors.append("Already approved/marketed")
        elif competitor.development_stage == DevelopmentStage.SUBMITTED:
            factors.append("Regulatory submission pending")
        elif competitor.development_stage == DevelopmentStage.PHASE_3:
            factors.append("Late-stage development (Phase 3)")

        # Dimension-based factors
        if dimension_scores.get(CompetitiveDimension.INDICATION, 0) > 0.5:
            factors.append("High indication overlap")
        if dimension_scores.get(CompetitiveDimension.MOA, 0) > 0.5:
            factors.append("Same mechanism of action")
        if dimension_scores.get(CompetitiveDimension.TARGET, 0) > 0.5:
            factors.append("Targets same molecular pathway")

        # Sponsor-based factors
        if competitor.sponsor:
            factors.append(f"Sponsored by {competitor.sponsor}")

        return factors

    def _generate_monitoring_actions(
        self,
        threat_level: ThreatLevel,
        time_horizon: TimeHorizon,
        competitor: CompetitiveNode,
    ) -> List[str]:
        """Generate recommended monitoring actions."""
        actions = []

        if threat_level == ThreatLevel.CRITICAL:
            actions.append("Immediate competitive response planning required")
            actions.append("Monitor regulatory filings weekly")
            actions.append("Analyze competitor trial results as released")
        elif threat_level == ThreatLevel.HIGH:
            actions.append("Develop contingency competitive strategy")
            actions.append("Monitor clinical trial progress monthly")
            actions.append("Track conference presentations and publications")
        elif threat_level == ThreatLevel.MEDIUM:
            actions.append("Include in quarterly competitive review")
            actions.append("Monitor key development milestones")
        else:
            actions.append("Annual competitive landscape review")

        # Time horizon specific
        if time_horizon == TimeHorizon.IMMINENT:
            actions.append("Prepare market access strategy")
        elif time_horizon == TimeHorizon.NEAR_TERM:
            actions.append("Begin differentiation messaging development")

        return actions

    def score_graph(
        self,
        graph: CompetitiveLandscapeGraph,
        therapeutic_area: Optional[str] = None,
    ) -> List[ThreatAssessment]:
        """
        Score all competitors in a graph.

        Args:
            graph: The competitive landscape graph
            therapeutic_area: Therapeutic area for weight overrides

        Returns:
            List of ThreatAssessments sorted by score descending
        """
        assessments = []
        core_node = graph.core_molecule

        if not core_node:
            return assessments

        for node in graph.get_competitors():
            edges = graph.get_edges_for_node(node.id)

            # Filter to edges connected to this competitor
            relevant_edges = [
                e for e in edges
                if (e.source_id == core_node.id and e.target_id == node.id) or
                   (e.target_id == core_node.id and e.source_id == node.id)
            ]

            assessment = self.assess_threat(
                core_node=core_node,
                competitor_node=node,
                edges=relevant_edges,
                therapeutic_area=therapeutic_area,
            )

            # Update node's threat score
            node.threat_score = assessment.overall_score

            assessments.append(assessment)

        # Sort by overall score descending
        assessments.sort(key=lambda a: a.overall_score, reverse=True)

        return assessments


# Singleton instance
_scoring_engine: Optional[ScoringEngine] = None


async def get_scoring_engine(config: Optional[ScoringConfig] = None) -> ScoringEngine:
    """Get or create the scoring engine instance."""
    global _scoring_engine

    if _scoring_engine is None:
        _scoring_engine = ScoringEngine(config)
        await _scoring_engine.initialize()

    return _scoring_engine
