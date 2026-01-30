"""
Evidence Requirements Service

Defines and validates evidence requirements for each lifecycle stage.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from uuid import UUID
from dataclasses import dataclass
from enum import Enum
import logging
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


class EvidenceType(str, Enum):
    """Types of evidence."""
    STRUCTURE = "structure"
    BIOACTIVITY = "bioactivity"
    TARGET = "target"
    PUBLICATION = "publication"
    CLINICAL_TRIAL = "clinical_trial"
    DRUG_LABEL = "drug_label"
    SAFETY_DATA = "safety_data"
    REGULATORY_SUBMISSION = "regulatory_submission"
    APPROVAL_DATE = "approval_date"
    PRODUCT_INFO = "product_info"
    WITHDRAWAL_EVIDENCE = "withdrawal_evidence"
    SAFETY_CONCERNS = "safety_concerns"


@dataclass
class EvidenceRequirement:
    """Single evidence requirement."""
    type: str
    description: str
    required: bool
    sources: List[str]
    min_count: Optional[int] = None
    phase: Optional[List[str]] = None
    status_filter: Optional[List[str]] = None
    min_reports: Optional[int] = None


@dataclass
class EvidenceResult:
    """Result of evidence check."""
    requirement: EvidenceRequirement
    satisfied: bool
    evidence_count: int
    evidence_items: List[Dict[str, Any]]
    source_links: List[str]
    notes: Optional[str] = None


@dataclass
class StageEvidenceReport:
    """Complete evidence report for a lifecycle stage."""
    molecule_id: UUID
    stage: str
    stage_name: str
    requirements: List[EvidenceResult]
    required_count: int
    satisfied_count: int
    missing_required: List[EvidenceRequirement]
    confidence: float
    can_progress: bool
    generated_at: datetime


class EvidenceRequirementService:
    """
    Service for managing evidence requirements.

    Features:
    - Load requirements from YAML config
    - Check molecule against stage requirements
    - Generate evidence gap reports
    - Calculate stage confidence
    """

    def __init__(self, db_pool, config_path: Optional[str] = None):
        """
        Initialize evidence requirement service.

        Args:
            db_pool: Database connection pool
            config_path: Path to lifecycle_requirements.yaml
        """
        self.db_pool = db_pool
        self.config = self._load_config(config_path)
        self.stage_requirements = self._parse_requirements()

    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load requirements configuration."""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "lifecycle_requirements.yaml"

        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Could not load config from {config_path}: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            "stages": {},
            "confidence": {"high": 0.8, "medium": 0.5, "low": 0.3},
            "source_weights": {"openfda_labels": 1.0, "clinicaltrials_gov": 0.95}
        }

    def _parse_requirements(self) -> Dict[str, List[EvidenceRequirement]]:
        """Parse requirements from config."""
        requirements = {}
        for stage_key, stage_data in self.config.get("stages", {}).items():
            stage_reqs = []
            for req in stage_data.get("requirements", []):
                stage_reqs.append(EvidenceRequirement(
                    type=req.get("type"),
                    description=req.get("description", ""),
                    required=req.get("required", False),
                    sources=req.get("sources", []),
                    min_count=req.get("min_count"),
                    phase=req.get("phase"),
                    status_filter=req.get("status_filter"),
                    min_reports=req.get("min_reports"),
                ))
            requirements[stage_key] = stage_reqs
        return requirements

    async def check_evidence(
        self,
        molecule_id: UUID,
        stage: str
    ) -> StageEvidenceReport:
        """
        Check molecule evidence against stage requirements.

        Args:
            molecule_id: UUID of the molecule
            stage: Lifecycle stage to check

        Returns:
            StageEvidenceReport with all results
        """
        requirements = self.stage_requirements.get(stage, [])
        stage_info = self.config.get("stages", {}).get(stage, {})

        results = []
        for req in requirements:
            result = await self._check_requirement(molecule_id, req)
            results.append(result)

        required_count = sum(1 for r in requirements if r.required)
        satisfied_count = sum(1 for r in results if r.satisfied and r.requirement.required)

        missing_required = [
            r.requirement for r in results
            if r.requirement.required and not r.satisfied
        ]

        # Calculate confidence
        if required_count > 0:
            base_confidence = satisfied_count / required_count
        else:
            base_confidence = 1.0

        # Bonus for optional evidence
        optional_satisfied = sum(1 for r in results if r.satisfied and not r.requirement.required)
        optional_count = len(requirements) - required_count
        if optional_count > 0:
            optional_bonus = (optional_satisfied / optional_count) * 0.2
            base_confidence = min(1.0, base_confidence + optional_bonus)

        return StageEvidenceReport(
            molecule_id=molecule_id,
            stage=stage,
            stage_name=stage_info.get("name", stage),
            requirements=results,
            required_count=required_count,
            satisfied_count=satisfied_count,
            missing_required=missing_required,
            confidence=round(base_confidence, 2),
            can_progress=len(missing_required) == 0,
            generated_at=datetime.utcnow(),
        )

    async def _check_requirement(
        self,
        molecule_id: UUID,
        requirement: EvidenceRequirement
    ) -> EvidenceResult:
        """Check a single requirement against molecule data."""
        evidence_items = []
        source_links = []

        async with self.db_pool.acquire() as conn:
            if requirement.type == "structure":
                evidence_items = await self._check_structure(conn, molecule_id)
            elif requirement.type == "bioactivity":
                evidence_items = await self._check_bioactivity(conn, molecule_id, requirement)
            elif requirement.type == "target":
                evidence_items = await self._check_targets(conn, molecule_id, requirement)
            elif requirement.type == "publication":
                evidence_items = await self._check_publications(conn, molecule_id, requirement)
            elif requirement.type in ["clinical_trial", "phase_1_complete", "phase_2_complete"]:
                evidence_items = await self._check_trials(conn, molecule_id, requirement)
            elif requirement.type == "drug_label":
                evidence_items = await self._check_labels(conn, molecule_id)
            elif requirement.type == "safety_data":
                evidence_items = await self._check_safety(conn, molecule_id, requirement)
            elif requirement.type == "approval_date":
                evidence_items = await self._check_approval(conn, molecule_id)

        # Generate source links
        for item in evidence_items:
            if link := item.get("url"):
                source_links.append(link)

        # Determine if satisfied
        min_count = requirement.min_count or 1
        satisfied = len(evidence_items) >= min_count

        return EvidenceResult(
            requirement=requirement,
            satisfied=satisfied,
            evidence_count=len(evidence_items),
            evidence_items=evidence_items,
            source_links=source_links,
        )

    async def _check_structure(self, conn, molecule_id: UUID) -> List[Dict]:
        """Check for chemical structure."""
        row = await conn.fetchrow("""
            SELECT inchi_key, canonical_smiles, inchi
            FROM silver.molecules WHERE id = $1
        """, molecule_id)

        if row and (row['inchi_key'] or row['canonical_smiles']):
            return [{
                "type": "structure",
                "inchi_key": row['inchi_key'],
                "smiles": row['canonical_smiles'],
            }]
        return []

    async def _check_bioactivity(self, conn, molecule_id: UUID, req: EvidenceRequirement) -> List[Dict]:
        """Check for bioactivity data."""
        rows = await conn.fetch("""
            SELECT id, target_name, standard_type, standard_value, pchembl_value
            FROM silver.bioactivity WHERE molecule_id = $1
            LIMIT 10
        """, molecule_id)

        return [dict(r) for r in rows]

    async def _check_targets(self, conn, molecule_id: UUID, req: EvidenceRequirement) -> List[Dict]:
        """Check for target associations."""
        rows = await conn.fetch("""
            SELECT DISTINCT t.id, t.target_name, t.uniprot_id
            FROM silver.targets t
            JOIN silver.bioactivity b ON b.target_id = t.id
            WHERE b.molecule_id = $1
            LIMIT 10
        """, molecule_id)

        return [dict(r) for r in rows]

    async def _check_publications(self, conn, molecule_id: UUID, req: EvidenceRequirement) -> List[Dict]:
        """Check for publications."""
        rows = await conn.fetch("""
            SELECT p.id, p.title, p.doi, p.publication_year
            FROM silver.publications p
            JOIN silver.molecule_publications mp ON mp.publication_id = p.id
            WHERE mp.molecule_id = $1
            ORDER BY p.publication_year DESC
            LIMIT 20
        """, molecule_id)

        return [{"url": f"https://doi.org/{r['doi']}" if r['doi'] else None, **dict(r)} for r in rows]

    async def _check_trials(self, conn, molecule_id: UUID, req: EvidenceRequirement) -> List[Dict]:
        """Check for clinical trials."""
        phases = req.phase or []
        statuses = req.status_filter or []

        query = """
            SELECT nct_id, title, phase, status, start_date
            FROM silver.clinical_trials WHERE molecule_id = $1
        """
        params = [molecule_id]

        if phases:
            query += " AND phase = ANY($2)"
            params.append(phases)

        if statuses:
            idx = len(params) + 1
            query += f" AND status = ANY(${idx})"
            params.append(statuses)

        query += " ORDER BY start_date DESC LIMIT 10"
        rows = await conn.fetch(query, *params)

        return [{
            "url": f"https://clinicaltrials.gov/study/{r['nct_id']}",
            **dict(r)
        } for r in rows]

    async def _check_labels(self, conn, molecule_id: UUID) -> List[Dict]:
        """Check for FDA drug labels."""
        rows = await conn.fetch("""
            SELECT set_id, brand_name, generic_name, effective_date
            FROM silver.drug_labels WHERE molecule_id = $1
            ORDER BY effective_date DESC LIMIT 5
        """, molecule_id)

        return [{
            "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={r['set_id']}",
            **dict(r)
        } for r in rows]

    async def _check_safety(self, conn, molecule_id: UUID, req: EvidenceRequirement) -> List[Dict]:
        """Check for safety data."""
        row = await conn.fetchrow("""
            SELECT COUNT(*) as total_reports,
                   COUNT(*) FILTER (WHERE serious_count > 0) as serious_reports
            FROM silver.adverse_events WHERE molecule_id = $1
        """, molecule_id)

        if row and row['total_reports'] >= (req.min_reports or 1):
            return [{"total_reports": row['total_reports'], "serious_reports": row['serious_reports']}]
        return []

    async def _check_approval(self, conn, molecule_id: UUID) -> List[Dict]:
        """Check for approval date."""
        row = await conn.fetchrow("""
            SELECT approval_date, first_approval_year
            FROM silver.molecules WHERE id = $1
        """, molecule_id)

        if row and (row['approval_date'] or row['first_approval_year']):
            return [dict(row)]
        return []

    def get_requirements_for_stage(self, stage: str) -> List[EvidenceRequirement]:
        """Get requirements for a specific stage."""
        return self.stage_requirements.get(stage, [])

    def get_stage_info(self, stage: str) -> Dict[str, Any]:
        """Get stage metadata."""
        return self.config.get("stages", {}).get(stage, {})

    async def get_evidence_gaps(
        self,
        molecule_id: UUID,
        current_stage: str,
        target_stage: str
    ) -> List[EvidenceRequirement]:
        """Get evidence gaps between current and target stage."""
        report = await self.check_evidence(molecule_id, target_stage)
        return report.missing_required
