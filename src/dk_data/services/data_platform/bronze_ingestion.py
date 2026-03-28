"""
Bronze Ingestion Service

Transforms Raw layer JSONB responses into Bronze typed columns.
Extracts structured data while preserving original JSON for audit.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import json
import re
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class TransformResult:
    """Result of a transformation operation."""
    records_processed: int
    records_inserted: int
    records_failed: int
    errors: List[str]


class BronzeIngestionService:
    """
    Service for transforming Raw layer data into Bronze typed columns.

    Bronze layer:
    - Extracts JSON fields into typed columns
    - Preserves original JSON for audit
    - Tracks source lineage
    - Does NOT perform entity resolution (that's Silver)
    """

    def __init__(self, db_pool):
        """
        Initialize the bronze ingestion service.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool

    async def process_clinicaltrials(self, limit: int = 100) -> TransformResult:
        """Transform raw clinical trials data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            # Get unprocessed raw records
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp
                FROM mol_raw.clinicaltrials
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    # Handle both single study and search results
                    studies = []
                    if 'studies' in data:
                        studies = data['studies']
                    elif 'protocolSection' in data:
                        studies = [data]

                    for study in studies:
                        await self._insert_bronze_trial(conn, study, raw_record['id'])
                        result.records_inserted += 1

                    # Mark as processed
                    await conn.execute("""
                        UPDATE mol_raw.clinicaltrials
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process clinical trial {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_trial(self, conn, study: Dict, raw_id):
        """Insert a single clinical trial into Bronze."""
        protocol = study.get('protocolSection', {})
        id_module = protocol.get('identificationModule', {})
        status_module = protocol.get('statusModule', {})
        design_module = protocol.get('designModule', {})
        sponsor_module = protocol.get('sponsorCollaboratorsModule', {})
        eligibility_module = protocol.get('eligibilityModule', {})
        contacts_module = protocol.get('contactsLocationsModule', {})
        outcomes_module = protocol.get('outcomesModule', {})
        conditions_module = protocol.get('conditionsModule', {})
        arms_module = protocol.get('armsInterventionsModule', {})

        nct_id = id_module.get('nctId')
        if not nct_id:
            return

        # Parse dates
        start_date = self._parse_date(status_module.get('startDateStruct', {}).get('date'))
        completion_date = self._parse_date(status_module.get('completionDateStruct', {}).get('date'))

        # Get sponsor info
        lead_sponsor = sponsor_module.get('leadSponsor', {})
        collaborators = sponsor_module.get('collaborators', [])

        # Extract phases as JSONB array
        phases = design_module.get('phases', [])

        await conn.execute("""
            INSERT INTO mol_bronze.clinicaltrials (
                raw_id, nct_id, org_study_id, brief_title, official_title,
                overall_status, start_date, completion_date,
                lead_sponsor_name, lead_sponsor_class, collaborators,
                study_type, phases, allocation, intervention_model, masking,
                enrollment_count, enrollment_type,
                eligibility_criteria, minimum_age, maximum_age, sex,
                conditions, interventions, primary_outcomes, secondary_outcomes,
                locations
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27
            )
            ON CONFLICT (nct_id) DO UPDATE SET
                brief_title = EXCLUDED.brief_title,
                official_title = EXCLUDED.official_title,
                overall_status = EXCLUDED.overall_status,
                completion_date = EXCLUDED.completion_date,
                enrollment_count = EXCLUDED.enrollment_count,
                conditions = EXCLUDED.conditions,
                interventions = EXCLUDED.interventions,
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            nct_id,
            id_module.get('orgStudyIdInfo', {}).get('id'),
            id_module.get('briefTitle'),
            id_module.get('officialTitle'),
            status_module.get('overallStatus'),
            start_date,
            completion_date,
            lead_sponsor.get('name'),
            lead_sponsor.get('class'),
            json.dumps(collaborators) if collaborators else None,
            design_module.get('studyType'),
            json.dumps(phases) if phases else None,
            design_module.get('designInfo', {}).get('allocation'),
            design_module.get('designInfo', {}).get('interventionModel'),
            design_module.get('designInfo', {}).get('maskingInfo', {}).get('masking'),
            design_module.get('enrollmentInfo', {}).get('count'),
            design_module.get('enrollmentInfo', {}).get('type'),
            eligibility_module.get('eligibilityCriteria'),
            eligibility_module.get('minimumAge'),
            eligibility_module.get('maximumAge'),
            eligibility_module.get('sex'),
            json.dumps(conditions_module.get('conditions', [])) if conditions_module.get('conditions') else None,
            json.dumps(arms_module.get('interventions', [])) if arms_module.get('interventions') else None,
            json.dumps(outcomes_module.get('primaryOutcomes', [])) if outcomes_module.get('primaryOutcomes') else None,
            json.dumps(outcomes_module.get('secondaryOutcomes', [])) if outcomes_module.get('secondaryOutcomes') else None,
            json.dumps(contacts_module.get('locations', [])) if contacts_module.get('locations') else None
        )

    async def process_faers(self, limit: int = 100) -> TransformResult:
        """Transform raw FAERS data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp
                FROM mol_raw.openfda_faers
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    events = data.get('results', [])
                    for event in events:
                        await self._insert_bronze_faers(conn, event, raw_record['id'])
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.openfda_faers
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process FAERS {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_faers(self, conn, event: Dict, raw_id):
        """Insert a single FAERS event into Bronze."""
        safety_report_id = event.get('safeportid') or event.get('safetyreportid')
        if not safety_report_id:
            return

        patient = event.get('patient', {})
        drugs = patient.get('drug', [])
        reactions = patient.get('reaction', [])

        receive_date = self._parse_faers_date(event.get('receivedate'))
        receipt_date = self._parse_faers_date(event.get('receiptdate'))

        # Convert serious flags to integers (0 or 1) for the table schema
        serious = 1 if event.get('serious') == '1' else 0
        serious_death = 1 if event.get('seriousnessdeath') == '1' else 0
        serious_hospitalization = 1 if event.get('seriousnesshospitalization') == '1' else 0
        serious_life_threatening = 1 if event.get('seriousnesslifethreatening') == '1' else 0
        serious_disabling = 1 if event.get('seriousnessdisabling') == '1' else 0
        serious_other = 1 if event.get('seriousnessother') == '1' else 0

        await conn.execute("""
            INSERT INTO mol_bronze.openfda_faers (
                raw_id, safety_report_id, safety_report_version, receive_date, receipt_date,
                serious, serious_death, serious_hospitalization, serious_life_threatening,
                serious_disabling, serious_other,
                patient_age, patient_age_unit, patient_sex, patient_weight,
                patient_drug, patient_reaction,
                sender_organization, occurrence_country, companynumb
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
            )
            ON CONFLICT (safety_report_id, safety_report_version) DO UPDATE SET
                patient_drug = EXCLUDED.patient_drug,
                patient_reaction = EXCLUDED.patient_reaction,
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            safety_report_id,
            self._safe_int(event.get('safetyreportversion', 1)),
            receive_date,
            receipt_date,
            serious,
            serious_death,
            serious_hospitalization,
            serious_life_threatening,
            serious_disabling,
            serious_other,
            self._safe_float(patient.get('patientonsetage')),
            patient.get('patientonsetageunit'),
            patient.get('patientsex'),
            self._safe_float(patient.get('patientweight')),
            json.dumps(drugs) if drugs else None,
            json.dumps(reactions) if reactions else None,
            event.get('sender', {}).get('senderorganization'),
            event.get('occurcountry'),
            event.get('companynumb')
        )

    async def process_labels(self, limit: int = 100) -> TransformResult:
        """Transform raw FDA labels to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp
                FROM mol_raw.openfda_labels
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    labels = data.get('results', [])
                    for label in labels:
                        await self._insert_bronze_label(conn, label, raw_record['id'])
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.openfda_labels
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process label {raw_record['id']}: {e}")

        return result

    def _extract_drug_names_from_alternative_fields(self, label: Dict) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract drug names from alternative fields when openfda section is empty.
        
        Returns:
            Tuple of (generic_name, brand_name) extracted from alternative fields
        """
        generic_name = None
        brand_name = None
        
        # Try to extract from description field (e.g., "Ofloxacin Ophthalmic Solution USP, 0.3%")
        description = self._first_or_join(label.get('description'))
        if description:
            # Look for drug name patterns in description
            # Pattern: Drug name followed by formulation (e.g., "Ofloxacin Ophthalmic Solution")
            drug_patterns = [
                r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)*)\s+(?:Ophthalmic|Oral|Topical|Injectable|Solution|Tablet|Capsule|Cream|Ointment|Gel|Suspension|Injection)',
                r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)*)\s+(?:USP|HCl|Gluconate|Acetate)',
            ]
            for pattern in drug_patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip()
                    # Filter out common non-drug words
                    if candidate and len(candidate) > 3 and candidate not in ['Contains', 'Active', 'Purpose', 'Description']:
                        generic_name = candidate
                        logger.debug(f"Extracted generic name from description: {generic_name}")
                        break
        
        # Try to extract from active_ingredient field
        active_ingredients = label.get('active_ingredient', [])
        if active_ingredients:
            # Handle both list and string formats
            if isinstance(active_ingredients, list) and len(active_ingredients) > 0:
                first_ingredient = active_ingredients[0]
            elif isinstance(active_ingredients, str):
                first_ingredient = active_ingredients
            else:
                first_ingredient = None
            
            if first_ingredient:
                # Extract drug name from active ingredient string
                # Examples: "Ofloxacin 0.3%", "Pseudoephedrine HCl 60 mg", "Chlorhexidine Gluconate 4%"
                ingredient_text = str(first_ingredient)
                
                # Remove common prefixes
                cleaned = re.sub(r'^(?:ACTIVE INGREDIENTS?:?|Active Ingredient.*?---|BRONZE ACTIVE INGREDIENTS?:?)\s*', '', ingredient_text, flags=re.IGNORECASE)
                # Remove percentages and concentrations
                cleaned = re.sub(r'\s+\d+\.?\d*\s*%', '', cleaned)
                cleaned = re.sub(r'\s+\d+\s*(mg|g|mL|mcg|mcg/mL|mg/mL|mg/tablet)', '', cleaned, flags=re.IGNORECASE)
                # Remove parenthetical info
                cleaned = re.sub(r'\s*\([^)]+\)', '', cleaned)
                # Remove dots and ellipses used as separators
                cleaned = re.sub(r'\.{3,}', ' ', cleaned)
                cleaned = re.sub(r'\s*\.\s*$', '', cleaned)
                # Remove common label text patterns
                cleaned = re.sub(r'DESCRIPTION\s+', '', cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(r'Purpose\s+', '', cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(r'medication\s*', '', cleaned, flags=re.IGNORECASE)
                cleaned = cleaned.strip()
                
                # Extract the main drug name (usually first 1-4 words, capitalized)
                words = cleaned.split()
                if len(words) >= 1:
                    # Take first 1-4 capitalized words as drug name
                    drug_words = []
                    for word in words[:4]:
                        # Clean word
                        word = word.strip('.,:;')
                        if not word:
                            continue
                        # Include word if it starts with capital and is meaningful
                        if word and word[0].isupper() and len(word) > 2:
                            # Skip common non-drug words
                            if word.upper() not in ['ACTIVE', 'INGREDIENT', 'INGREDIENTS', 'PURPOSE', 'EACH', 'BOTTLE', 'DESCRIPTION']:
                                drug_words.append(word)
                            else:
                                break
                        elif word and word[0].isupper() and len(word) > 1:
                            drug_words.append(word)
                        else:
                            break
                    if drug_words:
                        extracted = ' '.join(drug_words)
                        # Clean up common patterns and extra spaces
                        extracted = re.sub(r'\s+', ' ', extracted).strip()
                        # Remove trailing common words
                        extracted = re.sub(r'\s+(Solution|Tablet|Capsule|Cream|Ointment|Gel)$', '', extracted, flags=re.IGNORECASE)
                        if extracted:
                            generic_name = generic_name or extracted
                            logger.debug(f"Extracted generic name from active_ingredient: {generic_name}")
        
        # Try to extract brand name from package_label_principal_display_panel
        display_panel = self._first_or_join(label.get('package_label_principal_display_panel'))
        if display_panel:
            # Look for product names (usually at the beginning, before descriptions)
            lines = display_panel.split('\n')
            for line in lines[:10]:  # Check first 10 lines
                line = line.strip()
                if line and 3 < len(line) < 100:
                    # Check if it looks like a product name (starts with capital, not all caps)
                    if line[0].isupper() and not line.isupper():
                        # Skip common label text
                        skip_patterns = ['PRINCIPAL DISPLAY', 'NDC', 'NET WT', 'NET WEIGHT', 'LABEL', 
                                        'IMAGE', 'PRINCIPAL', 'DISPLAY', 'PANEL', 'APPLICATOR', 'BOX']
                        if not any(skip in line.upper() for skip in skip_patterns):
                            # Extract first meaningful word/phrase (up to 3 words)
                            words = line.split()
                            if words:
                                # Take first 1-3 words that look like a brand name
                                brand_candidate = ' '.join(words[:3])
                                # Remove common suffixes
                                brand_candidate = re.sub(r'\s+(?:SPF|USP|HCl|CHG|NDC).*$', '', brand_candidate, flags=re.IGNORECASE)
                                if len(brand_candidate) > 2:
                                    brand_name = brand_candidate
                                    logger.debug(f"Extracted brand name from display panel: {brand_name}")
                                    break
        
        return (generic_name, brand_name)
    
    async def _insert_bronze_label(self, conn, label: Dict, raw_id):
        """Insert a single FDA label into Bronze."""
        set_id = label.get('set_id')
        if not set_id:
            openfda = label.get('openfda', {})
            set_ids = openfda.get('spl_set_id', [])
            set_id = set_ids[0] if set_ids else None

        if not set_id:
            return

        openfda = label.get('openfda', {})
        effective_time = self._parse_label_date(label.get('effective_time'))
        
        # Extract brand_name and generic_name from openfda first
        brand_name = self._first_or_none(openfda.get('brand_name'))
        generic_name = self._first_or_none(openfda.get('generic_name'))
        
        # If openfda is empty or missing names, try alternative fields
        if (not brand_name and not generic_name) or (openfda == {}):
            extracted_generic, extracted_brand = self._extract_drug_names_from_alternative_fields(label)
            generic_name = generic_name or extracted_generic
            brand_name = brand_name or extracted_brand
            if generic_name or brand_name:
                logger.info(f"Extracted drug names from alternative fields for set_id {set_id}: generic={generic_name}, brand={brand_name}")

        await conn.execute("""
            INSERT INTO mol_bronze.openfda_labels (
                raw_id, set_id, spl_id, version,
                brand_name, generic_name, manufacturer_name, application_number, product_type,
                route, substance_name,
                indications_and_usage, dosage_and_administration, contraindications,
                warnings, warnings_and_cautions, boxed_warning, adverse_reactions, drug_interactions,
                mechanism_of_action, clinical_pharmacology, pharmacodynamics, pharmacokinetics,
                effective_time, openfda
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25
            )
            ON CONFLICT (set_id, version) DO UPDATE SET
                brand_name = COALESCE(EXCLUDED.brand_name, mol_bronze.openfda_labels.brand_name),
                generic_name = COALESCE(EXCLUDED.generic_name, mol_bronze.openfda_labels.generic_name),
                boxed_warning = EXCLUDED.boxed_warning,
                adverse_reactions = EXCLUDED.adverse_reactions,
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            set_id,
            label.get('id'),
            self._safe_int(label.get('version', '1')),
            json.dumps([brand_name]) if brand_name else None,
            json.dumps([generic_name]) if generic_name else None,
            self._first_or_none(openfda.get('manufacturer_name')),
            self._first_or_none(openfda.get('application_number')),
            self._first_or_none(openfda.get('product_type')),
            json.dumps(openfda.get('route', [])) if openfda.get('route') else None,
            json.dumps(openfda.get('substance_name', [])) if openfda.get('substance_name') else None,
            self._first_or_join(label.get('indications_and_usage')),
            self._first_or_join(label.get('dosage_and_administration')),
            self._first_or_join(label.get('contraindications')),
            self._first_or_join(label.get('warnings')),
            self._first_or_join(label.get('warnings_and_cautions')),
            self._first_or_join(label.get('boxed_warning')),
            self._first_or_join(label.get('adverse_reactions')),
            self._first_or_join(label.get('drug_interactions')),
            self._first_or_join(label.get('mechanism_of_action')),
            self._first_or_join(label.get('clinical_pharmacology')),
            self._first_or_join(label.get('pharmacodynamics')),
            self._first_or_join(label.get('pharmacokinetics')),
            effective_time,
            json.dumps(openfda) if openfda else None
        )

    async def process_chembl(self, limit: int = 100) -> TransformResult:
        """Transform raw ChEMBL data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp, api_endpoint
                FROM mol_raw.chembl
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    endpoint = raw_record['api_endpoint']

                    # Handle different ChEMBL endpoints
                    if '/molecule/' in endpoint:
                        molecules = data.get('molecules', [data]) if 'molecules' not in data else data['molecules']
                        for mol in molecules:
                            await self._insert_bronze_chembl_molecule(conn, mol, raw_record['id'])
                            result.records_inserted += 1
                    elif '/activity' in endpoint:
                        activities = data.get('activities', [])
                        for activity in activities:
                            await self._insert_bronze_chembl_activity(conn, activity, raw_record['id'])
                            result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.chembl
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process ChEMBL {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_chembl_molecule(self, conn, mol: Dict, raw_id):
        """Insert a ChEMBL molecule into Bronze."""
        chembl_id = mol.get('molecule_chembl_id')
        if not chembl_id:
            return

        properties = mol.get('molecule_properties', {}) or {}
        structures = mol.get('molecule_structures', {}) or {}

        # Insert into existing mol_bronze.chembl table with correct column names
        await conn.execute("""
            INSERT INTO mol_bronze.chembl (
                molecule_chembl_id, pref_name, molecule_type, max_phase,
                molecular_formula, molecular_weight, canonical_smiles,
                standard_inchi, standard_inchi_key,
                alogp, hba, hbd, psa, num_ro5_violations,
                first_approval, indication_class, raw_id
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17
            )
            ON CONFLICT (molecule_chembl_id) DO UPDATE SET
                pref_name = COALESCE(EXCLUDED.pref_name, mol_bronze.chembl.pref_name),
                max_phase = COALESCE(EXCLUDED.max_phase, mol_bronze.chembl.max_phase),
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            chembl_id,
            mol.get('pref_name'),
            mol.get('molecule_type'),
            self._safe_int(mol.get('max_phase')),
            properties.get('full_molformula'),
            self._safe_float(properties.get('full_mwt')),
            structures.get('canonical_smiles'),
            structures.get('standard_inchi'),
            structures.get('standard_inchi_key'),
            self._safe_float(properties.get('alogp')),
            self._safe_int(properties.get('hba')),
            self._safe_int(properties.get('hbd')),
            self._safe_float(properties.get('psa')),
            self._safe_int(properties.get('num_ro5_violations')),
            self._safe_int(mol.get('first_approval')),
            mol.get('indication_class'),
            raw_id
        )

    async def _insert_bronze_chembl_activity(self, conn, activity: Dict, raw_id):
        """Insert a ChEMBL activity into Bronze - skipped as table doesn't exist."""
        # mol_bronze.chembl_activities table doesn't exist in current schema
        # Activities could be added to a future migration
        logger.debug(f"Skipping activity insert - table not implemented: {activity.get('activity_id')}")

    async def process_bindingdb(self, limit: int = 100) -> TransformResult:
        """Transform raw BindingDB data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp
                FROM mol_raw.bindingdb
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    # Handle BindingDB response format
                    ligands = data.get('affinities', data.get('ligands', [data]))
                    if not isinstance(ligands, list):
                        ligands = [ligands]

                    for ligand in ligands:
                        await self._insert_bronze_bindingdb(conn, ligand, raw_record['id'])
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.bindingdb
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process BindingDB {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_bindingdb(self, conn, ligand: Dict, raw_id):
        """Insert a BindingDB binding record into Bronze."""
        bindingdb_id = ligand.get('monomerid') or ligand.get('ligandid')
        if not bindingdb_id:
            return

        await conn.execute("""
            INSERT INTO mol_bronze.bindingdb (
                raw_id, bindingdb_id, ligand_name, smiles, inchi, inchi_key,
                target_name, target_source, target_source_id, target_organism,
                ki_nm, kd_nm, ic50_nm, ec50_nm,
                activity_type, activity_value, activity_unit,
                pmid, doi, patent_id
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
            )
            ON CONFLICT (bindingdb_id) DO UPDATE SET
                ki_nm = COALESCE(EXCLUDED.ki_nm, mol_bronze.bindingdb.ki_nm),
                kd_nm = COALESCE(EXCLUDED.kd_nm, mol_bronze.bindingdb.kd_nm),
                ic50_nm = COALESCE(EXCLUDED.ic50_nm, mol_bronze.bindingdb.ic50_nm),
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            str(bindingdb_id),
            ligand.get('name') or ligand.get('ligand_name'),
            ligand.get('smiles'),
            ligand.get('inchi'),
            ligand.get('inchi_key') or ligand.get('inchikey'),
            ligand.get('target') or ligand.get('target_name'),
            ligand.get('target_source', 'UniProt'),
            ligand.get('uniprot_id') or ligand.get('target_uniprot'),
            ligand.get('organism') or ligand.get('target_organism'),
            self._safe_float(ligand.get('ki_nm') or ligand.get('Ki (nM)')),
            self._safe_float(ligand.get('kd_nm') or ligand.get('Kd (nM)')),
            self._safe_float(ligand.get('ic50_nm') or ligand.get('IC50 (nM)')),
            self._safe_float(ligand.get('ec50_nm') or ligand.get('EC50 (nM)')),
            ligand.get('activity_type'),
            self._safe_float(ligand.get('activity_value')),
            ligand.get('activity_unit'),
            ligand.get('pmid') or ligand.get('pubmed_id'),
            ligand.get('doi'),
            ligand.get('patent_id')
        )

    async def process_ema(self, limit: int = 100) -> TransformResult:
        """Transform raw EMA data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp
                FROM mol_raw.ema
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    medicines = data.get('value', data.get('medicines', [data]))
                    if not isinstance(medicines, list):
                        medicines = [medicines]

                    for medicine in medicines:
                        await self._insert_bronze_ema(conn, medicine, raw_record['id'])
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.ema
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process EMA {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_ema(self, conn, medicine: Dict, raw_id):
        """Insert an EMA medicine record into Bronze."""
        product_number = medicine.get('productNumber') or medicine.get('product_number')
        if not product_number:
            return

        auth_date = self._parse_date(medicine.get('authorizationDate') or medicine.get('authorization_date'))
        revision_date = self._parse_date(medicine.get('revisionDate') or medicine.get('revision_date'))

        await conn.execute("""
            INSERT INTO mol_bronze.ema (
                raw_id, product_number, product_name, active_substance, inn, atc_code,
                marketing_authorization_holder, authorization_status, authorization_date, revision_date,
                medicine_type, therapeutic_area, pharmacotherapeutic_group,
                epar_url, summary_url
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
            )
            ON CONFLICT (product_number) DO UPDATE SET
                authorization_status = EXCLUDED.authorization_status,
                revision_date = EXCLUDED.revision_date,
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            product_number,
            medicine.get('name') or medicine.get('product_name'),
            medicine.get('activeSubstance') or medicine.get('active_substance'),
            medicine.get('inn'),
            medicine.get('atcCode') or medicine.get('atc_code'),
            medicine.get('marketingAuthorisationHolder') or medicine.get('holder'),
            medicine.get('authorizationStatus') or medicine.get('status'),
            auth_date,
            revision_date,
            medicine.get('medicineType') or medicine.get('type'),
            medicine.get('therapeuticArea') or medicine.get('therapeutic_area'),
            medicine.get('pharmacotherapeuticGroup'),
            medicine.get('eparUrl') or medicine.get('epar_url'),
            medicine.get('summaryUrl') or medicine.get('summary_url')
        )

    async def process_orange_book(self, limit: int = 100) -> TransformResult:
        """Transform raw Orange Book data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp, request_id
                FROM mol_raw.orange_book
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    # Orange Book data comes in different formats based on file type
                    request_id = raw_record['request_id']
                    products = data.get('products', data.get('rows', [data]))
                    if not isinstance(products, list):
                        products = [products]

                    for product in products:
                        await self._insert_bronze_orange_book(conn, product, raw_record['id'], request_id)
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.orange_book
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process Orange Book {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_orange_book(self, conn, product: Dict, raw_id, request_id: str):
        """Insert an Orange Book record into Bronze."""
        app_number = product.get('Appl_No') or product.get('application_number')
        product_number = product.get('Product_No') or product.get('product_number') or '001'
        patent_number = product.get('Patent_No') or product.get('patent_number')

        if not app_number:
            return

        approval_date = self._parse_date(product.get('Approval_Date') or product.get('approval_date'))
        patent_expiration = self._parse_date(product.get('Patent_Expire_Date_Text') or product.get('patent_expiration'))
        exclusivity_date = self._parse_date(product.get('Exclusivity_Date') or product.get('exclusivity_date'))

        await conn.execute("""
            INSERT INTO mol_bronze.orange_book (
                raw_id, application_number, product_number, ingredient, trade_name, applicant,
                strength, dosage_form, route, approval_date, te_code, rld,
                patent_number, patent_expiration, drug_substance_patent, drug_product_patent, patent_use_code,
                exclusivity_code, exclusivity_date
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19
            )
            ON CONFLICT (application_number, product_number, patent_number) DO UPDATE SET
                patent_expiration = EXCLUDED.patent_expiration,
                exclusivity_date = EXCLUDED.exclusivity_date,
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            app_number,
            product_number,
            product.get('Ingredient') or product.get('ingredient'),
            product.get('Trade_Name') or product.get('trade_name'),
            product.get('Applicant') or product.get('applicant') or product.get('Applicant_Full_Name'),
            product.get('Strength') or product.get('strength'),
            product.get('DF') or product.get('Dosage_Form') or product.get('dosage_form'),
            product.get('Route') or product.get('route'),
            approval_date,
            product.get('TE_Code') or product.get('te_code'),
            product.get('RLD') or product.get('rld'),
            patent_number,
            patent_expiration,
            product.get('Drug_Substance_Flag') == 'Y' if product.get('Drug_Substance_Flag') else None,
            product.get('Drug_Product_Flag') == 'Y' if product.get('Drug_Product_Flag') else None,
            product.get('Patent_Use_Code') or product.get('patent_use_code'),
            product.get('Exclusivity_Code') or product.get('exclusivity_code'),
            exclusivity_date
        )

    async def process_uspto_patents(self, limit: int = 100) -> TransformResult:
        """Transform raw USPTO patent data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp
                FROM mol_raw.uspto_patents
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    patents = data.get('patents', [])
                    for patent in patents:
                        await self._insert_bronze_uspto_patent(conn, patent, raw_record['id'])
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.uspto_patents
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process USPTO patent {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_uspto_patent(self, conn, patent: Dict, raw_id):
        """Insert a USPTO patent record into Bronze."""
        patent_number = patent.get('patent_number')
        if not patent_number:
            return

        patent_date = self._parse_date(patent.get('patent_date'))

        # Extract CPC codes
        cpc_codes = patent.get('cpcs', [])
        if isinstance(cpc_codes, list) and len(cpc_codes) > 0:
            cpc_codes = [c.get('cpc_group_id') or c for c in cpc_codes if c]

        # Check if pharma-related (A61K, A61P, C07D classifications)
        is_pharma = any(
            str(cpc).startswith(('A61K', 'A61P', 'C07D', 'C07K'))
            for cpc in cpc_codes
        ) if cpc_codes else False

        # Extract inventors
        inventors = patent.get('inventors', [])
        if isinstance(inventors, list):
            inventors = [
                {
                    'first_name': inv.get('inventor_first_name'),
                    'last_name': inv.get('inventor_last_name'),
                    'city': inv.get('inventor_city'),
                    'country': inv.get('inventor_country')
                }
                for inv in inventors
            ]

        await conn.execute("""
            INSERT INTO mol_bronze.uspto_patents (
                raw_id, patent_number, patent_title, patent_abstract, patent_date,
                patent_type, patent_kind, cpc_codes,
                assignee_organization, assignee_type,
                inventors, num_claims, is_pharma_related
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
            )
            ON CONFLICT (patent_number) DO UPDATE SET
                patent_title = EXCLUDED.patent_title,
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            patent_number,
            patent.get('patent_title'),
            patent.get('patent_abstract'),
            patent_date,
            patent.get('patent_type'),
            patent.get('patent_kind'),
            json.dumps(cpc_codes) if cpc_codes else None,
            patent.get('assignees', [{}])[0].get('assignee_organization') if patent.get('assignees') else None,
            patent.get('assignees', [{}])[0].get('assignee_type') if patent.get('assignees') else None,
            json.dumps(inventors) if inventors else None,
            self._safe_int(patent.get('patent_num_claims')),
            is_pharma
        )

    async def process_pubchem(self, limit: int = 100) -> TransformResult:
        """Transform raw PubChem data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp
                FROM mol_raw.pubchem
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    # Handle PubChem compound response format
                    compounds = data.get('PC_Compounds', [])
                    if not compounds and 'PropertyTable' in data:
                        # Property table response
                        props = data.get('PropertyTable', {}).get('Properties', [])
                        for prop in props:
                            await self._insert_bronze_pubchem_property(conn, prop, raw_record['id'])
                            result.records_inserted += 1
                    else:
                        for compound in compounds:
                            await self._insert_bronze_pubchem(conn, compound, raw_record['id'])
                            result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.pubchem
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process PubChem {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_pubchem(self, conn, compound: Dict, raw_id):
        """Insert a PubChem compound into Bronze."""
        cid = compound.get('id', {}).get('id', {}).get('cid')
        if not cid:
            return

        props = {}
        for prop_list in compound.get('props', []):
            urn = prop_list.get('urn', {})
            label = urn.get('label', '')
            name = urn.get('name', '')
            value = prop_list.get('value', {})
            # Get first value type
            val = value.get('sval') or value.get('fval') or value.get('ival')
            if label or name:
                props[f"{label}_{name}".strip('_')] = val

        await conn.execute("""
            INSERT INTO mol_bronze.pubchem (
                raw_id, cid, iupac_name, title,
                canonical_smiles, isomeric_smiles, inchi, inchikey,
                molecular_formula, molecular_weight, exact_mass,
                xlogp, hbond_acceptor, hbond_donor, tpsa,
                rotatable_bond, heavy_atom_count, complexity, charge
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19
            )
            ON CONFLICT (cid) DO UPDATE SET
                canonical_smiles = COALESCE(EXCLUDED.canonical_smiles, mol_bronze.pubchem.canonical_smiles),
                inchikey = COALESCE(EXCLUDED.inchikey, mol_bronze.pubchem.inchikey),
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            cid,
            props.get('IUPAC Name_Preferred'),
            props.get('Title_'),
            props.get('SMILES_Canonical'),
            props.get('SMILES_Isomeric'),
            props.get('InChI_Standard'),
            props.get('InChIKey_Standard'),
            props.get('Molecular Formula_'),
            self._safe_float(props.get('Molecular Weight_')),
            self._safe_float(props.get('Mass_Exact')),
            self._safe_float(props.get('Log P_XLogP3')),
            self._safe_int(props.get('Hydrogen Bond Acceptor Count_')),
            self._safe_int(props.get('Hydrogen Bond Donor Count_')),
            self._safe_float(props.get('Topological Polar Surface Area_')),
            self._safe_int(props.get('Rotatable Bond Count_')),
            self._safe_int(props.get('Heavy Atom Count_')),
            self._safe_float(props.get('Complexity_')),
            self._safe_int(props.get('Charge_'))
        )

    async def _insert_bronze_pubchem_property(self, conn, prop: Dict, raw_id):
        """Insert PubChem property table data into Bronze."""
        cid = prop.get('CID')
        if not cid:
            return

        await conn.execute("""
            INSERT INTO mol_bronze.pubchem (
                raw_id, cid, canonical_smiles, isomeric_smiles,
                inchi, inchikey, molecular_formula, molecular_weight,
                xlogp, hbond_acceptor, hbond_donor, tpsa,
                rotatable_bond, heavy_atom_count, complexity
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
            )
            ON CONFLICT (cid) DO UPDATE SET
                canonical_smiles = COALESCE(EXCLUDED.canonical_smiles, mol_bronze.pubchem.canonical_smiles),
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            cid,
            prop.get('CanonicalSMILES'),
            prop.get('IsomericSMILES'),
            prop.get('InChI'),
            prop.get('InChIKey'),
            prop.get('MolecularFormula'),
            self._safe_float(prop.get('MolecularWeight')),
            self._safe_float(prop.get('XLogP')),
            self._safe_int(prop.get('HBondAcceptorCount')),
            self._safe_int(prop.get('HBondDonorCount')),
            self._safe_float(prop.get('TPSA')),
            self._safe_int(prop.get('RotatableBondCount')),
            self._safe_int(prop.get('HeavyAtomCount')),
            self._safe_float(prop.get('Complexity'))
        )

    async def process_sider(self, limit: int = 100) -> TransformResult:
        """Transform raw SIDER data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp, request_id
                FROM mol_raw.sider
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    # SIDER data can be in various formats
                    effects = data.get('effects', data.get('rows', [data]))
                    if not isinstance(effects, list):
                        effects = [effects]

                    for effect in effects:
                        await self._insert_bronze_sider(conn, effect, raw_record['id'])
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.sider
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process SIDER {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_sider(self, conn, effect: Dict, raw_id):
        """Insert a SIDER side effect into Bronze."""
        stitch_id = effect.get('stitch_id') or effect.get('cid') or effect.get('compound_id')
        if not stitch_id:
            return

        await conn.execute("""
            INSERT INTO mol_bronze.sider (
                raw_id, stitch_id, drug_name,
                meddra_concept_type, meddra_umls_id, meddra_concept_name,
                side_effect_name, frequency, frequency_lower, frequency_upper
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
            raw_id,
            str(stitch_id),
            effect.get('drug_name') or effect.get('name'),
            effect.get('meddra_type') or effect.get('concept_type'),
            effect.get('umls_id') or effect.get('meddra_id'),
            effect.get('meddra_name') or effect.get('concept_name'),
            effect.get('side_effect') or effect.get('effect_name'),
            effect.get('frequency'),
            self._safe_float(effect.get('freq_lower') or effect.get('frequency_lower')),
            self._safe_float(effect.get('freq_upper') or effect.get('frequency_upper'))
        )

    async def process_who_inn(self, limit: int = 100) -> TransformResult:
        """Transform raw WHO INN data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp
                FROM mol_raw.who_inn
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    # Handle PubChem synonyms response (used for INN lookup)
                    synonyms = data.get('InformationList', {}).get('Information', [])
                    if synonyms:
                        for info in synonyms:
                            await self._insert_bronze_who_inn_from_pubchem(conn, info, raw_record['id'])
                            result.records_inserted += 1
                    else:
                        # Direct INN data format
                        entries = data.get('entries', [data])
                        for entry in entries if isinstance(entries, list) else [entries]:
                            await self._insert_bronze_who_inn(conn, entry, raw_record['id'])
                            result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.who_inn
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process WHO INN {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_who_inn(self, conn, entry: Dict, raw_id):
        """Insert WHO INN entry into Bronze."""
        inn_name = entry.get('inn_name') or entry.get('name')
        if not inn_name:
            return

        research_codes = entry.get('research_codes', [])
        if isinstance(research_codes, str):
            research_codes = [research_codes]

        await conn.execute("""
            INSERT INTO mol_bronze.who_inn (
                raw_id, inn_name, inn_latin, inn_list_number, inn_year,
                cas_number, molecular_formula, smiles, inchi_key,
                inn_stem, stem_definition, research_codes, synonyms, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (inn_name) DO UPDATE SET
                research_codes = COALESCE(EXCLUDED.research_codes, mol_bronze.who_inn.research_codes),
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            inn_name,
            entry.get('inn_latin'),
            self._safe_int(entry.get('list_number')),
            self._safe_int(entry.get('year')),
            entry.get('cas_number'),
            entry.get('molecular_formula'),
            entry.get('smiles'),
            entry.get('inchi_key') or entry.get('inchikey'),
            entry.get('stem'),
            entry.get('stem_definition'),
            json.dumps(research_codes) if research_codes else None,
            json.dumps(entry.get('synonyms', [])) if entry.get('synonyms') else None,
            entry.get('status', 'published')
        )

    async def _insert_bronze_who_inn_from_pubchem(self, conn, info: Dict, raw_id):
        """Extract INN from PubChem synonyms response."""
        synonyms = info.get('Synonym', [])
        if not synonyms:
            return

        # Find INN name (usually first synonym or look for specific patterns)
        inn_name = None
        research_codes = []

        for syn in synonyms:
            # Research codes often have patterns like XX-#### or ABC-####
            if any(pattern in syn for pattern in ['-', ' ']):
                if syn[0].isupper() and any(c.isdigit() for c in syn):
                    research_codes.append(syn)
            elif not inn_name and syn.islower():
                # INN names are typically lowercase
                inn_name = syn

        if not inn_name and synonyms:
            inn_name = synonyms[0]

        if inn_name:
            await conn.execute("""
                INSERT INTO mol_bronze.who_inn (
                    raw_id, inn_name, research_codes, synonyms
                ) VALUES ($1, $2, $3, $4)
                ON CONFLICT (inn_name) DO UPDATE SET
                    research_codes = COALESCE(EXCLUDED.research_codes, mol_bronze.who_inn.research_codes),
                    synonyms = COALESCE(EXCLUDED.synonyms, mol_bronze.who_inn.synonyms),
                    processed_to_silver = FALSE,
                    ingested_at = NOW()
            """,
                raw_id,
                inn_name,
                json.dumps(research_codes[:10]) if research_codes else None,
                json.dumps(synonyms[:20])
            )

    async def process_uniprot(self, limit: int = 100) -> TransformResult:
        """Transform raw UniProt data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp
                FROM mol_raw.uniprot
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    # Handle single protein or search results
                    if 'results' in data:
                        proteins = data['results']
                    else:
                        proteins = [data]

                    for protein in proteins:
                        await self._insert_bronze_uniprot(conn, protein, raw_record['id'])
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.uniprot
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process UniProt {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_uniprot(self, conn, protein: Dict, raw_id):
        """Insert a UniProt protein into Bronze."""
        accession = protein.get('primaryAccession') or protein.get('accession')
        if not accession:
            return

        # Extract gene names
        genes = protein.get('genes', [])
        gene_names = []
        for gene in genes:
            if gene.get('geneName'):
                gene_names.append(gene['geneName'].get('value'))

        # Extract organism info
        organism = protein.get('organism', {})

        # Extract cross-references
        xrefs = protein.get('uniProtKBCrossReferences', [])
        pdb_ids = [x.get('id') for x in xrefs if x.get('database') == 'PDB']
        drugbank_ids = [x.get('id') for x in xrefs if x.get('database') == 'DrugBank']
        chembl_ids = [x.get('id') for x in xrefs if x.get('database') == 'ChEMBL']

        # Extract function
        function_desc = None
        comments = protein.get('comments', [])
        for comment in comments:
            if comment.get('commentType') == 'FUNCTION':
                texts = comment.get('texts', [])
                if texts:
                    function_desc = texts[0].get('value')

        # Sequence info
        sequence = protein.get('sequence', {})

        await conn.execute("""
            INSERT INTO mol_bronze.uniprot (
                raw_id, accession, entry_name, protein_name,
                gene_names, organism, organism_id,
                sequence, sequence_length, sequence_mass,
                function_description, features,
                pdb_ids, drugbank_ids, chembl_ids
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
            )
            ON CONFLICT (accession) DO UPDATE SET
                protein_name = COALESCE(EXCLUDED.protein_name, mol_bronze.uniprot.protein_name),
                gene_names = COALESCE(EXCLUDED.gene_names, mol_bronze.uniprot.gene_names),
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            accession,
            protein.get('uniProtkbId'),
            protein.get('proteinDescription', {}).get('recommendedName', {}).get('fullName', {}).get('value'),
            json.dumps(gene_names) if gene_names else None,
            organism.get('scientificName'),
            organism.get('taxonId'),
            sequence.get('value'),
            sequence.get('length'),
            sequence.get('molWeight'),
            function_desc,
            json.dumps(protein.get('features', [])) if protein.get('features') else None,
            json.dumps(pdb_ids) if pdb_ids else None,
            json.dumps(drugbank_ids) if drugbank_ids else None,
            json.dumps(chembl_ids) if chembl_ids else None
        )

    async def process_kegg(self, limit: int = 100) -> TransformResult:
        """Transform raw KEGG Drug data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp
                FROM mol_raw.kegg_drug
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    # KEGG returns flat text format, parse it
                    entries = data.get('entries', [data])
                    for entry in entries if isinstance(entries, list) else [entries]:
                        await self._insert_bronze_kegg(conn, entry, raw_record['id'])
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.kegg_drug
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process KEGG {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_kegg(self, conn, entry: Dict, raw_id):
        """Insert a KEGG Drug entry into Bronze."""
        kegg_id = entry.get('entry') or entry.get('kegg_id') or entry.get('id')
        if not kegg_id:
            return

        await conn.execute("""
            INSERT INTO mol_bronze.kegg_drug (
                raw_id, kegg_id, name, formula, exact_mass,
                smiles, inchi, inchi_key,
                drug_class, atc_codes, therapeutic_target,
                targets, pathways, enzymes,
                drugbank_id, pubchem_sid, chembl_id, cas_number,
                research_codes, synonyms
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
            )
            ON CONFLICT (kegg_id) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, mol_bronze.kegg_drug.name),
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            kegg_id,
            entry.get('name'),
            entry.get('formula'),
            self._safe_float(entry.get('exact_mass')),
            entry.get('smiles'),
            entry.get('inchi'),
            entry.get('inchi_key') or entry.get('inchikey'),
            json.dumps(entry.get('drug_class', [])) if entry.get('drug_class') else None,
            json.dumps(entry.get('atc_codes', [])) if entry.get('atc_codes') else None,
            entry.get('target') or entry.get('therapeutic_target'),
            json.dumps(entry.get('targets', [])) if entry.get('targets') else None,
            json.dumps(entry.get('pathways', [])) if entry.get('pathways') else None,
            json.dumps(entry.get('enzymes', [])) if entry.get('enzymes') else None,
            entry.get('drugbank_id'),
            self._safe_int(entry.get('pubchem_sid')),
            entry.get('chembl_id'),
            entry.get('cas_number'),
            json.dumps(entry.get('research_codes', [])) if entry.get('research_codes') else None,
            json.dumps(entry.get('synonyms', [])) if entry.get('synonyms') else None
        )

    async def process_rxnorm(self, limit: int = 100) -> TransformResult:
        """Transform raw RxNorm data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp, api_endpoint
                FROM mol_raw.rxnorm
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    # Handle different RxNorm response formats
                    if 'idGroup' in data:
                        # rxcui lookup response
                        await self._insert_bronze_rxnorm_concept(conn, data, raw_record['id'])
                        result.records_inserted += 1
                    elif 'properties' in data:
                        # Concept properties response
                        await self._insert_bronze_rxnorm_from_properties(conn, data, raw_record['id'])
                        result.records_inserted += 1
                    elif 'relatedGroup' in data:
                        # Related concepts response
                        for group in data.get('relatedGroup', {}).get('conceptGroup', []):
                            for prop in group.get('conceptProperties', []):
                                await self._insert_bronze_rxnorm_related(conn, prop, raw_record['id'])
                                result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.rxnorm
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process RxNorm {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_rxnorm_concept(self, conn, data: Dict, raw_id):
        """Insert RxNorm concept from idGroup response."""
        id_group = data.get('idGroup', {})
        rxcui = id_group.get('rxnormId', [None])[0]
        if not rxcui:
            return

        await conn.execute("""
            INSERT INTO mol_bronze.rxnorm_concepts (
                raw_id, rxcui, name, tty
            ) VALUES ($1, $2, $3, $4)
            ON CONFLICT (rxcui) DO UPDATE SET
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            rxcui,
            id_group.get('name'),
            id_group.get('tty')
        )

    async def _insert_bronze_rxnorm_from_properties(self, conn, data: Dict, raw_id):
        """Insert RxNorm concept from properties response."""
        props = data.get('properties', {})
        rxcui = props.get('rxcui')
        if not rxcui:
            return

        await conn.execute("""
            INSERT INTO mol_bronze.rxnorm_concepts (
                raw_id, rxcui, name, tty, synonym, suppress
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (rxcui) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, mol_bronze.rxnorm_concepts.name),
                tty = COALESCE(EXCLUDED.tty, mol_bronze.rxnorm_concepts.tty),
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            rxcui,
            props.get('name'),
            props.get('tty'),
            props.get('synonym'),
            props.get('suppress')
        )

    async def _insert_bronze_rxnorm_related(self, conn, prop: Dict, raw_id):
        """Insert RxNorm related concept."""
        rxcui = prop.get('rxcui')
        if not rxcui:
            return

        await conn.execute("""
            INSERT INTO mol_bronze.rxnorm_concepts (
                raw_id, rxcui, name, tty, synonym
            ) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (rxcui) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, mol_bronze.rxnorm_concepts.name),
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            rxcui,
            prop.get('name'),
            prop.get('tty'),
            prop.get('synonym')
        )

    async def process_tdc_admet(self, limit: int = 100) -> TransformResult:
        """Transform raw TDC ADMET data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp, request_id
                FROM mol_raw.tdc_admet
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    # TDC data typically has records with SMILES and values
                    dataset_name = raw_record['request_id'].replace('tdc_admet_', '') if raw_record.get('request_id') else 'unknown'
                    records = data.get('data', data.get('records', [data]))

                    for record in records if isinstance(records, list) else [records]:
                        await self._insert_bronze_tdc_admet(conn, record, raw_id=raw_record['id'], dataset_name=dataset_name)
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.tdc_admet
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process TDC ADMET {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_tdc_admet(self, conn, record: Dict, raw_id, dataset_name: str):
        """Insert TDC ADMET record into Bronze."""
        smiles = record.get('Drug') or record.get('smiles') or record.get('SMILES')
        if not smiles:
            return

        compound_id = record.get('Drug_ID') or record.get('compound_id') or smiles[:50]
        property_value = record.get('Y') or record.get('value') or record.get('label')

        # Determine property category from dataset name
        category_map = {
            'Caco2': 'absorption', 'HIA': 'absorption', 'Pgp': 'absorption', 'Bioavailability': 'absorption',
            'Lipophilicity': 'distribution', 'BBB': 'distribution', 'PPBR': 'distribution', 'VDss': 'distribution',
            'CYP': 'metabolism', 'Half_Life': 'metabolism', 'Clearance': 'excretion',
            'hERG': 'toxicity', 'AMES': 'toxicity', 'DILI': 'toxicity', 'LD50': 'toxicity',
            'Carcinogens': 'toxicity', 'ClinTox': 'toxicity', 'Solubility': 'absorption'
        }
        category = next((v for k, v in category_map.items() if k in dataset_name), 'other')

        await conn.execute("""
            INSERT INTO mol_bronze.tdc_admet (
                raw_id, compound_id, smiles, inchi_key,
                dataset_name, dataset_type, property_name,
                property_value, property_category
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
            raw_id,
            compound_id,
            smiles,
            record.get('InChIKey') or record.get('inchi_key'),
            dataset_name,
            category,
            dataset_name,
            self._safe_float(property_value),
            category
        )

    async def process_pharmgkb(self, limit: int = 100) -> TransformResult:
        """Transform raw PharmGKB data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp, api_endpoint
                FROM mol_raw.pharmgkb
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    # Handle different PharmGKB response types
                    items = data.get('data', [data])
                    if not isinstance(items, list):
                        items = [items]

                    for item in items:
                        await self._insert_bronze_pharmgkb(conn, item, raw_record['id'])
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.pharmgkb
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process PharmGKB {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_pharmgkb(self, conn, item: Dict, raw_id):
        """Insert PharmGKB entity into Bronze."""
        pharmgkb_id = item.get('id') or item.get('pharmgkbId')
        if not pharmgkb_id:
            return

        # Extract cross-references
        xrefs = item.get('crossReferences', {})

        await conn.execute("""
            INSERT INTO mol_bronze.pharmgkb (
                raw_id, pharmgkb_id, name, entity_type,
                drugbank_id, chembl_id, rxnorm_id, pubchem_cid, cas_number,
                drug_type, smiles, inchi_key,
                clinical_annotations, dosing_guidelines, drug_labels,
                variant_annotations, pathways
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17
            )
            ON CONFLICT (pharmgkb_id) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, mol_bronze.pharmgkb.name),
                clinical_annotations = COALESCE(EXCLUDED.clinical_annotations, mol_bronze.pharmgkb.clinical_annotations),
                processed_to_silver = FALSE,
                ingested_at = NOW()
        """,
            raw_id,
            pharmgkb_id,
            item.get('name'),
            item.get('type') or item.get('objCls'),
            xrefs.get('DrugBank', [None])[0] if xrefs.get('DrugBank') else None,
            xrefs.get('ChEMBL', [None])[0] if xrefs.get('ChEMBL') else None,
            xrefs.get('RxNorm', [None])[0] if xrefs.get('RxNorm') else None,
            self._safe_int(xrefs.get('PubChem Compound', [None])[0]) if xrefs.get('PubChem Compound') else None,
            xrefs.get('CAS', [None])[0] if xrefs.get('CAS') else None,
            item.get('drugType'),
            item.get('smiles'),
            item.get('inchiKey'),
            json.dumps(item.get('clinicalAnnotations', [])) if item.get('clinicalAnnotations') else None,
            json.dumps(item.get('dosingGuidelines', [])) if item.get('dosingGuidelines') else None,
            json.dumps(item.get('drugLabels', [])) if item.get('drugLabels') else None,
            json.dumps(item.get('variantAnnotations', [])) if item.get('variantAnnotations') else None,
            json.dumps(item.get('pathways', [])) if item.get('pathways') else None
        )

    async def process_websearch(self, limit: int = 100) -> TransformResult:
        """Transform raw WebSearch data to Bronze."""
        result = TransformResult(0, 0, 0, [])

        async with self.db_pool.acquire() as conn:
            raw_records = await conn.fetch("""
                SELECT id, response_body, request_timestamp, request_params
                FROM mol_raw.websearch
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            for raw_record in raw_records:
                result.records_processed += 1
                try:
                    data = raw_record['response_body']
                    if isinstance(data, str):
                        data = json.loads(data)

                    params = raw_record['request_params']
                    if isinstance(params, str):
                        params = json.loads(params)

                    search_query = params.get('q', '') if params else ''

                    # Handle different search result formats
                    articles = data.get('articles', data.get('results', data.get('organic_results', [])))

                    for idx, article in enumerate(articles if isinstance(articles, list) else []):
                        await self._insert_bronze_websearch(conn, article, raw_record['id'], search_query, idx)
                        result.records_inserted += 1

                    await conn.execute("""
                        UPDATE mol_raw.websearch
                        SET processed_to_bronze = TRUE, processed_at = NOW()
                        WHERE id = $1
                    """, raw_record['id'])

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"Record {raw_record['id']}: {str(e)}")
                    logger.error(f"Failed to process WebSearch {raw_record['id']}: {e}")

        return result

    async def _insert_bronze_websearch(self, conn, article: Dict, raw_id, search_query: str, rank: int):
        """Insert web search result into Bronze."""
        url = article.get('url') or article.get('link')
        if not url:
            return

        # Parse publication date
        pub_date = None
        date_str = article.get('publishedAt') or article.get('date') or article.get('publication_date')
        if date_str:
            pub_date = self._parse_date(date_str[:10])

        await conn.execute("""
            INSERT INTO mol_bronze.websearch_results (
                raw_id, search_query, search_engine, search_type,
                result_url, result_title, result_snippet, result_rank, result_domain,
                publication_date, authors, source_name, relevance_score
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        """,
            raw_id,
            search_query,
            article.get('source', {}).get('name', 'web') if isinstance(article.get('source'), dict) else 'web',
            'news' if 'news' in str(article.get('source', '')).lower() else 'general',
            url,
            article.get('title'),
            article.get('description') or article.get('snippet'),
            rank + 1,
            url.split('/')[2] if '/' in url else url,
            pub_date,
            json.dumps(article.get('authors', [])) if article.get('authors') else None,
            article.get('source', {}).get('name') if isinstance(article.get('source'), dict) else article.get('source'),
            self._safe_float(article.get('score') or article.get('relevance'))
        )

    async def process_all_sources(self, limit_per_source: int = 100) -> Dict[str, TransformResult]:
        """Process all data sources."""
        results = {}

        # Process each source - complete list of all 16 data sources
        processors = [
            ('clinical_trials', self.process_clinicaltrials),
            ('faers', self.process_faers),
            ('labels', self.process_labels),
            ('chembl', self.process_chembl),
            ('bindingdb', self.process_bindingdb),
            ('ema', self.process_ema),
            ('orange_book', self.process_orange_book),
            ('uspto_patents', self.process_uspto_patents),
            # New processors for complete medallion architecture
            ('pubchem', self.process_pubchem),
            ('sider', self.process_sider),
            ('who_inn', self.process_who_inn),
            ('uniprot', self.process_uniprot),
            ('kegg', self.process_kegg),
            ('rxnorm', self.process_rxnorm),
            ('tdc_admet', self.process_tdc_admet),
            ('pharmgkb', self.process_pharmgkb),
            ('websearch', self.process_websearch),
        ]

        for source_name, processor in processors:
            try:
                results[source_name] = await processor(limit_per_source)
                logger.info(f"Processed {source_name}: {results[source_name].records_inserted} inserted")
            except Exception as e:
                logger.error(f"Failed to process {source_name}: {e}")
                results[source_name] = TransformResult(0, 0, 0, [str(e)])

        return results

    # Helper methods
    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime."""
        if not date_str:
            return None
        try:
            # Handle various formats
            for fmt in ['%Y-%m-%d', '%Y-%m', '%B %Y', '%Y']:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            return None
        except Exception:
            return None

    @staticmethod
    def _parse_faers_date(date_str: Optional[str]) -> Optional[datetime]:
        """Parse FAERS date format (YYYYMMDD)."""
        if not date_str or len(date_str) < 8:
            return None
        try:
            return datetime.strptime(date_str[:8], '%Y%m%d')
        except ValueError:
            return None

    @staticmethod
    def _parse_label_date(date_str: Optional[str]) -> Optional[datetime]:
        """Parse FDA label date format (YYYYMMDD)."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str[:8], '%Y%m%d')
        except ValueError:
            return None

    @staticmethod
    def _extract_phases(phases: List[str]) -> Optional[str]:
        """Extract phase string from phases list."""
        if not phases:
            return None
        # Return highest phase
        phase_order = ['Phase 4', 'Phase 3', 'Phase 2', 'Phase 1', 'Early Phase 1', 'Not Applicable']
        for phase in phase_order:
            if phase in phases:
                return phase
        return phases[0] if phases else None

    @staticmethod
    def _extract_countries(locations: List[Dict]) -> List[str]:
        """Extract unique countries from locations."""
        countries = set()
        for loc in locations:
            country = loc.get('country')
            if country:
                countries.add(country)
        return list(countries)

    @staticmethod
    def _first_or_none(lst: Optional[List]) -> Optional[str]:
        """Return first element or None."""
        if lst and len(lst) > 0:
            return lst[0]
        return None

    @staticmethod
    def _first_or_join(lst: Optional[List[str]], sep: str = '\n\n') -> Optional[str]:
        """Return first element or join all."""
        if not lst:
            return None
        if len(lst) == 1:
            return lst[0]
        return sep.join(lst)

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """Safely convert to float."""
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(val) -> Optional[int]:
        """Safely convert to int, handling float strings like '4.0'."""
        if val is None:
            return None
        try:
            # First try direct int conversion
            return int(val)
        except (ValueError, TypeError):
            try:
                # Try converting via float (handles "4.0" -> 4)
                return int(float(val))
            except (ValueError, TypeError):
                return None
