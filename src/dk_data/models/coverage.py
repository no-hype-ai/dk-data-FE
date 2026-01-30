"""
Data Coverage Models.

Implements T018: DataSufficiencyScore dataclass
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class CoverageStatus(str, Enum):
    """Data coverage status levels."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    MISSING = "missing"


class DataCategory(str, Enum):
    """Data categories for coverage assessment."""
    REGULATORY = "regulatory"
    CLINICAL_TRIALS = "clinical_trials"
    SAFETY = "safety"
    PATENTS = "patents"
    PUBLICATIONS = "publications"
    PRICING = "pricing"
    MARKET = "market"


@dataclass
class SourceCoverage:
    """Coverage details for a single data source."""
    source_name: str
    category: DataCategory
    is_available: bool
    completeness: float  # 0-1 score
    record_count: int
    last_updated: Optional[datetime] = None
    quality_score: float = 1.0
    critical: bool = False  # Whether this is a critical source

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_name": self.source_name,
            "category": self.category.value,
            "is_available": self.is_available,
            "completeness": round(self.completeness, 3),
            "record_count": self.record_count,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "quality_score": round(self.quality_score, 3),
            "critical": self.critical,
        }


@dataclass
class CategoryScore:
    """Score for a data category."""
    category: DataCategory
    score: float
    sources_available: int
    sources_total: int
    critical_sources_missing: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category.value,
            "score": round(self.score, 3),
            "sources_available": self.sources_available,
            "sources_total": self.sources_total,
            "critical_sources_missing": self.critical_sources_missing,
        }


@dataclass
class DataSufficiencyScore:
    """
    Comprehensive data sufficiency score for a molecule.

    Tracks coverage across multiple data sources and categories.
    """
    drug_id: str
    drug_name: str
    overall_score: float  # 0-100 score
    overall_status: CoverageStatus
    category_scores: Dict[DataCategory, CategoryScore] = field(default_factory=dict)
    source_coverage: Dict[str, SourceCoverage] = field(default_factory=dict)
    missing_critical: List[str] = field(default_factory=list)
    missing_optional: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    assessed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "drug_id": self.drug_id,
            "drug_name": self.drug_name,
            "overall_score": round(self.overall_score, 1),
            "overall_status": self.overall_status.value,
            "category_scores": {
                k.value: v.to_dict() for k, v in self.category_scores.items()
            },
            "sources": {k: v.to_dict() for k, v in self.source_coverage.items()},
            "missing_critical": self.missing_critical,
            "missing_optional": self.missing_optional,
            "recommendations": self.recommendations,
            "assessed_at": self.assessed_at.isoformat(),
        }

    @staticmethod
    def calculate_status(score: float) -> CoverageStatus:
        """Calculate status from score."""
        if score >= 90:
            return CoverageStatus.EXCELLENT
        elif score >= 70:
            return CoverageStatus.GOOD
        elif score >= 50:
            return CoverageStatus.FAIR
        elif score > 0:
            return CoverageStatus.POOR
        else:
            return CoverageStatus.MISSING


@dataclass
class CoverageGap:
    """Represents a gap in data coverage."""
    source: str
    category: DataCategory
    severity: str  # critical, high, medium, low
    description: str
    remediation: str
    estimated_effort: str  # hours/days

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source": self.source,
            "category": self.category.value,
            "severity": self.severity,
            "description": self.description,
            "remediation": self.remediation,
            "estimated_effort": self.estimated_effort,
        }


@dataclass
class CoverageReport:
    """Full coverage report for a molecule."""
    drug_id: str
    drug_name: str
    sufficiency_score: DataSufficiencyScore
    gaps: List[CoverageGap] = field(default_factory=list)
    data_freshness: Dict[str, datetime] = field(default_factory=dict)
    comparison_to_peers: Optional[Dict[str, float]] = None
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "drug_id": self.drug_id,
            "drug_name": self.drug_name,
            "sufficiency_score": self.sufficiency_score.to_dict(),
            "gaps": [g.to_dict() for g in self.gaps],
            "data_freshness": {
                k: v.isoformat() for k, v in self.data_freshness.items()
            },
            "comparison_to_peers": self.comparison_to_peers,
            "generated_at": self.generated_at.isoformat(),
        }


# Source definitions with criticality
CRITICAL_SOURCES = {
    "fda_approvals": DataCategory.REGULATORY,
    "clinicaltrials_gov": DataCategory.CLINICAL_TRIALS,
    "faers": DataCategory.SAFETY,
    "orange_book": DataCategory.PATENTS,
}

OPTIONAL_SOURCES = {
    "ema": DataCategory.REGULATORY,
    "health_canada": DataCategory.REGULATORY,
    "pubmed": DataCategory.PUBLICATIONS,
    "patents_view": DataCategory.PATENTS,
    "nadac": DataCategory.PRICING,
    "drugbank": DataCategory.SAFETY,
}


def calculate_coverage_score(
    sources: Dict[str, SourceCoverage],
    category_weights: Optional[Dict[DataCategory, float]] = None,
) -> float:
    """
    Calculate overall coverage score from source coverage.

    Args:
        sources: Dictionary of source coverage
        category_weights: Optional weights per category

    Returns:
        Score between 0-100
    """
    if not sources:
        return 0.0

    if category_weights is None:
        category_weights = {
            DataCategory.REGULATORY: 0.25,
            DataCategory.CLINICAL_TRIALS: 0.25,
            DataCategory.SAFETY: 0.20,
            DataCategory.PATENTS: 0.15,
            DataCategory.PUBLICATIONS: 0.10,
            DataCategory.PRICING: 0.05,
        }

    # Group by category
    by_category: Dict[DataCategory, List[SourceCoverage]] = {}
    for source in sources.values():
        if source.category not in by_category:
            by_category[source.category] = []
        by_category[source.category].append(source)

    # Calculate weighted score
    total_weight = 0.0
    weighted_score = 0.0

    for category, weight in category_weights.items():
        if category in by_category:
            category_sources = by_category[category]
            # Average completeness for category
            avg_completeness = sum(s.completeness for s in category_sources) / len(category_sources)
            # Bonus for having critical sources
            critical_bonus = sum(0.1 for s in category_sources if s.critical and s.is_available)
            category_score = min(1.0, avg_completeness + critical_bonus)
            weighted_score += weight * category_score
            total_weight += weight

    if total_weight == 0:
        return 0.0

    return (weighted_score / total_weight) * 100
