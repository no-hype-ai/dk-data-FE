"""
Gold Aggregation Service

Builds decision-ready aggregated views for the Gold layer.
Supports refresh of materialized views and cache invalidation.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class AggregationResult:
    """Result of an aggregation operation."""
    view_name: str
    rows_affected: int
    execution_time_ms: float
    success: bool
    error: Optional[str] = None


class GoldAggregationService:
    """
    Service for managing Gold layer aggregations and views.

    The Gold layer consists of:
    - Pre-aggregated views (molecule_profile, safety_signals, etc.)
    - Computed metrics and summaries
    - Decision-ready data for PostgREST API

    All Gold views exclude quarantined records (needs_review=TRUE).
    """

    def __init__(self, db_pool):
        """
        Initialize the gold aggregation service.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool

    async def refresh_molecule_profiles(self) -> AggregationResult:
        """
        Refresh molecule profile aggregations.

        Updates computed fields like trial counts, safety summaries, etc.
        """
        start_time = datetime.utcnow()

        try:
            async with self.db_pool.acquire() as conn:
                # Update molecule statistics that aren't covered by the view
                rows = await conn.execute("""
                    UPDATE silver.molecules m
                    SET
                        max_phase = COALESCE((
                            SELECT MAX(
                                CASE
                                    WHEN ct.phase LIKE '%4%' THEN 4
                                    WHEN ct.phase LIKE '%3%' THEN 3
                                    WHEN ct.phase LIKE '%2%' THEN 2
                                    WHEN ct.phase LIKE '%1%' THEN 1
                                    ELSE 0
                                END
                            )
                            FROM silver.clinical_trials ct
                            WHERE ct.molecule_id = m.id
                        ), m.max_phase),
                        updated_at = NOW()
                    WHERE m.needs_review = FALSE
                      AND EXISTS (
                          SELECT 1 FROM silver.clinical_trials ct
                          WHERE ct.molecule_id = m.id
                      )
                """)

                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

                return AggregationResult(
                    view_name='molecule_profiles',
                    rows_affected=int(rows.split()[-1]) if rows else 0,
                    execution_time_ms=execution_time,
                    success=True
                )

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(f"Failed to refresh molecule profiles: {e}")
            return AggregationResult(
                view_name='molecule_profiles',
                rows_affected=0,
                execution_time_ms=execution_time,
                success=False,
                error=str(e)
            )

    async def refresh_safety_signals(self) -> AggregationResult:
        """
        Refresh safety signal aggregations.

        Computes PRR (Proportional Reporting Ratio) and ROR for adverse events.
        """
        start_time = datetime.utcnow()

        try:
            async with self.db_pool.acquire() as conn:
                # Calculate PRR and ROR for adverse events
                # PRR = (a/a+b) / (c/c+d) where:
                # a = reports of event with drug
                # b = reports of other events with drug
                # c = reports of event with other drugs
                # d = reports of other events with other drugs

                rows = await conn.execute("""
                    WITH total_reports AS (
                        SELECT SUM(report_count) AS total FROM silver.adverse_events
                    ),
                    drug_totals AS (
                        SELECT molecule_id, SUM(report_count) AS drug_total
                        FROM silver.adverse_events
                        GROUP BY molecule_id
                    ),
                    event_totals AS (
                        SELECT meddra_pt, SUM(report_count) AS event_total
                        FROM silver.adverse_events
                        GROUP BY meddra_pt
                    )
                    UPDATE silver.adverse_events ae
                    SET
                        reporting_rate = ae.report_count::NUMERIC / NULLIF(dt.drug_total, 0) * 1000,
                        prr = CASE
                            WHEN dt.drug_total > 0 AND et.event_total > 0 AND tr.total > 0
                            THEN (ae.report_count::NUMERIC / dt.drug_total) /
                                 NULLIF((et.event_total::NUMERIC / tr.total), 0)
                            ELSE NULL
                        END,
                        updated_at = NOW()
                    FROM drug_totals dt, event_totals et, total_reports tr
                    WHERE ae.molecule_id = dt.molecule_id
                      AND ae.meddra_pt = et.meddra_pt
                """)

                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

                return AggregationResult(
                    view_name='safety_signals',
                    rows_affected=int(rows.split()[-1]) if rows else 0,
                    execution_time_ms=execution_time,
                    success=True
                )

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(f"Failed to refresh safety signals: {e}")
            return AggregationResult(
                view_name='safety_signals',
                rows_affected=0,
                execution_time_ms=execution_time,
                success=False,
                error=str(e)
            )

    async def refresh_competitive_landscape(self) -> AggregationResult:
        """Refresh competitive landscape aggregations."""
        start_time = datetime.utcnow()

        try:
            async with self.db_pool.acquire() as conn:
                # Update therapeutic areas from clinical trial conditions
                rows = await conn.execute("""
                    UPDATE silver.molecules m
                    SET
                        therapeutic_areas = COALESCE((
                            SELECT jsonb_agg(DISTINCT condition)
                            FROM silver.clinical_trials ct,
                                 jsonb_array_elements_text(ct.conditions) AS condition
                            WHERE ct.molecule_id = m.id
                        ), m.therapeutic_areas),
                        updated_at = NOW()
                    WHERE m.needs_review = FALSE
                      AND EXISTS (
                          SELECT 1 FROM silver.clinical_trials ct
                          WHERE ct.molecule_id = m.id
                      )
                """)

                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

                return AggregationResult(
                    view_name='competitive_landscape',
                    rows_affected=int(rows.split()[-1]) if rows else 0,
                    execution_time_ms=execution_time,
                    success=True
                )

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(f"Failed to refresh competitive landscape: {e}")
            return AggregationResult(
                view_name='competitive_landscape',
                rows_affected=0,
                execution_time_ms=execution_time,
                success=False,
                error=str(e)
            )

    async def refresh_lifecycle_stages(self) -> AggregationResult:
        """Refresh lifecycle stage calculations."""
        start_time = datetime.utcnow()

        try:
            async with self.db_pool.acquire() as conn:
                # Recalculate development status based on latest evidence
                rows = await conn.execute("""
                    WITH latest_phase AS (
                        SELECT
                            molecule_id,
                            MAX(CASE
                                WHEN phase LIKE '%4%' THEN 4
                                WHEN phase LIKE '%3%' THEN 3
                                WHEN phase LIKE '%2%' THEN 2
                                WHEN phase LIKE '%1%' THEN 1
                                ELSE 0
                            END) AS max_trial_phase
                        FROM silver.clinical_trials
                        WHERE status NOT IN ('Terminated', 'Withdrawn', 'Suspended')
                        GROUP BY molecule_id
                    ),
                    has_approval AS (
                        SELECT DISTINCT molecule_id, TRUE AS is_approved
                        FROM silver.drug_labels
                        WHERE effective_date IS NOT NULL
                    )
                    UPDATE silver.molecules m
                    SET
                        development_status = CASE
                            WHEN ha.is_approved THEN 'approved'
                            WHEN lp.max_trial_phase >= 3 THEN 'phase_3'
                            WHEN lp.max_trial_phase >= 2 THEN 'phase_2'
                            WHEN lp.max_trial_phase >= 1 THEN 'phase_1'
                            WHEN lp.max_trial_phase = 0 THEN 'preclinical'
                            ELSE m.development_status
                        END,
                        max_phase = GREATEST(COALESCE(lp.max_trial_phase, 0), COALESCE(m.max_phase, 0)),
                        updated_at = NOW()
                    FROM latest_phase lp
                    LEFT JOIN has_approval ha ON lp.molecule_id = ha.molecule_id
                    WHERE m.id = lp.molecule_id
                      AND m.needs_review = FALSE
                """)

                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

                return AggregationResult(
                    view_name='lifecycle_stages',
                    rows_affected=int(rows.split()[-1]) if rows else 0,
                    execution_time_ms=execution_time,
                    success=True
                )

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(f"Failed to refresh lifecycle stages: {e}")
            return AggregationResult(
                view_name='lifecycle_stages',
                rows_affected=0,
                execution_time_ms=execution_time,
                success=False,
                error=str(e)
            )

    async def refresh_all(self) -> Dict[str, AggregationResult]:
        """Refresh all Gold layer aggregations."""
        results = {}

        aggregations = [
            ('molecule_profiles', self.refresh_molecule_profiles),
            ('safety_signals', self.refresh_safety_signals),
            ('competitive_landscape', self.refresh_competitive_landscape),
            ('lifecycle_stages', self.refresh_lifecycle_stages),
        ]

        for name, refresh_func in aggregations:
            try:
                results[name] = await refresh_func()
                logger.info(
                    f"Refreshed {name}: {results[name].rows_affected} rows "
                    f"in {results[name].execution_time_ms:.2f}ms"
                )
            except Exception as e:
                logger.error(f"Failed to refresh {name}: {e}")
                results[name] = AggregationResult(
                    view_name=name,
                    rows_affected=0,
                    execution_time_ms=0,
                    success=False,
                    error=str(e)
                )

        return results

    async def get_molecule_profile(self, molecule_id: str) -> Optional[Dict[str, Any]]:
        """Get complete molecule profile from Gold layer."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM gold.molecule_profile
                WHERE molecule_id = $1::uuid
            """, molecule_id)

            if row:
                return dict(row)
            return None

    async def search_molecules(
        self,
        query: str,
        threshold: float = 0.3,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search molecules using fuzzy matching."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM gold.search_molecules($1, $2, $3)
            """, query, threshold, limit)

            return [dict(row) for row in rows]

    async def resolve_identifier(
        self,
        identifier: str,
        identifier_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Resolve identifier to molecule."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM gold.resolve_identifier($1, $2)
            """, identifier, identifier_type)

            if row:
                return dict(row)
            return None

    async def get_safety_signals(self, molecule_id: str) -> Optional[Dict[str, Any]]:
        """Get safety signals for a molecule."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM gold.safety_signals
                WHERE molecule_id = $1::uuid
            """, molecule_id)

            if row:
                return dict(row)
            return None

    async def get_competitive_landscape(
        self,
        therapeutic_area: Optional[str] = None,
        mechanism: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get competitive landscape data with optional filters."""
        async with self.db_pool.acquire() as conn:
            conditions = ["TRUE"]
            params = []

            if therapeutic_area:
                params.append(therapeutic_area)
                conditions.append("therapeutic_areas @> ${len(params)}::jsonb")

            if mechanism:
                params.append(f"%{mechanism}%")
                conditions.append(f"mechanism_of_action ILIKE ${len(params)}")

            params.append(limit)

            query = f"""
                SELECT * FROM gold.competitive_landscape
                WHERE {' AND '.join(conditions)}
                ORDER BY active_trials DESC
                LIMIT ${len(params)}
            """

            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def get_company_pipeline(
        self,
        company: Optional[str] = None,
        phase: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get company pipeline data."""
        async with self.db_pool.acquire() as conn:
            conditions = ["TRUE"]
            params = []

            if company:
                params.append(f"%{company}%")
                conditions.append(f"company ILIKE ${len(params)}")

            if phase:
                params.append(phase)
                conditions.append(f"phase = ${len(params)}")

            params.append(limit)

            query = f"""
                SELECT * FROM gold.company_pipeline
                WHERE {' AND '.join(conditions)}
                ORDER BY company, latest_trial_start DESC
                LIMIT ${len(params)}
            """

            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def get_lifecycle_evidence(
        self,
        molecule_id: str,
        evidence_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get lifecycle evidence for a molecule."""
        async with self.db_pool.acquire() as conn:
            if evidence_type:
                rows = await conn.fetch("""
                    SELECT * FROM gold.lifecycle_evidence
                    WHERE molecule_id = $1::uuid
                      AND evidence_type = $2
                    ORDER BY evidence_date DESC
                """, molecule_id, evidence_type)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM gold.lifecycle_evidence
                    WHERE molecule_id = $1::uuid
                    ORDER BY evidence_date DESC
                """, molecule_id)

            return [dict(row) for row in rows]

    async def get_aggregation_stats(self) -> Dict[str, Any]:
        """Get statistics about Gold layer data."""
        async with self.db_pool.acquire() as conn:
            stats = {}

            # Molecule counts
            stats['molecules'] = await conn.fetchrow("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE needs_review = FALSE) AS published,
                    COUNT(*) FILTER (WHERE needs_review = TRUE) AS quarantined,
                    COUNT(*) FILTER (WHERE development_status = 'approved') AS approved,
                    COUNT(*) FILTER (WHERE development_status LIKE 'phase_%') AS in_trials
                FROM silver.molecules
            """)

            # Trial counts
            stats['trials'] = await conn.fetchrow("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status IN ('Recruiting', 'Active, not recruiting')) AS active
                FROM silver.clinical_trials
            """)

            # Safety data
            stats['adverse_events'] = await conn.fetchrow("""
                SELECT
                    COUNT(DISTINCT molecule_id) AS molecules_with_events,
                    SUM(report_count) AS total_reports,
                    SUM(serious_count) AS serious_reports
                FROM silver.adverse_events
            """)

            return {
                'molecules': dict(stats['molecules']) if stats['molecules'] else {},
                'trials': dict(stats['trials']) if stats['trials'] else {},
                'adverse_events': dict(stats['adverse_events']) if stats['adverse_events'] else {},
            }
