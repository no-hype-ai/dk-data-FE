"""
Silver Transformation Service

Transforms Bronze layer data into Silver normalized entities.
Implements entity resolution using InChI Key as master identifier.
Handles cross-source deduplication and data merging.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import json
from typing import Dict, Optional, List
from dataclasses import dataclass
import logging

from .identifier_resolver import IdentifierResolver, IdentifierType
from .fuzzy_matcher import FuzzyMatcher

logger = logging.getLogger(__name__)


# Source precedence for conflicting data (lower = higher priority)
# Complete list of all 16 data sources
SOURCE_PRECEDENCE = {
    'drugbank': 1,          # Highest quality curated data
    'chembl': 2,            # High quality bioactivity data
    'rxnorm': 3,            # FDA drug nomenclature standard
    'pubchem': 4,           # Large compound database
    'pharmgkb': 5,          # Pharmacogenomics annotations
    'kegg_drug': 6,         # Pathway and target data
    'who_inn': 7,           # International drug naming
    'clinicaltrials': 8,    # Clinical trial data
    'openfda_labels': 9,    # FDA drug labels
    'openfda_faers': 10,    # FDA adverse events
    'dailymed': 11,         # Drug labels
    'sider': 12,            # Side effects
    'bindingdb': 13,        # Binding affinity data
    'tdc_admet': 14,        # ADMET predictions
    'openalex': 15,         # Publications
    'uniprot': 16,          # Protein targets
    'websearch': 17,        # Web search results
}


@dataclass
class TransformationResult:
    """Result of a transformation operation."""
    records_processed: int
    molecules_created: int
    molecules_updated: int
    records_quarantined: int
    errors: List[str]


class SilverTransformationService:
    """
    Service for transforming Bronze data into Silver normalized entities.

    Key responsibilities:
    - Entity resolution (molecule identity)
    - Cross-source deduplication
    - Data merging with source precedence
    - Quarantine for low-confidence records
    """

    CONFIDENCE_THRESHOLD = 0.8  # Below this, records are quarantined

    def __init__(self, db_pool, identifier_resolver: Optional[IdentifierResolver] = None):
        """
        Initialize the silver transformation service.

        Args:
            db_pool: Database connection pool
            identifier_resolver: Optional pre-configured resolver
        """
        self.db_pool = db_pool
        self.fuzzy_matcher = FuzzyMatcher(db_pool)
        self.resolver = identifier_resolver or IdentifierResolver(
            db_pool, fuzzy_matcher=self.fuzzy_matcher
        )

    async def process_chembl_molecules(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze ChEMBL molecules to Silver."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            # Get unprocessed Bronze records (use mol_bronze.chembl table with correct column names)
            bronze_records = await conn.fetch("""
                SELECT id, molecule_chembl_id, pref_name, molecule_type, max_phase,
                       molecular_formula, molecular_weight, canonical_smiles,
                       standard_inchi as inchi, standard_inchi_key as inchi_key,
                       first_approval, indication_class
                FROM mol_bronze.chembl
                WHERE processed_to_silver = FALSE OR processed_to_silver IS NULL
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    molecule_id = await self._process_chembl_molecule(conn, record)
                    if molecule_id:
                        result.molecules_created += 1
                    else:
                        result.molecules_updated += 1

                    # Mark as processed
                    await conn.execute("""
                        UPDATE mol_bronze.chembl
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, record['id'])

                except Exception as e:
                    result.errors.append(f"ChEMBL {record['molecule_chembl_id']}: {str(e)}")
                    logger.error(f"Failed to process ChEMBL molecule {record['molecule_chembl_id']}: {e}")

        return result

    async def _process_chembl_molecule(self, conn, record: Dict) -> Optional[str]:
        """Process a single ChEMBL molecule into Silver."""
        inchi_key = record['inchi_key']
        chembl_id = record['molecule_chembl_id']

        # Step 1: Try to find existing molecule by InChI Key
        existing = None
        if inchi_key:
            existing = await conn.fetchrow("""
                SELECT id, data_sources FROM mol_silver.molecules
                WHERE inchi_key = $1
            """, inchi_key)

        # Step 2: If no InChI Key match, try ChEMBL ID lookup
        if not existing and chembl_id:
            existing = await conn.fetchrow("""
                SELECT m.id, m.data_sources
                FROM mol_silver.molecules m
                JOIN mol_silver.identifier_mappings im ON m.id = im.molecule_id
                WHERE im.identifier_type = 'chembl_id'
                  AND im.identifier_value = $1
            """, chembl_id)

        # Step 3: Create or update molecule
        if existing:
            # Update existing molecule (merge data based on precedence)
            await self._update_molecule_from_chembl(conn, existing['id'], record)
            return None  # Indicates update, not create
        else:
            # Create new molecule
            molecule_id = await self._create_molecule_from_chembl(conn, record)
            return molecule_id

    async def _create_molecule_from_chembl(self, conn, record: Dict) -> str:
        """Create a new Silver molecule from ChEMBL data."""
        # Determine development status from max_phase
        development_status = self._phase_to_status(record['max_phase'])

        row = await conn.fetchrow("""
            INSERT INTO mol_silver.molecules (
                inchi_key, canonical_name, name_source,
                canonical_smiles, inchi, molecular_formula, molecular_weight,
                molecule_type, development_status, max_phase,
                first_approval_year, resolution_confidence,
                data_sources, primary_source
            ) VALUES (
                $1, $2, 'chembl', $3, $4, $5, $6, $7, $8, $9, $10, 1.0,
                $11::jsonb, 'chembl'
            )
            RETURNING id::text
        """,
            record['inchi_key'],
            record['pref_name'],
            record['canonical_smiles'],
            record['inchi'],
            record['molecular_formula'],
            record['molecular_weight'],
            record['molecule_type'],
            development_status,
            record['max_phase'],
            record['first_approval'],
            json.dumps(['chembl'])
        )

        molecule_id = row['id']

        # Add identifier mapping for ChEMBL ID
        await self._add_identifier_mapping(
            conn, molecule_id, 'chembl_id', record['molecule_chembl_id'], 'chembl'
        )

        # Add InChI Key mapping if available
        if record['inchi_key']:
            await self._add_identifier_mapping(
                conn, molecule_id, 'inchi_key', record['inchi_key'], 'chembl'
            )

        # Add name as alias
        if record['pref_name']:
            await self._add_alias(
                conn, molecule_id, record['pref_name'], 'preferred_name', 'chembl'
            )

        return molecule_id

    async def _update_molecule_from_chembl(self, conn, molecule_id: str, record: Dict):
        """Update existing molecule with ChEMBL data (respecting precedence)."""
        # Get current molecule data
        current = await conn.fetchrow("""
            SELECT primary_source, data_sources FROM mol_silver.molecules WHERE id = $1::uuid
        """, molecule_id)

        current_precedence = SOURCE_PRECEDENCE.get(current['primary_source'], 999)
        chembl_precedence = SOURCE_PRECEDENCE['chembl']

        # Update fields if ChEMBL has higher precedence
        if chembl_precedence <= current_precedence:
            updates = []
            params = [molecule_id]

            if record['pref_name']:
                updates.append(f"canonical_name = ${len(params) + 1}")
                params.append(record['pref_name'])
                updates.append("name_source = 'chembl'")

            if record['canonical_smiles']:
                updates.append(f"canonical_smiles = ${len(params) + 1}")
                params.append(record['canonical_smiles'])

            if record['molecular_formula']:
                updates.append(f"molecular_formula = ${len(params) + 1}")
                params.append(record['molecular_formula'])

            if updates:
                await conn.execute(f"""
                    UPDATE mol_silver.molecules
                    SET {', '.join(updates)}, updated_at = NOW()
                    WHERE id = $1::uuid
                """, *params)

        # Always add ChEMBL to data sources
        data_sources = current['data_sources'] or []
        if isinstance(data_sources, str):
            data_sources = json.loads(data_sources)
        if 'chembl' not in data_sources:
            data_sources.append('chembl')
            await conn.execute("""
                UPDATE mol_silver.molecules
                SET data_sources = $2::jsonb, updated_at = NOW()
                WHERE id = $1::uuid
            """, molecule_id, json.dumps(data_sources))

        # Add ChEMBL ID mapping if not exists
        await self._add_identifier_mapping(
            conn, molecule_id, 'chembl_id', record['molecule_chembl_id'], 'chembl'
        )

    async def process_clinical_trials(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze clinical trials to Silver."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            # Use correct column names from mol_bronze.clinicaltrials table
            bronze_records = await conn.fetch("""
                SELECT id, nct_id, org_study_id,
                       COALESCE(official_title, brief_title) as title,
                       NULL as brief_summary,
                       phases as phase, study_type, overall_status as status,
                       start_date, completion_date, completion_date as primary_completion_date,
                       lead_sponsor_name as sponsor, lead_sponsor_class as sponsor_type, collaborators,
                       allocation, intervention_model, masking, enrollment_count as enrollment,
                       eligibility_criteria, minimum_age, maximum_age, sex,
                       NULL as conditions, interventions, primary_outcomes, secondary_outcomes,
                       NULL as locations, NULL as countries
                FROM mol_bronze.clinicaltrials
                WHERE processed_to_silver = FALSE OR processed_to_silver IS NULL
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    # Extract drug names from interventions
                    interventions = record['interventions']
                    if isinstance(interventions, str):
                        interventions = json.loads(interventions)

                    drug_names = self._extract_drug_names(interventions)

                    for drug_name in drug_names:
                        # Resolve drug name to molecule
                        resolution = await self.resolver.resolve(
                            drug_name,
                            IdentifierType.NAME,
                            source='clinicaltrials'
                        )

                        if resolution.molecule_id:
                            # Link trial to molecule
                            await self._upsert_silver_trial(
                                conn, record, resolution.molecule_id
                            )

                            if resolution.needs_review:
                                result.records_quarantined += 1
                        else:
                            # Create placeholder or queue for review
                            result.records_quarantined += 1

                    # Mark as processed
                    await conn.execute("""
                        UPDATE mol_bronze.clinicaltrials
                        SET processed_to_silver = TRUE
                        WHERE id = $1
                    """, record['id'])

                except Exception as e:
                    result.errors.append(f"Trial {record['nct_id']}: {str(e)}")
                    logger.error(f"Failed to process trial {record['nct_id']}: {e}")

        return result

    async def _upsert_silver_trial(self, conn, record: Dict, molecule_id: str):
        """Upsert clinical trial into Silver layer."""
        conditions = record['conditions']
        if isinstance(conditions, str):
            conditions = json.loads(conditions)

        interventions = record['interventions']
        if isinstance(interventions, str):
            interventions = json.loads(interventions)

        primary_outcomes = record['primary_outcomes']
        if isinstance(primary_outcomes, str):
            primary_outcomes = json.loads(primary_outcomes)

        secondary_outcomes = record['secondary_outcomes']
        if isinstance(secondary_outcomes, str):
            secondary_outcomes = json.loads(secondary_outcomes)

        locations = record['locations']
        if isinstance(locations, str):
            locations = json.loads(locations)

        countries = record['countries']
        if isinstance(countries, str):
            countries = json.loads(countries)

        collaborators = record['collaborators']
        if isinstance(collaborators, str):
            collaborators = json.loads(collaborators)

        await conn.execute("""
            INSERT INTO mol_silver.clinical_trials (
                molecule_id, nct_id, org_study_id, title, brief_summary,
                phase, study_type, status,
                start_date, completion_date, primary_completion_date,
                sponsor, sponsor_type, collaborators,
                allocation, intervention_model, masking, enrollment,
                eligibility_criteria, minimum_age, maximum_age, sex,
                conditions, interventions, primary_outcomes, secondary_outcomes,
                locations, countries, source
            ) VALUES (
                $1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27, $28, 'clinicaltrials_gov'
            )
            ON CONFLICT (nct_id) DO UPDATE SET
                molecule_id = EXCLUDED.molecule_id,
                title = EXCLUDED.title,
                status = EXCLUDED.status,
                phase = EXCLUDED.phase,
                enrollment = EXCLUDED.enrollment,
                completion_date = EXCLUDED.completion_date,
                updated_at = NOW()
        """,
            molecule_id,
            record['nct_id'],
            record['org_study_id'],
            record['title'],
            record['brief_summary'],
            record['phase'],
            record['study_type'],
            record['status'],
            record['start_date'],
            record['completion_date'],
            record['primary_completion_date'],
            record['sponsor'],
            record['sponsor_type'],
            json.dumps(collaborators),
            record['allocation'],
            record['intervention_model'],
            record['masking'],
            record['enrollment'],
            record['eligibility_criteria'],
            record['minimum_age'],
            record['maximum_age'],
            record['sex'],
            json.dumps(conditions),
            json.dumps(interventions),
            json.dumps(primary_outcomes),
            json.dumps(secondary_outcomes),
            json.dumps(locations),
            json.dumps(countries)
        )

    async def process_faers_events(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze FAERS events to Silver aggregated adverse events."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            # Get drug names extracted from patient_drug JSONB array
            # Each event has patient_drug array with medicinalproduct field
            drug_groups = await conn.fetch("""
                SELECT
                    UPPER(drug->>'medicinalproduct') as drug_name,
                    COUNT(DISTINCT f.id) as event_count
                FROM mol_bronze.openfda_faers f,
                     jsonb_array_elements(COALESCE(f.patient_drug, '[]'::jsonb)) AS drug
                WHERE (f.processed_to_silver = FALSE OR f.processed_to_silver IS NULL)
                  AND drug->>'medicinalproduct' IS NOT NULL
                GROUP BY UPPER(drug->>'medicinalproduct')
                ORDER BY event_count DESC
                LIMIT $1
            """, limit)

            for drug_group in drug_groups:
                result.records_processed += 1
                drug_name = drug_group['drug_name']

                if not drug_name:
                    continue

                try:
                    # Resolve drug name to molecule
                    resolution = await self.resolver.resolve(
                        drug_name,
                        IdentifierType.NAME,
                        source='openfda_faers'
                    )

                    if resolution.molecule_id:
                        # Aggregate events for this molecule
                        await self._aggregate_faers_for_molecule(
                            conn, drug_name, resolution.molecule_id
                        )
                        result.molecules_updated += 1

                        if resolution.needs_review:
                            result.records_quarantined += 1
                    else:
                        # Queue for review
                        await self._queue_for_resolution(
                            conn, drug_name, 'name', 'openfda_faers'
                        )
                        result.records_quarantined += 1

                    # Mark events containing this drug as processed
                    await conn.execute("""
                        UPDATE mol_bronze.openfda_faers
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id IN (
                            SELECT f.id FROM mol_bronze.openfda_faers f,
                                   jsonb_array_elements(COALESCE(f.patient_drug, '[]'::jsonb)) AS drug
                            WHERE UPPER(drug->>'medicinalproduct') = $1
                        )
                    """, drug_name)

                except Exception as e:
                    result.errors.append(f"FAERS drug {drug_name}: {str(e)}")
                    logger.error(f"Failed to process FAERS for {drug_name}: {e}")

        return result

    async def _aggregate_faers_for_molecule(self, conn, drug_name: str, molecule_id: str):
        """Aggregate FAERS events into Silver adverse_events."""
        # Aggregate by MedDRA preferred term using correct column names
        # patient_reaction contains the reaction array, serious flags are integers
        aggregates = await conn.fetch("""
            SELECT
                reaction->>'reactionmeddrapt' AS meddra_pt,
                COUNT(DISTINCT f.id) AS report_count,
                SUM(CASE WHEN f.serious = 1 THEN 1 ELSE 0 END) AS serious_count,
                SUM(CASE WHEN f.serious_death = 1 THEN 1 ELSE 0 END) AS death_count,
                SUM(CASE WHEN f.serious_hospitalization = 1 THEN 1 ELSE 0 END) AS hospitalization_count,
                MIN(f.receive_date) AS first_report_date,
                MAX(f.receive_date) AS last_report_date
            FROM mol_bronze.openfda_faers f,
                 jsonb_array_elements(COALESCE(f.patient_drug, '[]'::jsonb)) AS drug,
                 jsonb_array_elements(COALESCE(f.patient_reaction, '[]'::jsonb)) AS reaction
            WHERE UPPER(drug->>'medicinalproduct') = $1
            GROUP BY reaction->>'reactionmeddrapt'
        """, drug_name)

        for agg in aggregates:
            if not agg['meddra_pt']:
                continue

            await conn.execute("""
                INSERT INTO mol_silver.adverse_events (
                    molecule_id, meddra_pt,
                    report_count, serious_count, death_count, hospitalization_count,
                    first_report_date, last_report_date, source
                ) VALUES (
                    $1::uuid, $2, $3, $4, $5, $6, $7, $8, 'openfda_faers'
                )
                ON CONFLICT (molecule_id, meddra_pt_code) DO UPDATE SET
                    report_count = EXCLUDED.report_count,
                    serious_count = EXCLUDED.serious_count,
                    death_count = EXCLUDED.death_count,
                    hospitalization_count = EXCLUDED.hospitalization_count,
                    last_report_date = EXCLUDED.last_report_date,
                    updated_at = NOW()
            """,
                molecule_id,
                agg['meddra_pt'],
                agg['report_count'],
                agg['serious_count'],
                agg['death_count'],
                agg['hospitalization_count'],
                agg['first_report_date'],
                agg['last_report_date']
            )

    async def process_drug_labels(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze drug labels to Silver."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            # Use correct column names from mol_bronze.openfda_labels table
            bronze_records = await conn.fetch("""
                SELECT id, set_id, spl_id, version,
                       brand_name, generic_name, manufacturer_name as manufacturer,
                       application_number, product_type,
                       indications_and_usage, dosage_and_administration,
                       contraindications, warnings, boxed_warning, adverse_reactions,
                       drug_interactions, mechanism_of_action, effective_time as effective_date
                FROM mol_bronze.openfda_labels
                WHERE processed_to_silver = FALSE OR processed_to_silver IS NULL
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    # Try to resolve by generic name first, then brand name
                    drug_name = record['generic_name'] or record['brand_name']
                    if not drug_name:
                        continue

                    resolution = await self.resolver.resolve(
                        drug_name,
                        IdentifierType.NAME,
                        source='openfda_labels'
                    )

                    if resolution.molecule_id:
                        await self._upsert_silver_label(
                            conn, record, resolution.molecule_id
                        )
                        result.molecules_updated += 1

                        # Add brand name as alias
                        if record['brand_name']:
                            await self._add_alias(
                                conn, resolution.molecule_id,
                                record['brand_name'], 'brand_name', 'openfda_labels'
                            )

                        if resolution.needs_review:
                            result.records_quarantined += 1
                    else:
                        result.records_quarantined += 1

                    await conn.execute("""
                        UPDATE mol_bronze.openfda_labels
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, record['id'])

                except Exception as e:
                    result.errors.append(f"Label {record['set_id']}: {str(e)}")
                    logger.error(f"Failed to process label {record['set_id']}: {e}")

        return result

    async def _upsert_silver_label(self, conn, record: Dict, molecule_id: str):
        """Upsert drug label into Silver layer."""
        await conn.execute("""
            INSERT INTO mol_silver.drug_labels (
                molecule_id, set_id, spl_id, version,
                brand_name, generic_name, manufacturer, application_number,
                product_type, indications_and_usage, dosage_and_administration,
                contraindications, warnings, boxed_warning, adverse_reactions,
                drug_interactions, mechanism_of_action, effective_date, source
            ) VALUES (
                $1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, 'openfda_labels'
            )
            ON CONFLICT (set_id, version) DO UPDATE SET
                molecule_id = EXCLUDED.molecule_id,
                brand_name = EXCLUDED.brand_name,
                boxed_warning = EXCLUDED.boxed_warning,
                adverse_reactions = EXCLUDED.adverse_reactions,
                updated_at = NOW()
        """,
            molecule_id,
            record['set_id'],
            record['spl_id'],
            record['version'],
            record['brand_name'],
            record['generic_name'],
            record['manufacturer'],
            record['application_number'],
            record['product_type'],
            record['indications_and_usage'],
            record['dosage_and_administration'],
            record['contraindications'],
            record['warnings'],
            record['boxed_warning'],
            record['adverse_reactions'],
            record['drug_interactions'],
            record['mechanism_of_action'],
            record['effective_date']
        )

        # Update molecule approval info if this is an approved drug
        if record['effective_date']:
            await conn.execute("""
                UPDATE mol_silver.molecules
                SET development_status = 'approved',
                    approval_date = COALESCE(approval_date, $2),
                    first_approval_year = COALESCE(first_approval_year, EXTRACT(YEAR FROM $2)::INTEGER),
                    updated_at = NOW()
                WHERE id = $1::uuid
                  AND (development_status IS NULL OR development_status != 'approved')
            """, molecule_id, record['effective_date'])

    async def _add_identifier_mapping(
        self, conn, molecule_id: str, id_type: str, id_value: str, source: str
    ):
        """Add an identifier mapping."""
        await conn.execute("""
            INSERT INTO mol_silver.identifier_mappings (
                molecule_id, identifier_type, identifier_value, source, is_primary
            ) VALUES ($1::uuid, $2, $3, $4, TRUE)
            ON CONFLICT (molecule_id, identifier_type, identifier_value) DO NOTHING
        """, molecule_id, id_type, id_value, source)

    async def _add_alias(
        self, conn, molecule_id: str, alias_name: str, alias_type: str, source: str
    ):
        """Add a molecule alias."""
        normalized = FuzzyMatcher.normalize_name(alias_name)
        await conn.execute("""
            INSERT INTO mol_silver.molecule_aliases (
                molecule_id, alias_name, alias_type, alias_name_normalized, source
            ) VALUES ($1::uuid, $2, $3, $4, $5)
            ON CONFLICT (molecule_id, alias_name, alias_type) DO NOTHING
        """, molecule_id, alias_name, alias_type, normalized, source)

    async def _queue_for_resolution(
        self, conn, identifier: str, id_type: str, source: str
    ):
        """Add to resolution queue for manual review."""
        await conn.execute("""
            INSERT INTO mol_silver.resolution_queue (
                original_identifier, identifier_type, confidence_score, status
            ) VALUES ($1, $2, 0.0, 'pending')
            ON CONFLICT DO NOTHING
        """, identifier, id_type)

    @staticmethod
    def _extract_drug_names(interventions: Optional[List[Dict]]) -> List[str]:
        """Extract drug names from clinical trial interventions."""
        if not interventions:
            return []
        drug_names = []
        for intervention in interventions:
            if intervention and intervention.get('type') == 'DRUG':
                name = intervention.get('name')
                if name:
                    drug_names.append(name)
        return drug_names

    @staticmethod
    def _phase_to_status(max_phase: Optional[int]) -> str:
        """Convert max phase to development status."""
        if max_phase is None:
            return 'unknown'
        if max_phase == 4:
            return 'approved'
        elif max_phase == 3:
            return 'phase_3'
        elif max_phase == 2:
            return 'phase_2'
        elif max_phase == 1:
            return 'phase_1'
        else:
            return 'preclinical'

    async def process_pubchem_to_silver(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze PubChem data to Silver."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            bronze_records = await conn.fetch("""
                SELECT id, cid, iupac_name, canonical_smiles, inchi, inchikey,
                       molecular_formula, molecular_weight
                FROM mol_bronze.pubchem
                WHERE (processed_to_silver = FALSE OR processed_to_silver IS NULL)
                  AND inchikey IS NOT NULL
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    inchi_key = record['inchikey']

                    # Check for existing molecule by InChI Key
                    existing = await conn.fetchrow("""
                        SELECT id, data_sources FROM mol_silver.molecules
                        WHERE inchi_key = $1
                    """, inchi_key)

                    if existing:
                        # Update existing with PubChem data
                        await self._update_molecule_from_pubchem(conn, existing['id'], record)
                        result.molecules_updated += 1
                    else:
                        # Create new molecule
                        await self._create_molecule_from_pubchem(conn, record)
                        result.molecules_created += 1

                    await conn.execute("""
                        UPDATE mol_bronze.pubchem
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, record['id'])

                except Exception as e:
                    result.errors.append(f"PubChem CID {record['cid']}: {str(e)}")
                    logger.error(f"Failed to process PubChem {record['cid']}: {e}")

        return result

    async def _create_molecule_from_pubchem(self, conn, record: Dict) -> str:
        """Create a Silver molecule from PubChem data."""
        row = await conn.fetchrow("""
            INSERT INTO mol_silver.molecules (
                inchi_key, canonical_name, name_source,
                canonical_smiles, inchi, molecular_formula, molecular_weight,
                resolution_confidence, data_sources, primary_source
            ) VALUES (
                $1, $2, 'pubchem', $3, $4, $5, $6, 0.9,
                $7::jsonb, 'pubchem'
            )
            RETURNING id::text
        """,
            record['inchikey'],
            record['iupac_name'],
            record['canonical_smiles'],
            record['inchi'],
            record['molecular_formula'],
            record['molecular_weight'],
            json.dumps(['pubchem'])
        )

        molecule_id = row['id']

        # Add identifier mapping for PubChem CID
        await self._add_identifier_mapping(
            conn, molecule_id, 'pubchem_cid', str(record['cid']), 'pubchem'
        )

        return molecule_id

    async def _update_molecule_from_pubchem(self, conn, molecule_id: str, record: Dict):
        """Update existing molecule with PubChem data."""
        # Add PubChem to data sources
        await conn.execute("""
            UPDATE mol_silver.molecules
            SET data_sources = COALESCE(data_sources, '[]'::jsonb) || '["pubchem"]'::jsonb,
                updated_at = NOW()
            WHERE id = $1::uuid
              AND NOT (data_sources ? 'pubchem')
        """, molecule_id)

        # Add PubChem CID mapping
        await self._add_identifier_mapping(
            conn, molecule_id, 'pubchem_cid', str(record['cid']), 'pubchem'
        )

    async def process_sider_to_silver(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze SIDER data to Silver adverse events."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            # Group by drug and aggregate side effects
            drug_groups = await conn.fetch("""
                SELECT
                    drug_name,
                    COUNT(DISTINCT meddra_concept_name) as effect_count
                FROM mol_bronze.sider
                WHERE (processed_to_silver = FALSE OR processed_to_silver IS NULL)
                  AND drug_name IS NOT NULL
                GROUP BY drug_name
                ORDER BY effect_count DESC
                LIMIT $1
            """, limit)

            for drug_group in drug_groups:
                result.records_processed += 1
                drug_name = drug_group['drug_name']

                try:
                    # Resolve drug name to molecule
                    resolution = await self.resolver.resolve(
                        drug_name,
                        IdentifierType.NAME,
                        source='sider'
                    )

                    if resolution.molecule_id:
                        await self._aggregate_sider_for_molecule(conn, drug_name, resolution.molecule_id)
                        result.molecules_updated += 1
                    else:
                        result.records_quarantined += 1

                    # Mark SIDER records as processed
                    await conn.execute("""
                        UPDATE mol_bronze.sider
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE drug_name = $1
                    """, drug_name)

                except Exception as e:
                    result.errors.append(f"SIDER drug {drug_name}: {str(e)}")
                    logger.error(f"Failed to process SIDER for {drug_name}: {e}")

        return result

    async def _aggregate_sider_for_molecule(self, conn, drug_name: str, molecule_id: str):
        """Aggregate SIDER side effects into Silver adverse_events."""
        aggregates = await conn.fetch("""
            SELECT
                meddra_concept_name as meddra_pt,
                meddra_umls_id,
                AVG(COALESCE(frequency_lower, 0.01)) as avg_freq,
                COUNT(*) as report_count
            FROM mol_bronze.sider
            WHERE drug_name = $1
              AND meddra_concept_name IS NOT NULL
            GROUP BY meddra_concept_name, meddra_umls_id
        """, drug_name)

        for agg in aggregates:
            if not agg['meddra_pt']:
                continue

            await conn.execute("""
                INSERT INTO mol_silver.adverse_events (
                    molecule_id, meddra_pt, meddra_pt_code,
                    report_count, source
                ) VALUES ($1::uuid, $2, $3, $4, 'sider')
                ON CONFLICT (molecule_id, meddra_pt_code) DO UPDATE SET
                    report_count = EXCLUDED.report_count,
                    updated_at = NOW()
            """,
                molecule_id,
                agg['meddra_pt'],
                agg['meddra_umls_id'],
                agg['report_count']
            )

    async def process_rxnorm_to_silver(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze RxNorm data to Silver identifier mappings."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            bronze_records = await conn.fetch("""
                SELECT id, rxcui, name, tty, ingredients, atc_codes
                FROM mol_bronze.rxnorm_concepts
                WHERE (processed_to_silver = FALSE OR processed_to_silver IS NULL)
                  AND rxcui IS NOT NULL
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    # Try to resolve RxNorm concept to molecule
                    resolution = await self.resolver.resolve(
                        record['name'],
                        IdentifierType.NAME,
                        source='rxnorm'
                    )

                    if resolution.molecule_id:
                        # Add RxCUI mapping
                        await self._add_identifier_mapping(
                            conn, resolution.molecule_id, 'rxcui', record['rxcui'], 'rxnorm'
                        )

                        # Add ATC codes if available
                        atc_codes = record['atc_codes']
                        if isinstance(atc_codes, str):
                            atc_codes = json.loads(atc_codes)
                        if atc_codes:
                            for atc in atc_codes:
                                await self._add_identifier_mapping(
                                    conn, resolution.molecule_id, 'atc_code', atc, 'rxnorm'
                                )

                        result.molecules_updated += 1
                    else:
                        result.records_quarantined += 1

                    await conn.execute("""
                        UPDATE mol_bronze.rxnorm_concepts
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, record['id'])

                except Exception as e:
                    result.errors.append(f"RxNorm {record['rxcui']}: {str(e)}")
                    logger.error(f"Failed to process RxNorm {record['rxcui']}: {e}")

        return result

    async def process_bindingdb_to_silver(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze BindingDB data to Silver bioactivity."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            bronze_records = await conn.fetch("""
                SELECT id, bindingdb_id, ligand_name, smiles, inchi_key,
                       target_name, target_source_id, target_organism,
                       ki_nm, kd_nm, ic50_nm, ec50_nm,
                       pmid, doi
                FROM mol_bronze.bindingdb
                WHERE (processed_to_silver = FALSE OR processed_to_silver IS NULL)
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    # Try to resolve by InChI key or name
                    molecule_id = None
                    if record['inchi_key']:
                        existing = await conn.fetchrow("""
                            SELECT id FROM mol_silver.molecules WHERE inchi_key = $1
                        """, record['inchi_key'])
                        if existing:
                            molecule_id = existing['id']

                    if not molecule_id and record['ligand_name']:
                        resolution = await self.resolver.resolve(
                            record['ligand_name'],
                            IdentifierType.NAME,
                            source='bindingdb'
                        )
                        molecule_id = resolution.molecule_id

                    if molecule_id:
                        # Insert bioactivity data
                        for activity_type, value in [
                            ('Ki', record['ki_nm']),
                            ('Kd', record['kd_nm']),
                            ('IC50', record['ic50_nm']),
                            ('EC50', record['ec50_nm'])
                        ]:
                            if value is not None:
                                await conn.execute("""
                                    INSERT INTO mol_silver.bioactivity (
                                        molecule_id, target_name, target_uniprot_id, target_organism,
                                        activity_type, activity_value, activity_unit,
                                        source, source_id, pmid, doi
                                    ) VALUES ($1::uuid, $2, $3, $4, $5, $6, 'nM', 'bindingdb', $7, $8, $9)
                                """,
                                    str(molecule_id),
                                    record['target_name'],
                                    record['target_source_id'],
                                    record['target_organism'],
                                    activity_type,
                                    value,
                                    record['bindingdb_id'],
                                    record['pmid'],
                                    record['doi']
                                )
                        result.molecules_updated += 1
                    else:
                        result.records_quarantined += 1

                    await conn.execute("""
                        UPDATE mol_bronze.bindingdb
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, record['id'])

                except Exception as e:
                    result.errors.append(f"BindingDB {record['bindingdb_id']}: {str(e)}")
                    logger.error(f"Failed to process BindingDB {record['bindingdb_id']}: {e}")

        return result

    async def process_kegg_to_silver(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze KEGG Drug data to Silver."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            bronze_records = await conn.fetch("""
                SELECT id, kegg_id, name, inchi_key, smiles, drugbank_id,
                       atc_codes, targets, research_codes
                FROM mol_bronze.kegg_drug
                WHERE (processed_to_silver = FALSE OR processed_to_silver IS NULL)
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    # Try to find existing molecule
                    molecule_id = None
                    if record['inchi_key']:
                        existing = await conn.fetchrow("""
                            SELECT id FROM mol_silver.molecules WHERE inchi_key = $1
                        """, record['inchi_key'])
                        if existing:
                            molecule_id = existing['id']

                    if not molecule_id and record['drugbank_id']:
                        existing = await conn.fetchrow("""
                            SELECT molecule_id FROM mol_silver.identifier_mappings
                            WHERE identifier_type = 'drugbank_id' AND identifier_value = $1
                        """, record['drugbank_id'])
                        if existing:
                            molecule_id = existing['molecule_id']

                    if molecule_id:
                        # Add KEGG ID mapping
                        await self._add_identifier_mapping(
                            conn, str(molecule_id), 'kegg_id', record['kegg_id'], 'kegg_drug'
                        )

                        # Add research code aliases
                        research_codes = record['research_codes']
                        if isinstance(research_codes, str):
                            research_codes = json.loads(research_codes)
                        if research_codes:
                            for code in research_codes:
                                await self._add_alias(
                                    conn, str(molecule_id), code, 'research_code', 'kegg_drug'
                                )

                        result.molecules_updated += 1
                    else:
                        result.records_quarantined += 1

                    await conn.execute("""
                        UPDATE mol_bronze.kegg_drug
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, record['id'])

                except Exception as e:
                    result.errors.append(f"KEGG {record['kegg_id']}: {str(e)}")
                    logger.error(f"Failed to process KEGG {record['kegg_id']}: {e}")

        return result

    async def process_uniprot_to_silver(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze UniProt data to Silver targets."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            bronze_records = await conn.fetch("""
                SELECT id, accession, entry_name, protein_name,
                       gene_names, organism, organism_id,
                       sequence, sequence_length, function_description,
                       drugbank_ids, chembl_ids
                FROM mol_bronze.uniprot
                WHERE (processed_to_silver = FALSE OR processed_to_silver IS NULL)
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    # Insert or update target in mol_silver.targets
                    await conn.execute("""
                        INSERT INTO mol_silver.targets (
                            uniprot_id, entry_name, protein_name,
                            gene_names, organism, organism_id,
                            sequence, sequence_length, function_description,
                            source
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'uniprot')
                        ON CONFLICT (uniprot_id) DO UPDATE SET
                            protein_name = COALESCE(EXCLUDED.protein_name, mol_silver.targets.protein_name),
                            function_description = COALESCE(EXCLUDED.function_description, mol_silver.targets.function_description),
                            updated_at = NOW()
                    """,
                        record['accession'],
                        record['entry_name'],
                        record['protein_name'],
                        record['gene_names'],
                        record['organism'],
                        record['organism_id'],
                        record['sequence'],
                        record['sequence_length'],
                        record['function_description']
                    )

                    result.molecules_created += 1  # Using molecules_created for targets

                    await conn.execute("""
                        UPDATE mol_bronze.uniprot
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, record['id'])

                except Exception as e:
                    result.errors.append(f"UniProt {record['accession']}: {str(e)}")
                    logger.error(f"Failed to process UniProt {record['accession']}: {e}")

        return result

    async def process_who_inn_to_silver(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze WHO INN data to Silver molecule aliases."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            bronze_records = await conn.fetch("""
                SELECT id, inn_name, inn_latin, inchi_key, research_codes, synonyms
                FROM mol_bronze.who_inn
                WHERE (processed_to_silver = FALSE OR processed_to_silver IS NULL)
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    # Try to find molecule by InChI key or name
                    molecule_id = None
                    if record['inchi_key']:
                        existing = await conn.fetchrow("""
                            SELECT id FROM mol_silver.molecules WHERE inchi_key = $1
                        """, record['inchi_key'])
                        if existing:
                            molecule_id = existing['id']

                    if not molecule_id:
                        resolution = await self.resolver.resolve(
                            record['inn_name'],
                            IdentifierType.NAME,
                            source='who_inn'
                        )
                        molecule_id = resolution.molecule_id

                    if molecule_id:
                        # Add INN name as alias
                        await self._add_alias(
                            conn, str(molecule_id), record['inn_name'], 'inn_name', 'who_inn'
                        )

                        # Add Latin name if different
                        if record['inn_latin'] and record['inn_latin'] != record['inn_name']:
                            await self._add_alias(
                                conn, str(molecule_id), record['inn_latin'], 'inn_latin', 'who_inn'
                            )

                        # Add research codes as aliases
                        research_codes = record['research_codes']
                        if isinstance(research_codes, str):
                            research_codes = json.loads(research_codes)
                        if research_codes:
                            for code in research_codes:
                                await self._add_alias(
                                    conn, str(molecule_id), code, 'research_code', 'who_inn'
                                )

                        result.molecules_updated += 1
                    else:
                        result.records_quarantined += 1

                    await conn.execute("""
                        UPDATE mol_bronze.who_inn
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, record['id'])

                except Exception as e:
                    result.errors.append(f"WHO INN {record['inn_name']}: {str(e)}")
                    logger.error(f"Failed to process WHO INN {record['inn_name']}: {e}")

        return result

    async def process_tdc_admet_to_silver(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze TDC ADMET data to Silver predictions."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            bronze_records = await conn.fetch("""
                SELECT id, compound_id, smiles, inchi_key,
                       dataset_name, property_name, property_value, property_category
                FROM mol_bronze.tdc_admet
                WHERE (processed_to_silver = FALSE OR processed_to_silver IS NULL)
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    # Try to find molecule by InChI key or SMILES
                    molecule_id = None
                    if record['inchi_key']:
                        existing = await conn.fetchrow("""
                            SELECT id FROM mol_silver.molecules WHERE inchi_key = $1
                        """, record['inchi_key'])
                        if existing:
                            molecule_id = existing['id']

                    if molecule_id:
                        # Insert ADMET prediction
                        await conn.execute("""
                            INSERT INTO mol_silver.admet_predictions (
                                molecule_id, inchi_key, property_name, property_category,
                                predicted_value, source
                            ) VALUES ($1::uuid, $2, $3, $4, $5, 'tdc_admet')
                            ON CONFLICT (molecule_id, property_name, source) DO UPDATE SET
                                predicted_value = EXCLUDED.predicted_value,
                                updated_at = NOW()
                        """,
                            str(molecule_id),
                            record['inchi_key'],
                            record['property_name'],
                            record['property_category'],
                            record['property_value']
                        )
                        result.molecules_updated += 1
                    else:
                        result.records_quarantined += 1

                    await conn.execute("""
                        UPDATE mol_bronze.tdc_admet
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, record['id'])

                except Exception as e:
                    result.errors.append(f"TDC {record['compound_id']}: {str(e)}")
                    logger.error(f"Failed to process TDC {record['compound_id']}: {e}")

        return result

    async def process_pharmgkb_to_silver(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze PharmGKB data to Silver pharmacogenomics."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            bronze_records = await conn.fetch("""
                SELECT id, pharmgkb_id, name, drugbank_id, chembl_id, inchi_key,
                       clinical_annotations, dosing_guidelines
                FROM mol_bronze.pharmgkb
                WHERE (processed_to_silver = FALSE OR processed_to_silver IS NULL)
                  AND entity_type = 'drug'
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    # Find molecule
                    molecule_id = None

                    # Try InChI key first
                    if record['inchi_key']:
                        existing = await conn.fetchrow("""
                            SELECT id FROM mol_silver.molecules WHERE inchi_key = $1
                        """, record['inchi_key'])
                        if existing:
                            molecule_id = existing['id']

                    # Try DrugBank ID
                    if not molecule_id and record['drugbank_id']:
                        existing = await conn.fetchrow("""
                            SELECT molecule_id FROM mol_silver.identifier_mappings
                            WHERE identifier_type = 'drugbank_id' AND identifier_value = $1
                        """, record['drugbank_id'])
                        if existing:
                            molecule_id = existing['molecule_id']

                    # Try ChEMBL ID
                    if not molecule_id and record['chembl_id']:
                        existing = await conn.fetchrow("""
                            SELECT molecule_id FROM mol_silver.identifier_mappings
                            WHERE identifier_type = 'chembl_id' AND identifier_value = $1
                        """, record['chembl_id'])
                        if existing:
                            molecule_id = existing['molecule_id']

                    if molecule_id:
                        # Add PharmGKB ID mapping
                        await self._add_identifier_mapping(
                            conn, str(molecule_id), 'pharmgkb_id', record['pharmgkb_id'], 'pharmgkb'
                        )

                        # Process clinical annotations
                        annotations = record['clinical_annotations']
                        if isinstance(annotations, str):
                            annotations = json.loads(annotations)
                        if annotations:
                            for ann in annotations:
                                gene = ann.get('gene', {}).get('symbol', '')
                                if gene:
                                    await conn.execute("""
                                        INSERT INTO mol_silver.pharmacogenomics (
                                            molecule_id, gene_symbol, variant_id,
                                            phenotype_category, clinical_annotation,
                                            level_of_evidence, source, pharmgkb_annotation_id
                                        ) VALUES ($1::uuid, $2, $3, $4, $5, $6, 'pharmgkb', $7)
                                        ON CONFLICT (molecule_id, gene_symbol, variant_id, source) DO UPDATE SET
                                            clinical_annotation = EXCLUDED.clinical_annotation,
                                            updated_at = NOW()
                                    """,
                                        str(molecule_id),
                                        gene,
                                        ann.get('variant', {}).get('name'),
                                        ann.get('phenotypeCategory'),
                                        ann.get('sentence'),
                                        ann.get('level'),
                                        ann.get('id')
                                    )

                        result.molecules_updated += 1
                    else:
                        result.records_quarantined += 1

                    await conn.execute("""
                        UPDATE mol_bronze.pharmgkb
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, record['id'])

                except Exception as e:
                    result.errors.append(f"PharmGKB {record['pharmgkb_id']}: {str(e)}")
                    logger.error(f"Failed to process PharmGKB {record['pharmgkb_id']}: {e}")

        return result

    async def process_all_sources(self, limit_per_source: int = 100) -> Dict[str, TransformationResult]:
        """Process all Bronze sources to Silver."""
        results = {}

        # Complete list of all processors for 16 data sources
        processors = [
            ('chembl_molecules', self.process_chembl_molecules),
            ('clinical_trials', self.process_clinical_trials),
            ('faers_events', self.process_faers_events),
            ('drug_labels', self.process_drug_labels),
            # New processors for complete medallion architecture
            ('pubchem', self.process_pubchem_to_silver),
            ('sider', self.process_sider_to_silver),
            ('rxnorm', self.process_rxnorm_to_silver),
            ('bindingdb', self.process_bindingdb_to_silver),
            ('kegg', self.process_kegg_to_silver),
            ('uniprot', self.process_uniprot_to_silver),
            ('who_inn', self.process_who_inn_to_silver),
            ('tdc_admet', self.process_tdc_admet_to_silver),
            ('pharmgkb', self.process_pharmgkb_to_silver),
        ]

        for source_name, processor in processors:
            try:
                results[source_name] = await processor(limit_per_source)
                logger.info(
                    f"Processed {source_name}: "
                    f"{results[source_name].molecules_created} created, "
                    f"{results[source_name].molecules_updated} updated, "
                    f"{results[source_name].records_quarantined} quarantined"
                )
            except Exception as e:
                logger.error(f"Failed to process {source_name}: {e}")
                results[source_name] = TransformationResult(0, 0, 0, 0, [str(e)])

        return results
