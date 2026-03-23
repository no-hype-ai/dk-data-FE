"""DEPRECATED: On-demand Silver + Gold refresher.

THIS MODULE IS DEPRECATED. Silver transformation now flows through the proper
medallion pipeline: raw → BronzeTransformer → SilverTransformation (which uses
IdentifierResolver for entity linking).

The base_tool.py data tools gateway was updated to call SilverTransformation
instead of this refresher. This file is kept only for backward compatibility
with any remaining callers. New code should use SilverTransformation directly.

The gold refresh methods (_refresh_gold_*) may still be useful and could be
extracted into a standalone GoldRefresher if needed.
"""

import json
import uuid
from datetime import datetime, date
from typing import Optional

from loguru import logger


class SilverGoldRefresher:
    """Refreshes silver and gold layers for a molecule after bronze ingestion."""

    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def refresh(self, drug_name: str, source_name: str, api_response: dict) -> None:
        """Refresh silver + gold for a molecule after new data arrives.

        Args:
            drug_name: The drug/molecule name from the MCP request.
            source_name: Which MCP source provided the data.
            api_response: The raw API response (used to extract silver-level data).
        """
        if not drug_name:
            return

        # 1. Resolve or create molecule in silver.molecules
        molecule_id = await self._resolve_molecule(drug_name, source_name)
        if not molecule_id:
            return

        # 2. Source-specific silver upserts
        handler = self._SILVER_HANDLERS.get(source_name)
        if handler:
            try:
                await handler(self, molecule_id, api_response)
            except Exception as e:
                logger.error(f"Silver refresh failed for {source_name}: {e}")

        # 3. Refresh gold aggregates for this molecule
        try:
            await self._refresh_gold(molecule_id, drug_name)
        except Exception as e:
            logger.error(f"Gold refresh failed for {drug_name}: {e}")

    # -------------------------------------------------------------------------
    # Molecule resolution
    # -------------------------------------------------------------------------

    async def _resolve_molecule(self, drug_name: str, source_name: str) -> Optional[str]:
        """Find or create a silver.molecules record for the given drug name."""
        normalized = drug_name.lower().strip()

        async with self.db_pool.acquire() as conn:
            # Try exact match on canonical_name
            row = await conn.fetchrow(
                "SELECT molecule_id FROM mol_silver.molecules WHERE LOWER(canonical_name) = $1",
                normalized,
            )
            if row:
                return str(row["molecule_id"])

            # Try alias match
            row = await conn.fetchrow(
                "SELECT molecule_id FROM mol_silver.molecule_aliases WHERE alias_name_normalized = $1",
                normalized,
            )
            if row:
                return str(row["molecule_id"])

            # Create new molecule
            mol_id = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO mol_silver.molecules (molecule_id, canonical_name, source_count)
                VALUES ($1, $2, 1)
            """, mol_id, drug_name)

            # Add alias
            await conn.execute("""
                INSERT INTO mol_silver.molecule_aliases
                (molecule_id, alias_name, alias_type, alias_name_normalized, source)
                VALUES ($1, $2, 'generic_name', $3, $4)
                ON CONFLICT DO NOTHING
            """, mol_id, drug_name, normalized, source_name)

            logger.info(f"Created silver.molecules entry for '{drug_name}' → {mol_id}")
            return mol_id

    # -------------------------------------------------------------------------
    # Silver handlers (source-specific)
    # -------------------------------------------------------------------------

    async def _silver_clinicaltrials(self, molecule_id: str, response: dict) -> None:
        """Upsert clinical trials into silver.clinical_trials."""
        studies = response.get("studies", [])
        # Handle individual study responses (no 'studies' wrapper)
        if not studies and response.get("protocolSection"):
            studies = [response]
        if not studies:
            return

        async with self.db_pool.acquire() as conn:
            for study in studies:
                proto = study.get("protocolSection", {})
                ident = proto.get("identificationModule", {})
                status_mod = proto.get("statusModule", {})
                design = proto.get("designModule", {})
                sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
                conditions_mod = proto.get("conditionsModule", {})
                interventions_mod = proto.get("armsInterventionsModule", {})
                eligibility_mod = proto.get("eligibilityModule", {})
                outcomes_mod = proto.get("outcomesModule", {})
                contacts_mod = proto.get("contactsLocationsModule", {})

                nct_id = ident.get("nctId")
                if not nct_id:
                    continue

                phases = design.get("phases", [])
                phase = phases[0] if phases else None

                enrollment_info = design.get("enrollmentInfo", {})
                lead_sponsor = sponsor_mod.get("leadSponsor", {})
                collaborators = sponsor_mod.get("collaborators", [])

                conditions = conditions_mod.get("conditions", [])
                interventions = [
                    {"name": i.get("name"), "type": i.get("type")}
                    for i in interventions_mod.get("interventions", [])
                ]
                primary_outcomes = outcomes_mod.get("primaryOutcomes", [])
                secondary_outcomes = outcomes_mod.get("secondaryOutcomes", [])

                locations = contacts_mod.get("locations", [])
                countries = list({
                    loc.get("country") for loc in locations if loc.get("country")
                })

                # start_date and completion_date are TEXT columns; primary_completion_date is DATE
                start_date = _date_str(status_mod.get("startDateStruct", {}).get("date"))
                completion_date = _date_str(
                    status_mod.get("completionDateStruct", {}).get("date")
                )
                primary_completion = _parse_date(
                    status_mod.get("primaryCompletionDateStruct", {}).get("date")
                )

                # Extract results data if available
                results_section = study.get("resultsSection")
                has_results = study.get("hasResults", False) or results_section is not None
                results_om = None
                results_ae = None
                if results_section:
                    om_module = results_section.get("outcomeMeasuresModule", {})
                    results_om = om_module.get("outcomeMeasures") if om_module else None
                    ae_module = results_section.get("adverseEventsModule", {})
                    results_ae = ae_module if ae_module else None

                # Extract ALL API fields (zero data loss)
                oversight = proto.get("oversightModule", {})
                refs_mod = proto.get("referencesModule", {})
                ipd_mod = proto.get("ipdSharingStatementModule", {})
                derived = study.get("derivedSection", {})

                await conn.execute("""
                    INSERT INTO mol_silver.clinical_trials
                    (trial_id, molecule_id, nct_id, org_study_id, brief_title, official_title, acronym,
                     brief_summary, detailed_description,
                     overall_status, last_known_status, why_stopped,
                     phase, phases, study_type,
                     start_date, start_date_type, completion_date, completion_date_type,
                     primary_completion_date,
                     study_first_submit_date, study_first_post_date, last_update_post_date,
                     allocation, intervention_model, primary_purpose, masking,
                     enrollment_count, enrollment_type,
                     conditions, keywords, mesh_terms,
                     interventions, arms_groups,
                     eligibility_criteria, sex, minimum_age, maximum_age, healthy_volunteers,
                     lead_sponsor_name, lead_sponsor_class, collaborators, central_contacts,
                     locations,
                     primary_outcomes, secondary_outcomes,
                     fda_regulated_drug, fda_regulated_device, ipd_sharing,
                     has_results, results_section,
                     results_outcome_measures, results_adverse_events,
                     results_participant_flow, results_baseline,
                     condition_browse, intervention_browse, "references",
                     source)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15,
                            $16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,
                            $30::jsonb,$31::jsonb,$32::jsonb,$33::jsonb,$34::jsonb,
                            $35,$36,$37,$38,$39,$40,$41,$42::jsonb,$43::jsonb,$44::jsonb,
                            $45::jsonb,$46::jsonb,$47,$48,$49,$50,$51::jsonb,
                            $52::jsonb,$53::jsonb,$54::jsonb,$55::jsonb,
                            $56::jsonb,$57::jsonb,$58::jsonb,
                            'clinicaltrials_gov')
                    ON CONFLICT (nct_id) DO UPDATE SET
                        molecule_id = EXCLUDED.molecule_id,
                        brief_title = EXCLUDED.brief_title,
                        official_title = EXCLUDED.official_title,
                        overall_status = EXCLUDED.overall_status,
                        phase = EXCLUDED.phase,
                        enrollment_count = EXCLUDED.enrollment_count,
                        conditions = EXCLUDED.conditions,
                        interventions = EXCLUDED.interventions,
                        start_date = EXCLUDED.start_date,
                        completion_date = EXCLUDED.completion_date,
                        has_results = COALESCE(EXCLUDED.has_results, mol_silver.clinical_trials.has_results),
                        results_section = COALESCE(EXCLUDED.results_section, mol_silver.clinical_trials.results_section),
                        results_outcome_measures = COALESCE(EXCLUDED.results_outcome_measures, mol_silver.clinical_trials.results_outcome_measures),
                        results_adverse_events = COALESCE(EXCLUDED.results_adverse_events, mol_silver.clinical_trials.results_adverse_events),
                        updated_at = NOW()
                """,
                    str(uuid.uuid4()), molecule_id, nct_id,
                    ident.get("orgStudyIdInfo", {}).get("id"),
                    ident.get("briefTitle"),
                    ident.get("officialTitle"),
                    ident.get("acronym"),
                    proto.get("descriptionModule", {}).get("briefSummary"),
                    proto.get("descriptionModule", {}).get("detailedDescription"),
                    status_mod.get("overallStatus"),
                    status_mod.get("lastKnownStatus"),
                    status_mod.get("whyStopped"),
                    phase,
                    json.dumps(phases),
                    design.get("studyType"),
                    start_date,
                    status_mod.get("startDateStruct", {}).get("type"),
                    completion_date,
                    status_mod.get("completionDateStruct", {}).get("type"),
                    primary_completion,
                    status_mod.get("studyFirstSubmitDate"),
                    status_mod.get("studyFirstPostDateStruct", {}).get("date") if status_mod.get("studyFirstPostDateStruct") else None,
                    status_mod.get("lastUpdatePostDateStruct", {}).get("date") if status_mod.get("lastUpdatePostDateStruct") else None,
                    design.get("designInfo", {}).get("allocation"),
                    design.get("designInfo", {}).get("interventionModel"),
                    design.get("designInfo", {}).get("primaryPurpose"),
                    design.get("designInfo", {}).get("maskingInfo", {}).get("masking") if design.get("designInfo", {}).get("maskingInfo") else None,
                    enrollment_info.get("count"),
                    enrollment_info.get("type"),
                    json.dumps(conditions),
                    json.dumps(conditions_mod.get("keywords", [])),
                    json.dumps(conditions_mod.get("meshes", [])),
                    json.dumps(interventions),
                    json.dumps(interventions_mod.get("armGroups", [])),
                    eligibility_mod.get("eligibilityCriteria"),
                    eligibility_mod.get("sex"),
                    eligibility_mod.get("minimumAge"),
                    eligibility_mod.get("maximumAge"),
                    eligibility_mod.get("healthyVolunteers"),
                    lead_sponsor.get("name"),
                    lead_sponsor.get("class"),
                    json.dumps(collaborators),
                    json.dumps(contacts_mod.get("centralContacts", [])),
                    json.dumps(locations[:50]),
                    json.dumps(primary_outcomes),
                    json.dumps(secondary_outcomes),
                    oversight.get("isFdaRegulatedDrug"),
                    oversight.get("isFdaRegulatedDevice"),
                    ipd_mod.get("ipdSharing"),
                    has_results,
                    json.dumps(results_section) if results_section else None,
                    json.dumps(results_om) if results_om else None,
                    json.dumps(results_ae) if results_ae else None,
                    json.dumps(results_section.get("participantFlowModule")) if results_section and results_section.get("participantFlowModule") else None,
                    json.dumps(results_section.get("baselineCharacteristicsModule")) if results_section and results_section.get("baselineCharacteristicsModule") else None,
                    json.dumps(derived.get("conditionBrowseModule")) if derived.get("conditionBrowseModule") else None,
                    json.dumps(derived.get("interventionBrowseModule")) if derived.get("interventionBrowseModule") else None,
                    json.dumps(refs_mod.get("references", refs_mod.get("seeAlsoLinks", []))),
                )

    async def _silver_openfda_labels(self, molecule_id: str, response: dict) -> None:
        """Upsert drug labels into silver.drug_labels."""
        results = response.get("results", [])
        if not results:
            return

        async with self.db_pool.acquire() as conn:
            for r in results:
                set_id = r.get("set_id")
                if not set_id:
                    continue

                openfda = r.get("openfda", {})
                brand_names = openfda.get("brand_name", [])
                generic_names = openfda.get("generic_name", [])

                await conn.execute("""
                    INSERT INTO mol_silver.drug_labels
                    (label_id, molecule_id, set_id, spl_id, version, effective_time,
                     brand_name, generic_name, manufacturer_name,
                     product_type, route, substance_name, active_ingredient,
                     indications_and_usage, dosage_and_administration,
                     dosage_forms_and_strengths,
                     contraindications, warnings, warnings_and_cautions,
                     boxed_warning, adverse_reactions, drug_interactions,
                     use_in_specific_populations,
                     clinical_pharmacology, mechanism_of_action,
                     pharmacodynamics, pharmacokinetics,
                     overdosage, description, clinical_studies,
                     how_supplied, storage_and_handling,
                     package_label_principal_display_panel,
                     pregnancy, nursing_mothers, pediatric_use, geriatric_use,
                     information_for_patients, spl_medguide,
                     spl_product_data_elements, nonclinical_toxicology,
                     laboratory_tests, pharmacogenomics,
                     "references",
                     openfda::jsonb,
                     openfda_application_number::jsonb,
                     openfda_brand_name, openfda_generic_name,
                     openfda_manufacturer_name, openfda_product_type,
                     openfda_route::jsonb, openfda_rxcui::jsonb,
                     openfda_spl_id, openfda_spl_set_id::jsonb,
                     openfda_unii::jsonb, openfda_nui::jsonb,
                     openfda_pharm_class_cs::jsonb,
                     openfda_pharm_class_epc::jsonb,
                     openfda_pharm_class_moa::jsonb,
                     openfda_pharm_class_pe::jsonb,
                     openfda_substance_name,
                     openfda_is_original_packager,
                     source)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                            $16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,
                            $29,$30,$31,$32,$33,$34,$35,$36,$37,$38,$39,$40,$41,
                            $42,$43,$44::jsonb,$45::jsonb,$46,$47,$48,$49,
                            $50::jsonb,$51::jsonb,$52,$53::jsonb,$54::jsonb,
                            $55::jsonb,$56::jsonb,$57::jsonb,$58::jsonb,
                            $59::jsonb,$60,$61,
                            'openfda_labels')
                    ON CONFLICT (set_id) DO UPDATE SET
                        molecule_id = EXCLUDED.molecule_id,
                        brand_name = EXCLUDED.brand_name,
                        indications_and_usage = COALESCE(EXCLUDED.indications_and_usage, mol_silver.drug_labels.indications_and_usage),
                        adverse_reactions = COALESCE(EXCLUDED.adverse_reactions, mol_silver.drug_labels.adverse_reactions),
                        mechanism_of_action = COALESCE(EXCLUDED.mechanism_of_action, mol_silver.drug_labels.mechanism_of_action),
                        clinical_studies = COALESCE(EXCLUDED.clinical_studies, mol_silver.drug_labels.clinical_studies),
                        updated_at = NOW()
                """,
                    str(uuid.uuid4()), molecule_id, set_id,
                    r.get("id"),
                    r.get("version"),
                    r.get("effective_time"),
                    brand_names[0] if brand_names else r.get("brand_name"),
                    generic_names[0] if generic_names else r.get("generic_name"),
                    (openfda.get("manufacturer_name", [None]) or [None])[0],
                    (openfda.get("product_type", [None]) or [None])[0],
                    (openfda.get("route", [None]) or [None])[0],
                    (openfda.get("substance_name", [None]) or [None])[0],
                    _join_text(r.get("active_ingredient")),
                    _join_text(r.get("indications_and_usage")),
                    _join_text(r.get("dosage_and_administration")),
                    _join_text(r.get("dosage_forms_and_strengths")),
                    _join_text(r.get("contraindications")),
                    _join_text(r.get("warnings")),
                    _join_text(r.get("warnings_and_cautions")),
                    _join_text(r.get("boxed_warning")),
                    _join_text(r.get("adverse_reactions")),
                    _join_text(r.get("drug_interactions")),
                    _join_text(r.get("use_in_specific_populations")),
                    _join_text(r.get("clinical_pharmacology")),
                    _join_text(r.get("mechanism_of_action")),
                    _join_text(r.get("pharmacodynamics")),
                    _join_text(r.get("pharmacokinetics")),
                    _join_text(r.get("overdosage")),
                    _join_text(r.get("description")),
                    _join_text(r.get("clinical_studies")),
                    _join_text(r.get("how_supplied")),
                    _join_text(r.get("storage_and_handling")),
                    _join_text(r.get("package_label_principal_display_panel")),
                    _join_text(r.get("pregnancy")),
                    _join_text(r.get("nursing_mothers")),
                    _join_text(r.get("pediatric_use")),
                    _join_text(r.get("geriatric_use")),
                    _join_text(r.get("information_for_patients")),
                    _join_text(r.get("spl_medguide")),
                    _join_text(r.get("spl_product_data_elements")),
                    _join_text(r.get("nonclinical_toxicology")),
                    _join_text(r.get("laboratory_tests")),
                    _join_text(r.get("pharmacogenomics")),
                    _join_text(r.get("references")),
                    json.dumps(openfda) if openfda else None,
                    json.dumps(openfda.get("application_number")) if openfda.get("application_number") else None,
                    (openfda.get("brand_name", [None]) or [None])[0],
                    (openfda.get("generic_name", [None]) or [None])[0],
                    (openfda.get("manufacturer_name", [None]) or [None])[0],
                    (openfda.get("product_type", [None]) or [None])[0],
                    json.dumps(openfda.get("route")) if openfda.get("route") else None,
                    json.dumps(openfda.get("rxcui")) if openfda.get("rxcui") else None,
                    (openfda.get("spl_id", [None]) or [None])[0],
                    json.dumps(openfda.get("spl_set_id")) if openfda.get("spl_set_id") else None,
                    json.dumps(openfda.get("unii")) if openfda.get("unii") else None,
                    json.dumps(openfda.get("nui")) if openfda.get("nui") else None,
                    json.dumps(openfda.get("pharm_class_cs")) if openfda.get("pharm_class_cs") else None,
                    json.dumps(openfda.get("pharm_class_epc")) if openfda.get("pharm_class_epc") else None,
                    json.dumps(openfda.get("pharm_class_moa")) if openfda.get("pharm_class_moa") else None,
                    json.dumps(openfda.get("pharm_class_pe")) if openfda.get("pharm_class_pe") else None,
                    (openfda.get("substance_name", [None]) or [None])[0],
                    openfda.get("is_original_packager"),
                )

    async def _silver_openfda_faers(self, molecule_id: str, response: dict) -> None:
        """Insert report-level FAERS data into silver.adverse_events (zero data loss)."""
        results = response.get("results", [])
        if not results:
            return

        async with self.db_pool.acquire() as conn:
            for r in results:
                safety_report_id = r.get("safetyreportid")
                if not safety_report_id:
                    continue

                patient = r.get("patient", {})

                # Extract primary suspect drug name
                drug_name = None
                for drug in patient.get("drug", []):
                    if drug.get("drugcharacterization") == "1":
                        drug_name = drug.get("medicinalproduct")
                        break

                await conn.execute("""
                    INSERT INTO mol_silver.adverse_events
                    (event_id, molecule_id, safety_report_id, safety_report_version,
                     receive_date, receipt_date,
                     serious, serious_death, serious_hospitalization,
                     serious_lifethreatening, serious_disabling, serious_other,
                     patient_age, patient_age_unit, patient_sex, patient_weight,
                     drug_name_reported, reporter_country, occurrence_country, companynumb,
                     drugs, reactions, outcomes,
                     source)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                            $17,$18,$19,$20,$21::jsonb,$22::jsonb,$23::jsonb,
                            'openfda_faers')
                    ON CONFLICT (safety_report_id, safety_report_version) DO UPDATE SET
                        molecule_id = EXCLUDED.molecule_id,
                        updated_at = NOW()
                """,
                    str(uuid.uuid4()), molecule_id,
                    safety_report_id,
                    r.get("safetyreportversion"),
                    r.get("receivedate"),
                    r.get("receiptdate"),
                    r.get("serious") == 1 if r.get("serious") is not None else None,
                    r.get("seriousnessdeath") == 1 if r.get("seriousnessdeath") is not None else None,
                    r.get("seriousnesshospitalization") == 1 if r.get("seriousnesshospitalization") is not None else None,
                    r.get("seriousnesslifethreatening") == 1 if r.get("seriousnesslifethreatening") is not None else None,
                    r.get("seriousnessdisabling") == 1 if r.get("seriousnessdisabling") is not None else None,
                    r.get("seriousnessother") == 1 if r.get("seriousnessother") is not None else None,
                    float(patient.get("patientonsetage")) if patient.get("patientonsetage") else None,
                    patient.get("patientonsetageunit"),
                    patient.get("patientsex"),
                    float(patient.get("patientweight")) if patient.get("patientweight") else None,
                    drug_name,
                    r.get("primarysource", {}).get("reportercountry") if r.get("primarysource") else r.get("occurcountry"),
                    r.get("occurcountry"),
                    r.get("companynumb"),
                    json.dumps(patient.get("drug", [])),
                    json.dumps(patient.get("reaction", [])),
                    json.dumps([rx.get("reactionoutcome") for rx in patient.get("reaction", []) if rx.get("reactionoutcome")]),
                )

    async def _silver_openalex(self, molecule_id: str, response: dict) -> None:
        """Upsert publications from OpenAlex into silver.publications."""
        results = response.get("results", [])
        if not results:
            return

        async with self.db_pool.acquire() as conn:
            for w in results:
                work_id = w.get("id", "")
                if not work_id:
                    continue

                authorships = w.get("authorships", [])
                authors = [
                    {
                        "name": a.get("author", {}).get("display_name"),
                        "author_id": a.get("author", {}).get("id"),
                        "institution": (a.get("institutions", [{}]) or [{}])[0].get("display_name"),
                    }
                    for a in authorships
                ]
                first_author = authors[0]["name"] if authors else None

                ids = w.get("ids", {})
                concepts = w.get("concepts", [])
                keywords = [c.get("display_name") for c in concepts[:10]]

                pub_id = str(uuid.uuid4())
                await conn.execute("""
                    INSERT INTO mol_silver.publications
                    (id, openalex_id, doi, pmid, title, abstract,
                     publication_year, journal_name, author_names, first_author_name,
                     cited_by_count, is_open_access, keywords, source)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                            $9::jsonb, $10, $11, $12, $13::jsonb, 'openalex')
                    ON CONFLICT (openalex_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        abstract = COALESCE(EXCLUDED.abstract, mol_silver.publications.abstract),
                        cited_by_count = EXCLUDED.cited_by_count,
                        updated_at = NOW()
                    RETURNING id
                """,
                    pub_id, work_id,
                    w.get("doi"),
                    ids.get("pmid"),
                    w.get("title"),
                    w.get("abstract_inverted_index") and _reconstruct_abstract(w.get("abstract_inverted_index")),
                    w.get("publication_year"),
                    w.get("primary_location", {}).get("source", {}).get("display_name") if w.get("primary_location") else None,
                    json.dumps(authors),
                    first_author,
                    w.get("cited_by_count", 0),
                    w.get("open_access", {}).get("is_oa", False),
                    json.dumps(keywords),
                )

                # Link molecule ↔ publication
                await conn.execute("""
                    INSERT INTO mol_silver.molecule_publications
                    (id, molecule_id, publication_id, mention_type)
                    VALUES ($1, $2, $3, 'primary_subject')
                    ON CONFLICT (molecule_id, publication_id) DO NOTHING
                """, str(uuid.uuid4()), molecule_id, pub_id)

    async def _silver_chembl(self, molecule_id: str, response: dict) -> None:
        """Update silver.molecules with ChEMBL data and create identifier mappings."""
        molecules = response.get("molecules", [])
        if not molecules:
            return

        mol = molecules[0]  # Primary match
        chembl_id = mol.get("molecule_chembl_id")
        if not chembl_id:
            return

        props = mol.get("molecule_properties", {}) or {}
        structures = mol.get("molecule_structures", {}) or {}

        async with self.db_pool.acquire() as conn:
            # Update molecule with ChEMBL data
            await conn.execute("""
                UPDATE mol_silver.molecules SET
                    canonical_smiles = COALESCE(canonical_smiles, $2),
                    molecular_formula = COALESCE(molecular_formula, $3),
                    molecular_weight = COALESCE(molecular_weight, $4),
                    molecule_type = COALESCE(molecule_type, $5),
                    max_phase = GREATEST(COALESCE(max_phase, 0), $6),
                    mechanism_of_action = COALESCE(mechanism_of_action, $7),
                    updated_at = NOW()
                WHERE molecule_id = $1::uuid
            """,
                molecule_id,
                structures.get("canonical_smiles"),
                props.get("full_molformula"),
                float(props["full_mwt"]) if props.get("full_mwt") else None,
                mol.get("molecule_type"),
                mol.get("max_phase", 0),
                mol.get("mechanism_of_action"),
            )

            # Add ChEMBL ID mapping
            await conn.execute("""
                INSERT INTO mol_silver.identifier_mappings
                (mapping_id, molecule_id, identifier_type, identifier_value, source, is_primary)
                VALUES ($1, $2, 'chembl_id', $3, 'chembl', TRUE)
                ON CONFLICT (molecule_id, identifier_type, identifier_value) DO NOTHING
            """, str(uuid.uuid4()), molecule_id, chembl_id)

    async def _silver_drugbank(self, molecule_id: str, response: dict) -> None:
        """Update silver.molecules with DrugBank data."""
        drugs = response.get("drugs", [])
        if not drugs:
            return

        drug = drugs[0]
        db_id = drug.get("drugbank_id") or drug.get("drugbank-id")
        if not db_id:
            return

        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE mol_silver.molecules SET
                    mechanism_of_action = COALESCE(mechanism_of_action, $2),
                    updated_at = NOW()
                WHERE molecule_id = $1::uuid
            """, molecule_id, drug.get("mechanism-of-action") or drug.get("mechanism_of_action"))

            await conn.execute("""
                INSERT INTO mol_silver.identifier_mappings
                (mapping_id, molecule_id, identifier_type, identifier_value, source, is_primary)
                VALUES ($1, $2, 'drugbank_id', $3, 'drugbank', TRUE)
                ON CONFLICT (molecule_id, identifier_type, identifier_value) DO NOTHING
            """, str(uuid.uuid4()), molecule_id, db_id)

    async def _silver_pubchem(self, molecule_id: str, response: dict) -> None:
        """Update silver.molecules with PubChem data."""
        props = response.get("PropertyTable", {}).get("Properties", [])
        compounds = response.get("PC_Compounds", props)
        if not compounds:
            return

        c = compounds[0]
        cid = str(c.get("CID", c.get("cid", "")))
        if not cid:
            return

        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE mol_silver.molecules SET
                    canonical_smiles = COALESCE(canonical_smiles, $2),
                    molecular_formula = COALESCE(molecular_formula, $3),
                    molecular_weight = COALESCE(molecular_weight, $4),
                    inchi = COALESCE(inchi, $5),
                    inchi_key = COALESCE(inchi_key, $6),
                    updated_at = NOW()
                WHERE molecule_id = $1::uuid
            """,
                molecule_id,
                c.get("CanonicalSMILES") or c.get("canonical_smiles"),
                c.get("MolecularFormula") or c.get("molecular_formula"),
                float(c["MolecularWeight"]) if c.get("MolecularWeight") else (
                    float(c["molecular_weight"]) if c.get("molecular_weight") else None
                ),
                c.get("InChI") or c.get("inchi"),
                c.get("InChIKey") or c.get("inchi_key"),
            )

            await conn.execute("""
                INSERT INTO mol_silver.identifier_mappings
                (mapping_id, molecule_id, identifier_type, identifier_value, source, is_primary)
                VALUES ($1, $2, 'pubchem_cid', $3, 'pubchem', TRUE)
                ON CONFLICT (molecule_id, identifier_type, identifier_value) DO NOTHING
            """, str(uuid.uuid4()), molecule_id, cid)

    # Silver handler registry
    _SILVER_HANDLERS = {
        "clinicaltrials": _silver_clinicaltrials,
        "openfda_labels": _silver_openfda_labels,
        "openfda_faers": _silver_openfda_faers,
        "openalex": _silver_openalex,
        "chembl": _silver_chembl,
        "drugbank": _silver_drugbank,
        "pubchem": _silver_pubchem,
    }

    # -------------------------------------------------------------------------
    # Gold layer refresh
    # -------------------------------------------------------------------------

    async def _refresh_gold(self, molecule_id: str, drug_name: str) -> None:
        """Rebuild gold aggregates for one molecule from silver data."""
        async with self.db_pool.acquire() as conn:
            await self._refresh_gold_molecule_profile(conn, molecule_id, drug_name)
            await self._refresh_gold_safety_signals(conn, molecule_id)
            await self._refresh_gold_lifecycle_stages(conn, molecule_id)
            await self._refresh_gold_trial_outcomes_direct(conn, molecule_id)
            await self._refresh_gold_competitive_landscape(conn, molecule_id)
            # _parse_mda_and_refresh_indication_revenue removed: revenue extraction
            # from MD&A text is handled by xenon's LLM (processFinancialFilingsWithLLM),
            # not by dk-data-FE regex patterns. mol_silver.indication_revenue and
            # mol_gold.indication_revenue_summary are no longer populated here.

    async def _refresh_gold_molecule_profile(self, conn, molecule_id: str, drug_name: str) -> None:
        """Refresh gold_molecule_profile from silver tables."""
        mol = await conn.fetchrow(
            "SELECT * FROM mol_silver.molecules WHERE molecule_id = $1::uuid", molecule_id
        )
        if not mol:
            return

        # Count safety data (adverse_events tracks individual events)
        ae_row = await conn.fetchrow("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN serious = TRUE
                             OR seriousness_text IN ('Serious', '1') THEN 1 ELSE 0 END) as serious
            FROM mol_silver.adverse_events WHERE molecule_id::text = $1
        """, molecule_id)

        # Top adverse events aggregated by reaction term
        top_aes = await conn.fetch("""
            SELECT reaction_meddra_pt as term, COUNT(*) as cnt
            FROM mol_silver.adverse_events
            WHERE molecule_id::text = $1 AND reaction_meddra_pt IS NOT NULL
            GROUP BY reaction_meddra_pt
            ORDER BY cnt DESC LIMIT 10
        """, molecule_id)
        top_ae_terms = [{"term": r["term"], "count": r["cnt"]} for r in top_aes]

        # Pipeline indications from trials
        pipeline = await conn.fetch("""
            SELECT phase, COUNT(*) as trial_count
            FROM mol_silver.clinical_trials
            WHERE molecule_id::text = $1
            GROUP BY phase
        """, molecule_id)
        pipeline_indications = [
            {"phase": r["phase"], "trial_count": r["trial_count"]}
            for r in pipeline
        ]

        # No patent table currently populated
        patent_row = None

        # Count data sources
        source_counts = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM mol_silver.clinical_trials WHERE molecule_id::text = $1) as trials,
                (SELECT COUNT(*) FROM mol_silver.drug_labels WHERE molecule_id::text = $1) as labels,
                (SELECT COUNT(*) FROM mol_silver.adverse_events WHERE molecule_id::text = $1) as aes,
                (SELECT COUNT(*) FROM mol_silver.molecule_publications mp
                 WHERE mp.molecule_id::text = $1) as pubs
        """, molecule_id)

        trial_count = int(source_counts["trials"]) if source_counts else 0
        label_count = int(source_counts["labels"]) if source_counts else 0
        ae_count = int(source_counts["aes"]) if source_counts else 0
        pub_count = int(source_counts["pubs"]) if source_counts else 0

        data_sources = {}
        if trial_count: data_sources["clinical_trials"] = trial_count
        if label_count: data_sources["drug_labels"] = label_count
        if ae_count: data_sources["adverse_events"] = ae_count
        if pub_count: data_sources["publications"] = pub_count

        total_sources = sum(1 for v in data_sources.values() if v > 0)
        completeness = min(1.0, total_sources / 5.0)

        # Upsert mol_gold.molecule_profile (actual columns)
        try:
            await conn.execute("""
                INSERT INTO mol_gold.molecule_profile
                (molecule_id, canonical_name, inchi_key,
                 pipeline_indications, serious_ae_count, top_ae_terms,
                 trial_count, active_trial_count, label_count,
                 adverse_event_count, publication_count,
                 earliest_patent_expiry, patent_count,
                 data_completeness_score, data_sources, last_data_update)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb,
                        $7, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, NOW())
                ON CONFLICT (molecule_id) DO UPDATE SET
                    canonical_name = EXCLUDED.canonical_name,
                    pipeline_indications = EXCLUDED.pipeline_indications,
                    serious_ae_count = EXCLUDED.serious_ae_count,
                    top_ae_terms = EXCLUDED.top_ae_terms,
                    trial_count = EXCLUDED.trial_count,
                    active_trial_count = EXCLUDED.active_trial_count,
                    label_count = EXCLUDED.label_count,
                    adverse_event_count = EXCLUDED.adverse_event_count,
                    publication_count = EXCLUDED.publication_count,
                    earliest_patent_expiry = EXCLUDED.earliest_patent_expiry,
                    patent_count = EXCLUDED.patent_count,
                    data_completeness_score = EXCLUDED.data_completeness_score,
                    data_sources = EXCLUDED.data_sources,
                    last_data_update = NOW(),
                    updated_at = NOW()
            """,
                molecule_id,
                mol["canonical_name"] or drug_name,
                mol["inchi_key"],
                json.dumps(pipeline_indications),
                int(ae_row["serious"]) if ae_row and ae_row["serious"] else 0,
                json.dumps(top_ae_terms),
                trial_count,
                label_count,
                ae_count,
                pub_count,
                str(patent_row["earliest"]) if patent_row and patent_row["earliest"] else None,
                int(patent_row["cnt"]) if patent_row else 0,
                completeness,
                json.dumps(data_sources),
            )
        except Exception as e:
            logger.warning(f"gold.molecule_profile upsert skipped: {e}")

    async def _refresh_gold_safety_signals(self, conn, molecule_id: str) -> None:
        """Refresh gold.safety_signals from silver.adverse_events."""
        try:
            # Clear old signals for this molecule
            await conn.execute(
                "DELETE FROM mol_gold.safety_signals WHERE molecule_id::text = $1", molecule_id
            )

            # Rebuild from silver — aggregate individual events by reaction term
            aes = await conn.fetch("""
                SELECT
                    reaction_meddra_pt,
                    COUNT(*) as case_count,
                    MIN(report_date) as first_reported,
                    MAX(report_date) as last_reported,
                    SUM(CASE WHEN serious = TRUE
                             OR seriousness_text IN ('Serious', '1') THEN 1 ELSE 0 END) as serious_count
                FROM mol_silver.adverse_events
                WHERE molecule_id::text = $1
                  AND reaction_meddra_pt IS NOT NULL
                GROUP BY reaction_meddra_pt
                HAVING COUNT(*) >= 3
                ORDER BY COUNT(*) DESC
                LIMIT 100
            """, molecule_id)

            for ae in aes:
                case_count = int(ae["case_count"])
                signal_strength = 'strong' if case_count >= 10 else 'moderate' if case_count >= 5 else 'weak'
                await conn.execute("""
                    INSERT INTO mol_gold.safety_signals
                    (molecule_id, reaction_meddra_pt, case_count,
                     signal_strength, first_reported, last_reported, last_updated)
                    VALUES ($1, $2, $3, $4, $5, $6, NOW())
                    ON CONFLICT (molecule_id, reaction_meddra_pt) DO UPDATE SET
                        case_count = EXCLUDED.case_count,
                        signal_strength = EXCLUDED.signal_strength,
                        first_reported = EXCLUDED.first_reported,
                        last_reported = EXCLUDED.last_reported,
                        last_updated = NOW()
                """,
                    molecule_id,
                    ae["reaction_meddra_pt"],
                    case_count,
                    signal_strength,
                    ae["first_reported"],
                    ae["last_reported"],
                )
        except Exception as e:
            logger.warning(f"gold.safety_signals refresh skipped: {e}")

    async def _refresh_gold_lifecycle_stages(self, conn, molecule_id: str) -> None:
        """Refresh gold.lifecycle_stages from silver clinical trials."""
        try:
            # Group trials by phase to build lifecycle stages
            phases = await conn.fetch("""
                SELECT phase, overall_status, COUNT(*) as cnt,
                       jsonb_agg(DISTINCT c) as indications
                FROM mol_silver.clinical_trials,
                     jsonb_array_elements_text(conditions) c
                WHERE molecule_id::text = $1
                GROUP BY phase, overall_status
            """, molecule_id)

            if not phases:
                return

            # Upsert lifecycle stages
            for row in phases:
                phase = row["phase"]
                if not phase:
                    continue
                stage = _phase_to_lifecycle_from_trial(phase)
                if not stage:
                    continue

                indications = row.get("indications")
                indication_str = None
                if indications:
                    try:
                        ind_list = json.loads(indications) if isinstance(indications, str) else indications
                        indication_str = ind_list[0] if ind_list else None
                    except Exception:
                        pass

                await conn.execute("""
                    INSERT INTO mol_gold.lifecycle_stages
                    (molecule_id, indication, lifecycle_stage,
                     confidence, evidence_sources, detected_at)
                    VALUES ($1, $2, $3, 0.9, ARRAY['clinical_trials'], NOW())
                    ON CONFLICT (molecule_id, indication) DO UPDATE SET
                        lifecycle_stage = EXCLUDED.lifecycle_stage,
                        confidence = EXCLUDED.confidence,
                        detected_at = NOW()
                """,
                    molecule_id,
                    indication_str or 'general',
                    stage,
                )
        except Exception as e:
            logger.warning(f"gold.lifecycle_stages refresh skipped: {e}")

    async def _refresh_gold_competitive_landscape(self, conn, molecule_id: str) -> None:
        """Refresh gold.competitive_landscape from indication-matched trials."""
        try:
            # Get this molecule's conditions
            conditions = await conn.fetch("""
                SELECT DISTINCT c as condition
                FROM mol_silver.clinical_trials,
                     jsonb_array_elements_text(conditions) c
                WHERE molecule_id::text = $1
            """, molecule_id)

            if not conditions:
                return

            for cond_row in conditions[:5]:  # Top 5 indications
                condition = cond_row["condition"]

                # Count competing molecules for this indication
                landscape = await conn.fetchrow("""
                    SELECT
                        COUNT(DISTINCT molecule_id) as total,
                        COUNT(DISTINCT molecule_id) FILTER (WHERE phase IN ('PHASE3', 'Phase 3')) as p3,
                        COUNT(DISTINCT molecule_id) FILTER (WHERE phase IN ('PHASE2', 'Phase 2')) as p2,
                        COUNT(DISTINCT molecule_id) FILTER (WHERE phase IN ('PHASE1', 'Phase 1')) as p1
                    FROM mol_silver.clinical_trials
                    WHERE conditions ? $1
                """, condition)

                if not landscape or landscape["total"] == 0:
                    continue

                today = date.today()
                await conn.execute("""
                    INSERT INTO mol_gold.competitive_landscape
                    (id, molecule_id, indication, total_molecules,
                     phase_3_count, phase_2_count, phase_1_count, snapshot_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (indication, snapshot_date) DO UPDATE SET
                        total_molecules = EXCLUDED.total_molecules,
                        phase_3_count = EXCLUDED.phase_3_count,
                        phase_2_count = EXCLUDED.phase_2_count,
                        phase_1_count = EXCLUDED.phase_1_count,
                        updated_at = NOW()
                """,
                    str(uuid.uuid4()), molecule_id, condition,
                    landscape["total"],
                    landscape["p3"], landscape["p2"], landscape["p1"],
                    today,
                )
        except Exception as e:
            logger.warning(f"gold.competitive_landscape refresh skipped: {e}")

    async def _refresh_gold_trial_outcomes_direct(self, conn, molecule_id: str) -> None:
        """Populate gold.trial_outcomes directly from silver.clinical_trials."""
        try:
            trials = await conn.fetch("""
                SELECT nct_id, brief_title, phase, overall_status,
                       enrollment_count, lead_sponsor_name, conditions
                FROM mol_silver.clinical_trials
                WHERE molecule_id::text = $1
            """, molecule_id)

            if not trials:
                return

            for t in trials:
                nct_id = t.get("nct_id")
                if not nct_id:
                    continue

                await conn.execute("""
                    INSERT INTO mol_gold.trial_outcomes
                    (id, molecule_id, nct_id, endpoint_name, result,
                     phase, overall_status, enrollment_count, lead_sponsor_name, conditions)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                    ON CONFLICT (nct_id) DO UPDATE SET
                        phase = EXCLUDED.phase,
                        overall_status = EXCLUDED.overall_status,
                        enrollment_count = EXCLUDED.enrollment_count,
                        conditions = EXCLUDED.conditions,
                        updated_at = NOW()
                """,
                    str(uuid.uuid4()), molecule_id, nct_id,
                    t.get("brief_title"),
                    t.get("overall_status"),
                    t.get("phase"),
                    t.get("overall_status"),
                    t.get("enrollment_count"),
                    t.get("lead_sponsor_name"),
                    json.dumps(t["conditions"]) if t.get("conditions") else None,
                )
        except Exception as e:
            logger.error(f"gold.trial_outcomes refresh failed: {e}")

    async def _parse_mda_and_refresh_indication_revenue(self, conn, molecule_id: str) -> None:
        """Parse MD&A excerpts from financial_filings → silver.indication_revenue → gold summary."""
        try:
            from ..data_platform.mda_revenue_parser import parse_mda_for_indication_revenue

            # Step 1: Parse MD&A text from financial_filings into silver.indication_revenue
            filings = await conn.fetch("""
                SELECT product_name, mda_excerpt, revenue, period, accession_number
                FROM mol_silver.financial_filings
                WHERE molecule_id = $1::uuid
                  AND mda_excerpt IS NOT NULL AND LENGTH(mda_excerpt) > 100
                ORDER BY period DESC
            """, molecule_id)

            parsed_count = 0
            for f in filings:
                # Extract year from period like "annual_2026"
                data_year = None
                if f['period']:
                    import re
                    m = re.search(r'(\d{4})', f['period'])
                    if m:
                        data_year = int(m.group(1))
                if not data_year:
                    continue

                results = parse_mda_for_indication_revenue(
                    mda_text=f['mda_excerpt'],
                    product_name=f['product_name'] or 'Unknown',
                    data_year=data_year,
                    source_filing=f['accession_number'] or f['period'],
                    molecule_id=molecule_id,
                    total_product_revenue=float(f['revenue']) if f['revenue'] else None,
                )

                for r in results:
                    await conn.execute("""
                        INSERT INTO mol_silver.indication_revenue
                            (id, icd10_code, molecule_id, product_name,
                             indication_revenue_usd, total_product_revenue_usd,
                             indication_revenue_share, data_year, source_filing, source)
                        VALUES (gen_random_uuid(), $1, $2::uuid, $3, $4, $5, $6, $7, $8, 'sec_edgar')
                        ON CONFLICT (molecule_id, icd10_code, product_name, data_year) DO UPDATE SET
                            indication_revenue_usd = EXCLUDED.indication_revenue_usd,
                            total_product_revenue_usd = EXCLUDED.total_product_revenue_usd,
                            indication_revenue_share = EXCLUDED.indication_revenue_share,
                            source_filing = EXCLUDED.source_filing,
                            updated_at = NOW()
                    """,
                        r['icd10_code'], molecule_id, r['product_name'],
                        r['indication_revenue_usd'], r['total_product_revenue_usd'],
                        r['indication_revenue_share'], r['data_year'], r['source_filing'],
                    )
                    parsed_count += 1

            if parsed_count:
                logger.info(f"Parsed {parsed_count} indication-revenue entries from {len(filings)} filings")

            # Fallback: if no indication-level data found, create product-level summary
            # directly from financial_filings (icd10='ALL' = total product)
            silver_count = await conn.fetchval(
                "SELECT COUNT(*) FROM mol_silver.indication_revenue WHERE molecule_id = $1::uuid",
                molecule_id,
            )
            if silver_count == 0 and filings:
                logger.info("No indication-level revenue found; creating product-level gold summary from financial_filings")
                for f in filings:
                    data_year = None
                    if f['period']:
                        import re
                        m = re.search(r'(\d{4})', f['period'])
                        if m:
                            data_year = int(m.group(1))
                    if not data_year or not f['revenue']:
                        continue
                    # Insert product-level entry with icd10='ALL'
                    await conn.execute("""
                        INSERT INTO mol_silver.indication_revenue
                            (id, icd10_code, molecule_id, product_name,
                             indication_revenue_usd, total_product_revenue_usd,
                             indication_revenue_share, data_year, source_filing, source)
                        VALUES (gen_random_uuid(), 'ALL', $1::uuid, $2, $3, $3, 100.0, $4, $5, 'sec_edgar')
                        ON CONFLICT (molecule_id, icd10_code, product_name, data_year) DO UPDATE SET
                            indication_revenue_usd = EXCLUDED.indication_revenue_usd,
                            updated_at = NOW()
                    """,
                        molecule_id, f['product_name'] or 'Unknown',
                        float(f['revenue']), data_year,
                        f['accession_number'] or f['period'],
                    )

            # Step 2: Aggregate silver.indication_revenue → gold.indication_revenue_summary
            # Get indication names from ontology for display
            rows = await conn.fetch("""
                SELECT
                    ir.icd10_code,
                    ir.product_name,
                    MAX(CASE WHEN ir.data_year = latest.max_year THEN ir.indication_revenue_usd END) AS latest_revenue_usd,
                    MAX(ir.indication_revenue_usd) AS peak_revenue_usd,
                    MAX(CASE WHEN ir.data_year = latest.max_year THEN ir.total_product_revenue_usd END) AS latest_total_product_usd,
                    MAX(CASE WHEN ir.data_year = latest.max_year THEN ir.indication_revenue_share END) AS revenue_share_pct,
                    (SELECT x.data_year FROM mol_silver.indication_revenue x
                     WHERE x.molecule_id = ir.molecule_id AND x.icd10_code = ir.icd10_code
                     ORDER BY x.indication_revenue_usd DESC NULLS LAST LIMIT 1) AS year_of_peak,
                    latest.max_year AS latest_year,
                    COUNT(DISTINCT ir.source_filing) AS filing_count
                FROM mol_silver.indication_revenue ir
                JOIN (
                    SELECT molecule_id, icd10_code, MAX(data_year) AS max_year
                    FROM mol_silver.indication_revenue
                    WHERE molecule_id = $1::uuid
                    GROUP BY molecule_id, icd10_code
                ) latest ON ir.molecule_id = latest.molecule_id
                    AND ir.icd10_code = latest.icd10_code
                WHERE ir.molecule_id = $1::uuid
                GROUP BY ir.molecule_id, ir.icd10_code, ir.product_name,
                         latest.max_year
            """, molecule_id)

            for r in rows:
                # Compute trend from multi-year data
                year_data = await conn.fetch("""
                    SELECT data_year, indication_revenue_usd
                    FROM mol_silver.indication_revenue
                    WHERE molecule_id = $1::uuid AND icd10_code = $2
                    ORDER BY data_year
                """, molecule_id, r['icd10_code'])

                trend = 'stable'
                cagr = None
                if len(year_data) >= 2:
                    first_val = float(year_data[0]['indication_revenue_usd'] or 0)
                    last_val = float(year_data[-1]['indication_revenue_usd'] or 0)
                    years_span = year_data[-1]['data_year'] - year_data[0]['data_year']
                    if first_val > 0 and years_span > 0:
                        cagr = ((last_val / first_val) ** (1.0 / years_span) - 1) * 100
                        if cagr > 5:
                            trend = 'increasing'
                        elif cagr < -5:
                            trend = 'declining'

                # Confidence: 0.3 base + 0.2 per filing (max 3) + 0.1 if multi-year
                confidence = min(1.0, 0.3 + 0.2 * min(r['filing_count'], 3) + (0.1 if len(year_data) >= 2 else 0))

                await conn.execute("""
                    INSERT INTO mol_gold.indication_revenue_summary
                        (molecule_id, icd10_code, indication_name, product_name,
                         latest_revenue_usd, peak_revenue_usd, latest_total_product_usd,
                         revenue_share_pct, year_of_peak, latest_year, trend, cagr_pct,
                         filing_count, confidence_score, snapshot_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, CURRENT_DATE)
                    ON CONFLICT (molecule_id, icd10_code) DO UPDATE SET
                        indication_name = COALESCE(EXCLUDED.indication_name, mol_gold.indication_revenue_summary.indication_name),
                        product_name = EXCLUDED.product_name,
                        latest_revenue_usd = EXCLUDED.latest_revenue_usd,
                        peak_revenue_usd = EXCLUDED.peak_revenue_usd,
                        latest_total_product_usd = EXCLUDED.latest_total_product_usd,
                        revenue_share_pct = EXCLUDED.revenue_share_pct,
                        year_of_peak = EXCLUDED.year_of_peak,
                        latest_year = EXCLUDED.latest_year,
                        trend = EXCLUDED.trend,
                        cagr_pct = EXCLUDED.cagr_pct,
                        filing_count = EXCLUDED.filing_count,
                        confidence_score = EXCLUDED.confidence_score,
                        snapshot_date = CURRENT_DATE,
                        updated_at = NOW()
                """,
                    molecule_id, r['icd10_code'],
                    None, r['product_name'],  # indication_name filled by ICD-10 lookup if available
                    r['latest_revenue_usd'], r['peak_revenue_usd'],
                    r['latest_total_product_usd'], r['revenue_share_pct'],
                    r['year_of_peak'], r['latest_year'],
                    trend, cagr,
                    r['filing_count'], confidence,
                )

            if rows:
                logger.info(f"Refreshed gold.indication_revenue_summary: {len(rows)} indications")

        except Exception as e:
            logger.warning(f"gold.indication_revenue_summary refresh skipped: {e}")


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _parse_date(date_str: Optional[str]):
    """Best-effort date parsing, returns datetime.date."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y", "%B %d, %Y", "%B %Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _date_str(date_str: Optional[str]) -> Optional[str]:
    """Best-effort date parsing, returns ISO string (for TEXT columns)."""
    d = _parse_date(date_str)
    return str(d) if d else None


def _join_text(field) -> Optional[str]:
    """Join OpenFDA text arrays into a single string."""
    if isinstance(field, list):
        return " ".join(field)
    if isinstance(field, str):
        return field
    return None


def _reconstruct_abstract(inverted_index: Optional[dict]) -> Optional[str]:
    """Reconstruct abstract text from OpenAlex inverted index format."""
    if not inverted_index:
        return None
    try:
        words = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word
        return " ".join(words[i] for i in sorted(words))
    except Exception:
        return None


def _phase_to_lifecycle(max_phase) -> str:
    """Map ChEMBL max_phase to lifecycle stage."""
    if max_phase is None:
        return "preclinical"
    phase = int(max_phase) if max_phase else 0
    return {0: "preclinical", 1: "phase_1", 2: "phase_2", 3: "phase_3", 4: "approved"}.get(
        phase, "preclinical"
    )


def _phase_to_lifecycle_from_trial(phase_str: str) -> Optional[str]:
    """Map ClinicalTrials.gov phase string to lifecycle stage."""
    if not phase_str:
        return None
    p = phase_str.upper()
    if "4" in p:
        return "marketed"
    if "3" in p:
        return "phase_3"
    if "2" in p:
        return "phase_2"
    if "1" in p:
        return "phase_1"
    if "EARLY" in p:
        return "preclinical"
    return None
