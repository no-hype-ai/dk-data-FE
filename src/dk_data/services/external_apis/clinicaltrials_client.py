"""
ClinicalTrials.gov API Client.

Provides access to clinical trial data via the new CTGOV v2 API:
- Trial search by drug, indication, sponsor
- Trial details and status
- Development phase extraction
- Competitor identification

API Documentation: https://clinicaltrials.gov/data-api/api
Rate Limit: 100 requests/minute (1.67/sec)
"""

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager, DataSource


class TrialPhase(str, Enum):
    """Clinical trial phases."""

    EARLY_PHASE_1 = "EARLY_PHASE1"
    PHASE_1 = "PHASE1"
    PHASE_1_2 = "PHASE1/PHASE2"
    PHASE_2 = "PHASE2"
    PHASE_2_3 = "PHASE2/PHASE3"
    PHASE_3 = "PHASE3"
    PHASE_4 = "PHASE4"
    NA = "NA"


class TrialStatus(str, Enum):
    """Clinical trial overall status."""

    NOT_YET_RECRUITING = "NOT_YET_RECRUITING"
    RECRUITING = "RECRUITING"
    ENROLLING_BY_INVITATION = "ENROLLING_BY_INVITATION"
    ACTIVE_NOT_RECRUITING = "ACTIVE_NOT_RECRUITING"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"
    COMPLETED = "COMPLETED"
    WITHDRAWN = "WITHDRAWN"
    UNKNOWN = "UNKNOWN"


class StudyType(str, Enum):
    """Clinical study type."""

    INTERVENTIONAL = "INTERVENTIONAL"
    OBSERVATIONAL = "OBSERVATIONAL"
    EXPANDED_ACCESS = "EXPANDED_ACCESS"


@dataclass
class Sponsor:
    """Trial sponsor information."""

    name: str
    class_type: Optional[str] = None  # INDUSTRY, NIH, OTHER, etc.
    lead_or_collaborator: str = "LEAD"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "class_type": self.class_type,
            "lead_or_collaborator": self.lead_or_collaborator,
        }


@dataclass
class Intervention:
    """Trial intervention (drug, device, procedure, etc.)."""

    name: str
    intervention_type: str  # DRUG, BIOLOGICAL, DEVICE, PROCEDURE, etc.
    description: Optional[str] = None
    arm_group_labels: List[str] = field(default_factory=list)
    other_names: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "intervention_type": self.intervention_type,
            "description": self.description,
            "arm_group_labels": self.arm_group_labels,
            "other_names": self.other_names,
        }


@dataclass
class Condition:
    """Trial condition/indication."""

    name: str
    mesh_terms: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "mesh_terms": self.mesh_terms,
        }


@dataclass
class OutcomeMeasure:
    """Outcome measure from trial protocol or results."""

    measure: str  # Name/description of the outcome measure
    description: Optional[str] = None
    time_frame: Optional[str] = None  # e.g., "Week 16", "52 weeks"
    outcome_type: str = "PRIMARY"  # PRIMARY, SECONDARY, OTHER

    def to_dict(self) -> Dict[str, Any]:
        return {
            "measure": self.measure,
            "description": self.description,
            "time_frame": self.time_frame,
            "outcome_type": self.outcome_type,
        }


@dataclass
class OutcomeResult:
    """
    Actual results for an outcome measure from completed trials.
    Contains efficacy numbers like response rates, scores, etc.
    """

    measure_title: str  # Name of the outcome measure
    measure_type: str  # PRIMARY, SECONDARY, OTHER
    time_frame: Optional[str] = None
    population: Optional[str] = None  # Analysis population description

    # Statistical results
    param_type: Optional[str] = None  # "Mean", "Number", "Median", etc.
    param_value: Optional[str] = None  # The actual value
    dispersion_type: Optional[str] = None  # "Standard Deviation", "95% CI", etc.
    dispersion_value: Optional[str] = None

    # Group-specific results (arm comparisons)
    group_results: List[Dict[str, Any]] = field(default_factory=list)
    # e.g., [{"group": "Dupixent", "value": "36%"}, {"group": "Placebo", "value": "8%"}]

    # Statistical analysis
    p_value: Optional[str] = None
    statistical_method: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "measure_title": self.measure_title,
            "measure_type": self.measure_type,
            "time_frame": self.time_frame,
            "population": self.population,
            "param_type": self.param_type,
            "param_value": self.param_value,
            "dispersion_type": self.dispersion_type,
            "dispersion_value": self.dispersion_value,
            "group_results": self.group_results,
            "p_value": self.p_value,
            "statistical_method": self.statistical_method,
        }


@dataclass
class ClinicalTrial:
    """A clinical trial from ClinicalTrials.gov."""

    # Identifiers
    nct_id: str
    org_study_id: Optional[str] = None
    secondary_ids: List[str] = field(default_factory=list)

    # Basic info
    brief_title: str = ""
    official_title: Optional[str] = None
    acronym: Optional[str] = None

    # Status
    overall_status: TrialStatus = TrialStatus.UNKNOWN
    phase: TrialPhase = TrialPhase.NA
    study_type: StudyType = StudyType.INTERVENTIONAL

    # Dates
    start_date: Optional[date] = None
    completion_date: Optional[date] = None
    primary_completion_date: Optional[date] = None
    first_posted_date: Optional[date] = None
    last_update_date: Optional[date] = None

    # Sponsors
    lead_sponsor: Optional[Sponsor] = None
    collaborators: List[Sponsor] = field(default_factory=list)

    # Interventions
    interventions: List[Intervention] = field(default_factory=list)

    # Conditions
    conditions: List[str] = field(default_factory=list)
    condition_meshes: List[str] = field(default_factory=list)

    # Keywords
    keywords: List[str] = field(default_factory=list)

    # Enrollment
    enrollment: Optional[int] = None
    enrollment_type: Optional[str] = None  # ACTUAL, ESTIMATED

    # Location
    location_countries: List[str] = field(default_factory=list)

    # Design
    design_allocation: Optional[str] = None
    design_masking: Optional[str] = None
    design_primary_purpose: Optional[str] = None

    # Protocol-defined outcome measures (what they planned to measure)
    primary_outcomes: List[OutcomeMeasure] = field(default_factory=list)
    secondary_outcomes: List[OutcomeMeasure] = field(default_factory=list)
    other_outcomes: List[OutcomeMeasure] = field(default_factory=list)

    # Actual results (efficacy data from completed trials)
    has_results: bool = False
    results_first_posted: Optional[date] = None
    outcome_results: List[OutcomeResult] = field(default_factory=list)  # Actual efficacy numbers!

    # Adverse events summary from results
    serious_adverse_events_count: Optional[int] = None
    other_adverse_events_count: Optional[int] = None

    def get_drug_interventions(self) -> List[Intervention]:
        """Get only drug/biological interventions."""
        return [i for i in self.interventions if i.intervention_type in ["DRUG", "BIOLOGICAL"]]

    def is_industry_sponsored(self) -> bool:
        """Check if trial is industry-sponsored."""
        if self.lead_sponsor:
            return self.lead_sponsor.class_type == "INDUSTRY"
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nct_id": self.nct_id,
            "org_study_id": self.org_study_id,
            "secondary_ids": self.secondary_ids,
            "brief_title": self.brief_title,
            "official_title": self.official_title,
            "acronym": self.acronym,
            "overall_status": self.overall_status.value,
            "phase": self.phase.value,
            "study_type": self.study_type.value,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "completion_date": self.completion_date.isoformat() if self.completion_date else None,
            "primary_completion_date": self.primary_completion_date.isoformat() if self.primary_completion_date else None,
            "first_posted_date": self.first_posted_date.isoformat() if self.first_posted_date else None,
            "last_update_date": self.last_update_date.isoformat() if self.last_update_date else None,
            "lead_sponsor": self.lead_sponsor.to_dict() if self.lead_sponsor else None,
            "collaborators": [c.to_dict() for c in self.collaborators],
            "interventions": [i.to_dict() for i in self.interventions],
            "conditions": self.conditions,
            "condition_meshes": self.condition_meshes,
            "keywords": self.keywords,
            "enrollment": self.enrollment,
            "enrollment_type": self.enrollment_type,
            "location_countries": self.location_countries,
            "design_allocation": self.design_allocation,
            "design_masking": self.design_masking,
            "design_primary_purpose": self.design_primary_purpose,
            "primary_outcomes": [o.to_dict() for o in self.primary_outcomes],
            "secondary_outcomes": [o.to_dict() for o in self.secondary_outcomes],
            "other_outcomes": [o.to_dict() for o in self.other_outcomes],
            "has_results": self.has_results,
            "results_first_posted": self.results_first_posted.isoformat() if self.results_first_posted else None,
            "outcome_results": [r.to_dict() for r in self.outcome_results],
            "serious_adverse_events_count": self.serious_adverse_events_count,
            "other_adverse_events_count": self.other_adverse_events_count,
            "is_industry_sponsored": self.is_industry_sponsored(),
        }


@dataclass
class TrialSearchResult:
    """Result from trial search."""

    total_count: int
    trials: List[ClinicalTrial]
    next_page_token: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_count": self.total_count,
            "trials": [t.to_dict() for t in self.trials],
            "next_page_token": self.next_page_token,
        }


class ClinicalTrialsClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for ClinicalTrials.gov API (v2).

    No API key required - public access.

    Usage:
        client = ClinicalTrialsClient()
        trials = await client.search_by_drug("pembrolizumab")
        trial = await client.get_trial("NCT02478099")
    """

    # Default fields to return
    DEFAULT_FIELDS = [
        "NCTId",
        "OrgStudyId",
        "SecondaryId",
        "BriefTitle",
        "OfficialTitle",
        "Acronym",
        "OverallStatus",
        "Phase",
        "StudyType",
        "StartDate",
        "CompletionDate",
        "PrimaryCompletionDate",
        "StudyFirstPostDate",
        "LastUpdatePostDate",
        "LeadSponsorName",
        "LeadSponsorClass",
        "CollaboratorName",
        "CollaboratorClass",
        "InterventionName",
        "InterventionType",
        "InterventionDescription",
        "InterventionOtherName",
        "Condition",
        "ConditionMeshTerm",
        "Keyword",
        "EnrollmentCount",
        "EnrollmentType",
        "LocationCountry",
        "DesignAllocation",
        "DesignMasking",
        "DesignPrimaryPurpose",
        "ResultsFirstPostDate",
        # Protocol-defined outcome measures
        "PrimaryOutcomeMeasure",
        "PrimaryOutcomeDescription",
        "PrimaryOutcomeTimeFrame",
        "SecondaryOutcomeMeasure",
        "SecondaryOutcomeDescription",
        "SecondaryOutcomeTimeFrame",
        "OtherOutcomeMeasure",
        "OtherOutcomeDescription",
        "OtherOutcomeTimeFrame",
    ]

    # Extended fields to request when fetching full trial details with results
    RESULTS_FIELDS = [
        # All default fields plus results section
        *DEFAULT_FIELDS,
        # Outcome results
        "OutcomeMeasureTitle",
        "OutcomeMeasureType",
        "OutcomeMeasureTimeFrame",
        "OutcomeMeasurePopulationDescription",
        "OutcomeMeasureParamType",
        "OutcomeMeasureDispersionType",
        "OutcomeGroupTitle",
        "OutcomeGroupDescription",
        "OutcomeMeasurementValue",
        "OutcomeAnalysisStatisticalMethod",
        "OutcomeAnalysisPValue",
        # Adverse events
        "EventsFrequencyThreshold",
        "EventsTimeFrame",
        "EventsDescription",
        "SeriousEventTerm",
        "OtherEventTerm",
    ]

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url="https://clinicaltrials.gov/api/v2",
            timeout=60.0,  # CTG can be slow
            max_retries=3,
            requests_per_second=1.67,  # 100/minute
            cache_ttl=86400,  # 24 hours (updates daily)
        )
        super().__init__(config, cache_manager)

    async def health_check(self) -> bool:
        """Check if ClinicalTrials.gov API is accessible."""
        try:
            result = await self._get(
                "/studies",
                params={"query.term": "aspirin", "pageSize": 1},
                use_cache=False
            )
            return "studies" in result
        except Exception as e:
            logger.error(f"ClinicalTrials.gov health check failed: {e}")
            return False

    async def search_studies(
        self,
        query: Optional[str] = None,
        condition: Optional[str] = None,
        intervention: Optional[str] = None,
        sponsor: Optional[str] = None,
        phase: Optional[List[str]] = None,
        status: Optional[List[str]] = None,
        study_type: Optional[str] = None,
        page_size: int = 20,
        page_token: Optional[str] = None,
    ) -> TrialSearchResult:
        """
        Search for clinical trials.

        Args:
            query: Free-text search
            condition: Condition/disease
            intervention: Drug/intervention name
            sponsor: Sponsor name
            phase: List of phases to filter
            status: List of statuses to filter
            study_type: Study type filter
            page_size: Results per page (max 1000)
            page_token: Token for pagination

        Returns:
            TrialSearchResult with trials and pagination info
        """
        params = {
            "pageSize": min(page_size, 1000),
            "fields": ",".join(self.DEFAULT_FIELDS),
        }

        # Build query parts
        query_parts = []
        if query:
            query_parts.append(query)

        if condition:
            params["query.cond"] = condition

        if intervention:
            params["query.intr"] = intervention

        if sponsor:
            params["query.spons"] = sponsor

        if query_parts:
            params["query.term"] = " ".join(query_parts)

        # Build filter.advanced for phase, status, and study_type
        # ClinicalTrials.gov v2 API uses filter.advanced with AREA[] syntax
        filter_parts = []

        if phase:
            phase_conditions = " OR ".join(phase)
            filter_parts.append(f"AREA[Phase]({phase_conditions})")

        if status:
            status_conditions = " OR ".join(status)
            filter_parts.append(f"AREA[OverallStatus]({status_conditions})")

        if study_type:
            filter_parts.append(f"AREA[StudyType]{study_type}")

        if filter_parts:
            params["filter.advanced"] = " AND ".join(filter_parts)

        if page_token:
            params["pageToken"] = page_token

        try:
            result = await self._get("/studies", params=params)

            trials = []
            for study in result.get("studies", []):
                trial = self._parse_study(study)
                if trial:
                    trials.append(trial)

            return TrialSearchResult(
                total_count=result.get("totalCount", len(trials)),
                trials=trials,
                next_page_token=result.get("nextPageToken"),
            )
        except Exception as e:
            logger.error(f"Error searching trials: {e}")
            return TrialSearchResult(total_count=0, trials=[])

    async def get_trial(self, nct_id: str, include_results: bool = False) -> Optional[ClinicalTrial]:
        """
        Get a specific trial by NCT ID.

        Args:
            nct_id: NCT identifier (e.g., "NCT02478099")
            include_results: If True, fetch full results section with efficacy data

        Returns:
            ClinicalTrial or None
        """
        try:
            # Use RESULTS_FIELDS if we want full efficacy data
            fields = self.RESULTS_FIELDS if include_results else self.DEFAULT_FIELDS
            result = await self._get(
                f"/studies/{nct_id}",
                params={"fields": ",".join(fields)}
            )

            return self._parse_study(result)
        except Exception as e:
            logger.error(f"Error getting trial {nct_id}: {e}")
            return None

    async def get_trial_with_results(self, nct_id: str) -> Optional[ClinicalTrial]:
        """
        Get a specific trial with full results/efficacy data.

        This fetches the complete resultsSection including:
        - Outcome measure results (efficacy numbers)
        - Statistical analyses (p-values)
        - Adverse events summary

        Args:
            nct_id: NCT identifier (e.g., "NCT02478099")

        Returns:
            ClinicalTrial with populated outcome_results field, or None
        """
        return await self.get_trial(nct_id, include_results=True)

    async def search_completed_trials_with_results(
        self,
        drug_name: str,
        page_size: int = 50
    ) -> List[ClinicalTrial]:
        """
        Search for completed trials with results for a drug.

        This returns trials that have posted results, which contain
        actual efficacy data (response rates, scores, etc.).

        Args:
            drug_name: Drug name to search
            page_size: Results per page

        Returns:
            List of clinical trials with results
        """
        result = await self.search_studies(
            intervention=drug_name,
            status=["COMPLETED"],
            page_size=page_size,
        )

        # Filter to only trials with results and fetch full data
        trials_with_results = []
        for trial in result.trials:
            if trial.has_results:
                # Fetch the full trial with results section
                full_trial = await self.get_trial_with_results(trial.nct_id)
                if full_trial:
                    trials_with_results.append(full_trial)

        return trials_with_results

    async def search_by_drug(
        self,
        drug_name: str,
        phases: Optional[List[str]] = None,
        active_only: bool = True,
        page_size: int = 100
    ) -> List[ClinicalTrial]:
        """
        Search trials by drug/intervention name.

        Args:
            drug_name: Drug name to search
            phases: Filter by phases
            active_only: Only include active trials
            page_size: Results per page

        Returns:
            List of clinical trials
        """
        status = None
        if active_only:
            status = [
                "NOT_YET_RECRUITING",
                "RECRUITING",
                "ENROLLING_BY_INVITATION",
                "ACTIVE_NOT_RECRUITING",
            ]

        result = await self.search_studies(
            intervention=drug_name,
            phase=phases,
            status=status,
            page_size=page_size,
        )

        return result.trials

    async def search_by_condition(
        self,
        condition: str,
        phases: Optional[List[str]] = None,
        intervention_type: str = "DRUG",
        page_size: int = 100
    ) -> List[ClinicalTrial]:
        """
        Search trials by condition/indication.

        Args:
            condition: Condition name or MeSH term
            phases: Filter by phases
            intervention_type: Filter by intervention type
            page_size: Results per page

        Returns:
            List of clinical trials
        """
        result = await self.search_studies(
            condition=condition,
            phase=phases,
            study_type="INTERVENTIONAL",
            page_size=page_size,
        )

        # Filter by intervention type
        if intervention_type:
            return [
                t for t in result.trials
                if any(i.intervention_type == intervention_type for i in t.interventions)
            ]

        return result.trials

    async def search_by_sponsor(
        self,
        sponsor_name: str,
        active_only: bool = True,
        page_size: int = 100
    ) -> List[ClinicalTrial]:
        """
        Search trials by sponsor name.

        Args:
            sponsor_name: Sponsor/company name
            active_only: Only include active trials
            page_size: Results per page

        Returns:
            List of clinical trials
        """
        status = None
        if active_only:
            status = [
                "NOT_YET_RECRUITING",
                "RECRUITING",
                "ENROLLING_BY_INVITATION",
                "ACTIVE_NOT_RECRUITING",
            ]

        result = await self.search_studies(
            sponsor=sponsor_name,
            status=status,
            page_size=page_size,
        )

        return result.trials

    async def get_competitors_for_indication(
        self,
        indication: str,
        exclude_drugs: Optional[List[str]] = None,
        phases: Optional[List[str]] = None
    ) -> Dict[str, List[ClinicalTrial]]:
        """
        Find competing drugs in trials for an indication.

        Args:
            indication: Condition/indication
            exclude_drugs: Drugs to exclude from results
            phases: Filter by phases

        Returns:
            Dictionary of drug name -> trials
        """
        trials = await self.search_by_condition(
            indication,
            phases=phases,
            intervention_type="DRUG",
            page_size=500,
        )

        exclude_set = set(d.lower() for d in (exclude_drugs or []))

        # Group by drug name
        competitors: Dict[str, List[ClinicalTrial]] = {}
        for trial in trials:
            for intervention in trial.get_drug_interventions():
                name = intervention.name.lower()
                if name not in exclude_set:
                    if name not in competitors:
                        competitors[name] = []
                    competitors[name].append(trial)

        return competitors

    async def get_pipeline_for_sponsor(
        self,
        sponsor_name: str
    ) -> Dict[str, List[ClinicalTrial]]:
        """
        Get development pipeline for a sponsor by phase.

        Args:
            sponsor_name: Sponsor/company name

        Returns:
            Dictionary of phase -> trials
        """
        trials = await self.search_by_sponsor(sponsor_name, active_only=True)

        # Group by phase
        pipeline: Dict[str, List[ClinicalTrial]] = {}
        for trial in trials:
            phase = trial.phase.value
            if phase not in pipeline:
                pipeline[phase] = []
            pipeline[phase].append(trial)

        return pipeline

    def _parse_study(self, data: Dict[str, Any]) -> Optional[ClinicalTrial]:
        """Parse a study response into a ClinicalTrial object."""
        try:
            # Get protocol section
            protocol = data.get("protocolSection", {})
            id_module = protocol.get("identificationModule", {})
            status_module = protocol.get("statusModule", {})
            sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
            design_module = protocol.get("designModule", {})
            arms_module = protocol.get("armsInterventionsModule", {})
            conditions_module = protocol.get("conditionsModule", {})
            results_section = data.get("resultsSection")

            # Parse dates
            def parse_date(date_struct: Optional[Dict]) -> Optional[date]:
                if not date_struct:
                    return None
                date_str = date_struct.get("date")
                if not date_str:
                    return None
                try:
                    # Try full date first (YYYY-MM-DD)
                    return datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        # Try month-year (YYYY-MM)
                        return datetime.strptime(date_str, "%Y-%m").date()
                    except ValueError:
                        return None

            # Parse lead sponsor
            lead_sponsor = None
            sponsor_info = sponsor_module.get("leadSponsor", {})
            if sponsor_info:
                lead_sponsor = Sponsor(
                    name=sponsor_info.get("name", ""),
                    class_type=sponsor_info.get("class"),
                    lead_or_collaborator="LEAD",
                )

            # Parse collaborators
            collaborators = []
            for collab in sponsor_module.get("collaborators", []):
                collaborators.append(Sponsor(
                    name=collab.get("name", ""),
                    class_type=collab.get("class"),
                    lead_or_collaborator="COLLABORATOR",
                ))

            # Parse interventions
            interventions = []
            for intervention in arms_module.get("interventions", []):
                interventions.append(Intervention(
                    name=intervention.get("name", ""),
                    intervention_type=intervention.get("type", ""),
                    description=intervention.get("description"),
                    arm_group_labels=intervention.get("armGroupLabels", []),
                    other_names=intervention.get("otherNames", []),
                ))

            # Parse phase
            phase_str = design_module.get("phases", ["NA"])[0] if design_module.get("phases") else "NA"
            try:
                phase = TrialPhase(phase_str)
            except ValueError:
                phase = TrialPhase.NA

            # Parse status
            status_str = status_module.get("overallStatus", "UNKNOWN")
            try:
                status = TrialStatus(status_str)
            except ValueError:
                status = TrialStatus.UNKNOWN

            # Parse study type
            study_type_str = design_module.get("studyType", "INTERVENTIONAL")
            try:
                study_type = StudyType(study_type_str)
            except ValueError:
                study_type = StudyType.INTERVENTIONAL

            # Parse protocol-defined outcome measures
            outcomes_module = protocol.get("outcomesModule", {})

            primary_outcomes = []
            for outcome in outcomes_module.get("primaryOutcomes", []):
                primary_outcomes.append(OutcomeMeasure(
                    measure=outcome.get("measure", ""),
                    description=outcome.get("description"),
                    time_frame=outcome.get("timeFrame"),
                    outcome_type="PRIMARY",
                ))

            secondary_outcomes = []
            for outcome in outcomes_module.get("secondaryOutcomes", []):
                secondary_outcomes.append(OutcomeMeasure(
                    measure=outcome.get("measure", ""),
                    description=outcome.get("description"),
                    time_frame=outcome.get("timeFrame"),
                    outcome_type="SECONDARY",
                ))

            other_outcomes = []
            for outcome in outcomes_module.get("otherOutcomes", []):
                other_outcomes.append(OutcomeMeasure(
                    measure=outcome.get("measure", ""),
                    description=outcome.get("description"),
                    time_frame=outcome.get("timeFrame"),
                    outcome_type="OTHER",
                ))

            # Parse results section (actual efficacy data from completed trials)
            outcome_results = []
            results_first_posted = None
            serious_ae_count = None
            other_ae_count = None

            if results_section:
                # Results first posted date
                results_first_posted = parse_date(
                    status_module.get("resultsFirstPostDateStruct")
                )

                # Parse outcome measures from results
                outcomes_results_module = results_section.get("outcomeMeasuresModule", {})
                for measure in outcomes_results_module.get("outcomeMeasures", []):
                    # Extract group results
                    group_results = []
                    for group in measure.get("groups", []):
                        group_results.append({
                            "group_id": group.get("id"),
                            "title": group.get("title"),
                            "description": group.get("description"),
                        })

                    # Extract measurement values from classes/categories
                    for measure_class in measure.get("classes", []):
                        for category in measure_class.get("categories", []):
                            for measurement in category.get("measurements", []):
                                group_id = measurement.get("groupId")
                                value = measurement.get("value")
                                # Find the group title
                                group_title = next(
                                    (g["title"] for g in group_results if g["group_id"] == group_id),
                                    group_id
                                )
                                if group_title and value:
                                    # Update group_results with actual values
                                    for gr in group_results:
                                        if gr["group_id"] == group_id:
                                            gr["value"] = value
                                            gr["spread"] = measurement.get("spread")

                    # Parse statistical analyses
                    p_value = None
                    stat_method = None
                    for analysis in measure.get("analyses", []):
                        if analysis.get("pValue"):
                            p_value = analysis.get("pValue")
                        if analysis.get("statisticalMethod"):
                            stat_method = analysis.get("statisticalMethod")

                    outcome_results.append(OutcomeResult(
                        measure_title=measure.get("title", ""),
                        measure_type=measure.get("type", "PRIMARY"),
                        time_frame=measure.get("timeFrame"),
                        population=measure.get("populationDescription"),
                        param_type=measure.get("paramType"),
                        dispersion_type=measure.get("dispersionType"),
                        group_results=[
                            {"group": gr.get("title"), "value": gr.get("value"), "spread": gr.get("spread")}
                            for gr in group_results if gr.get("value")
                        ],
                        p_value=p_value,
                        statistical_method=stat_method,
                    ))

                # Parse adverse events summary
                adverse_events_module = results_section.get("adverseEventsModule", {})
                if adverse_events_module:
                    # Count serious adverse events
                    serious_events = adverse_events_module.get("seriousEvents", [])
                    if serious_events:
                        serious_ae_count = sum(
                            int(stat.get("numAffected", 0))
                            for event in serious_events
                            for stat in event.get("stats", [])
                        )

                    # Count other adverse events
                    other_events = adverse_events_module.get("otherEvents", [])
                    if other_events:
                        other_ae_count = sum(
                            int(stat.get("numAffected", 0))
                            for event in other_events
                            for stat in event.get("stats", [])
                        )

            return ClinicalTrial(
                nct_id=id_module.get("nctId", ""),
                org_study_id=id_module.get("orgStudyIdInfo", {}).get("id"),
                secondary_ids=[s.get("id", "") for s in id_module.get("secondaryIdInfos", [])],
                brief_title=id_module.get("briefTitle", ""),
                official_title=id_module.get("officialTitle"),
                acronym=id_module.get("acronym"),
                overall_status=status,
                phase=phase,
                study_type=study_type,
                start_date=parse_date(status_module.get("startDateStruct")),
                completion_date=parse_date(status_module.get("completionDateStruct")),
                primary_completion_date=parse_date(status_module.get("primaryCompletionDateStruct")),
                first_posted_date=parse_date(status_module.get("studyFirstPostDateStruct")),
                last_update_date=parse_date(status_module.get("lastUpdatePostDateStruct")),
                lead_sponsor=lead_sponsor,
                collaborators=collaborators,
                interventions=interventions,
                conditions=conditions_module.get("conditions", []),
                condition_meshes=[m.get("term", "") for m in conditions_module.get("meshes", [])],
                keywords=conditions_module.get("keywords", []),
                enrollment=design_module.get("enrollmentInfo", {}).get("count"),
                enrollment_type=design_module.get("enrollmentInfo", {}).get("type"),
                location_countries=list(set(
                    loc.get("country", "")
                    for loc in protocol.get("contactsLocationsModule", {}).get("locations", [])
                )),
                design_allocation=design_module.get("designInfo", {}).get("allocation"),
                design_masking=design_module.get("designInfo", {}).get("maskingInfo", {}).get("masking"),
                design_primary_purpose=design_module.get("designInfo", {}).get("primaryPurpose"),
                primary_outcomes=primary_outcomes,
                secondary_outcomes=secondary_outcomes,
                other_outcomes=other_outcomes,
                has_results=results_section is not None,
                results_first_posted=results_first_posted,
                outcome_results=outcome_results,
                serious_adverse_events_count=serious_ae_count,
                other_adverse_events_count=other_ae_count,
            )
        except Exception as e:
            logger.error(f"Error parsing study: {e}")
            return None


# Singleton instance
_clinicaltrials_client: Optional[ClinicalTrialsClient] = None


async def get_clinicaltrials_client(cache_manager: Optional[CacheManager] = None) -> ClinicalTrialsClient:
    """Get or create the ClinicalTrials.gov client instance."""
    global _clinicaltrials_client

    if _clinicaltrials_client is None:
        _clinicaltrials_client = ClinicalTrialsClient(cache_manager)

    return _clinicaltrials_client
