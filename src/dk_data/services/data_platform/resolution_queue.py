"""
Resolution Queue Service

Manages the quarantine workflow for low-confidence entity resolution.
Records with confidence < 0.8 are marked needs_review=TRUE and excluded from Gold layer.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ResolutionAction(Enum):
    """Actions that can be taken on queued items."""
    APPROVE = "approve"       # Confirm the resolution is correct
    REJECT = "reject"         # Mark as incorrect, remove resolution
    MERGE = "merge"           # Merge with another molecule
    CREATE_NEW = "create_new" # Create as new molecule


class QueuePriority(Enum):
    """Priority levels for queue items."""
    HIGH = "high"       # Confidence 0.5-0.8, likely correct
    MEDIUM = "medium"   # Confidence 0.3-0.5, needs review
    LOW = "low"         # Confidence < 0.3, likely incorrect


@dataclass
class QueueItem:
    """Representation of a resolution queue item."""
    id: str
    molecule_id: Optional[str]
    original_identifier: str
    identifier_type: str
    confidence_score: float
    candidate_matches: List[Dict[str, Any]]
    status: str
    priority: str
    created_at: datetime
    source: Optional[str] = None


@dataclass
class ResolutionStats:
    """Statistics about the resolution queue."""
    pending_count: int
    pending_by_priority: Dict[str, int]
    approved_today: int
    rejected_today: int
    merged_today: int
    avg_resolution_time_hours: float


class ResolutionQueueService:
    """
    Service for managing the resolution queue.

    The resolution queue contains:
    - Low-confidence entity resolutions (< 0.8 confidence)
    - Ambiguous identifier matches
    - Potential duplicates requiring manual review

    Workflow:
    1. Silver transformation flags low-confidence matches
    2. Data ops reviews queued items
    3. Approved items are promoted to Gold (needs_review=FALSE)
    4. Rejected items remain quarantined or are deleted
    5. Merged items are combined with existing molecules
    """

    CONFIDENCE_THRESHOLD = 0.8

    def __init__(self, db_pool):
        """
        Initialize the resolution queue service.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool

    async def add_to_queue(
        self,
        original_identifier: str,
        identifier_type: str,
        confidence_score: float,
        molecule_id: Optional[str] = None,
        candidate_matches: Optional[List[Dict]] = None,
        source: Optional[str] = None
    ) -> str:
        """
        Add an item to the resolution queue.

        Args:
            original_identifier: The identifier that needs resolution
            identifier_type: Type of identifier (name, chembl_id, etc.)
            confidence_score: Confidence of the match (0-1)
            molecule_id: Tentative molecule ID if one was assigned
            candidate_matches: List of potential matches
            source: Source of the identifier

        Returns:
            Queue item ID
        """
        priority = self._calculate_priority(confidence_score)

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO silver.resolution_queue (
                    molecule_id,
                    original_identifier,
                    identifier_type,
                    confidence_score,
                    candidate_inchi_keys,
                    status
                ) VALUES ($1::uuid, $2, $3, $4, $5::jsonb, 'pending')
                RETURNING id::text
            """,
                molecule_id,
                original_identifier,
                identifier_type,
                confidence_score,
                json.dumps(candidate_matches or [])
            )

            return row['id']

    async def get_pending_items(
        self,
        priority: Optional[QueuePriority] = None,
        identifier_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[QueueItem]:
        """
        Get pending items from the queue.

        Args:
            priority: Filter by priority level
            identifier_type: Filter by identifier type
            limit: Maximum items to return
            offset: Pagination offset

        Returns:
            List of queue items
        """
        conditions = ["status = 'pending'"]
        params = []

        if priority:
            confidence_range = self._priority_to_confidence_range(priority)
            params.append(confidence_range[0])
            params.append(confidence_range[1])
            conditions.append(f"confidence_score >= ${len(params) - 1} AND confidence_score < ${len(params)}")

        if identifier_type:
            params.append(identifier_type)
            conditions.append(f"identifier_type = ${len(params)}")

        params.extend([limit, offset])

        query = f"""
            SELECT
                rq.id::text,
                rq.molecule_id::text,
                rq.original_identifier,
                rq.identifier_type,
                rq.confidence_score,
                rq.candidate_inchi_keys,
                rq.status,
                rq.created_at,
                m.canonical_name AS molecule_name
            FROM silver.resolution_queue rq
            LEFT JOIN silver.molecules m ON rq.molecule_id = m.id
            WHERE {' AND '.join(conditions)}
            ORDER BY rq.confidence_score DESC, rq.created_at ASC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

            items = []
            for row in rows:
                priority = self._calculate_priority(row['confidence_score'])
                candidates = row['candidate_inchi_keys']
                if isinstance(candidates, str):
                    candidates = json.loads(candidates)

                items.append(QueueItem(
                    id=row['id'],
                    molecule_id=row['molecule_id'],
                    original_identifier=row['original_identifier'],
                    identifier_type=row['identifier_type'],
                    confidence_score=float(row['confidence_score']),
                    candidate_matches=candidates or [],
                    status=row['status'],
                    priority=priority.value,
                    created_at=row['created_at']
                ))

            return items

    async def get_item(self, item_id: str) -> Optional[QueueItem]:
        """Get a single queue item by ID."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    rq.id::text,
                    rq.molecule_id::text,
                    rq.original_identifier,
                    rq.identifier_type,
                    rq.confidence_score,
                    rq.candidate_inchi_keys,
                    rq.status,
                    rq.created_at,
                    m.canonical_name AS molecule_name
                FROM silver.resolution_queue rq
                LEFT JOIN silver.molecules m ON rq.molecule_id = m.id
                WHERE rq.id = $1::uuid
            """, item_id)

            if not row:
                return None

            priority = self._calculate_priority(row['confidence_score'])
            candidates = row['candidate_inchi_keys']
            if isinstance(candidates, str):
                candidates = json.loads(candidates)

            return QueueItem(
                id=row['id'],
                molecule_id=row['molecule_id'],
                original_identifier=row['original_identifier'],
                identifier_type=row['identifier_type'],
                confidence_score=float(row['confidence_score']),
                candidate_matches=candidates or [],
                status=row['status'],
                priority=priority.value,
                created_at=row['created_at']
            )

    async def approve(
        self,
        item_id: str,
        reviewed_by: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Approve a resolution - promote molecule to Gold layer.

        Args:
            item_id: Queue item ID
            reviewed_by: Username of reviewer
            notes: Optional review notes

        Returns:
            True if successful
        """
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                # Get the queue item
                item = await conn.fetchrow("""
                    SELECT molecule_id FROM silver.resolution_queue
                    WHERE id = $1::uuid AND status = 'pending'
                """, item_id)

                if not item or not item['molecule_id']:
                    return False

                # Update the molecule to remove quarantine flag
                await conn.execute("""
                    UPDATE silver.molecules
                    SET needs_review = FALSE,
                        resolution_confidence = 1.0,
                        review_reason = NULL,
                        updated_at = NOW()
                    WHERE id = $1::uuid
                """, item['molecule_id'])

                # Update queue item
                await conn.execute("""
                    UPDATE silver.resolution_queue
                    SET status = 'approved',
                        resolution_action = 'approve',
                        reviewed_by = $2,
                        reviewed_at = NOW(),
                        review_notes = $3
                    WHERE id = $1::uuid
                """, item_id, reviewed_by, notes)

                return True

    async def reject(
        self,
        item_id: str,
        reviewed_by: str,
        notes: Optional[str] = None,
        delete_molecule: bool = False
    ) -> bool:
        """
        Reject a resolution - keep molecule quarantined or delete.

        Args:
            item_id: Queue item ID
            reviewed_by: Username of reviewer
            notes: Optional review notes
            delete_molecule: If True, delete the molecule entirely

        Returns:
            True if successful
        """
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                item = await conn.fetchrow("""
                    SELECT molecule_id FROM silver.resolution_queue
                    WHERE id = $1::uuid AND status = 'pending'
                """, item_id)

                if not item:
                    return False

                if delete_molecule and item['molecule_id']:
                    # Delete the molecule (cascades to related tables)
                    await conn.execute("""
                        DELETE FROM silver.molecules
                        WHERE id = $1::uuid
                    """, item['molecule_id'])

                # Update queue item
                await conn.execute("""
                    UPDATE silver.resolution_queue
                    SET status = 'rejected',
                        resolution_action = 'reject',
                        reviewed_by = $2,
                        reviewed_at = NOW(),
                        review_notes = $3
                    WHERE id = $1::uuid
                """, item_id, reviewed_by, notes)

                return True

    async def merge(
        self,
        item_id: str,
        target_molecule_id: str,
        reviewed_by: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Merge molecule with another existing molecule.

        Args:
            item_id: Queue item ID
            target_molecule_id: ID of molecule to merge into
            reviewed_by: Username of reviewer
            notes: Optional review notes

        Returns:
            True if successful
        """
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                item = await conn.fetchrow("""
                    SELECT molecule_id, original_identifier, identifier_type
                    FROM silver.resolution_queue
                    WHERE id = $1::uuid AND status = 'pending'
                """, item_id)

                if not item:
                    return False

                source_molecule_id = item['molecule_id']

                if source_molecule_id:
                    # Transfer all related records to target molecule
                    await self._transfer_relationships(
                        conn, source_molecule_id, target_molecule_id
                    )

                    # Delete the source molecule
                    await conn.execute("""
                        DELETE FROM silver.molecules
                        WHERE id = $1::uuid
                    """, source_molecule_id)

                # Add the original identifier as an alias on target
                await conn.execute("""
                    INSERT INTO silver.molecule_aliases (
                        molecule_id, alias_name, alias_type,
                        alias_name_normalized, source
                    ) VALUES ($1::uuid, $2, $3, LOWER($2), 'manual_resolution')
                    ON CONFLICT DO NOTHING
                """, target_molecule_id, item['original_identifier'], item['identifier_type'])

                # Update queue item
                await conn.execute("""
                    UPDATE silver.resolution_queue
                    SET status = 'merged',
                        resolution_action = 'merge',
                        merge_target_id = $2::uuid,
                        reviewed_by = $3,
                        reviewed_at = NOW(),
                        review_notes = $4
                    WHERE id = $1::uuid
                """, item_id, target_molecule_id, reviewed_by, notes)

                return True

    async def _transfer_relationships(
        self,
        conn,
        source_id: str,
        target_id: str
    ):
        """Transfer all relationships from source to target molecule."""
        # Transfer identifier mappings
        await conn.execute("""
            UPDATE silver.identifier_mappings
            SET molecule_id = $2::uuid
            WHERE molecule_id = $1::uuid
            ON CONFLICT DO NOTHING
        """, source_id, target_id)

        # Transfer aliases
        await conn.execute("""
            UPDATE silver.molecule_aliases
            SET molecule_id = $2::uuid
            WHERE molecule_id = $1::uuid
            ON CONFLICT DO NOTHING
        """, source_id, target_id)

        # Transfer clinical trials
        await conn.execute("""
            UPDATE silver.clinical_trials
            SET molecule_id = $2::uuid
            WHERE molecule_id = $1::uuid
        """, source_id, target_id)

        # Transfer adverse events
        await conn.execute("""
            UPDATE silver.adverse_events
            SET molecule_id = $2::uuid
            WHERE molecule_id = $1::uuid
            ON CONFLICT DO NOTHING
        """, source_id, target_id)

        # Transfer drug labels
        await conn.execute("""
            UPDATE silver.drug_labels
            SET molecule_id = $2::uuid
            WHERE molecule_id = $1::uuid
        """, source_id, target_id)

        # Transfer bioactivity
        await conn.execute("""
            UPDATE silver.bioactivity
            SET molecule_id = $2::uuid
            WHERE molecule_id = $1::uuid
            ON CONFLICT DO NOTHING
        """, source_id, target_id)

        # Transfer molecule-target relationships
        await conn.execute("""
            UPDATE silver.molecule_targets
            SET molecule_id = $2::uuid
            WHERE molecule_id = $1::uuid
            ON CONFLICT DO NOTHING
        """, source_id, target_id)

        # Transfer molecule-publication relationships
        await conn.execute("""
            UPDATE silver.molecule_publications
            SET molecule_id = $2::uuid
            WHERE molecule_id = $1::uuid
            ON CONFLICT DO NOTHING
        """, source_id, target_id)

        # Transfer patents
        await conn.execute("""
            UPDATE silver.patents
            SET molecule_id = $2::uuid
            WHERE molecule_id = $1::uuid
        """, source_id, target_id)

    async def get_stats(self) -> ResolutionStats:
        """Get statistics about the resolution queue."""
        async with self.db_pool.acquire() as conn:
            # Pending counts
            pending = await conn.fetchrow("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE confidence_score >= 0.5) AS high,
                    COUNT(*) FILTER (WHERE confidence_score >= 0.3 AND confidence_score < 0.5) AS medium,
                    COUNT(*) FILTER (WHERE confidence_score < 0.3) AS low
                FROM silver.resolution_queue
                WHERE status = 'pending'
            """)

            # Today's resolutions
            today = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE resolution_action = 'approve') AS approved,
                    COUNT(*) FILTER (WHERE resolution_action = 'reject') AS rejected,
                    COUNT(*) FILTER (WHERE resolution_action = 'merge') AS merged
                FROM silver.resolution_queue
                WHERE reviewed_at >= CURRENT_DATE
            """)

            # Average resolution time
            avg_time = await conn.fetchval("""
                SELECT AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at)) / 3600)
                FROM silver.resolution_queue
                WHERE reviewed_at IS NOT NULL
                  AND reviewed_at >= NOW() - INTERVAL '30 days'
            """)

            return ResolutionStats(
                pending_count=pending['total'],
                pending_by_priority={
                    'high': pending['high'],
                    'medium': pending['medium'],
                    'low': pending['low']
                },
                approved_today=today['approved'],
                rejected_today=today['rejected'],
                merged_today=today['merged'],
                avg_resolution_time_hours=float(avg_time) if avg_time else 0.0
            )

    async def find_potential_duplicates(
        self,
        molecule_id: str,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Find potential duplicate molecules for review.

        Args:
            molecule_id: ID of molecule to check
            threshold: Similarity threshold for name matching

        Returns:
            List of potential duplicate molecules
        """
        async with self.db_pool.acquire() as conn:
            # Get the molecule's name
            mol = await conn.fetchrow("""
                SELECT canonical_name, inchi_key FROM silver.molecules
                WHERE id = $1::uuid
            """, molecule_id)

            if not mol:
                return []

            # Find similar names using trigram similarity
            rows = await conn.fetch("""
                SELECT
                    m.id::text AS molecule_id,
                    m.canonical_name,
                    m.inchi_key,
                    m.data_sources,
                    similarity(lower(m.canonical_name), lower($1)) AS name_similarity
                FROM silver.molecules m
                WHERE m.id != $2::uuid
                  AND m.needs_review = FALSE
                  AND similarity(lower(m.canonical_name), lower($1)) > $3
                ORDER BY name_similarity DESC
                LIMIT 10
            """, mol['canonical_name'], molecule_id, threshold)

            return [dict(row) for row in rows]

    async def bulk_approve(
        self,
        item_ids: List[str],
        reviewed_by: str
    ) -> Dict[str, bool]:
        """
        Bulk approve multiple queue items.

        Args:
            item_ids: List of queue item IDs
            reviewed_by: Username of reviewer

        Returns:
            Dict mapping item IDs to success status
        """
        results = {}
        for item_id in item_ids:
            results[item_id] = await self.approve(item_id, reviewed_by)
        return results

    @staticmethod
    def _calculate_priority(confidence: float) -> QueuePriority:
        """Calculate priority based on confidence score."""
        if confidence >= 0.5:
            return QueuePriority.HIGH
        elif confidence >= 0.3:
            return QueuePriority.MEDIUM
        else:
            return QueuePriority.LOW

    @staticmethod
    def _priority_to_confidence_range(priority: QueuePriority) -> tuple:
        """Convert priority to confidence range."""
        if priority == QueuePriority.HIGH:
            return (0.5, 0.8)
        elif priority == QueuePriority.MEDIUM:
            return (0.3, 0.5)
        else:
            return (0.0, 0.3)
