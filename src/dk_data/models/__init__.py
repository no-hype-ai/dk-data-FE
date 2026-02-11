"""
DK Data Models Package.

Pydantic models for the Medallion Architecture:
- Bronze: Raw data models from external sources
- Silver: Transformed and normalized models
- Gold: Aggregated analytics models
- Application: User-facing API models
"""

from . import bronze
from . import silver
from . import gold
from . import application

# Standalone models
from .competitive_graph import (
    CompetitiveNode,
    CompetitiveEdge,
    CompetitiveLandscapeGraph,
    ThreatAssessment,
)

from .coverage import (
    CoverageStatus,
    SourceCoverage,
    OverallCoverage,
    CoverageGap,
)

from .indication import (
    Indication,
    IndicationMatch,
    IndicationHierarchy,
)

from .lifecycle import (
    DataCoverage,
    DrugLifecycle,
    LifecycleStage,
    Milestone,
)

__all__ = [
    # Sub-packages
    "bronze",
    "silver",
    "gold",
    "application",
    # Competitive Graph
    "CompetitiveNode",
    "CompetitiveEdge",
    "CompetitiveLandscapeGraph",
    "ThreatAssessment",
    # Coverage
    "CoverageStatus",
    "SourceCoverage",
    "OverallCoverage",
    "CoverageGap",
    # Indication
    "Indication",
    "IndicationMatch",
    "IndicationHierarchy",
    # Lifecycle
    "DataCoverage",
    "DrugLifecycle",
    "LifecycleStage",
    "Milestone",
]
