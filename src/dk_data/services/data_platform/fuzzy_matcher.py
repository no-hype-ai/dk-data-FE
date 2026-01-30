"""
Fuzzy Matcher Service

Implements fuzzy molecule name matching using PostgreSQL pg_trgm extension.
Uses Levenshtein + trigram similarity for typo-tolerant matching.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class FuzzyMatch:
    """Result of fuzzy matching."""
    molecule_id: str
    inchi_key: Optional[str]
    canonical_name: str
    matched_alias: Optional[str]
    similarity: float
    match_type: str  # canonical_name, alias


class FuzzyMatcher:
    """
    Fuzzy molecule name matcher using PostgreSQL pg_trgm extension.

    Uses trigram similarity for efficient fuzzy matching:
    - Handles typos well (asprin → aspirin)
    - Good balance of speed and accuracy
    - Native PostgreSQL - no external service needed
    - Configurable similarity threshold (default 0.3)
    """

    DEFAULT_THRESHOLD = 0.3
    DEFAULT_LIMIT = 20

    def __init__(self, db_pool, threshold: float = DEFAULT_THRESHOLD):
        """
        Initialize the fuzzy matcher.

        Args:
            db_pool: Database connection pool
            threshold: Minimum similarity score (0-1)
        """
        self.db_pool = db_pool
        self.threshold = threshold

    @staticmethod
    def normalize_name(name: str) -> str:
        """
        Normalize a molecule name for matching.

        - Convert to lowercase
        - Remove special characters
        - Collapse whitespace
        """
        if not name:
            return ""

        # Lowercase
        normalized = name.lower()

        # Remove common prefixes/suffixes that don't help matching
        prefixes = ['(+)-', '(-)-', '(±)-', 'd-', 'l-', 'dl-']
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]

        # Keep alphanumeric and spaces only
        normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)

        # Collapse whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    async def search(
        self,
        query: str,
        threshold: Optional[float] = None,
        limit: int = DEFAULT_LIMIT
    ) -> List[Dict[str, Any]]:
        """
        Search for molecules by fuzzy name matching.

        Args:
            query: Search query (molecule name)
            threshold: Minimum similarity score (default: class threshold)
            limit: Maximum results to return

        Returns:
            List of matching molecules with similarity scores
        """
        if not query or len(query) < 2:
            return []

        threshold = threshold if threshold is not None else self.threshold
        normalized_query = self.normalize_name(query)

        async with self.db_pool.acquire() as conn:
            # Search both canonical names and aliases
            rows = await conn.fetch("""
                WITH name_matches AS (
                    -- Match against canonical names
                    SELECT
                        m.id AS molecule_id,
                        m.inchi_key,
                        m.canonical_name,
                        NULL::VARCHAR AS matched_alias,
                        similarity(lower(m.canonical_name), $1) AS sim,
                        'canonical_name' AS match_type
                    FROM silver.molecules m
                    WHERE m.needs_review = FALSE
                      AND similarity(lower(m.canonical_name), $1) > $2

                    UNION ALL

                    -- Match against aliases
                    SELECT
                        m.id AS molecule_id,
                        m.inchi_key,
                        m.canonical_name,
                        ma.alias_name AS matched_alias,
                        similarity(ma.alias_name_normalized, $1) AS sim,
                        'alias' AS match_type
                    FROM silver.molecules m
                    JOIN silver.molecule_aliases ma ON m.id = ma.molecule_id
                    WHERE m.needs_review = FALSE
                      AND similarity(ma.alias_name_normalized, $1) > $2
                )
                SELECT DISTINCT ON (molecule_id)
                    molecule_id,
                    inchi_key,
                    canonical_name,
                    matched_alias,
                    sim AS similarity,
                    match_type
                FROM name_matches
                ORDER BY molecule_id, sim DESC
                LIMIT $3
            """, normalized_query, threshold, limit)

            results = []
            for row in rows:
                results.append({
                    'molecule_id': str(row['molecule_id']),
                    'inchi_key': row['inchi_key'],
                    'canonical_name': row['canonical_name'],
                    'matched_alias': row['matched_alias'],
                    'similarity': float(row['similarity']),
                    'match_type': row['match_type'],
                })

            # Sort by similarity descending
            results.sort(key=lambda x: x['similarity'], reverse=True)

            return results[:limit]

    async def find_exact_match(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Find an exact name match (case-insensitive).

        Args:
            name: Molecule name to match

        Returns:
            Matching molecule or None
        """
        if not name:
            return None

        normalized_name = self.normalize_name(name)

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    m.id AS molecule_id,
                    m.inchi_key,
                    m.canonical_name
                FROM silver.molecules m
                WHERE m.needs_review = FALSE
                  AND lower(m.canonical_name) = $1

                UNION ALL

                SELECT
                    m.id AS molecule_id,
                    m.inchi_key,
                    m.canonical_name
                FROM silver.molecules m
                JOIN silver.molecule_aliases ma ON m.id = ma.molecule_id
                WHERE m.needs_review = FALSE
                  AND ma.alias_name_normalized = $1

                LIMIT 1
            """, normalized_name)

            if row:
                return {
                    'molecule_id': str(row['molecule_id']),
                    'inchi_key': row['inchi_key'],
                    'canonical_name': row['canonical_name'],
                    'similarity': 1.0,
                    'match_type': 'exact',
                }

            return None

    async def suggest_completions(
        self,
        prefix: str,
        limit: int = 10
    ) -> List[str]:
        """
        Get name suggestions for autocomplete.

        Args:
            prefix: Start of molecule name
            limit: Maximum suggestions

        Returns:
            List of matching molecule names
        """
        if not prefix or len(prefix) < 2:
            return []

        normalized_prefix = self.normalize_name(prefix)

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT canonical_name
                FROM silver.molecules
                WHERE needs_review = FALSE
                  AND lower(canonical_name) LIKE $1 || '%'
                ORDER BY length(canonical_name), canonical_name
                LIMIT $2
            """, normalized_prefix, limit)

            return [row['canonical_name'] for row in rows]

    async def get_similar_molecules(
        self,
        molecule_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find molecules with similar names to a given molecule.

        Useful for finding potential duplicates or related compounds.

        Args:
            molecule_id: ID of the molecule to find similars for
            limit: Maximum results

        Returns:
            List of similar molecules
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                WITH target AS (
                    SELECT canonical_name
                    FROM silver.molecules
                    WHERE id = $1::uuid
                )
                SELECT
                    m.id AS molecule_id,
                    m.inchi_key,
                    m.canonical_name,
                    similarity(lower(m.canonical_name), lower(t.canonical_name)) AS sim
                FROM silver.molecules m, target t
                WHERE m.id != $1::uuid
                  AND m.needs_review = FALSE
                  AND similarity(lower(m.canonical_name), lower(t.canonical_name)) > $2
                ORDER BY sim DESC
                LIMIT $3
            """, molecule_id, self.threshold, limit)

            return [
                {
                    'molecule_id': str(row['molecule_id']),
                    'inchi_key': row['inchi_key'],
                    'canonical_name': row['canonical_name'],
                    'similarity': float(row['sim']),
                }
                for row in rows
            ]
