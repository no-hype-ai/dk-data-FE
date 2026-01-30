"""
Identifier Linker Service

Automatically links molecule identifiers across all 16 data sources.
Runs as part of the daily/weekly pipeline to maintain cross-references.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from enum import Enum

from .identifier_resolver import IdentifierResolver, IdentifierType
from .external_resolver import ExternalResolverService

logger = logging.getLogger(__name__)


class LinkingPriority(Enum):
    """Priority levels for linking tasks."""
    HIGH = "high"        # New molecules, critical sources
    MEDIUM = "medium"    # Periodic refresh
    LOW = "low"          # Background enrichment


@dataclass
class LinkingResult:
    """Result of a linking operation."""
    molecules_processed: int = 0
    identifiers_linked: int = 0
    new_cross_refs_found: int = 0
    conflicts_detected: int = 0
    errors: List[str] = field(default_factory=list)
    sources_checked: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class IdentifierLink:
    """A cross-reference link between identifiers."""
    source_type: str       # e.g., 'chembl_id'
    source_value: str      # e.g., 'CHEMBL25'
    target_type: str       # e.g., 'drugbank_id'
    target_value: str      # e.g., 'DB00945'
    confidence: float      # 0.0 - 1.0
    via_source: str        # e.g., 'unichem', 'pubchem'


class IdentifierLinkerService:
    """
    Service for automatically linking identifiers across all data sources.

    Workflow:
    1. Find molecules with incomplete identifier coverage
    2. Query external APIs to find cross-references
    3. Validate and store new identifier mappings
    4. Handle conflicts when sources disagree
    """

    # Complete mapping of identifier types to their sources
    IDENTIFIER_SOURCES = {
        IdentifierType.DRUGBANK_ID: 'drugbank',
        IdentifierType.CHEMBL_ID: 'chembl',
        IdentifierType.RXCUI: 'rxnorm',
        IdentifierType.PUBCHEM_CID: 'pubchem',
        IdentifierType.PUBCHEM_SID: 'pubchem',
        IdentifierType.PHARMGKB_ID: 'pharmgkb',
        IdentifierType.KEGG_ID: 'kegg_drug',
        IdentifierType.ATC_CODE: 'who_inn',
        IdentifierType.UNIPROT_ID: 'uniprot',
        IdentifierType.NCT_ID: 'clinicaltrials',
        IdentifierType.NDC_CODE: 'dailymed',
        IdentifierType.UNII: 'openfda_labels',
        IdentifierType.CAS_NUMBER: 'pubchem',
        IdentifierType.PDB_ID: 'uniprot',
        IdentifierType.STITCH_ID: 'sider',
        IdentifierType.BINDINGDB_ID: 'bindingdb',
        IdentifierType.EMA_NUMBER: 'ema',
        IdentifierType.DAILYMED_SET_ID: 'dailymed',
        IdentifierType.RESEARCH_CODE: 'who_inn',
    }

    # Sources to check for cross-references (in priority order)
    CROSS_REF_SOURCES = [
        'chembl',
        'drugbank',
        'pubchem',
        'rxnorm',
        'pharmgkb',
        'kegg',
        'bindingdb',
    ]

    def __init__(
        self,
        db_pool,
        identifier_resolver: Optional[IdentifierResolver] = None,
        external_resolver: Optional[ExternalResolverService] = None,
    ):
        """Initialize the identifier linker service."""
        self.db_pool = db_pool
        self.resolver = identifier_resolver or IdentifierResolver(db_pool)
        self.external = external_resolver or ExternalResolverService()

    async def close(self):
        """Clean up resources."""
        await self.external.close()

    async def run_daily_linking(self, batch_size: int = 100) -> LinkingResult:
        """
        Run daily identifier linking job.

        Focuses on:
        1. New molecules added today
        2. Molecules with missing critical identifiers (DrugBank, ChEMBL)
        """
        start_time = datetime.utcnow()
        result = LinkingResult()

        try:
            # Find molecules needing linking
            molecules = await self._find_molecules_needing_links(
                priority=LinkingPriority.HIGH,
                limit=batch_size
            )

            for molecule in molecules:
                try:
                    links_found = await self._link_molecule_identifiers(molecule)
                    result.molecules_processed += 1
                    result.identifiers_linked += links_found
                except Exception as e:
                    result.errors.append(f"Molecule {molecule['id']}: {str(e)}")
                    logger.error(f"Error linking molecule {molecule['id']}: {e}")

            result.sources_checked = self.CROSS_REF_SOURCES[:4]  # Top sources for daily

        except Exception as e:
            result.errors.append(f"Daily linking failed: {str(e)}")
            logger.error(f"Daily linking job failed: {e}")

        result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
        return result

    async def run_weekly_linking(self, batch_size: int = 500) -> LinkingResult:
        """
        Run weekly identifier linking job.

        More comprehensive than daily:
        1. All molecules with < 5 identifier types
        2. Refresh cross-references for existing molecules
        3. Check all external sources
        """
        start_time = datetime.utcnow()
        result = LinkingResult()

        try:
            # Find molecules with incomplete coverage
            molecules = await self._find_molecules_needing_links(
                priority=LinkingPriority.MEDIUM,
                limit=batch_size
            )

            for molecule in molecules:
                try:
                    links_found = await self._link_molecule_identifiers(
                        molecule,
                        check_all_sources=True
                    )
                    result.molecules_processed += 1
                    result.identifiers_linked += links_found
                except Exception as e:
                    result.errors.append(f"Molecule {molecule['id']}: {str(e)}")

            result.sources_checked = self.CROSS_REF_SOURCES

        except Exception as e:
            result.errors.append(f"Weekly linking failed: {str(e)}")
            logger.error(f"Weekly linking job failed: {e}")

        result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
        return result

    async def link_single_molecule(
        self,
        molecule_id: str,
        force_refresh: bool = False
    ) -> LinkingResult:
        """
        Link identifiers for a single molecule.

        Args:
            molecule_id: UUID of the molecule
            force_refresh: If True, re-check all sources even if mappings exist
        """
        result = LinkingResult()
        start_time = datetime.utcnow()

        try:
            async with self.db_pool.acquire() as conn:
                molecule = await conn.fetchrow("""
                    SELECT id, inchi_key, canonical_name
                    FROM silver.molecules
                    WHERE id = $1::uuid
                """, molecule_id)

                if not molecule:
                    result.errors.append(f"Molecule {molecule_id} not found")
                    return result

                links_found = await self._link_molecule_identifiers(
                    dict(molecule),
                    check_all_sources=True,
                    force_refresh=force_refresh
                )

                result.molecules_processed = 1
                result.identifiers_linked = links_found
                result.sources_checked = self.CROSS_REF_SOURCES

        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"Error linking molecule {molecule_id}: {e}")

        result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
        return result

    async def _find_molecules_needing_links(
        self,
        priority: LinkingPriority,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Find molecules that need identifier linking."""
        async with self.db_pool.acquire() as conn:
            if priority == LinkingPriority.HIGH:
                # New molecules or missing critical identifiers
                return await conn.fetch("""
                    SELECT m.id, m.inchi_key, m.canonical_name
                    FROM silver.molecules m
                    LEFT JOIN (
                        SELECT molecule_id, COUNT(DISTINCT identifier_type) as id_count
                        FROM silver.identifier_mappings
                        WHERE identifier_type IN ('chembl_id', 'drugbank_id', 'pubchem_cid', 'rxcui')
                        GROUP BY molecule_id
                    ) im ON m.id = im.molecule_id
                    WHERE m.inchi_key IS NOT NULL
                      AND (im.id_count IS NULL OR im.id_count < 3)
                      AND (m.created_at > NOW() - INTERVAL '1 day'
                           OR m.needs_review = FALSE)
                    ORDER BY m.created_at DESC
                    LIMIT $1
                """, limit)

            elif priority == LinkingPriority.MEDIUM:
                # Molecules with fewer than 5 identifier types
                return await conn.fetch("""
                    SELECT m.id, m.inchi_key, m.canonical_name
                    FROM silver.molecules m
                    LEFT JOIN (
                        SELECT molecule_id, COUNT(DISTINCT identifier_type) as id_count
                        FROM silver.identifier_mappings
                        GROUP BY molecule_id
                    ) im ON m.id = im.molecule_id
                    WHERE m.inchi_key IS NOT NULL
                      AND m.needs_review = FALSE
                      AND (im.id_count IS NULL OR im.id_count < 5)
                    ORDER BY im.id_count ASC NULLS FIRST, m.updated_at ASC
                    LIMIT $1
                """, limit)

            else:  # LOW priority - background enrichment
                return await conn.fetch("""
                    SELECT m.id, m.inchi_key, m.canonical_name
                    FROM silver.molecules m
                    WHERE m.inchi_key IS NOT NULL
                      AND m.needs_review = FALSE
                      AND m.updated_at < NOW() - INTERVAL '30 days'
                    ORDER BY m.updated_at ASC
                    LIMIT $1
                """, limit)

    async def _link_molecule_identifiers(
        self,
        molecule: Dict[str, Any],
        check_all_sources: bool = False,
        force_refresh: bool = False
    ) -> int:
        """
        Link identifiers for a single molecule.

        Returns number of new identifiers linked.
        """
        molecule_id = str(molecule['id'])
        inchi_key = molecule.get('inchi_key')
        name = molecule.get('canonical_name')
        links_added = 0

        if not inchi_key and not name:
            return 0

        async with self.db_pool.acquire() as conn:
            # Get existing identifiers
            existing = await conn.fetch("""
                SELECT identifier_type, identifier_value
                FROM silver.identifier_mappings
                WHERE molecule_id = $1::uuid
            """, molecule_id)

            existing_types = {row['identifier_type'] for row in existing}
            existing_values = {row['identifier_value'] for row in existing}

            # Determine which sources to check
            sources_to_check = self.CROSS_REF_SOURCES if check_all_sources else self.CROSS_REF_SOURCES[:4]

            # Get cross-references via UniChem if we have InChI Key
            if inchi_key:
                try:
                    cross_refs = await self.external.unichem.get_cross_references(inchi_key)

                    for source, ids in cross_refs.items():
                        id_type = self._source_to_identifier_type(source)
                        if id_type and (force_refresh or id_type not in existing_types):
                            for id_value in ids:
                                if id_value not in existing_values:
                                    await self._add_identifier_mapping(
                                        conn, molecule_id, id_type, id_value,
                                        source='unichem', confidence=0.95
                                    )
                                    links_added += 1
                except Exception as e:
                    logger.warning(f"UniChem cross-ref failed for {inchi_key}: {e}")

            # Query individual sources for additional identifiers
            for source in sources_to_check:
                try:
                    new_links = await self._query_source_for_links(
                        conn, molecule_id, source, inchi_key, name,
                        existing_types, existing_values, force_refresh
                    )
                    links_added += new_links
                except Exception as e:
                    logger.warning(f"Source {source} query failed: {e}")

            # Update molecule's data_sources list
            if links_added > 0:
                await conn.execute("""
                    UPDATE silver.molecules
                    SET updated_at = NOW()
                    WHERE id = $1::uuid
                """, molecule_id)

        return links_added

    async def _query_source_for_links(
        self,
        conn,
        molecule_id: str,
        source: str,
        inchi_key: Optional[str],
        name: Optional[str],
        existing_types: Set[str],
        existing_values: Set[str],
        force_refresh: bool
    ) -> int:
        """Query a specific source for identifier cross-references."""
        links_added = 0

        # Resolve via external API
        result = None
        if source == 'chembl' and inchi_key:
            result = await self.external.chembl.resolve_by_inchi_key(inchi_key)
        elif source == 'pubchem' and inchi_key:
            result = await self.external.pubchem.resolve_by_inchi_key(inchi_key)
        elif source == 'rxnorm' and name:
            result = await self.external.rxnorm.resolve_by_name(name)
        elif source == 'pharmgkb' and name:
            results = await self.external.pharmgkb.search_by_name(name, limit=1)
            result = results[0] if results else None
        elif source == 'kegg' and name:
            results = await self.external.kegg.search_by_name(name)
            result = results[0] if results else None

        if result and result.success and result.identifiers:
            for id_type, id_value in result.identifiers.items():
                if id_value and (force_refresh or id_type not in existing_types):
                    if id_value not in existing_values:
                        await self._add_identifier_mapping(
                            conn, molecule_id, id_type, id_value,
                            source=source, confidence=0.9
                        )
                        links_added += 1

        return links_added

    async def _add_identifier_mapping(
        self,
        conn,
        molecule_id: str,
        identifier_type: str,
        identifier_value: str,
        source: str,
        confidence: float = 0.9
    ):
        """Add an identifier mapping to the database."""
        await conn.execute("""
            INSERT INTO silver.identifier_mappings (
                molecule_id, identifier_type, identifier_value,
                source, confidence, is_primary
            ) VALUES ($1::uuid, $2, $3, $4, $5, FALSE)
            ON CONFLICT (molecule_id, identifier_type, identifier_value) DO UPDATE SET
                confidence = GREATEST(silver.identifier_mappings.confidence, EXCLUDED.confidence),
                updated_at = NOW()
        """, molecule_id, identifier_type, identifier_value, source, confidence)

    def _source_to_identifier_type(self, source: str) -> Optional[str]:
        """Convert UniChem source name to identifier type."""
        mapping = {
            'chembl': 'chembl_id',
            'drugbank': 'drugbank_id',
            'pubchem': 'pubchem_cid',
            'pubchem_sid': 'pubchem_sid',
            'kegg': 'kegg_id',
            'bindingdb': 'bindingdb_id',
            'pharmgkb': 'pharmgkb_id',
            'pdb': 'pdb_id',
            'chebi': 'chebi_id',
        }
        return mapping.get(source.lower())

    async def get_linking_stats(self) -> Dict[str, Any]:
        """Get statistics about identifier linking coverage."""
        async with self.db_pool.acquire() as conn:
            stats = {}

            # Total molecules
            total = await conn.fetchval("SELECT COUNT(*) FROM silver.molecules")
            stats['total_molecules'] = total

            # Molecules by identifier count
            coverage = await conn.fetch("""
                SELECT
                    COALESCE(id_count, 0) as identifier_count,
                    COUNT(*) as molecule_count
                FROM silver.molecules m
                LEFT JOIN (
                    SELECT molecule_id, COUNT(DISTINCT identifier_type) as id_count
                    FROM silver.identifier_mappings
                    GROUP BY molecule_id
                ) im ON m.id = im.molecule_id
                GROUP BY COALESCE(id_count, 0)
                ORDER BY identifier_count
            """)
            stats['coverage_distribution'] = {
                row['identifier_count']: row['molecule_count'] for row in coverage
            }

            # Identifier type coverage
            type_coverage = await conn.fetch("""
                SELECT identifier_type, COUNT(DISTINCT molecule_id) as molecule_count
                FROM silver.identifier_mappings
                GROUP BY identifier_type
                ORDER BY molecule_count DESC
            """)
            stats['identifier_type_coverage'] = {
                row['identifier_type']: row['molecule_count'] for row in type_coverage
            }

            # Molecules needing links (< 3 critical identifiers)
            needs_links = await conn.fetchval("""
                SELECT COUNT(*)
                FROM silver.molecules m
                LEFT JOIN (
                    SELECT molecule_id, COUNT(DISTINCT identifier_type) as id_count
                    FROM silver.identifier_mappings
                    WHERE identifier_type IN ('chembl_id', 'drugbank_id', 'pubchem_cid', 'rxcui')
                    GROUP BY molecule_id
                ) im ON m.id = im.molecule_id
                WHERE m.inchi_key IS NOT NULL
                  AND (im.id_count IS NULL OR im.id_count < 3)
            """)
            stats['molecules_needing_links'] = needs_links

            return stats


# Factory function for creating linker with all dependencies
async def create_identifier_linker(db_pool) -> IdentifierLinkerService:
    """Create an identifier linker service with all dependencies."""
    from .identifier_resolver import IdentifierResolver
    from .fuzzy_matcher import FuzzyMatcher

    fuzzy_matcher = FuzzyMatcher(db_pool)
    resolver = IdentifierResolver(db_pool, fuzzy_matcher=fuzzy_matcher)
    external = ExternalResolverService()

    return IdentifierLinkerService(
        db_pool=db_pool,
        identifier_resolver=resolver,
        external_resolver=external
    )
