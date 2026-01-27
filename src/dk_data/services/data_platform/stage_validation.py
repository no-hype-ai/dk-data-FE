"""
Stage Validation Service

Validates molecules have sufficient evidence for claimed lifecycle stage.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from dataclasses import dataclass
from enum import Enum
import logging

from .evidence_requirements import EvidenceRequirementService, StageEvidenceReport

logger = logging.getLogger(__name__)


class ValidationResult(str, Enum):
    """Validation result types."""
    PASSED = "passed"
    FAILED = "failed"
    OVERRIDE = "override"


@dataclass
class ValidationRecord:
    """Record of a validation event."""
    id: UUID
    tracking_id: UUID
    molecule_id: UUID
    user_id: UUID
    validated_stage: str
    result: ValidationResult
    required_evidence_count: int
    present_evidence_count: int
    missing_evidence: List[Dict[str, Any]]
    evidence_details: Dict[str, Any]
    override_reason: Optional[str]
    override_approved_by: Optional[UUID]
    created_at: datetime


class StageValidationService:
    """
    Service for validating molecule lifecycle stages.

    Features:
    - Validate molecules against stage requirements
    - Track validation history
    - Support admin override capability
    - Audit all validation events
    """

    def __init__(self, db_pool, evidence_service: EvidenceRequirementService):
        """
        Initialize stage validation service.

        Args:
            db_pool: Database connection pool
            evidence_service: Evidence requirement service
        """
        self.db_pool = db_pool
        self.evidence_service = evidence_service

    async def validate_stage(
        self,
        molecule_id: UUID,
        tracking_id: UUID,
        stage: str,
        user_id: UUID
    ) -> ValidationRecord:
        """
        Validate molecule has evidence for claimed stage.

        Args:
            molecule_id: UUID of the molecule
            tracking_id: UUID of the tracking record
            stage: Stage to validate
            user_id: User performing validation

        Returns:
            ValidationRecord with result
        """
        # Check evidence
        evidence_report = await self.evidence_service.check_evidence(molecule_id, stage)

        # Determine result
        if evidence_report.can_progress:
            result = ValidationResult.PASSED
        else:
            result = ValidationResult.FAILED

        # Create validation record
        record = ValidationRecord(
            id=uuid4(),
            tracking_id=tracking_id,
            molecule_id=molecule_id,
            user_id=user_id,
            validated_stage=stage,
            result=result,
            required_evidence_count=evidence_report.required_count,
            present_evidence_count=evidence_report.satisfied_count,
            missing_evidence=[
                {"type": m.type, "description": m.description}
                for m in evidence_report.missing_required
            ],
            evidence_details={
                "confidence": evidence_report.confidence,
                "requirements": [
                    {
                        "type": r.requirement.type,
                        "satisfied": r.satisfied,
                        "count": r.evidence_count,
                    }
                    for r in evidence_report.requirements
                ]
            },
            override_reason=None,
            override_approved_by=None,
            created_at=datetime.utcnow(),
        )

        # Save to database
        await self._save_validation(record)

        # Update tracking status if passed
        if result == ValidationResult.PASSED:
            await self._update_tracking_validated(tracking_id, stage, user_id)

        return record

    async def override_validation(
        self,
        molecule_id: UUID,
        tracking_id: UUID,
        stage: str,
        user_id: UUID,
        override_reason: str,
        approved_by: UUID
    ) -> ValidationRecord:
        """
        Override validation for a molecule stage.

        Requires admin approval.

        Args:
            molecule_id: UUID of the molecule
            tracking_id: UUID of the tracking record
            stage: Stage to override
            user_id: User requesting override
            override_reason: Reason for override
            approved_by: Admin who approved

        Returns:
            ValidationRecord with override
        """
        # Get current evidence (for record)
        evidence_report = await self.evidence_service.check_evidence(molecule_id, stage)

        record = ValidationRecord(
            id=uuid4(),
            tracking_id=tracking_id,
            molecule_id=molecule_id,
            user_id=user_id,
            validated_stage=stage,
            result=ValidationResult.OVERRIDE,
            required_evidence_count=evidence_report.required_count,
            present_evidence_count=evidence_report.satisfied_count,
            missing_evidence=[
                {"type": m.type, "description": m.description}
                for m in evidence_report.missing_required
            ],
            evidence_details={
                "confidence": evidence_report.confidence,
                "override": True,
            },
            override_reason=override_reason,
            override_approved_by=approved_by,
            created_at=datetime.utcnow(),
        )

        await self._save_validation(record)
        await self._update_tracking_validated(tracking_id, stage, user_id)

        # Log override event
        await self._log_audit(
            tracking_id=tracking_id,
            user_id=user_id,
            action='stage_override',
            details={
                'stage': stage,
                'reason': override_reason,
                'approved_by': str(approved_by),
            }
        )

        return record

    async def get_validation_history(
        self,
        molecule_id: UUID,
        limit: int = 10
    ) -> List[ValidationRecord]:
        """Get validation history for a molecule."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM stage_validations
                WHERE molecule_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, molecule_id, limit)

            return [
                ValidationRecord(
                    id=r['validation_id'],
                    tracking_id=r['tracking_id'],
                    molecule_id=r['molecule_id'],
                    user_id=r['user_id'],
                    validated_stage=r['validated_stage'],
                    result=ValidationResult(r['validation_result']),
                    required_evidence_count=r['required_evidence_count'],
                    present_evidence_count=r['present_evidence_count'],
                    missing_evidence=r['missing_evidence'] or [],
                    evidence_details=r['evidence_details'] or {},
                    override_reason=r['override_reason'],
                    override_approved_by=r['override_approved_by'],
                    created_at=r['created_at'],
                )
                for r in rows
            ]

    async def get_latest_validation(
        self,
        tracking_id: UUID
    ) -> Optional[ValidationRecord]:
        """Get most recent validation for a tracking record."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM stage_validations
                WHERE tracking_id = $1
                ORDER BY created_at DESC
                LIMIT 1
            """, tracking_id)

            if not row:
                return None

            return ValidationRecord(
                id=row['validation_id'],
                tracking_id=row['tracking_id'],
                molecule_id=row['molecule_id'],
                user_id=row['user_id'],
                validated_stage=row['validated_stage'],
                result=ValidationResult(row['validation_result']),
                required_evidence_count=row['required_evidence_count'],
                present_evidence_count=row['present_evidence_count'],
                missing_evidence=row['missing_evidence'] or [],
                evidence_details=row['evidence_details'] or {},
                override_reason=row['override_reason'],
                override_approved_by=row['override_approved_by'],
                created_at=row['created_at'],
            )

    async def _save_validation(self, record: ValidationRecord):
        """Save validation record to database."""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO stage_validations (
                    validation_id, tracking_id, molecule_id, user_id,
                    validated_stage, validation_result,
                    required_evidence_count, present_evidence_count,
                    missing_evidence, evidence_details,
                    override_reason, override_approved_by, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
                record.id, record.tracking_id, record.molecule_id, record.user_id,
                record.validated_stage, record.result.value,
                record.required_evidence_count, record.present_evidence_count,
                record.missing_evidence, record.evidence_details,
                record.override_reason, record.override_approved_by, record.created_at
            )

    async def _update_tracking_validated(
        self,
        tracking_id: UUID,
        stage: str,
        user_id: UUID
    ):
        """Update tracking record as validated."""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE user_tracked_molecules
                SET stage_validated = TRUE,
                    stage_validated_at = NOW(),
                    stage_validated_by = $3,
                    tracked_stage = $2,
                    updated_at = NOW()
                WHERE tracking_id = $1
            """, tracking_id, stage, user_id)

    async def _log_audit(
        self,
        tracking_id: UUID,
        user_id: UUID,
        action: str,
        details: Dict[str, Any]
    ):
        """Log audit event."""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO onboarding_audit_log (
                    audit_id, tracking_id, user_id, action_type, action_details, created_at
                ) VALUES ($1, $2, $3, $4, $5, NOW())
            """, uuid4(), tracking_id, user_id, action, details)
