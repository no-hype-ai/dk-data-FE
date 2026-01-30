"""
Lifecycle Service for tracking molecule development from discovery through post-market.

Implements:
- T080: LifecycleService class
- T081: Phase date extraction from ClinicalTrials.gov
- T082: FDA approval date extraction
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum
import asyncio
from loguru import logger

from ..external_apis.clinicaltrials_client import ClinicalTrialsClient
from ..external_apis.openfda_client import OpenFDAClient


class LifecyclePhase(str, Enum):
    """Development lifecycle phases."""
    DISCOVERY = "discovery"
    PRECLINICAL = "preclinical"
    IND_FILED = "ind_filed"
    PHASE_1 = "phase_1"
    PHASE_2 = "phase_2"
    PHASE_3 = "phase_3"
    NDA_BLA_FILED = "nda_bla_filed"
    FDA_REVIEW = "fda_review"
    APPROVED = "approved"
    MARKETED = "marketed"
    PATENT_EXPIRED = "patent_expired"
    GENERIC_AVAILABLE = "generic_available"
    DISCONTINUED = "discontinued"


class MilestoneType(str, Enum):
    """Types of regulatory milestones."""
    IND_SUBMISSION = "ind_submission"
    PHASE_START = "phase_start"
    PHASE_COMPLETION = "phase_completion"
    NDA_SUBMISSION = "nda_submission"
    BLA_SUBMISSION = "bla_submission"
    FDA_APPROVAL = "fda_approval"
    EMA_APPROVAL = "ema_approval"
    PATENT_GRANT = "patent_grant"
    PATENT_EXPIRY = "patent_expiry"
    EXCLUSIVITY_START = "exclusivity_start"
    EXCLUSIVITY_END = "exclusivity_end"
    FIRST_GENERIC = "first_generic"
    LABEL_UPDATE = "label_update"
    SAFETY_ALERT = "safety_alert"
    MARKET_WITHDRAWAL = "market_withdrawal"


@dataclass
class LifecycleMilestone:
    """A single milestone in a molecule's lifecycle."""
    milestone_type: MilestoneType
    date: date
    description: str
    source: str
    phase: Optional[LifecyclePhase] = None
    indication: Optional[str] = None
    region: str = "US"
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseTransition:
    """Transition between development phases."""
    from_phase: LifecyclePhase
    to_phase: LifecyclePhase
    transition_date: date
    duration_days: Optional[int] = None
    indication: Optional[str] = None
    trial_id: Optional[str] = None
    source: str = "clinicaltrials.gov"


@dataclass
class LifecycleTimeline:
    """Complete lifecycle timeline for a molecule."""
    molecule_name: str
    molecule_id: str
    current_phase: LifecyclePhase
    milestones: List[LifecycleMilestone]
    phase_transitions: List[PhaseTransition]
    first_in_human_date: Optional[date] = None
    approval_date: Optional[date] = None
    time_to_market_days: Optional[int] = None
    indications: List[str] = field(default_factory=list)
    active_trials_count: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "molecule_name": self.molecule_name,
            "molecule_id": self.molecule_id,
            "current_phase": self.current_phase.value,
            "milestones": [
                {
                    "type": m.milestone_type.value,
                    "date": m.date.isoformat(),
                    "description": m.description,
                    "source": m.source,
                    "phase": m.phase.value if m.phase else None,
                    "indication": m.indication,
                    "region": m.region,
                    "confidence": m.confidence,
                }
                for m in self.milestones
            ],
            "phase_transitions": [
                {
                    "from_phase": t.from_phase.value,
                    "to_phase": t.to_phase.value,
                    "date": t.transition_date.isoformat(),
                    "duration_days": t.duration_days,
                    "indication": t.indication,
                    "trial_id": t.trial_id,
                }
                for t in self.phase_transitions
            ],
            "first_in_human_date": self.first_in_human_date.isoformat() if self.first_in_human_date else None,
            "approval_date": self.approval_date.isoformat() if self.approval_date else None,
            "time_to_market_days": self.time_to_market_days,
            "indications": self.indications,
            "active_trials_count": self.active_trials_count,
            "timestamp": self.timestamp.isoformat(),
        }


class LifecycleService:
    """
    Service for tracking molecule development lifecycle.

    Aggregates data from:
    - ClinicalTrials.gov (trial phases, dates)
    - OpenFDA (approval dates, labels)
    - Orange Book (patents, exclusivity)
    - Purple Book (biosimilars)
    """

    # Phase mapping from ClinicalTrials.gov
    TRIAL_PHASE_MAP = {
        "EARLY_PHASE1": LifecyclePhase.PHASE_1,
        "PHASE1": LifecyclePhase.PHASE_1,
        "PHASE2": LifecyclePhase.PHASE_2,
        "PHASE3": LifecyclePhase.PHASE_3,
        "PHASE4": LifecyclePhase.MARKETED,
        "NA": LifecyclePhase.PRECLINICAL,
    }

    def __init__(
        self,
        clinicaltrials_client: Optional[ClinicalTrialsClient] = None,
        openfda_client: Optional[OpenFDAClient] = None,
    ):
        self._clinicaltrials = clinicaltrials_client or ClinicalTrialsClient()
        self._openfda = openfda_client or OpenFDAClient()

    async def get_lifecycle(
        self,
        molecule_name: str,
        molecule_id: Optional[str] = None,
        include_all_indications: bool = True,
    ) -> LifecycleTimeline:
        """
        Get complete lifecycle timeline for a molecule.

        Args:
            molecule_name: Name of the molecule/drug
            molecule_id: Optional identifier
            include_all_indications: Include milestones for all indications

        Returns:
            LifecycleTimeline with all milestones and transitions
        """
        logger.info(f"Building lifecycle timeline for {molecule_name}")

        # Gather data from multiple sources in parallel
        trials_task = self._get_trial_milestones(molecule_name)
        fda_task = self._get_fda_milestones(molecule_name)

        trials_milestones, fda_milestones = await asyncio.gather(
            trials_task, fda_task, return_exceptions=True
        )

        # Handle exceptions
        if isinstance(trials_milestones, Exception):
            logger.warning(f"Failed to get trial milestones: {trials_milestones}")
            trials_milestones = []
        if isinstance(fda_milestones, Exception):
            logger.warning(f"Failed to get FDA milestones: {fda_milestones}")
            fda_milestones = []

        # Combine and sort milestones
        all_milestones = trials_milestones + fda_milestones
        all_milestones.sort(key=lambda m: m.date)

        # Calculate phase transitions
        transitions = self._calculate_transitions(all_milestones)

        # Determine current phase
        current_phase = self._determine_current_phase(all_milestones, transitions)

        # Extract key dates
        first_in_human = self._find_first_in_human_date(all_milestones)
        approval_date = self._find_approval_date(all_milestones)

        # Calculate time to market
        time_to_market = None
        if first_in_human and approval_date:
            time_to_market = (approval_date - first_in_human).days

        # Extract unique indications
        indications = list(set(
            m.indication for m in all_milestones
            if m.indication
        ))

        # Count active trials
        active_trials = sum(
            1 for m in all_milestones
            if m.milestone_type == MilestoneType.PHASE_START
            and not any(
                t.milestone_type == MilestoneType.PHASE_COMPLETION
                and t.metadata.get("trial_id") == m.metadata.get("trial_id")
                for t in all_milestones
            )
        )

        return LifecycleTimeline(
            molecule_name=molecule_name,
            molecule_id=molecule_id or molecule_name.upper().replace(" ", "_"),
            current_phase=current_phase,
            milestones=all_milestones,
            phase_transitions=transitions,
            first_in_human_date=first_in_human,
            approval_date=approval_date,
            time_to_market_days=time_to_market,
            indications=indications,
            active_trials_count=active_trials,
        )

    async def _get_trial_milestones(self, molecule_name: str) -> List[LifecycleMilestone]:
        """Extract milestones from ClinicalTrials.gov data."""
        milestones = []

        try:
            # Search for trials involving this molecule
            trials = await self._clinicaltrials.search_trials(
                intervention=molecule_name,
                limit=100,
            )

            for trial in trials:
                trial_id = trial.get("nctId", "")
                phase = trial.get("phase", "")
                status = trial.get("status", "")
                conditions = trial.get("conditions", [])

                # Get dates
                start_date = self._parse_date(trial.get("startDate"))
                completion_date = self._parse_date(trial.get("completionDate"))
                self._parse_date(trial.get("firstPostedDate"))

                # Map phase
                lifecycle_phase = self.TRIAL_PHASE_MAP.get(phase)

                # Create milestone for trial start
                if start_date and lifecycle_phase:
                    milestones.append(LifecycleMilestone(
                        milestone_type=MilestoneType.PHASE_START,
                        date=start_date,
                        description=f"{phase} trial started: {trial.get('briefTitle', '')}",
                        source="clinicaltrials.gov",
                        phase=lifecycle_phase,
                        indication=conditions[0] if conditions else None,
                        confidence=0.95,
                        metadata={"trial_id": trial_id, "status": status},
                    ))

                # Create milestone for trial completion
                if completion_date and status in ["COMPLETED", "TERMINATED"]:
                    milestones.append(LifecycleMilestone(
                        milestone_type=MilestoneType.PHASE_COMPLETION,
                        date=completion_date,
                        description=f"{phase} trial {status.lower()}: {trial.get('briefTitle', '')}",
                        source="clinicaltrials.gov",
                        phase=lifecycle_phase,
                        indication=conditions[0] if conditions else None,
                        confidence=0.95,
                        metadata={"trial_id": trial_id, "status": status},
                    ))

        except Exception as e:
            logger.error(f"Error fetching trial milestones: {e}")

        return milestones

    async def _get_fda_milestones(self, molecule_name: str) -> List[LifecycleMilestone]:
        """Extract milestones from FDA data (approvals, labels)."""
        milestones = []

        try:
            # Get drug labels for approval information
            labels = await self._openfda.get_drug_label(molecule_name)

            for label in labels[:10]:  # Limit to first 10 labels
                openfda = label.get("openfda", {})

                # Extract approval date
                application_numbers = openfda.get("application_number", [])
                brand_names = openfda.get("brand_name", [])
                indications = label.get("indications_and_usage", [])

                # Parse effective date as proxy for approval
                effective_date = self._parse_date(label.get("effective_time"))

                if effective_date:
                    indication_text = indications[0][:100] if indications else None

                    milestones.append(LifecycleMilestone(
                        milestone_type=MilestoneType.FDA_APPROVAL,
                        date=effective_date,
                        description=f"FDA label effective for {brand_names[0] if brand_names else molecule_name}",
                        source="openfda",
                        phase=LifecyclePhase.APPROVED,
                        indication=indication_text,
                        region="US",
                        confidence=0.9,
                        metadata={
                            "application_numbers": application_numbers,
                            "brand_names": brand_names,
                        },
                    ))

            # Get approval dates from drugs@FDA
            approvals = await self._openfda.get_drug_approvals(molecule_name)

            for approval in approvals:
                approval_date = self._parse_date(approval.get("approval_date"))
                if approval_date:
                    milestones.append(LifecycleMilestone(
                        milestone_type=MilestoneType.FDA_APPROVAL,
                        date=approval_date,
                        description=f"FDA approval: {approval.get('application_type', 'NDA')}",
                        source="drugs@fda",
                        phase=LifecyclePhase.APPROVED,
                        indication=approval.get("indication"),
                        region="US",
                        confidence=0.95,
                        metadata=approval,
                    ))

        except Exception as e:
            logger.error(f"Error fetching FDA milestones: {e}")

        return milestones

    def _calculate_transitions(
        self, milestones: List[LifecycleMilestone]
    ) -> List[PhaseTransition]:
        """Calculate phase transitions from milestones."""
        transitions = []

        # Group milestones by phase
        phase_dates: Dict[LifecyclePhase, date] = {}

        for milestone in milestones:
            if milestone.phase and milestone.phase not in phase_dates:
                phase_dates[milestone.phase] = milestone.date

        # Create transitions between consecutive phases
        phase_order = [
            LifecyclePhase.PRECLINICAL,
            LifecyclePhase.PHASE_1,
            LifecyclePhase.PHASE_2,
            LifecyclePhase.PHASE_3,
            LifecyclePhase.APPROVED,
            LifecyclePhase.MARKETED,
        ]

        prev_phase = None
        prev_date = None

        for phase in phase_order:
            if phase in phase_dates:
                if prev_phase and prev_date:
                    duration = (phase_dates[phase] - prev_date).days
                    transitions.append(PhaseTransition(
                        from_phase=prev_phase,
                        to_phase=phase,
                        transition_date=phase_dates[phase],
                        duration_days=duration if duration > 0 else None,
                    ))
                prev_phase = phase
                prev_date = phase_dates[phase]

        return transitions

    def _determine_current_phase(
        self,
        milestones: List[LifecycleMilestone],
        transitions: List[PhaseTransition],
    ) -> LifecyclePhase:
        """Determine the current lifecycle phase."""
        if not milestones:
            return LifecyclePhase.DISCOVERY

        # Check for approval
        has_approval = any(
            m.milestone_type == MilestoneType.FDA_APPROVAL
            for m in milestones
        )
        if has_approval:
            return LifecyclePhase.MARKETED

        # Find the latest phase from milestones
        latest_phase = LifecyclePhase.DISCOVERY
        phase_order = {
            LifecyclePhase.DISCOVERY: 0,
            LifecyclePhase.PRECLINICAL: 1,
            LifecyclePhase.PHASE_1: 2,
            LifecyclePhase.PHASE_2: 3,
            LifecyclePhase.PHASE_3: 4,
            LifecyclePhase.APPROVED: 5,
            LifecyclePhase.MARKETED: 6,
        }

        for milestone in milestones:
            if milestone.phase:
                if phase_order.get(milestone.phase, 0) > phase_order.get(latest_phase, 0):
                    latest_phase = milestone.phase

        return latest_phase

    def _find_first_in_human_date(
        self, milestones: List[LifecycleMilestone]
    ) -> Optional[date]:
        """Find the first-in-human trial date."""
        phase1_milestones = [
            m for m in milestones
            if m.phase == LifecyclePhase.PHASE_1
            and m.milestone_type == MilestoneType.PHASE_START
        ]

        if phase1_milestones:
            return min(m.date for m in phase1_milestones)
        return None

    def _find_approval_date(
        self, milestones: List[LifecycleMilestone]
    ) -> Optional[date]:
        """Find the first FDA approval date."""
        approval_milestones = [
            m for m in milestones
            if m.milestone_type == MilestoneType.FDA_APPROVAL
        ]

        if approval_milestones:
            return min(m.date for m in approval_milestones)
        return None

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date string in various formats."""
        if not date_str:
            return None

        formats = [
            "%Y-%m-%d",
            "%Y%m%d",
            "%B %d, %Y",
            "%B %Y",
            "%Y",
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str[:len(date_str)], fmt)
                return parsed.date()
            except (ValueError, TypeError):
                continue

        return None

    async def compare_lifecycles(
        self,
        molecules: List[str],
    ) -> Dict[str, Any]:
        """
        Compare lifecycle timelines for multiple molecules.

        Args:
            molecules: List of molecule names to compare

        Returns:
            Comparison data including phase durations, time-to-market
        """
        # Get lifecycles in parallel
        lifecycle_tasks = [self.get_lifecycle(mol) for mol in molecules]
        lifecycles = await asyncio.gather(*lifecycle_tasks, return_exceptions=True)

        # Build comparison
        comparison = {
            "molecules": [],
            "phase_durations": {},
            "time_to_market": {},
            "current_phases": {},
        }

        for mol, lifecycle in zip(molecules, lifecycles):
            if isinstance(lifecycle, Exception):
                logger.warning(f"Failed to get lifecycle for {mol}: {lifecycle}")
                continue

            comparison["molecules"].append(mol)
            comparison["current_phases"][mol] = lifecycle.current_phase.value
            comparison["time_to_market"][mol] = lifecycle.time_to_market_days

            # Calculate phase durations
            for transition in lifecycle.phase_transitions:
                phase_key = f"{transition.from_phase.value}_to_{transition.to_phase.value}"
                if phase_key not in comparison["phase_durations"]:
                    comparison["phase_durations"][phase_key] = {}
                comparison["phase_durations"][phase_key][mol] = transition.duration_days

        return comparison
