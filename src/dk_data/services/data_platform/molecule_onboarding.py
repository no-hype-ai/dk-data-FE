"""
Molecule Onboarding Service

Orchestrates the full molecule onboarding workflow:
1. Accept identifier(s) from user
2. Resolve to canonical molecule
3. Fetch data from configured sources
4. Transform through medallion layers
5. Return enriched molecule profile

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
import logging

from ...models.application.onboarding import (
    OnboardingRequest,
    OnboardingResponse,
    OnboardingStatus,
    ResolutionResult,
    IdentifierInput,
    BulkOnboardingRequest,
    BulkOnboardingResponse,
)

logger = logging.getLogger(__name__)


class MoleculeOnboardingService:
    """
    Service for onboarding new molecules into the platform.

    Workflow:
    1. RESOLVING: Resolve identifiers to canonical InChI Key
    2. INGESTING: Fetch raw data from sources
    3. ENRICHING: Transform through Bronze → Silver → Gold
    4. COMPLETED: Return enriched profile
    """

    # Data sources in precedence order (complete list of all 16 sources)
    SOURCE_PRECEDENCE = [
        'drugbank',           # Highest quality curated data
        'chembl',             # High quality bioactivity data
        'rxnorm',             # FDA drug nomenclature standard
        'pubchem',            # Large compound database
        'pharmgkb',           # Pharmacogenomics annotations
        'kegg_drug',          # Pathway and target data
        'who_inn',            # International drug naming
        'clinicaltrials_gov', # Clinical trial data
        'openfda_labels',     # FDA drug labels
        'openfda_faers',      # FDA adverse events
        'dailymed',           # Drug labels
        'sider',              # Side effects database
        'bindingdb',          # Binding affinity data
        'tdc_admet',          # ADMET predictions
        'openalex',           # Publications
        'uniprot',            # Protein targets
        'websearch',          # Web search results
    ]

    # Identifier type to source mapping (complete mapping for all identifiers)
    IDENTIFIER_SOURCES = {
        'drugbank_id': 'drugbank',
        'chembl_id': 'chembl',
        'pubchem_cid': 'pubchem',
        'rxcui': 'rxnorm',
        'pharmgkb_id': 'pharmgkb',
        'kegg_id': 'kegg_drug',
        'inn_name': 'who_inn',
        'uniprot_id': 'uniprot',
        'nct_id': 'clinicaltrials_gov',
        'inchi_key': None,     # Can use any source
        'cas_number': 'pubchem',
        'unii': 'openfda_labels',
        'ndc': 'dailymed',
        'atc_code': 'rxnorm',
        'research_code': 'who_inn',
        'name': None,          # Fuzzy match needed
    }

    def __init__(
        self,
        db_pool,
        identifier_resolver,
        raw_ingestion_service,
        bronze_ingestion_service=None,
        silver_transformation_service=None,
        gold_aggregation_service=None,
        bulletproof_transformer=None,
    ):
        """
        Initialize the onboarding service.

        Args:
            db_pool: Database connection pool
            identifier_resolver: IdentifierResolver service
            raw_ingestion_service: RawIngestionService
            bronze_ingestion_service: BronzeIngestionService (optional if using transformer)
            silver_transformation_service: SilverTransformationService (optional if using transformer)
            gold_aggregation_service: GoldAggregationService (optional)
            bulletproof_transformer: BulletproofTransformer for dynamic transformations (preferred)
        """
        self.db_pool = db_pool
        self.resolver = identifier_resolver
        self.raw_service = raw_ingestion_service
        self.gold_service = gold_aggregation_service

        # Use BulletproofTransformer if provided (preferred - dynamic schema detection)
        self._transformer = bulletproof_transformer
        if self._transformer:
            # Use transformer methods directly
            self.bronze_service = None
            self.silver_service = self._transformer
            logger.info("MoleculeOnboardingService using BulletproofTransformer")
        else:
            # Fall back to separate services
            self.bronze_service = bronze_ingestion_service
            self.silver_service = silver_transformation_service
            logger.info("MoleculeOnboardingService using legacy services")

    async def onboard_molecule(
        self,
        request: OnboardingRequest,
        user_id: UUID
    ) -> OnboardingResponse:
        """
        Onboard a single molecule.

        Args:
            request: Onboarding request with identifiers
            user_id: ID of requesting user

        Returns:
            OnboardingResponse with status and result
        """
        request_id = uuid4()
        created_at = datetime.utcnow()

        # Log the onboarding request
        await self._log_audit(
            request_id=request_id,
            user_id=user_id,
            action='onboard_started',
            status=OnboardingStatus.PENDING,
            details={'identifiers': [i.model_dump() for i in request.identifiers]}
        )

        try:
            # Step 1: Resolve identifiers
            resolution = await self._resolve_identifiers(request.identifiers)

            if resolution.molecule_id is None:
                # No matches found - create new molecule in mol_silver
                resolution = await self._create_new_molecule(request.identifiers)

            molecule_id = resolution.molecule_id

            # Step 2: Ingest data from sources
            if not request.skip_enrichment:
                sources_fetched = await self._ingest_from_sources(
                    molecule_id=molecule_id,
                    inchi_key=resolution.inchi_key,
                    requested_sources=request.requested_sources
                )
            else:
                sources_fetched = []

            # Step 3: Get canonical name
            canonical_name = await self._get_canonical_name(molecule_id)

            await self._log_audit(
                request_id=request_id,
                user_id=user_id,
                action='onboard_completed',
                status=OnboardingStatus.COMPLETED,
                details={
                    'molecule_id': str(molecule_id),
                    'sources_fetched': sources_fetched
                }
            )

            return OnboardingResponse(
                request_id=request_id,
                status=OnboardingStatus.COMPLETED,
                resolution_result=resolution,
                molecule_id=molecule_id,
                canonical_name=canonical_name,
                data_sources_fetched=sources_fetched,
                enrichment_complete=not request.skip_enrichment,
                created_at=created_at,
                completed_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"Onboarding failed for request {request_id}: {e}")
            await self._log_audit(
                request_id=request_id,
                user_id=user_id,
                action='onboard_failed',
                status=OnboardingStatus.FAILED,
                error_message=str(e)
            )
            return OnboardingResponse(
                request_id=request_id,
                status=OnboardingStatus.FAILED,
                error_message=str(e),
                created_at=created_at,
            )

    async def onboard_bulk(
        self,
        request: BulkOnboardingRequest,
        user_id: UUID
    ) -> BulkOnboardingResponse:
        """
        Onboard multiple molecules.

        Args:
            request: Bulk onboarding request
            user_id: ID of requesting user

        Returns:
            BulkOnboardingResponse with results
        """
        batch_id = uuid4()
        created_at = datetime.utcnow()
        results = []
        errors = []

        for idx, mol_request in enumerate(request.molecules):
            try:
                result = await self.onboard_molecule(mol_request, user_id)
                results.append(result)
            except Exception as e:
                if not request.continue_on_error:
                    raise
                errors.append({
                    'index': idx,
                    'identifiers': [i.model_dump() for i in mol_request.identifiers],
                    'error': str(e)
                })

        successful = sum(1 for r in results if r.status == OnboardingStatus.COMPLETED)
        failed = sum(1 for r in results if r.status == OnboardingStatus.FAILED) + len(errors)
        pending = sum(1 for r in results if r.status in [
            OnboardingStatus.PENDING,
            OnboardingStatus.NEEDS_REVIEW
        ])

        return BulkOnboardingResponse(
            batch_id=batch_id,
            total_requested=len(request.molecules),
            successful=successful,
            failed=failed,
            pending=pending,
            results=results,
            errors=errors,
            created_at=created_at,
        )

    async def _resolve_identifiers(
        self,
        identifiers: List[IdentifierInput]
    ) -> ResolutionResult:
        """Resolve identifiers to canonical molecule."""
        matched = {}
        unmatched = []
        potential_matches = []
        best_molecule_id = None
        best_inchi_key = None
        best_confidence = 0.0

        for ident in identifiers:
            # Convert string type to IdentifierType enum if needed
            from .identifier_resolver import IdentifierType
            id_type = None
            try:
                id_type = IdentifierType(ident.identifier_type)
            except (ValueError, KeyError):
                pass  # Let resolver auto-detect
            result = await self.resolver.resolve(
                identifier=ident.identifier_value,
                identifier_type=id_type,
            )

            if result.molecule_id is not None:
                matched[ident.identifier_type] = ident.identifier_value
                if result.confidence > best_confidence:
                    best_confidence = result.confidence
                    best_molecule_id = result.molecule_id
                    best_inchi_key = result.inchi_key
            else:
                unmatched.append(f"{ident.identifier_type}:{ident.identifier_value}")

        return ResolutionResult(
            resolved=best_molecule_id is not None,
            molecule_id=UUID(str(best_molecule_id)) if best_molecule_id else None,
            inchi_key=best_inchi_key,
            confidence=best_confidence,
            matched_identifiers=matched,
            unmatched_identifiers=unmatched,
            potential_matches=potential_matches[:10],
        )

    async def _create_new_molecule(
        self,
        identifiers: List[IdentifierInput]
    ) -> ResolutionResult:
        """Create a new molecule from identifiers."""
        # Try to fetch from external sources to get InChI Key
        for ident in identifiers:
            source = self.IDENTIFIER_SOURCES.get(ident.identifier_type)
            if source:
                # Fetch from source to get canonical structure
                raw_data = await self.raw_service.fetch_single(
                    source=source,
                    identifier=ident.identifier_value
                )
                if raw_data and raw_data.get('inchi_key'):
                    # Create molecule in Silver layer
                    molecule_id = await self.silver_service.create_molecule(
                        inchi_key=raw_data['inchi_key'],
                        canonical_name=raw_data.get('name', 'Unknown'),
                        source=source
                    )
                    return ResolutionResult(
                        resolved=True,
                        molecule_id=UUID(str(molecule_id)) if not isinstance(molecule_id, UUID) else molecule_id,
                        inchi_key=raw_data['inchi_key'],
                        confidence=0.9,
                        matched_identifiers={ident.identifier_type: ident.identifier_value},
                    )

        # If no InChI Key found, create placeholder in mol_silver.molecules
        molecule_id = uuid4()
        name = identifiers[0].identifier_value
        placeholder_inchi = f"{name.upper()}-PLACEHOLDER-KEY"
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO mol_silver.molecules
                (molecule_id, inchi_key, canonical_name, needs_review, review_reason, resolution_confidence)
                VALUES ($1, $2, $3, TRUE, 'auto-onboarded', 0.5)
                ON CONFLICT (molecule_id) DO NOTHING
            """, molecule_id, placeholder_inchi, name.lower())

        return ResolutionResult(
            resolved=True,
            molecule_id=molecule_id,
            confidence=0.5,
            matched_identifiers={identifiers[0].identifier_type: identifiers[0].identifier_value},
        )

    async def _ingest_from_sources(
        self,
        molecule_id: UUID,
        inchi_key: Optional[str],
        requested_sources: Optional[List[str]] = None
    ) -> List[str]:
        """Ingest data from configured sources."""
        sources_to_fetch = requested_sources or self.SOURCE_PRECEDENCE
        fetched = []

        for source in sources_to_fetch:
            try:
                # Fetch raw data
                success = await self.raw_service.fetch_for_molecule(
                    molecule_id=molecule_id,
                    source=source,
                    inchi_key=inchi_key
                )
                if success:
                    fetched.append(source)

                    # Transform through layers
                    await self.bronze_service.process_source(source, molecule_id)
                    await self.silver_service.transform_source(source, molecule_id)
            except Exception as e:
                logger.warning(f"Failed to fetch from {source}: {e}")

        # Regenerate Gold layer
        if fetched:
            await self.gold_service.aggregate_molecule(molecule_id)

        return fetched

    async def _get_canonical_name(self, molecule_id: UUID) -> Optional[str]:
        """Get canonical name for molecule."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT canonical_name FROM silver.molecules
                WHERE id = $1
            """, molecule_id)
            return row['canonical_name'] if row else None

    async def _log_audit(
        self,
        request_id: UUID,
        user_id: UUID,
        action: str,
        status: OnboardingStatus,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ):
        """Log audit entry for onboarding action."""
        import json
        # asyncpg requires jsonb values as JSON strings, not Python dicts
        details_json = json.dumps(details) if details is not None else None
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO application.onboarding_audit_log
                (id, request_id, user_id, action, status, details, error_message)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            """, uuid4(), request_id, user_id, action, status.value,
            details_json, error_message)

    async def get_onboarding_status(
        self,
        request_id: UUID
    ) -> Optional[OnboardingResponse]:
        """Get status of an onboarding request."""
        async with self.db_pool.acquire() as conn:
            logs = await conn.fetch("""
                SELECT action, status, details, error_message, created_at
                FROM application.onboarding_audit_log
                WHERE request_id = $1
                ORDER BY created_at DESC
            """, request_id)

            if not logs:
                return None

            latest = logs[0]
            return OnboardingResponse(
                request_id=request_id,
                status=OnboardingStatus(latest['status']),
                error_message=latest['error_message'],
                created_at=logs[-1]['created_at'],
                completed_at=latest['created_at'] if latest['status'] in ['completed', 'failed'] else None,
            )
