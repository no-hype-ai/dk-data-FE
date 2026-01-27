"""
Drug Lifecycle and Data Coverage Models.

Models for tracking drug development lifecycle stages,
regulatory milestones, and data completeness/coverage.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class RegulatoryAgency(str, Enum):
    """Major regulatory agencies."""

    FDA = "fda"      # US Food and Drug Administration
    EMA = "ema"      # European Medicines Agency
    PMDA = "pmda"    # Japan Pharmaceuticals and Medical Devices Agency
    NMPA = "nmpa"    # China National Medical Products Administration
    TGA = "tga"      # Australia Therapeutic Goods Administration
    HEALTH_CANADA = "health_canada"
    MHRA = "mhra"    # UK Medicines and Healthcare products Regulatory Agency


class ApplicationType(str, Enum):
    """FDA application types."""

    NDA = "nda"         # New Drug Application (small molecule)
    BLA = "bla"         # Biologics License Application
    ANDA = "anda"       # Abbreviated NDA (generics)
    IND = "ind"         # Investigational New Drug
    SUPPLEMENT = "supplement"  # sNDA/sBLA
    OTC = "otc"         # Over-the-counter


class DesignationType(str, Enum):
    """Special FDA designations."""

    ORPHAN = "orphan"
    BREAKTHROUGH = "breakthrough"
    FAST_TRACK = "fast_track"
    PRIORITY_REVIEW = "priority_review"
    ACCELERATED_APPROVAL = "accelerated_approval"
    REMS = "rems"  # Risk Evaluation and Mitigation Strategy


class ExclusivityType(str, Enum):
    """Market exclusivity types."""

    NCE = "nce"                # New Chemical Entity (5 years)
    ORPHAN = "orphan"          # Orphan Drug (7 years)
    PEDIATRIC = "pediatric"    # Pediatric (6 months)
    NEW_PATIENT_POP = "new_patient_pop"  # 3 years
    BIOSIMILAR = "biosimilar"  # Reference product (12 years)
    PATENT = "patent"          # Patent protection


class PatentType(str, Enum):
    """Patent types for pharmaceutical products."""

    COMPOUND = "compound"          # Active ingredient
    FORMULATION = "formulation"    # Drug formulation
    METHOD_OF_USE = "method_of_use"  # Treatment method
    PROCESS = "process"            # Manufacturing process
    POLYMORPH = "polymorph"        # Crystal form


class DataSourceCategory(str, Enum):
    """Categories of data sources for coverage tracking."""

    IDENTIFIERS = "identifiers"       # DrugBank ID, InChI Key, etc.
    STRUCTURE = "structure"           # SMILES, molecular weight, etc.
    CLINICAL_TRIALS = "clinical_trials"
    REGULATORY = "regulatory"         # FDA/EMA approval status
    SAFETY = "safety"                 # FAERS, adverse events
    PRICING = "pricing"               # NADAC, market data
    PATENTS = "patents"               # Patent/exclusivity data
    PUBLICATIONS = "publications"     # Literature references


@dataclass
class RegulatoryMilestone:
    """
    A regulatory milestone in the drug development lifecycle.

    Represents events like IND filing, NDA submission, approval, etc.
    """

    milestone_type: str  # e.g., "IND_FILED", "NDA_SUBMITTED", "APPROVED"
    date: Optional[date] = None
    agency: RegulatoryAgency = RegulatoryAgency.FDA

    # Application details
    application_type: Optional[ApplicationType] = None
    application_number: Optional[str] = None  # e.g., "NDA 210861"

    # Status
    status: Optional[str] = None  # e.g., "Approved", "Tentative Approval"
    action_date: Optional[date] = None

    # Additional info
    indication: Optional[str] = None
    sponsor: Optional[str] = None
    notes: Optional[str] = None

    # Source
    source_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "milestone_type": self.milestone_type,
            "date": self.date.isoformat() if self.date else None,
            "agency": self.agency.value,
            "application_type": self.application_type.value if self.application_type else None,
            "application_number": self.application_number,
            "status": self.status,
            "action_date": self.action_date.isoformat() if self.action_date else None,
            "indication": self.indication,
            "sponsor": self.sponsor,
            "notes": self.notes,
            "source_url": self.source_url,
        }


@dataclass
class Designation:
    """
    A special regulatory designation for a drug.

    Tracks orphan drug, breakthrough therapy, fast track, etc.
    """

    designation_type: DesignationType
    indication: str
    grant_date: Optional[date] = None
    agency: RegulatoryAgency = RegulatoryAgency.FDA

    # Status
    is_active: bool = True
    withdrawn_date: Optional[date] = None

    # Source
    source_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "designation_type": self.designation_type.value,
            "indication": self.indication,
            "grant_date": self.grant_date.isoformat() if self.grant_date else None,
            "agency": self.agency.value,
            "is_active": self.is_active,
            "withdrawn_date": self.withdrawn_date.isoformat() if self.withdrawn_date else None,
            "source_url": self.source_url,
        }


@dataclass
class Exclusivity:
    """
    Market exclusivity period for a drug.

    Tracks NCE, orphan, pediatric, and other exclusivity periods.
    """

    exclusivity_type: ExclusivityType
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    application_number: Optional[str] = None

    # Status
    is_active: bool = True
    days_remaining: int = 0

    # Source (Orange Book, Purple Book, etc.)
    source: Optional[str] = None
    source_url: Optional[str] = None

    def calculate_days_remaining(self, as_of: date = None) -> int:
        """Calculate days remaining in exclusivity period."""
        if not self.end_date:
            return 0
        check_date = as_of or date.today()
        delta = self.end_date - check_date
        return max(0, delta.days)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "exclusivity_type": self.exclusivity_type.value,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "application_number": self.application_number,
            "is_active": self.is_active,
            "days_remaining": self.calculate_days_remaining(),
            "source": self.source,
            "source_url": self.source_url,
        }


@dataclass
class Patent:
    """
    A patent associated with a drug product.

    Tracks patent numbers, expiration dates, and types.
    """

    patent_number: str
    patent_type: PatentType = PatentType.COMPOUND
    expiration_date: Optional[date] = None

    # Claims
    claims_compound: bool = False
    claims_formulation: bool = False
    claims_method_of_use: bool = False

    # Status
    is_active: bool = True
    is_listed_orange_book: bool = False

    # Pediatric extension
    pediatric_extension: bool = False
    extended_expiration: Optional[date] = None

    # Source
    source: Optional[str] = None  # "orange_book", "purple_book", "uspto"

    def get_effective_expiration(self) -> Optional[date]:
        """Get effective expiration including extensions."""
        if self.extended_expiration:
            return self.extended_expiration
        return self.expiration_date

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "patent_number": self.patent_number,
            "patent_type": self.patent_type.value,
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
            "claims_compound": self.claims_compound,
            "claims_formulation": self.claims_formulation,
            "claims_method_of_use": self.claims_method_of_use,
            "is_active": self.is_active,
            "is_listed_orange_book": self.is_listed_orange_book,
            "pediatric_extension": self.pediatric_extension,
            "extended_expiration": self.extended_expiration.isoformat() if self.extended_expiration else None,
            "effective_expiration": self.get_effective_expiration().isoformat() if self.get_effective_expiration() else None,
            "source": self.source,
        }


@dataclass
class DrugLifecycle:
    """
    Complete lifecycle information for a drug.

    Aggregates all regulatory milestones, designations,
    exclusivities, and patents for competitive analysis.
    """

    drug_id: str
    drug_name: str

    # Development stage
    current_stage: str = "preclinical"  # Maps to DevelopmentStage
    is_approved: bool = False
    is_marketed: bool = False
    is_discontinued: bool = False

    # Milestones
    milestones: List[RegulatoryMilestone] = field(default_factory=list)

    # Designations
    designations: List[Designation] = field(default_factory=list)

    # Exclusivity
    exclusivities: List[Exclusivity] = field(default_factory=list)

    # Patents
    patents: List[Patent] = field(default_factory=list)

    # Key dates
    first_approval_date: Optional[date] = None
    first_marketed_date: Optional[date] = None
    patent_expiry_date: Optional[date] = None  # Earliest expiry
    exclusivity_expiry_date: Optional[date] = None

    # Time estimates (months)
    estimated_time_to_approval: Optional[int] = None
    estimated_time_to_market: Optional[int] = None

    # Metadata
    last_updated: datetime = field(default_factory=datetime.utcnow)
    data_sources: List[str] = field(default_factory=list)

    def add_milestone(self, milestone: RegulatoryMilestone) -> None:
        """Add a milestone and update stage if needed."""
        self.milestones.append(milestone)
        self._update_stage_from_milestones()

    def _update_stage_from_milestones(self) -> None:
        """Update current stage based on milestones."""
        stage_priority = {
            "APPROVED": "approved",
            "NDA_SUBMITTED": "submitted",
            "BLA_SUBMITTED": "submitted",
            "PHASE_3_STARTED": "phase_3",
            "PHASE_2_STARTED": "phase_2",
            "PHASE_1_STARTED": "phase_1",
            "IND_FILED": "phase_1",
            "PRECLINICAL": "preclinical",
        }

        highest_stage = "preclinical"
        for milestone in self.milestones:
            if milestone.milestone_type in stage_priority:
                highest_stage = stage_priority[milestone.milestone_type]
                break

        self.current_stage = highest_stage

    def get_active_designations(self) -> List[Designation]:
        """Get currently active designations."""
        return [d for d in self.designations if d.is_active]

    def get_active_exclusivities(self) -> List[Exclusivity]:
        """Get currently active exclusivities."""
        return [e for e in self.exclusivities if e.is_active]

    def get_active_patents(self) -> List[Patent]:
        """Get currently active patents."""
        today = date.today()
        return [
            p for p in self.patents
            if p.is_active and p.get_effective_expiration()
            and p.get_effective_expiration() > today
        ]

    def calculate_ip_runway(self) -> int:
        """Calculate days until all IP protection expires."""
        today = date.today()
        latest_date = today

        # Check patents
        for patent in self.get_active_patents():
            exp = patent.get_effective_expiration()
            if exp and exp > latest_date:
                latest_date = exp

        # Check exclusivities
        for excl in self.get_active_exclusivities():
            if excl.end_date and excl.end_date > latest_date:
                latest_date = excl.end_date

        return (latest_date - today).days

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "drug_id": self.drug_id,
            "drug_name": self.drug_name,
            "current_stage": self.current_stage,
            "is_approved": self.is_approved,
            "is_marketed": self.is_marketed,
            "is_discontinued": self.is_discontinued,
            "milestones": [m.to_dict() for m in self.milestones],
            "designations": [d.to_dict() for d in self.designations],
            "exclusivities": [e.to_dict() for e in self.exclusivities],
            "patents": [p.to_dict() for p in self.patents],
            "first_approval_date": self.first_approval_date.isoformat() if self.first_approval_date else None,
            "first_marketed_date": self.first_marketed_date.isoformat() if self.first_marketed_date else None,
            "patent_expiry_date": self.patent_expiry_date.isoformat() if self.patent_expiry_date else None,
            "exclusivity_expiry_date": self.exclusivity_expiry_date.isoformat() if self.exclusivity_expiry_date else None,
            "estimated_time_to_approval": self.estimated_time_to_approval,
            "estimated_time_to_market": self.estimated_time_to_market,
            "ip_runway_days": self.calculate_ip_runway(),
            "last_updated": self.last_updated.isoformat(),
            "data_sources": self.data_sources,
        }


@dataclass
class DataSourceStatus:
    """
    Status of a single data source for a drug.

    Tracks whether data was retrieved, last fetch time, and quality.
    """

    source_name: str  # e.g., "drugbank", "clinicaltrials", "openfda"
    category: DataSourceCategory

    # Availability
    is_available: bool = False
    fetch_attempted: bool = False
    last_fetch: Optional[datetime] = None
    next_refresh: Optional[datetime] = None

    # Quality
    completeness: float = 0.0  # 0-1 score for data completeness
    record_count: int = 0
    has_critical_fields: bool = False

    # Errors
    last_error: Optional[str] = None
    error_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_name": self.source_name,
            "category": self.category.value,
            "is_available": self.is_available,
            "fetch_attempted": self.fetch_attempted,
            "last_fetch": self.last_fetch.isoformat() if self.last_fetch else None,
            "next_refresh": self.next_refresh.isoformat() if self.next_refresh else None,
            "completeness": self.completeness,
            "record_count": self.record_count,
            "has_critical_fields": self.has_critical_fields,
            "last_error": self.last_error,
            "error_count": self.error_count,
        }


@dataclass
class DataCoverage:
    """
    Complete data coverage assessment for a drug.

    Tracks which data sources have been queried, what data
    is available, and overall data sufficiency score.
    """

    drug_id: str
    drug_name: str

    # Source status
    sources: Dict[str, DataSourceStatus] = field(default_factory=dict)

    # Category scores (from scoring_config.yaml)
    category_scores: Dict[DataSourceCategory, float] = field(default_factory=dict)

    # Overall score
    overall_score: float = 0.0
    overall_status: str = "insufficient"  # insufficient, poor, adequate, good, excellent

    # Missing data
    missing_critical: List[str] = field(default_factory=list)
    missing_optional: List[str] = field(default_factory=list)

    # Recommendations
    recommendations: List[str] = field(default_factory=list)

    # Timestamps
    assessed_at: datetime = field(default_factory=datetime.utcnow)

    def add_source_status(self, status: DataSourceStatus) -> None:
        """Add or update a source status."""
        self.sources[status.source_name] = status
        self._recalculate_scores()

    def _recalculate_scores(self) -> None:
        """Recalculate category and overall scores."""
        # Group sources by category
        category_completeness: Dict[DataSourceCategory, List[float]] = {}
        for source in self.sources.values():
            if source.category not in category_completeness:
                category_completeness[source.category] = []
            if source.is_available:
                category_completeness[source.category].append(source.completeness)

        # Calculate category scores (average of available sources)
        for category, scores in category_completeness.items():
            if scores:
                self.category_scores[category] = sum(scores) / len(scores)
            else:
                self.category_scores[category] = 0.0

        # Calculate overall score (weighted average based on config weights)
        # Default weights from scoring_config.yaml
        category_weights = {
            DataSourceCategory.IDENTIFIERS: 0.10,
            DataSourceCategory.STRUCTURE: 0.15,
            DataSourceCategory.CLINICAL_TRIALS: 0.20,
            DataSourceCategory.REGULATORY: 0.15,
            DataSourceCategory.SAFETY: 0.15,
            DataSourceCategory.PRICING: 0.10,
            DataSourceCategory.PATENTS: 0.10,
            DataSourceCategory.PUBLICATIONS: 0.05,
        }

        weighted_sum = 0.0
        for category, score in self.category_scores.items():
            weight = category_weights.get(category, 0.05)
            weighted_sum += score * weight

        self.overall_score = weighted_sum
        self._update_status()

    def _update_status(self) -> None:
        """Update overall status based on score."""
        if self.overall_score >= 0.90:
            self.overall_status = "excellent"
        elif self.overall_score >= 0.75:
            self.overall_status = "good"
        elif self.overall_score >= 0.50:
            self.overall_status = "adequate"
        elif self.overall_score >= 0.25:
            self.overall_status = "poor"
        else:
            self.overall_status = "insufficient"

    def get_available_sources(self) -> List[str]:
        """Get list of sources with data available."""
        return [name for name, status in self.sources.items() if status.is_available]

    def get_missing_sources(self) -> List[str]:
        """Get list of sources without data."""
        return [name for name, status in self.sources.items() if not status.is_available]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "drug_id": self.drug_id,
            "drug_name": self.drug_name,
            "sources": {k: v.to_dict() for k, v in self.sources.items()},
            "category_scores": {k.value: v for k, v in self.category_scores.items()},
            "overall_score": self.overall_score,
            "overall_status": self.overall_status,
            "missing_critical": self.missing_critical,
            "missing_optional": self.missing_optional,
            "recommendations": self.recommendations,
            "available_sources": self.get_available_sources(),
            "missing_sources": self.get_missing_sources(),
            "assessed_at": self.assessed_at.isoformat(),
        }


@dataclass
class TimelineEvent:
    """
    A single event in a drug's development timeline.

    Used for visualization and competitive timing analysis.
    """

    event_type: str  # e.g., "phase_start", "approval", "patent_expiry"
    event_date: date
    description: str

    # Categorization
    category: str = "development"  # development, regulatory, commercial, ip
    is_estimated: bool = False
    confidence: float = 1.0

    # Visual properties
    color: Optional[str] = None
    icon: Optional[str] = None

    # Source
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type,
            "event_date": self.event_date.isoformat(),
            "description": self.description,
            "category": self.category,
            "is_estimated": self.is_estimated,
            "confidence": self.confidence,
            "color": self.color,
            "icon": self.icon,
            "source": self.source,
        }


@dataclass
class CompetitiveTimeline:
    """
    Timeline comparison for competitive analysis.

    Shows key events for multiple drugs on a shared timeline
    for competitive positioning analysis.
    """

    core_drug_id: str
    competitor_ids: List[str] = field(default_factory=list)

    # Events by drug
    events: Dict[str, List[TimelineEvent]] = field(default_factory=dict)

    # Time range
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    # Analysis results
    key_milestones: List[Dict[str, Any]] = field(default_factory=list)
    competitive_windows: List[Dict[str, Any]] = field(default_factory=list)

    def add_event(self, drug_id: str, event: TimelineEvent) -> None:
        """Add an event for a drug."""
        if drug_id not in self.events:
            self.events[drug_id] = []
        self.events[drug_id].append(event)
        self._update_date_range(event.event_date)

    def _update_date_range(self, event_date: date) -> None:
        """Update timeline date range."""
        if self.start_date is None or event_date < self.start_date:
            self.start_date = event_date
        if self.end_date is None or event_date > self.end_date:
            self.end_date = event_date

    def to_visualization_format(self) -> Dict[str, Any]:
        """Convert to format suitable for timeline visualization."""
        timeline_data = {
            "core_drug_id": self.core_drug_id,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "drugs": {},
            "key_milestones": self.key_milestones,
            "competitive_windows": self.competitive_windows,
        }

        for drug_id, events in self.events.items():
            timeline_data["drugs"][drug_id] = {
                "events": [e.to_dict() for e in sorted(events, key=lambda x: x.event_date)],
                "is_core": drug_id == self.core_drug_id,
            }

        return timeline_data

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.to_visualization_format()
