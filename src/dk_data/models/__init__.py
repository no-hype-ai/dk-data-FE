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
    CoverageGap,
    CoverageReport,
    DataSufficiencyScore,
)

from .indication import (
    Indication,
    DrugIndication,
    ICD10Hierarchy,
    IndicationOverlap,
)

from .lifecycle import (
    DataCoverage,
    DrugLifecycle,
    RegulatoryMilestone,
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
    "CoverageGap",
    "CoverageReport",
    "DataSufficiencyScore",
    # Indication
    "Indication",
    "DrugIndication",
    "ICD10Hierarchy",
    "IndicationOverlap",
    # Lifecycle
    "DataCoverage",
    "DrugLifecycle",
    "RegulatoryMilestone",
]
