"""
DEPRECATED: SilverTransformationService — Python bronze→silver transformer.

THIS MODULE IS DEPRECATED.
All bronze→silver transformations are now handled by SQLMesh silver models in:
    sqlmesh/models/molecules/silver/

Entity resolution is performed in SQL via INCREMENTAL_BY_UNIQUE_KEY on inchi_key
in mol_silver.molecules. The hot-run path (base_tool._trigger_sqlmesh_hot) triggers
the full bronze→silver→gold chain immediately after ingest.

This file is retained for reference only and will be removed in a future cleanup.

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
            # Get unprocessed Bronze records (use bronze.chembl table with correct column names)
            bronze_records = await conn.fetch("""
                SELECT id, molecule_chembl_id as chembl_id, pref_name, molecule_type, max_phase,
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
                    result.errors.append(f"ChEMBL {record['chembl_id']}: {str(e)}")
                    logger.error(f"Failed to process ChEMBL molecule {record['chembl_id']}: {e}")

        return result

    async def _process_chembl_molecule(self, conn, record: Dict) -> Optional[str]:
        """Process a single ChEMBL molecule into Silver."""
        inchi_key = record['inchi_key']
        chembl_id = record['chembl_id']

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
            conn, molecule_id, 'chembl_id', record['chembl_id'], 'chembl'
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
            conn, molecule_id, 'chembl_id', record['chembl_id'], 'chembl'
        )

    async def process_clinical_trials(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze clinical trials to Silver."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            # Use correct column names from bronze.clinicaltrials table
            bronze_records = await conn.fetch("""
                SELECT id,
                       nct_id, brief_title, official_title, overall_status,
                       phase, study_type, lead_sponsor_name, lead_sponsor_class,
                       enrollment_count, enrollment_type, start_date, start_date_type,
                       completion_date, completion_date_type, primary_completion_date,
                       interventions, conditions, locations, org_study_id,
                       acronym, last_known_status, study_first_submit_date,
                       study_first_post_date, last_update_post_date, collaborators,
                       phases, allocation, intervention_model, primary_purpose,
                       masking, arms_groups, primary_outcomes, secondary_outcomes,
                       eligibility_criteria, sex, minimum_age, maximum_age,
                       healthy_volunteers, central_contacts, keywords, mesh_terms,
                       results_section, fda_regulated_drug, fda_regulated_device,
                       ipd_sharing, has_results, condition_browse, intervention_browse,
                       references, results_outcome_measures, results_adverse_events,
                       results_participant_flow, results_baseline, brief_summary,
                       detailed_description, why_stopped
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
        def _parse_json(val):
            if isinstance(val, str):
                return json.loads(val)
            return val

        conditions = _parse_json(record['conditions'])
        interventions = _parse_json(record['interventions'])
        primary_outcomes = _parse_json(record['primary_outcomes'])
        secondary_outcomes = _parse_json(record['secondary_outcomes'])
        locations = _parse_json(record['locations'])
        collaborators = _parse_json(record['collaborators'])
        arms_groups = _parse_json(record['arms_groups'])
        central_contacts = _parse_json(record['central_contacts'])
        keywords = _parse_json(record['keywords'])
        mesh_terms = _parse_json(record['mesh_terms'])
        results_section = _parse_json(record['results_section'])
        condition_browse = _parse_json(record['condition_browse'])
        intervention_browse = _parse_json(record['intervention_browse'])
        references = _parse_json(record['references'])
        results_outcome_measures = _parse_json(record['results_outcome_measures'])
        results_adverse_events = _parse_json(record['results_adverse_events'])
        results_participant_flow = _parse_json(record['results_participant_flow'])
        results_baseline = _parse_json(record['results_baseline'])
        phases = _parse_json(record['phases'])

        await conn.execute("""
            INSERT INTO mol_silver.clinical_trials (
                molecule_id, nct_id, brief_title, official_title, overall_status,
                phase, study_type, lead_sponsor_name, lead_sponsor_class,
                enrollment_count, enrollment_type, start_date, start_date_type,
                completion_date, completion_date_type, primary_completion_date,
                interventions, conditions, locations, org_study_id,
                acronym, last_known_status, study_first_submit_date,
                study_first_post_date, last_update_post_date, collaborators,
                phases, allocation, intervention_model, primary_purpose,
                masking, arms_groups, primary_outcomes, secondary_outcomes,
                eligibility_criteria, sex, minimum_age, maximum_age,
                healthy_volunteers, central_contacts, keywords, mesh_terms,
                results_section, fda_regulated_drug, fda_regulated_device,
                ipd_sharing, has_results, condition_browse, intervention_browse,
                references, results_outcome_measures, results_adverse_events,
                results_participant_flow, results_baseline, brief_summary,
                detailed_description, why_stopped, source
            ) VALUES (
                $1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
                $31, $32, $33, $34, $35, $36, $37, $38, $39, $40,
                $41, $42, $43, $44, $45, $46, $47, $48, $49, $50,
                $51, $52, $53, $54, $55, $56, $57,
                'clinicaltrials_gov'
            )
            ON CONFLICT (nct_id) DO UPDATE SET
                molecule_id = EXCLUDED.molecule_id,
                brief_title = EXCLUDED.brief_title,
                official_title = EXCLUDED.official_title,
                overall_status = EXCLUDED.overall_status,
                phase = EXCLUDED.phase,
                study_type = EXCLUDED.study_type,
                lead_sponsor_name = EXCLUDED.lead_sponsor_name,
                lead_sponsor_class = EXCLUDED.lead_sponsor_class,
                enrollment_count = EXCLUDED.enrollment_count,
                enrollment_type = EXCLUDED.enrollment_type,
                start_date = EXCLUDED.start_date,
                completion_date = EXCLUDED.completion_date,
                completion_date_type = EXCLUDED.completion_date_type,
                primary_completion_date = EXCLUDED.primary_completion_date,
                interventions = EXCLUDED.interventions,
                conditions = EXCLUDED.conditions,
                locations = EXCLUDED.locations,
                last_known_status = EXCLUDED.last_known_status,
                last_update_post_date = EXCLUDED.last_update_post_date,
                collaborators = EXCLUDED.collaborators,
                phases = EXCLUDED.phases,
                allocation = EXCLUDED.allocation,
                intervention_model = EXCLUDED.intervention_model,
                primary_purpose = EXCLUDED.primary_purpose,
                masking = EXCLUDED.masking,
                arms_groups = EXCLUDED.arms_groups,
                primary_outcomes = EXCLUDED.primary_outcomes,
                secondary_outcomes = EXCLUDED.secondary_outcomes,
                eligibility_criteria = EXCLUDED.eligibility_criteria,
                sex = EXCLUDED.sex,
                minimum_age = EXCLUDED.minimum_age,
                maximum_age = EXCLUDED.maximum_age,
                healthy_volunteers = EXCLUDED.healthy_volunteers,
                central_contacts = EXCLUDED.central_contacts,
                keywords = EXCLUDED.keywords,
                mesh_terms = EXCLUDED.mesh_terms,
                results_section = EXCLUDED.results_section,
                fda_regulated_drug = EXCLUDED.fda_regulated_drug,
                fda_regulated_device = EXCLUDED.fda_regulated_device,
                ipd_sharing = EXCLUDED.ipd_sharing,
                has_results = EXCLUDED.has_results,
                condition_browse = EXCLUDED.condition_browse,
                intervention_browse = EXCLUDED.intervention_browse,
                references = EXCLUDED.references,
                results_outcome_measures = EXCLUDED.results_outcome_measures,
                results_adverse_events = EXCLUDED.results_adverse_events,
                results_participant_flow = EXCLUDED.results_participant_flow,
                results_baseline = EXCLUDED.results_baseline,
                brief_summary = EXCLUDED.brief_summary,
                detailed_description = EXCLUDED.detailed_description,
                why_stopped = EXCLUDED.why_stopped,
                updated_at = NOW()
        """,
            molecule_id,
            record['nct_id'],
            record['brief_title'],
            record['official_title'],
            record['overall_status'],
            record['phase'],
            record['study_type'],
            record['lead_sponsor_name'],
            record['lead_sponsor_class'],
            record['enrollment_count'],
            record['enrollment_type'],
            record['start_date'],
            record['start_date_type'],
            record['completion_date'],
            record['completion_date_type'],
            record['primary_completion_date'],
            json.dumps(interventions),
            json.dumps(conditions),
            json.dumps(locations),
            record['org_study_id'],
            record['acronym'],
            record['last_known_status'],
            record['study_first_submit_date'],
            record['study_first_post_date'],
            record['last_update_post_date'],
            json.dumps(collaborators),
            json.dumps(phases),
            record['allocation'],
            record['intervention_model'],
            record['primary_purpose'],
            record['masking'],
            json.dumps(arms_groups),
            json.dumps(primary_outcomes),
            json.dumps(secondary_outcomes),
            record['eligibility_criteria'],
            record['sex'],
            record['minimum_age'],
            record['maximum_age'],
            record['healthy_volunteers'],
            json.dumps(central_contacts),
            json.dumps(keywords),
            json.dumps(mesh_terms),
            json.dumps(results_section),
            record['fda_regulated_drug'],
            record['fda_regulated_device'],
            record['ipd_sharing'],
            record['has_results'],
            json.dumps(condition_browse),
            json.dumps(intervention_browse),
            json.dumps(references),
            json.dumps(results_outcome_measures),
            json.dumps(results_adverse_events),
            json.dumps(results_participant_flow),
            json.dumps(results_baseline),
            record['brief_summary'],
            record['detailed_description'],
            record['why_stopped']
        )

    async def process_faers_events(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze FAERS events to Silver adverse events (report-level rows)."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            # Fetch full report-level rows from bronze
            bronze_records = await conn.fetch("""
                SELECT id, safety_report_id, receive_date, receipt_date,
                       serious, serious_death, serious_hospitalization,
                       serious_lifethreatening, serious_disabling,
                       serious_life_threatening, serious_other,
                       patient_age, patient_age_unit, patient_sex, patient_weight,
                       drugs, reactions, outcomes,
                       reporter_country, occurrence_country, companynumb,
                       safety_report_version, patient_drug, patient_reaction,
                       sender_organization, receiver_organization
                FROM mol_bronze.openfda_faers
                WHERE (processed_to_silver = FALSE OR processed_to_silver IS NULL)
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1

                # Extract drug names from patient_drug JSONB array
                patient_drug = record['patient_drug']
                if isinstance(patient_drug, str):
                    patient_drug = json.loads(patient_drug)
                if not patient_drug:
                    patient_drug = []

                drug_names = set()
                for drug_entry in patient_drug:
                    if isinstance(drug_entry, dict):
                        name = drug_entry.get('medicinalproduct')
                        if name:
                            drug_names.add(name.upper())

                if not drug_names:
                    # No resolvable drug name — mark processed to avoid re-fetching
                    await conn.execute("""
                        UPDATE mol_bronze.openfda_faers
                        SET processed_to_silver = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, record['id'])
                    continue

                for drug_name in drug_names:
                    try:
                        resolution = await self.resolver.resolve(
                            drug_name,
                            IdentifierType.NAME,
                            source='openfda_faers'
                        )

                        if resolution.molecule_id:
                            # Insert the full report row into silver with molecule_id
                            await conn.execute("""
                                INSERT INTO mol_silver.adverse_events (
                                    molecule_id,
                                    safety_report_id, receive_date, receipt_date,
                                    serious, serious_death, serious_hospitalization,
                                    serious_lifethreatening, serious_disabling,
                                    serious_life_threatening, serious_other,
                                    patient_age, patient_age_unit, patient_sex, patient_weight,
                                    drugs, reactions, outcomes,
                                    reporter_country, occurrence_country, companynumb,
                                    safety_report_version, patient_drug, patient_reaction,
                                    sender_organization, receiver_organization,
                                    source
                                ) VALUES (
                                    $1::uuid,
                                    $2, $3, $4,
                                    $5, $6, $7,
                                    $8, $9,
                                    $10, $11,
                                    $12, $13, $14, $15,
                                    $16, $17, $18,
                                    $19, $20, $21,
                                    $22, $23, $24,
                                    $25, $26,
                                    'openfda_faers'
                                )
                                ON CONFLICT (molecule_id, safety_report_id) DO UPDATE SET
                                    receive_date = EXCLUDED.receive_date,
                                    receipt_date = EXCLUDED.receipt_date,
                                    serious = EXCLUDED.serious,
                                    serious_death = EXCLUDED.serious_death,
                                    serious_hospitalization = EXCLUDED.serious_hospitalization,
                                    serious_lifethreatening = EXCLUDED.serious_lifethreatening,
                                    serious_disabling = EXCLUDED.serious_disabling,
                                    serious_life_threatening = EXCLUDED.serious_life_threatening,
                                    serious_other = EXCLUDED.serious_other,
                                    patient_age = EXCLUDED.patient_age,
                                    patient_age_unit = EXCLUDED.patient_age_unit,
                                    patient_sex = EXCLUDED.patient_sex,
                                    patient_weight = EXCLUDED.patient_weight,
                                    drugs = EXCLUDED.drugs,
                                    reactions = EXCLUDED.reactions,
                                    outcomes = EXCLUDED.outcomes,
                                    reporter_country = EXCLUDED.reporter_country,
                                    occurrence_country = EXCLUDED.occurrence_country,
                                    companynumb = EXCLUDED.companynumb,
                                    safety_report_version = EXCLUDED.safety_report_version,
                                    patient_drug = EXCLUDED.patient_drug,
                                    patient_reaction = EXCLUDED.patient_reaction,
                                    sender_organization = EXCLUDED.sender_organization,
                                    receiver_organization = EXCLUDED.receiver_organization,
                                    updated_at = NOW()
                            """,
                                resolution.molecule_id,
                                record['safety_report_id'],
                                record['receive_date'],
                                record['receipt_date'],
                                record['serious'],
                                record['serious_death'],
                                record['serious_hospitalization'],
                                record['serious_lifethreatening'],
                                record['serious_disabling'],
                                record['serious_life_threatening'],
                                record['serious_other'],
                                record['patient_age'],
                                record['patient_age_unit'],
                                record['patient_sex'],
                                record['patient_weight'],
                                json.dumps(record['drugs']) if record['drugs'] is not None else None,
                                json.dumps(record['reactions']) if record['reactions'] is not None else None,
                                json.dumps(record['outcomes']) if record['outcomes'] is not None else None,
                                record['reporter_country'],
                                record['occurrence_country'],
                                record['companynumb'],
                                record['safety_report_version'],
                                json.dumps(record['patient_drug']) if record['patient_drug'] is not None else None,
                                json.dumps(record['patient_reaction']) if record['patient_reaction'] is not None else None,
                                record['sender_organization'],
                                record['receiver_organization']
                            )
                            result.molecules_updated += 1

                            if resolution.needs_review:
                                result.records_quarantined += 1
                        else:
                            await self._queue_for_resolution(
                                conn, drug_name, 'name', 'openfda_faers'
                            )
                            result.records_quarantined += 1

                    except Exception as e:
                        result.errors.append(f"FAERS report {record['safety_report_id']} drug {drug_name}: {str(e)}")
                        logger.error(f"Failed to process FAERS report {record['safety_report_id']} drug {drug_name}: {e}")

                # Mark bronze row as processed
                await conn.execute("""
                    UPDATE mol_bronze.openfda_faers
                    SET processed_to_silver = TRUE, processed_at = NOW()
                    WHERE id = $1
                """, record['id'])

    async def process_drug_labels(self, limit: int = 100) -> TransformationResult:
        """Transform Bronze drug labels to Silver."""
        result = TransformationResult(0, 0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            # Use correct column names from bronze.openfda_labels table
            bronze_records = await conn.fetch("""
                SELECT id, set_id, spl_id, application_number, brand_name,
                       generic_name, manufacturer_name, product_type, route,
                       substance_name, active_ingredient, indications_and_usage,
                       contraindications, warnings, boxed_warning, adverse_reactions,
                       drug_interactions, effective_time, dosage_and_administration,
                       warnings_and_cautions, clinical_pharmacology,
                       mechanism_of_action, pharmacodynamics, pharmacokinetics,
                       clinical_studies, overdosage, description, how_supplied,
                       geriatric_use, pediatric_use, pregnancy,
                       storage_and_handling, use_in_specific_populations,
                       dosage_forms_and_strengths, openfda_rxcui, openfda_unii,
                       openfda_pharm_class_epc, openfda_pharm_class_moa,
                       openfda_application_number, version, openfda, references,
                       nonclinical_toxicology, information_for_patients,
                       spl_medguide, laboratory_tests, pharmacogenomics,
                       nursing_mothers, openfda_upc, openfda_route,
                       openfda_spl_id, openfda_brand_name, openfda_spl_set_id,
                       openfda_package_ndc, openfda_product_ndc,
                       openfda_generic_name, openfda_product_type,
                       openfda_substance_name, openfda_manufacturer_name,
                       openfda_is_original_packager, purpose, stop_use,
                       questions, do_not_use, inactive_ingredient,
                       spl_product_data_elements, pregnancy_or_breast_feeding,
                       keep_out_of_reach_of_children,
                       package_label_principal_display_panel, risks,
                       carcinogenesis_and_mutagenesis_and_impairment_of_fertility,
                       openfda_nui, openfda_pharm_class_cs,
                       spl_unclassified_section,
                       animal_pharmacology_and_or_toxicology,
                       instructions_for_use, openfda_pharm_class_pe,
                       ask_doctor, ask_doctor_or_pharmacist
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
                molecule_id, set_id, spl_id, application_number, brand_name,
                generic_name, manufacturer_name, product_type, route,
                substance_name, active_ingredient, indications_and_usage,
                contraindications, warnings, boxed_warning, adverse_reactions,
                drug_interactions, effective_time, dosage_and_administration,
                warnings_and_cautions, clinical_pharmacology,
                mechanism_of_action, pharmacodynamics, pharmacokinetics,
                clinical_studies, overdosage, description, how_supplied,
                geriatric_use, pediatric_use, pregnancy,
                storage_and_handling, use_in_specific_populations,
                dosage_forms_and_strengths, openfda_rxcui, openfda_unii,
                openfda_pharm_class_epc, openfda_pharm_class_moa,
                openfda_application_number, version, openfda, references,
                nonclinical_toxicology, information_for_patients,
                spl_medguide, laboratory_tests, pharmacogenomics,
                nursing_mothers, openfda_upc, openfda_route,
                openfda_spl_id, openfda_brand_name, openfda_spl_set_id,
                openfda_package_ndc, openfda_product_ndc,
                openfda_generic_name, openfda_product_type,
                openfda_substance_name, openfda_manufacturer_name,
                openfda_is_original_packager, purpose, stop_use,
                questions, do_not_use, inactive_ingredient,
                spl_product_data_elements, pregnancy_or_breast_feeding,
                keep_out_of_reach_of_children,
                package_label_principal_display_panel, risks,
                carcinogenesis_and_mutagenesis_and_impairment_of_fertility,
                openfda_nui, openfda_pharm_class_cs,
                spl_unclassified_section,
                animal_pharmacology_and_or_toxicology,
                instructions_for_use, openfda_pharm_class_pe,
                ask_doctor, ask_doctor_or_pharmacist, source
            ) VALUES (
                $1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
                $31, $32, $33, $34, $35, $36, $37, $38, $39, $40,
                $41, $42, $43, $44, $45, $46, $47, $48, $49, $50,
                $51, $52, $53, $54, $55, $56, $57, $58, $59, $60,
                $61, $62, $63, $64, $65, $66, $67, $68, $69, $70,
                $71, $72, $73, $74, $75, $76, $77, $78, $79, 'openfda_labels'
            )
            ON CONFLICT (set_id, version) DO UPDATE SET
                molecule_id = EXCLUDED.molecule_id,
                brand_name = EXCLUDED.brand_name,
                generic_name = EXCLUDED.generic_name,
                manufacturer_name = EXCLUDED.manufacturer_name,
                product_type = EXCLUDED.product_type,
                route = EXCLUDED.route,
                substance_name = EXCLUDED.substance_name,
                active_ingredient = EXCLUDED.active_ingredient,
                indications_and_usage = EXCLUDED.indications_and_usage,
                contraindications = EXCLUDED.contraindications,
                warnings = EXCLUDED.warnings,
                boxed_warning = EXCLUDED.boxed_warning,
                adverse_reactions = EXCLUDED.adverse_reactions,
                drug_interactions = EXCLUDED.drug_interactions,
                effective_time = EXCLUDED.effective_time,
                dosage_and_administration = EXCLUDED.dosage_and_administration,
                warnings_and_cautions = EXCLUDED.warnings_and_cautions,
                clinical_pharmacology = EXCLUDED.clinical_pharmacology,
                mechanism_of_action = EXCLUDED.mechanism_of_action,
                pharmacodynamics = EXCLUDED.pharmacodynamics,
                pharmacokinetics = EXCLUDED.pharmacokinetics,
                clinical_studies = EXCLUDED.clinical_studies,
                overdosage = EXCLUDED.overdosage,
                description = EXCLUDED.description,
                how_supplied = EXCLUDED.how_supplied,
                geriatric_use = EXCLUDED.geriatric_use,
                pediatric_use = EXCLUDED.pediatric_use,
                pregnancy = EXCLUDED.pregnancy,
                storage_and_handling = EXCLUDED.storage_and_handling,
                use_in_specific_populations = EXCLUDED.use_in_specific_populations,
                dosage_forms_and_strengths = EXCLUDED.dosage_forms_and_strengths,
                openfda_rxcui = EXCLUDED.openfda_rxcui,
                openfda_unii = EXCLUDED.openfda_unii,
                openfda_pharm_class_epc = EXCLUDED.openfda_pharm_class_epc,
                openfda_pharm_class_moa = EXCLUDED.openfda_pharm_class_moa,
                openfda_application_number = EXCLUDED.openfda_application_number,
                openfda = EXCLUDED.openfda,
                references = EXCLUDED.references,
                nonclinical_toxicology = EXCLUDED.nonclinical_toxicology,
                information_for_patients = EXCLUDED.information_for_patients,
                spl_medguide = EXCLUDED.spl_medguide,
                laboratory_tests = EXCLUDED.laboratory_tests,
                pharmacogenomics = EXCLUDED.pharmacogenomics,
                nursing_mothers = EXCLUDED.nursing_mothers,
                openfda_upc = EXCLUDED.openfda_upc,
                openfda_route = EXCLUDED.openfda_route,
                openfda_spl_id = EXCLUDED.openfda_spl_id,
                openfda_brand_name = EXCLUDED.openfda_brand_name,
                openfda_spl_set_id = EXCLUDED.openfda_spl_set_id,
                openfda_package_ndc = EXCLUDED.openfda_package_ndc,
                openfda_product_ndc = EXCLUDED.openfda_product_ndc,
                openfda_generic_name = EXCLUDED.openfda_generic_name,
                openfda_product_type = EXCLUDED.openfda_product_type,
                openfda_substance_name = EXCLUDED.openfda_substance_name,
                openfda_manufacturer_name = EXCLUDED.openfda_manufacturer_name,
                openfda_is_original_packager = EXCLUDED.openfda_is_original_packager,
                purpose = EXCLUDED.purpose,
                stop_use = EXCLUDED.stop_use,
                questions = EXCLUDED.questions,
                do_not_use = EXCLUDED.do_not_use,
                inactive_ingredient = EXCLUDED.inactive_ingredient,
                spl_product_data_elements = EXCLUDED.spl_product_data_elements,
                pregnancy_or_breast_feeding = EXCLUDED.pregnancy_or_breast_feeding,
                keep_out_of_reach_of_children = EXCLUDED.keep_out_of_reach_of_children,
                package_label_principal_display_panel = EXCLUDED.package_label_principal_display_panel,
                risks = EXCLUDED.risks,
                carcinogenesis_and_mutagenesis_and_impairment_of_fertility = EXCLUDED.carcinogenesis_and_mutagenesis_and_impairment_of_fertility,
                openfda_nui = EXCLUDED.openfda_nui,
                openfda_pharm_class_cs = EXCLUDED.openfda_pharm_class_cs,
                spl_unclassified_section = EXCLUDED.spl_unclassified_section,
                animal_pharmacology_and_or_toxicology = EXCLUDED.animal_pharmacology_and_or_toxicology,
                instructions_for_use = EXCLUDED.instructions_for_use,
                openfda_pharm_class_pe = EXCLUDED.openfda_pharm_class_pe,
                ask_doctor = EXCLUDED.ask_doctor,
                ask_doctor_or_pharmacist = EXCLUDED.ask_doctor_or_pharmacist,
                updated_at = NOW()
        """,
            molecule_id,
            record['set_id'],
            record['spl_id'],
            record['application_number'],
            record['brand_name'],
            record['generic_name'],
            record['manufacturer_name'],
            record['product_type'],
            record['route'],
            record['substance_name'],
            record['active_ingredient'],
            record['indications_and_usage'],
            record['contraindications'],
            record['warnings'],
            record['boxed_warning'],
            record['adverse_reactions'],
            record['drug_interactions'],
            record['effective_time'],
            record['dosage_and_administration'],
            record['warnings_and_cautions'],
            record['clinical_pharmacology'],
            record['mechanism_of_action'],
            record['pharmacodynamics'],
            record['pharmacokinetics'],
            record['clinical_studies'],
            record['overdosage'],
            record['description'],
            record['how_supplied'],
            record['geriatric_use'],
            record['pediatric_use'],
            record['pregnancy'],
            record['storage_and_handling'],
            record['use_in_specific_populations'],
            record['dosage_forms_and_strengths'],
            record['openfda_rxcui'],
            record['openfda_unii'],
            record['openfda_pharm_class_epc'],
            record['openfda_pharm_class_moa'],
            record['openfda_application_number'],
            record['version'],
            record['openfda'],
            record['references'],
            record['nonclinical_toxicology'],
            record['information_for_patients'],
            record['spl_medguide'],
            record['laboratory_tests'],
            record['pharmacogenomics'],
            record['nursing_mothers'],
            record['openfda_upc'],
            record['openfda_route'],
            record['openfda_spl_id'],
            record['openfda_brand_name'],
            record['openfda_spl_set_id'],
            record['openfda_package_ndc'],
            record['openfda_product_ndc'],
            record['openfda_generic_name'],
            record['openfda_product_type'],
            record['openfda_substance_name'],
            record['openfda_manufacturer_name'],
            record['openfda_is_original_packager'],
            record['purpose'],
            record['stop_use'],
            record['questions'],
            record['do_not_use'],
            record['inactive_ingredient'],
            record['spl_product_data_elements'],
            record['pregnancy_or_breast_feeding'],
            record['keep_out_of_reach_of_children'],
            record['package_label_principal_display_panel'],
            record['risks'],
            record['carcinogenesis_and_mutagenesis_and_impairment_of_fertility'],
            record['openfda_nui'],
            record['openfda_pharm_class_cs'],
            record['spl_unclassified_section'],
            record['animal_pharmacology_and_or_toxicology'],
            record['instructions_for_use'],
            record['openfda_pharm_class_pe'],
            record['ask_doctor'],
            record['ask_doctor_or_pharmacist']
        )

        # Update molecule approval info if this is an approved drug
        if record['effective_time']:
            await conn.execute("""
                UPDATE mol_silver.molecules
                SET development_status = 'approved',
                    approval_date = COALESCE(approval_date, $2),
                    first_approval_year = COALESCE(first_approval_year, EXTRACT(YEAR FROM $2)::INTEGER),
                    updated_at = NOW()
                WHERE id = $1::uuid
                  AND (development_status IS NULL OR development_status != 'approved')
            """, molecule_id, record['effective_time'])

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
                       sequence, sequence_length, sequence_mass,
                       function_description, subcellular_location,
                       tissue_specificity, features, pdb_ids,
                       drugbank_ids, chembl_ids, genes, comments,
                       keywords, organism_lineage, organism_taxonid,
                       organism_commonname, organism_scientificname,
                       entrytype, uniprotkbid, primaryaccession,
                       proteindescription_flag,
                       proteindescription_recommendedname_fullname,
                       proteindescription_alternativenames,
                       proteindescription_recommendedname_shortnames,
                       proteindescription_recommendedname_ecnumbers,
                       proteindescription_cdantigennames,
                       proteindescription_contains,
                       proteindescription_includes,
                       organism_evidences,
                       sequence_md5, sequence_crc64, sequence_value,
                       sequence_molweight, references, annotationscore,
                       secondaryaccessions, uniprotkbcrossreferences,
                       proteinexistence
                FROM mol_bronze.uniprot
                WHERE (processed_to_silver = FALSE OR processed_to_silver IS NULL)
                ORDER BY ingested_at ASC
                LIMIT $1
            """, limit)

            for record in bronze_records:
                result.records_processed += 1
                try:
                    # Insert or update target in silver.targets with ALL bronze columns
                    await conn.execute("""
                        INSERT INTO mol_silver.targets (
                            accession, entry_name, protein_name,
                            gene_names, organism, organism_id,
                            sequence, sequence_length, sequence_mass,
                            function_description, subcellular_location,
                            tissue_specificity, features, pdb_ids,
                            drugbank_ids, chembl_ids, genes, comments,
                            keywords, organism_lineage, organism_taxonid,
                            organism_commonname, organism_scientificname,
                            entrytype, uniprotkbid, primaryaccession,
                            proteindescription_flag,
                            proteindescription_recommendedname_fullname,
                            proteindescription_alternativenames,
                            proteindescription_recommendedname_shortnames,
                            proteindescription_recommendedname_ecnumbers,
                            proteindescription_cdantigennames,
                            proteindescription_contains,
                            proteindescription_includes,
                            organism_evidences,
                            sequence_md5, sequence_crc64, sequence_value,
                            sequence_molweight, references, annotationscore,
                            secondaryaccessions, uniprotkbcrossreferences,
                            proteinexistence,
                            source
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9,
                            $10, $11, $12, $13, $14, $15, $16, $17, $18,
                            $19, $20, $21, $22, $23, $24, $25, $26,
                            $27, $28, $29, $30, $31, $32, $33, $34,
                            $35, $36, $37, $38, $39, $40, $41, $42,
                            $43,
                            'uniprot'
                        )
                        ON CONFLICT (accession) DO UPDATE SET
                            entry_name = EXCLUDED.entry_name,
                            protein_name = COALESCE(EXCLUDED.protein_name, mol_silver.targets.protein_name),
                            gene_names = EXCLUDED.gene_names,
                            organism = EXCLUDED.organism,
                            organism_id = EXCLUDED.organism_id,
                            sequence = EXCLUDED.sequence,
                            sequence_length = EXCLUDED.sequence_length,
                            sequence_mass = EXCLUDED.sequence_mass,
                            function_description = COALESCE(EXCLUDED.function_description, mol_silver.targets.function_description),
                            subcellular_location = EXCLUDED.subcellular_location,
                            tissue_specificity = EXCLUDED.tissue_specificity,
                            features = EXCLUDED.features,
                            pdb_ids = EXCLUDED.pdb_ids,
                            drugbank_ids = EXCLUDED.drugbank_ids,
                            chembl_ids = EXCLUDED.chembl_ids,
                            genes = EXCLUDED.genes,
                            comments = EXCLUDED.comments,
                            keywords = EXCLUDED.keywords,
                            organism_lineage = EXCLUDED.organism_lineage,
                            organism_taxonid = EXCLUDED.organism_taxonid,
                            organism_commonname = EXCLUDED.organism_commonname,
                            organism_scientificname = EXCLUDED.organism_scientificname,
                            entrytype = EXCLUDED.entrytype,
                            uniprotkbid = EXCLUDED.uniprotkbid,
                            primaryaccession = EXCLUDED.primaryaccession,
                            proteindescription_flag = EXCLUDED.proteindescription_flag,
                            proteindescription_recommendedname_fullname = EXCLUDED.proteindescription_recommendedname_fullname,
                            proteindescription_alternativenames = EXCLUDED.proteindescription_alternativenames,
                            proteindescription_recommendedname_shortnames = EXCLUDED.proteindescription_recommendedname_shortnames,
                            proteindescription_recommendedname_ecnumbers = EXCLUDED.proteindescription_recommendedname_ecnumbers,
                            proteindescription_cdantigennames = EXCLUDED.proteindescription_cdantigennames,
                            proteindescription_contains = EXCLUDED.proteindescription_contains,
                            proteindescription_includes = EXCLUDED.proteindescription_includes,
                            organism_evidences = EXCLUDED.organism_evidences,
                            sequence_md5 = EXCLUDED.sequence_md5,
                            sequence_crc64 = EXCLUDED.sequence_crc64,
                            sequence_value = EXCLUDED.sequence_value,
                            sequence_molweight = EXCLUDED.sequence_molweight,
                            references = EXCLUDED.references,
                            annotationscore = EXCLUDED.annotationscore,
                            secondaryaccessions = EXCLUDED.secondaryaccessions,
                            uniprotkbcrossreferences = EXCLUDED.uniprotkbcrossreferences,
                            proteinexistence = EXCLUDED.proteinexistence,
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
                        record['sequence_mass'],
                        record['function_description'],
                        record['subcellular_location'],
                        record['tissue_specificity'],
                        json.dumps(record['features']) if record['features'] is not None else None,
                        json.dumps(record['pdb_ids']) if record['pdb_ids'] is not None else None,
                        json.dumps(record['drugbank_ids']) if record['drugbank_ids'] is not None else None,
                        json.dumps(record['chembl_ids']) if record['chembl_ids'] is not None else None,
                        json.dumps(record['genes']) if record['genes'] is not None else None,
                        json.dumps(record['comments']) if record['comments'] is not None else None,
                        json.dumps(record['keywords']) if record['keywords'] is not None else None,
                        json.dumps(record['organism_lineage']) if record['organism_lineage'] is not None else None,
                        record['organism_taxonid'],
                        record['organism_commonname'],
                        record['organism_scientificname'],
                        record['entrytype'],
                        record['uniprotkbid'],
                        record['primaryaccession'],
                        record['proteindescription_flag'],
                        record['proteindescription_recommendedname_fullname'],
                        json.dumps(record['proteindescription_alternativenames']) if record['proteindescription_alternativenames'] is not None else None,
                        json.dumps(record['proteindescription_recommendedname_shortnames']) if record['proteindescription_recommendedname_shortnames'] is not None else None,
                        json.dumps(record['proteindescription_recommendedname_ecnumbers']) if record['proteindescription_recommendedname_ecnumbers'] is not None else None,
                        json.dumps(record['proteindescription_cdantigennames']) if record['proteindescription_cdantigennames'] is not None else None,
                        json.dumps(record['proteindescription_contains']) if record['proteindescription_contains'] is not None else None,
                        json.dumps(record['proteindescription_includes']) if record['proteindescription_includes'] is not None else None,
                        json.dumps(record['organism_evidences']) if record['organism_evidences'] is not None else None,
                        record['sequence_md5'],
                        record['sequence_crc64'],
                        record['sequence_value'],
                        record['sequence_molweight'],
                        json.dumps(record['references']) if record['references'] is not None else None,
                        record['annotationscore'],
                        json.dumps(record['secondaryaccessions']) if record['secondaryaccessions'] is not None else None,
                        json.dumps(record['uniprotkbcrossreferences']) if record['uniprotkbcrossreferences'] is not None else None,
                        record['proteinexistence']
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
