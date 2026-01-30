"""
Lifecycle Detection Service

Auto-detects molecule lifecycle stage based on evidence in Silver layer.
Implements confidence scoring based on available evidence.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class LifecycleStage(Enum):
    """Molecule lifecycle stages."""
    UNKNOWN = "Unknown"
    DISCOVERY = "Discovery"
    PRECLINICAL = "Preclinical"
    PHASE_1 = "Phase 1"
    PHASE_2 = "Phase 2"
    PHASE_3 = "Phase 3"
    SUBMITTED = "Submitted"
    APPROVED = "Approved"
    MARKETED = "Marketed"
    WITHDRAWN = "Withdrawn"
    DISCONTINUED = "Discontinued"


# Stage progression order (for validation)
STAGE_ORDER = [
    LifecycleStage.UNKNOWN,
    LifecycleStage.DISCOVERY,
    LifecycleStage.PRECLINICAL,
    LifecycleStage.PHASE_1,
    LifecycleStage.PHASE_2,
    LifecycleStage.PHASE_3,
    LifecycleStage.SUBMITTED,
    LifecycleStage.APPROVED,
    LifecycleStage.MARKETED,
]


@dataclass
class EvidenceItem:
    """Single piece of evidence for lifecycle detection."""
    evidence_type: str  # clinical_trial, drug_label, publication, patent
    evidence_id: str
    title: Optional[str]
    detail: Optional[str]
    status: Optional[str]
    source: str
    date: Optional[datetime]
    url: Optional[str]
    weight: float = 1.0  # Evidence weight for confidence scoring


@dataclass
class LifecycleDetectionResult:
    """Result of lifecycle stage detection."""
    molecule_id: str
    detected_stage: LifecycleStage
    confidence: float
    previous_stage: Optional[LifecycleStage]
    stage_changed: bool
    evidence: List[EvidenceItem]
    evidence_summary: Dict[str, int]
    detected_at: datetime
    notes: Optional[str] = None


class LifecycleDetectionService:
    """
    Service for detecting molecule lifecycle stages from evidence.

    Detection Rules:
    - Approved: Has FDA label with approval date
    - Phase 3: Has active Phase 3 trial
    - Phase 2: Has active Phase 2 trial, no Phase 3
    - Phase 1: Has active Phase 1 trial, no Phase 2/3
    - Preclinical: Has bioactivity data, no clinical trials
    - Discovery: Only has publication/patent data

    Confidence Scoring:
    - Multiple evidence sources = higher confidence
    - Recent evidence = higher weight
    - Primary sources (FDA, CT.gov) = higher weight
    """

    # Evidence weights by source
    SOURCE_WEIGHTS = {
        'openfda_labels': 1.0,      # FDA label = definitive approval evidence
        'clinicaltrials_gov': 0.9,  # CT.gov = primary trial source
        'drugbank': 0.8,            # DrugBank = curated
        'chembl': 0.7,              # ChEMBL = comprehensive
        'pubchem': 0.6,             # PubChem = reference
        'openalex': 0.5,            # Publications
        'default': 0.5,
    }

    # Minimum confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.8
    MEDIUM_CONFIDENCE_THRESHOLD = 0.5

    def __init__(self, db_pool):
        """
        Initialize the lifecycle detection service.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool

    async def detect_lifecycle_stage(
        self,
        molecule_id: str
    ) -> LifecycleDetectionResult:
        """
        Detect lifecycle stage for a molecule.

        Args:
            molecule_id: UUID of the molecule

        Returns:
            LifecycleDetectionResult with detected stage and confidence
        """
        # Gather evidence from all sources
        evidence = await self._gather_evidence(molecule_id)

        # Get current stage from database
        current_stage = await self._get_current_stage(molecule_id)

        # Detect stage based on evidence
        detected_stage, confidence, notes = self._analyze_evidence(evidence)

        # Check if stage changed
        stage_changed = current_stage != detected_stage

        # Create evidence summary
        evidence_summary = self._summarize_evidence(evidence)

        result = LifecycleDetectionResult(
            molecule_id=molecule_id,
            detected_stage=detected_stage,
            confidence=confidence,
            previous_stage=current_stage if stage_changed else None,
            stage_changed=stage_changed,
            evidence=evidence,
            evidence_summary=evidence_summary,
            detected_at=datetime.utcnow(),
            notes=notes
        )

        # Update molecule if stage changed and confidence is high
        if stage_changed and confidence >= self.MEDIUM_CONFIDENCE_THRESHOLD:
            await self._update_molecule_stage(molecule_id, detected_stage, confidence)

        return result

    async def _gather_evidence(self, molecule_id: str) -> List[EvidenceItem]:
        """Gather all evidence for lifecycle detection."""
        evidence = []

        async with self.db_pool.acquire() as conn:
            # Check for FDA labels (approval evidence)
            labels = await conn.fetch("""
                SELECT set_id, brand_name, generic_name, effective_date,
                       product_type, source
                FROM silver.drug_labels
                WHERE molecule_id = $1::uuid
                ORDER BY effective_date DESC
            """, molecule_id)

            for label in labels:
                evidence.append(EvidenceItem(
                    evidence_type='drug_label',
                    evidence_id=label['set_id'],
                    title=f"{label['brand_name']} ({label['generic_name']})",
                    detail=label['product_type'],
                    status='Approved',
                    source=label['source'],
                    date=label['effective_date'],
                    url=f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={label['set_id']}",
                    weight=self.SOURCE_WEIGHTS.get(label['source'], 0.5)
                ))

            # Check for clinical trials
            trials = await conn.fetch("""
                SELECT nct_id, title, phase, status, start_date, source
                FROM silver.clinical_trials
                WHERE molecule_id = $1::uuid
                ORDER BY start_date DESC
            """, molecule_id)

            for trial in trials:
                is_active = trial['status'] in [
                    'Recruiting', 'Active, not recruiting',
                    'Enrolling by invitation', 'Not yet recruiting'
                ]
                evidence.append(EvidenceItem(
                    evidence_type='clinical_trial',
                    evidence_id=trial['nct_id'],
                    title=trial['title'],
                    detail=trial['phase'],
                    status=trial['status'],
                    source=trial['source'],
                    date=trial['start_date'],
                    url=f"https://clinicaltrials.gov/study/{trial['nct_id']}",
                    weight=1.0 if is_active else 0.5
                ))

            # Check for bioactivity data (preclinical evidence)
            bioactivity_count = await conn.fetchval("""
                SELECT COUNT(*) FROM silver.bioactivity
                WHERE molecule_id = $1::uuid
            """, molecule_id)

            if bioactivity_count > 0:
                evidence.append(EvidenceItem(
                    evidence_type='bioactivity',
                    evidence_id='aggregate',
                    title=f"{bioactivity_count} bioactivity records",
                    detail='Preclinical data',
                    status='Available',
                    source='chembl',
                    date=None,
                    url=None,
                    weight=0.6
                ))

            # Check for publications
            pub_count = await conn.fetchval("""
                SELECT COUNT(*) FROM silver.molecule_publications
                WHERE molecule_id = $1::uuid
            """, molecule_id)

            if pub_count > 0:
                evidence.append(EvidenceItem(
                    evidence_type='publication',
                    evidence_id='aggregate',
                    title=f"{pub_count} publications",
                    detail='Research literature',
                    status='Published',
                    source='openalex',
                    date=None,
                    url=None,
                    weight=0.4
                ))

            # Check for patents
            patents = await conn.fetch("""
                SELECT patent_number, title, grant_date, expiry_date, status
                FROM silver.patents
                WHERE molecule_id = $1::uuid
                ORDER BY grant_date DESC
                LIMIT 5
            """, molecule_id)

            for patent in patents:
                evidence.append(EvidenceItem(
                    evidence_type='patent',
                    evidence_id=patent['patent_number'],
                    title=patent['title'],
                    detail=f"Expires: {patent['expiry_date']}",
                    status=patent['status'],
                    source='patents',
                    date=patent['grant_date'],
                    url=None,
                    weight=0.3
                ))

        return evidence

    async def _get_current_stage(self, molecule_id: str) -> Optional[LifecycleStage]:
        """Get current lifecycle stage from database."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT development_status FROM silver.molecules
                WHERE id = $1::uuid
            """, molecule_id)

            if not row or not row['development_status']:
                return None

            status_map = {
                'preclinical': LifecycleStage.PRECLINICAL,
                'phase_1': LifecycleStage.PHASE_1,
                'phase_2': LifecycleStage.PHASE_2,
                'phase_3': LifecycleStage.PHASE_3,
                'approved': LifecycleStage.APPROVED,
                'withdrawn': LifecycleStage.WITHDRAWN,
            }
            return status_map.get(row['development_status'], LifecycleStage.UNKNOWN)

    def _analyze_evidence(
        self,
        evidence: List[EvidenceItem]
    ) -> Tuple[LifecycleStage, float, Optional[str]]:
        """
        Analyze evidence to determine lifecycle stage.

        Returns:
            Tuple of (stage, confidence, notes)
        """
        if not evidence:
            return LifecycleStage.UNKNOWN, 0.0, "No evidence found"

        # Check for approval evidence (highest priority)
        label_evidence = [e for e in evidence if e.evidence_type == 'drug_label']
        if label_evidence:
            confidence = min(1.0, sum(e.weight for e in label_evidence))
            return LifecycleStage.APPROVED, confidence, "FDA label found"

        # Check for clinical trial evidence
        trial_evidence = [e for e in evidence if e.evidence_type == 'clinical_trial']
        if trial_evidence:
            # Find highest phase from active trials
            active_trials = [e for e in trial_evidence if 'Recruiting' in (e.status or '') or 'Active' in (e.status or '')]

            if not active_trials:
                active_trials = trial_evidence  # Fall back to all trials

            phases = []
            for trial in active_trials:
                phase = trial.detail or ''
                if 'Phase 3' in phase or 'Phase 2/Phase 3' in phase:
                    phases.append(3)
                elif 'Phase 2' in phase or 'Phase 1/Phase 2' in phase:
                    phases.append(2)
                elif 'Phase 1' in phase:
                    phases.append(1)

            if phases:
                max_phase = max(phases)
                confidence = min(1.0, len(active_trials) * 0.3)

                if max_phase == 3:
                    return LifecycleStage.PHASE_3, confidence, f"{len(active_trials)} trials found"
                elif max_phase == 2:
                    return LifecycleStage.PHASE_2, confidence, f"{len(active_trials)} trials found"
                else:
                    return LifecycleStage.PHASE_1, confidence, f"{len(active_trials)} trials found"

        # Check for preclinical evidence
        bioactivity = [e for e in evidence if e.evidence_type == 'bioactivity']
        if bioactivity:
            return LifecycleStage.PRECLINICAL, 0.6, "Bioactivity data available"

        # Check for discovery-stage evidence
        pubs = [e for e in evidence if e.evidence_type == 'publication']
        patents = [e for e in evidence if e.evidence_type == 'patent']

        if pubs or patents:
            return LifecycleStage.DISCOVERY, 0.4, "Publications/patents only"

        return LifecycleStage.UNKNOWN, 0.0, "Insufficient evidence"

    def _summarize_evidence(self, evidence: List[EvidenceItem]) -> Dict[str, int]:
        """Create summary counts by evidence type."""
        summary = {}
        for item in evidence:
            key = item.evidence_type
            summary[key] = summary.get(key, 0) + 1
        return summary

    async def _update_molecule_stage(
        self,
        molecule_id: str,
        stage: LifecycleStage,
        confidence: float
    ):
        """Update molecule's lifecycle stage in database."""
        stage_map = {
            LifecycleStage.PRECLINICAL: 'preclinical',
            LifecycleStage.PHASE_1: 'phase_1',
            LifecycleStage.PHASE_2: 'phase_2',
            LifecycleStage.PHASE_3: 'phase_3',
            LifecycleStage.APPROVED: 'approved',
            LifecycleStage.WITHDRAWN: 'withdrawn',
        }

        status = stage_map.get(stage)
        if not status:
            return

        # Calculate max_phase
        phase_map = {
            LifecycleStage.PHASE_1: 1,
            LifecycleStage.PHASE_2: 2,
            LifecycleStage.PHASE_3: 3,
            LifecycleStage.APPROVED: 4,
        }
        max_phase = phase_map.get(stage, 0)

        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE silver.molecules
                SET development_status = $2,
                    max_phase = GREATEST(max_phase, $3),
                    resolution_confidence = $4,
                    updated_at = NOW()
                WHERE id = $1::uuid
            """, molecule_id, status, max_phase, confidence)

    async def detect_all_molecules(self, limit: int = 100) -> List[LifecycleDetectionResult]:
        """
        Run lifecycle detection on all molecules.

        Args:
            limit: Maximum molecules to process

        Returns:
            List of detection results
        """
        results = []

        async with self.db_pool.acquire() as conn:
            molecules = await conn.fetch("""
                SELECT id::text FROM silver.molecules
                WHERE needs_review = FALSE
                ORDER BY updated_at ASC
                LIMIT $1
            """, limit)

            for mol in molecules:
                try:
                    result = await self.detect_lifecycle_stage(mol['id'])
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to detect lifecycle for {mol['id']}: {e}")

        return results

    async def get_stage_transitions(
        self,
        molecule_id: str,
        days: int = 90
    ) -> List[Dict[str, Any]]:
        """
        Get recent lifecycle stage transitions for a molecule.

        Args:
            molecule_id: UUID of the molecule
            days: Look back period in days

        Returns:
            List of transition events
        """
        # This would query an audit/history table
        # For now, return empty list as placeholder
        return []
