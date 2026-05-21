"""Public config + value objects for the competitive graph service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ....models.competitive_graph import CompetitiveDimension, DevelopmentStage


@dataclass
class GraphBuildConfig:
    """Configuration for building competitive graphs."""

    depth: int = 1  # 1 = N+1 only, 2 = N+2
    min_score: float = 0.1
    dimensions: list[CompetitiveDimension] = field(
        default_factory=lambda: [
            CompetitiveDimension.INDICATION,
            CompetitiveDimension.MOA,
            CompetitiveDimension.TARGET,
        ]
    )
    max_competitors_per_dimension: int = 50
    include_preclinical: bool = False

    # CT.gov phase floor. Drops anything below — e.g. PHASE_2 cuts Phase 1.
    min_trial_phase: DevelopmentStage = DevelopmentStage.PHASE_2

    # Require RxNorm match — drops "study drug", trial-arm labels, vendor codes.
    validate_intervention_names: bool = True

    queue_failed_requests: bool = True


@dataclass
class FailedRequest:
    """A failed API request to retry later."""

    source: str
    query: str
    dimension: CompetitiveDimension
    error: str
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
