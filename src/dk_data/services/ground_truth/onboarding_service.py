"""
User Onboarding & Data Onboarding Pipeline.

Implements:
- T178: UserOnboardingService class
- T179: onboard_user() with role-based setup
- T180: setup_molecule_tracking()
- T181-T182: DataOnboardingPipeline class with 7-step pipeline
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import asyncio
from loguru import logger


class UserRole(str, Enum):
    """User roles for the platform."""
    ANALYST = "analyst"
    EXECUTIVE = "executive"
    SCIENTIST = "scientist"
    REGULATORY = "regulatory"
    COMMERCIAL = "commercial"
    ADMIN = "admin"


class OnboardingStatus(str, Enum):
    """User onboarding status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"


@dataclass
class UserProfile:
    """User profile for onboarding."""
    user_id: str
    email: str
    name: str
    role: UserRole = UserRole.ANALYST
    organization: Optional[str] = None
    therapeutic_areas: List[str] = field(default_factory=list)
    tracked_molecules: List[str] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    onboarding_status: OnboardingStatus = OnboardingStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    onboarded_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "role": self.role.value,
            "organization": self.organization,
            "therapeutic_areas": self.therapeutic_areas,
            "tracked_molecules_count": len(self.tracked_molecules),
            "onboarding_status": self.onboarding_status.value,
            "created_at": self.created_at.isoformat(),
            "onboarded_at": self.onboarded_at.isoformat() if self.onboarded_at else None,
        }


@dataclass
class MoleculeTracker:
    """Molecule tracking configuration."""
    user_id: str
    molecule_id: str
    molecule_name: str
    alerts_enabled: bool = True
    alert_types: List[str] = field(default_factory=lambda: ["regulatory", "clinical", "news"])
    notification_frequency: str = "daily"  # daily, weekly, instant
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "molecule_id": self.molecule_id,
            "molecule_name": self.molecule_name,
            "alerts_enabled": self.alerts_enabled,
            "alert_types": self.alert_types,
            "notification_frequency": self.notification_frequency,
            "created_at": self.created_at.isoformat(),
        }


class UserOnboardingService:
    """
    Service for user onboarding.

    Provides role-based setup and molecule tracking configuration.
    """

    # Default therapeutic areas by role
    ROLE_DEFAULT_TAS = {
        UserRole.ANALYST: [],
        UserRole.EXECUTIVE: [],
        UserRole.SCIENTIST: ["Oncology", "Immunology"],
        UserRole.REGULATORY: ["All"],
        UserRole.COMMERCIAL: ["Oncology", "Neurology", "Cardiology"],
        UserRole.ADMIN: [],
    }

    # Default preferences by role
    ROLE_DEFAULT_PREFS = {
        UserRole.ANALYST: {
            "dashboard_widgets": ["tracked_molecules", "recent_alerts", "quick_search"],
            "default_view": "dashboard",
            "export_format": "excel",
        },
        UserRole.EXECUTIVE: {
            "dashboard_widgets": ["key_metrics", "competitive_landscape", "insights"],
            "default_view": "insights",
            "export_format": "pdf",
        },
        UserRole.SCIENTIST: {
            "dashboard_widgets": ["trials", "publications", "safety"],
            "default_view": "molecule_detail",
            "export_format": "json",
        },
        UserRole.REGULATORY: {
            "dashboard_widgets": ["regulatory_status", "alerts", "timeline"],
            "default_view": "regulatory",
            "export_format": "excel",
        },
        UserRole.COMMERCIAL: {
            "dashboard_widgets": ["competitive_graph", "lifecycle", "pricing"],
            "default_view": "comparison",
            "export_format": "excel",
        },
        UserRole.ADMIN: {
            "dashboard_widgets": ["system_health", "user_activity", "data_quality"],
            "default_view": "admin",
            "export_format": "json",
        },
    }

    # In-memory storage (replace with database in production)
    _users: Dict[str, UserProfile] = {}
    _trackers: Dict[str, List[MoleculeTracker]] = {}

    async def onboard_user(
        self,
        email: str,
        name: str,
        role: str = "analyst",
        organization: Optional[str] = None,
        therapeutic_areas: Optional[List[str]] = None,
    ) -> UserProfile:
        """
        Onboard a new user with role-based setup.

        Args:
            email: User email
            name: User name
            role: User role (analyst, executive, scientist, regulatory, commercial, admin)
            organization: Organization name
            therapeutic_areas: Areas of interest

        Returns:
            UserProfile with configured defaults
        """
        import uuid

        logger.info(f"Onboarding user: {email} with role {role}")

        # Parse role
        try:
            user_role = UserRole(role.lower())
        except ValueError:
            user_role = UserRole.ANALYST

        # Generate user ID
        user_id = str(uuid.uuid4())[:12]

        # Set therapeutic areas (user override or role defaults)
        tas = therapeutic_areas or self.ROLE_DEFAULT_TAS.get(user_role, [])

        # Create user profile
        profile = UserProfile(
            user_id=user_id,
            email=email,
            name=name,
            role=user_role,
            organization=organization,
            therapeutic_areas=tas,
            preferences=self.ROLE_DEFAULT_PREFS.get(user_role, {}),
            onboarding_status=OnboardingStatus.IN_PROGRESS,
        )

        # Store user
        self._users[user_id] = profile

        # Initialize empty tracker list
        self._trackers[user_id] = []

        # Mark as completed
        profile.onboarding_status = OnboardingStatus.COMPLETED
        profile.onboarded_at = datetime.utcnow()

        logger.info(f"User {user_id} onboarded successfully")
        return profile

    async def setup_molecule_tracking(
        self,
        user_id: str,
        molecules: List[Dict[str, str]],
        alert_types: Optional[List[str]] = None,
        notification_frequency: str = "daily",
    ) -> List[MoleculeTracker]:
        """
        Set up molecule tracking for a user.

        Args:
            user_id: User ID
            molecules: List of {"molecule_id": ..., "molecule_name": ...}
            alert_types: Types of alerts to enable
            notification_frequency: How often to notify

        Returns:
            List of configured trackers
        """
        logger.info(f"Setting up molecule tracking for user {user_id}")

        if user_id not in self._users:
            raise ValueError(f"User {user_id} not found")

        default_alerts = alert_types or ["regulatory", "clinical", "news"]
        trackers = []

        for mol in molecules:
            tracker = MoleculeTracker(
                user_id=user_id,
                molecule_id=mol.get("molecule_id", ""),
                molecule_name=mol.get("molecule_name", ""),
                alert_types=default_alerts,
                notification_frequency=notification_frequency,
            )
            trackers.append(tracker)

        # Store trackers
        if user_id not in self._trackers:
            self._trackers[user_id] = []
        self._trackers[user_id].extend(trackers)

        # Update user tracked molecules
        self._users[user_id].tracked_molecules.extend(
            [t.molecule_id for t in trackers]
        )

        return trackers

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile by ID."""
        return self._users.get(user_id)

    async def get_tracked_molecules(self, user_id: str) -> List[MoleculeTracker]:
        """Get tracked molecules for a user."""
        return self._trackers.get(user_id, [])

    async def suggest_molecules(
        self,
        therapeutic_areas: List[str],
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Suggest molecules based on therapeutic areas.

        Returns suggested molecules for tracking.
        """
        # In production, query database for popular/relevant molecules
        suggestions = []

        if "Oncology" in therapeutic_areas or "oncology" in therapeutic_areas:
            suggestions.extend([
                {"molecule_id": "pembrolizumab", "molecule_name": "Pembrolizumab", "reason": "Leading checkpoint inhibitor"},
                {"molecule_id": "nivolumab", "molecule_name": "Nivolumab", "reason": "Key competitor in IO space"},
                {"molecule_id": "atezolizumab", "molecule_name": "Atezolizumab", "reason": "PD-L1 inhibitor"},
            ])

        if "Immunology" in therapeutic_areas or "immunology" in therapeutic_areas:
            suggestions.extend([
                {"molecule_id": "adalimumab", "molecule_name": "Adalimumab", "reason": "Blockbuster anti-TNF"},
                {"molecule_id": "ustekinumab", "molecule_name": "Ustekinumab", "reason": "IL-12/23 inhibitor"},
            ])

        if "Neurology" in therapeutic_areas or "neurology" in therapeutic_areas:
            suggestions.extend([
                {"molecule_id": "lecanemab", "molecule_name": "Lecanemab", "reason": "Recent Alzheimer's approval"},
                {"molecule_id": "donanemab", "molecule_name": "Donanemab", "reason": "Pipeline AD therapy"},
            ])

        return suggestions[:limit]


class PipelineStage(str, Enum):
    """Data onboarding pipeline stages."""
    INGEST = "ingest"
    NORMALIZE = "normalize"
    DEDUPLICATE = "deduplicate"
    ENRICH = "enrich"
    VALIDATE = "validate"
    INDEX = "index"
    SERVE = "serve"


@dataclass
class PipelineStatus:
    """Status of a pipeline run."""
    job_id: str
    molecule_id: str
    current_stage: PipelineStage
    stages_completed: List[str] = field(default_factory=list)
    stages_pending: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    progress_percent: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "molecule_id": self.molecule_id,
            "current_stage": self.current_stage.value,
            "stages_completed": self.stages_completed,
            "stages_pending": self.stages_pending,
            "errors": self.errors,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress_percent": self.progress_percent,
        }


class DataOnboardingPipeline:
    """
    7-step data onboarding pipeline.

    Stages:
    1. Ingest - Collect data from all sources
    2. Normalize - Standardize formats and terminology
    3. Deduplicate - Remove duplicate records
    4. Enrich - Add derived data (classifications, scores)
    5. Validate - Quality checks and completeness
    6. Index - Add to search indexes
    7. Serve - Make available via API
    """

    STAGES = [
        PipelineStage.INGEST,
        PipelineStage.NORMALIZE,
        PipelineStage.DEDUPLICATE,
        PipelineStage.ENRICH,
        PipelineStage.VALIDATE,
        PipelineStage.INDEX,
        PipelineStage.SERVE,
    ]

    # In-memory storage
    _jobs: Dict[str, PipelineStatus] = {}

    async def start_pipeline(
        self,
        molecule_id: str,
        molecule_name: str,
        data_sources: Optional[List[str]] = None,
    ) -> PipelineStatus:
        """
        Start data onboarding pipeline for a molecule.

        Args:
            molecule_id: Molecule identifier
            molecule_name: Molecule name
            data_sources: Data sources to ingest from

        Returns:
            PipelineStatus with job tracking info
        """
        import uuid

        job_id = str(uuid.uuid4())[:8]
        logger.info(f"Starting pipeline {job_id} for {molecule_name}")

        status = PipelineStatus(
            job_id=job_id,
            molecule_id=molecule_id,
            current_stage=PipelineStage.INGEST,
            stages_pending=[s.value for s in self.STAGES],
        )

        self._jobs[job_id] = status

        # Run pipeline asynchronously
        asyncio.create_task(self._run_pipeline(job_id, molecule_name, data_sources))

        return status

    async def _run_pipeline(
        self,
        job_id: str,
        molecule_name: str,
        data_sources: Optional[List[str]],
    ):
        """Execute the pipeline stages."""
        status = self._jobs[job_id]
        sources = data_sources or ["clinicaltrials", "fda", "openfda", "pubmed"]

        try:
            for i, stage in enumerate(self.STAGES):
                status.current_stage = stage
                status.stages_pending = [s.value for s in self.STAGES[i + 1:]]
                status.progress_percent = (i / len(self.STAGES)) * 100

                logger.info(f"Pipeline {job_id}: Running stage {stage.value}")

                # Execute stage
                if stage == PipelineStage.INGEST:
                    await self._stage_ingest(molecule_name, sources)
                elif stage == PipelineStage.NORMALIZE:
                    await self._stage_normalize(molecule_name)
                elif stage == PipelineStage.DEDUPLICATE:
                    await self._stage_deduplicate(molecule_name)
                elif stage == PipelineStage.ENRICH:
                    await self._stage_enrich(molecule_name)
                elif stage == PipelineStage.VALIDATE:
                    await self._stage_validate(molecule_name)
                elif stage == PipelineStage.INDEX:
                    await self._stage_index(molecule_name)
                elif stage == PipelineStage.SERVE:
                    await self._stage_serve(molecule_name)

                status.stages_completed.append(stage.value)

            status.progress_percent = 100.0
            status.completed_at = datetime.utcnow()
            logger.info(f"Pipeline {job_id} completed successfully")

        except Exception as e:
            logger.error(f"Pipeline {job_id} failed at {status.current_stage.value}: {e}")
            status.errors.append(str(e))

    async def _stage_ingest(self, molecule_name: str, sources: List[str]):
        """Ingest data from sources."""
        # In production, call various data services
        await asyncio.sleep(0.1)  # Simulate work
        logger.debug(f"Ingested data for {molecule_name} from {sources}")

    async def _stage_normalize(self, molecule_name: str):
        """Normalize data formats."""
        await asyncio.sleep(0.05)
        logger.debug(f"Normalized data for {molecule_name}")

    async def _stage_deduplicate(self, molecule_name: str):
        """Remove duplicates."""
        await asyncio.sleep(0.05)
        logger.debug(f"Deduplicated data for {molecule_name}")

    async def _stage_enrich(self, molecule_name: str):
        """Enrich with derived data."""
        await asyncio.sleep(0.1)
        logger.debug(f"Enriched data for {molecule_name}")

    async def _stage_validate(self, molecule_name: str):
        """Validate data quality."""
        await asyncio.sleep(0.05)
        logger.debug(f"Validated data for {molecule_name}")

    async def _stage_index(self, molecule_name: str):
        """Add to search indexes."""
        await asyncio.sleep(0.05)
        logger.debug(f"Indexed data for {molecule_name}")

    async def _stage_serve(self, molecule_name: str):
        """Make data available."""
        await asyncio.sleep(0.01)
        logger.debug(f"Data for {molecule_name} ready to serve")

    async def get_pipeline_status(self, job_id: str) -> Optional[PipelineStatus]:
        """Get status of a pipeline job."""
        return self._jobs.get(job_id)

    async def list_jobs(self, molecule_id: Optional[str] = None) -> List[PipelineStatus]:
        """List pipeline jobs, optionally filtered by molecule."""
        jobs = list(self._jobs.values())
        if molecule_id:
            jobs = [j for j in jobs if j.molecule_id == molecule_id]
        return jobs
