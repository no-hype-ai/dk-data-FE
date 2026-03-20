"""On-demand Silver + Gold refresher.

After bronze transform, this module immediately updates silver and gold
tables for the affected molecule. Each source type populates specific
silver tables, and gold aggregates are rebuilt from silver.
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
                "SELECT id FROM mol_silver.molecules WHERE LOWER(canonical_name) = $1",
                normalized,
            )
            if row:
                return str(row["id"])

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
                INSERT INTO mol_silver.molecules (id, canonical_name, name_source, primary_source, data_sources)
                VALUES ($1, $2, $3, $3, $4::jsonb)
            """, mol_id, drug_name, source_name, json.dumps([source_name]))

            # Add alias
            await conn.execute("""
                INSERT INTO mol_silver.molecule_aliases
                (id, molecule_id, alias_name, alias_type, alias_name_normalized, source)
                VALUES ($1, $2, $3, 'generic_name', $4, $5)
                ON CONFLICT DO NOTHING
            """, str(uuid.uuid4()), mol_id, drug_name, normalized, source_name)

            logger.info(f"Created silver.molecules entry for '{drug_name}' → {mol_id}")
            return mol_id

    # -------------------------------------------------------------------------
    # Silver handlers (source-specific)
    # -------------------------------------------------------------------------

    async def _silver_clinicaltrials(self, molecule_id: str, response: dict) -> None:
        """Upsert clinical trials into silver.clinical_trials."""
        studies = response.get("studies", [])
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

                await conn.execute("""
                    INSERT INTO mol_silver.clinical_trials
                    (id, molecule_id, nct_id, title, brief_summary, phase,
                     study_type, status, start_date, completion_date,
                     primary_completion_date, sponsor, sponsor_type,
                     collaborators, enrollment, conditions, interventions,
                     primary_outcomes, secondary_outcomes, locations, countries,
                     eligibility_criteria, minimum_age, maximum_age, sex, source)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                            $12, $13, $14::jsonb, $15, $16::jsonb, $17::jsonb,
                            $18::jsonb, $19::jsonb, $20::jsonb, $21::jsonb,
                            $22, $23, $24, $25, 'clinicaltrials_gov')
                    ON CONFLICT (nct_id) DO UPDATE SET
                        molecule_id = EXCLUDED.molecule_id,
                        title = EXCLUDED.title,
                        phase = EXCLUDED.phase,
                        status = EXCLUDED.status,
                        enrollment = EXCLUDED.enrollment,
                        conditions = EXCLUDED.conditions,
                        interventions = EXCLUDED.interventions,
                        start_date = EXCLUDED.start_date,
                        completion_date = EXCLUDED.completion_date,
                        updated_at = NOW()
                """,
                    str(uuid.uuid4()), molecule_id, nct_id,
                    ident.get("officialTitle") or ident.get("briefTitle"),
                    proto.get("descriptionModule", {}).get("briefSummary"),
                    phase,
                    design.get("studyType"),
                    status_mod.get("overallStatus"),
                    start_date, completion_date, primary_completion,
                    lead_sponsor.get("name"),
                    lead_sponsor.get("class"),
                    json.dumps(collaborators),
                    enrollment_info.get("count"),
                    json.dumps(conditions),
                    json.dumps(interventions),
                    json.dumps(primary_outcomes),
                    json.dumps(secondary_outcomes),
                    json.dumps(locations[:20]),  # limit location data
                    json.dumps(countries),
                    eligibility_mod.get("eligibilityCriteria"),
                    eligibility_mod.get("minimumAge"),
                    eligibility_mod.get("maximumAge"),
                    eligibility_mod.get("sex"),
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
                    (id, molecule_id, set_id, brand_name, generic_name,
                     manufacturer, application_number, product_type,
                     indications_and_usage, dosage_and_administration,
                     contraindications, warnings, boxed_warning,
                     adverse_reactions, drug_interactions, mechanism_of_action,
                     source)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                            $11, $12, $13, $14, $15, $16, 'openfda_labels')
                    ON CONFLICT (set_id, version) DO UPDATE SET
                        molecule_id = EXCLUDED.molecule_id,
                        brand_name = EXCLUDED.brand_name,
                        indications_and_usage = EXCLUDED.indications_and_usage,
                        adverse_reactions = EXCLUDED.adverse_reactions,
                        updated_at = NOW()
                """,
                    str(uuid.uuid4()), molecule_id, set_id,
                    brand_names[0] if brand_names else None,
                    generic_names[0] if generic_names else None,
                    (openfda.get("manufacturer_name", [None]) or [None])[0],
                    (openfda.get("application_number", [None]) or [None])[0],
                    (openfda.get("product_type", [None]) or [None])[0],
                    _join_text(r.get("indications_and_usage")),
                    _join_text(r.get("dosage_and_administration")),
                    _join_text(r.get("contraindications")),
                    _join_text(r.get("warnings")),
                    _join_text(r.get("boxed_warning")),
                    _join_text(r.get("adverse_reactions")),
                    _join_text(r.get("drug_interactions")),
                    _join_text(r.get("mechanism_of_action")),
                )

    async def _silver_openfda_faers(self, molecule_id: str, response: dict) -> None:
        """Aggregate FAERS adverse events into silver.adverse_events."""
        results = response.get("results", [])
        if not results:
            return

        # Aggregate reactions across reports
        reaction_counts: dict = {}
        for r in results:
            patient = r.get("patient", {})
            is_serious = r.get("serious") == 1

            for rx in patient.get("reaction", []):
                pt = rx.get("reactionmeddrapt")
                if not pt:
                    continue
                if pt not in reaction_counts:
                    reaction_counts[pt] = {"total": 0, "serious": 0, "death": 0}
                reaction_counts[pt]["total"] += 1
                if is_serious:
                    reaction_counts[pt]["serious"] += 1
                outcome = rx.get("reactionoutcome")
                if outcome == "5":  # death
                    reaction_counts[pt]["death"] += 1

        async with self.db_pool.acquire() as conn:
            for pt, counts in reaction_counts.items():
                await conn.execute("""
                    INSERT INTO mol_silver.adverse_events
                    (id, molecule_id, meddra_pt, report_count,
                     serious_count, death_count, source)
                    VALUES ($1, $2, $3, $4, $5, $6, 'openfda_faers')
                    ON CONFLICT (molecule_id, meddra_pt_code) DO UPDATE SET
                        report_count = mol_silver.adverse_events.report_count + EXCLUDED.report_count,
                        serious_count = mol_silver.adverse_events.serious_count + EXCLUDED.serious_count,
                        death_count = mol_silver.adverse_events.death_count + EXCLUDED.death_count,
                        updated_at = NOW()
                """,
                    str(uuid.uuid4()), molecule_id, pt,
                    counts["total"], counts["serious"], counts["death"],
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
                        "orcid": a.get("author", {}).get("orcid"),
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
                     publication_year, journal, authors, first_author,
                     cited_by_count, is_open_access, keywords, source)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                            $9::jsonb, $10, $11, $12, $13::jsonb, 'openalex')
                    ON CONFLICT (openalex_id) DO UPDATE SET
                        title = EXCLUDED.title,
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
                WHERE id = $1::uuid
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
                (id, molecule_id, identifier_type, identifier_value, source, is_primary)
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
                WHERE id = $1::uuid
            """, molecule_id, drug.get("mechanism-of-action") or drug.get("mechanism_of_action"))

            await conn.execute("""
                INSERT INTO mol_silver.identifier_mappings
                (id, molecule_id, identifier_type, identifier_value, source, is_primary)
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
                WHERE id = $1::uuid
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
                (id, molecule_id, identifier_type, identifier_value, source, is_primary)
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

    async def _refresh_gold_molecule_profile(self, conn, molecule_id: str, drug_name: str) -> None:
        """Refresh gold_molecule_profile from silver tables."""
        # Fetch silver molecule (id is UUID, molecule_id is passed as string)
        mol = await conn.fetchrow(
            "SELECT * FROM mol_silver.molecules WHERE id = $1::uuid", molecule_id
        )
        if not mol:
            return

        # Count safety data
        ae_row = await conn.fetchrow("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN serious_count > 0 THEN 1 ELSE 0 END) as serious
            FROM mol_silver.adverse_events WHERE molecule_id::text = $1
        """, molecule_id)

        # Top adverse events
        top_aes = await conn.fetch("""
            SELECT meddra_pt, report_count FROM mol_silver.adverse_events
            WHERE molecule_id::text = $1
            ORDER BY report_count DESC LIMIT 10
        """, molecule_id)
        ae_summary = [{"term": r["meddra_pt"], "count": r["report_count"]} for r in top_aes]

        # Fetch identifiers
        ids = await conn.fetch(
            "SELECT identifier_type, identifier_value FROM mol_silver.identifier_mappings WHERE molecule_id::text = $1 AND is_primary = TRUE",
            molecule_id,
        )
        id_map = {r["identifier_type"]: r["identifier_value"] for r in ids}

        # Pipeline indications from trials
        pipeline = await conn.fetch("""
            SELECT phase, COUNT(*) as trial_count,
                   jsonb_agg(DISTINCT c) as conds
            FROM mol_silver.clinical_trials,
                 jsonb_array_elements_text(conditions) c
            WHERE molecule_id::text = $1
            GROUP BY phase
        """, molecule_id)
        pipeline_indications = [
            {"phase": r["phase"], "trial_count": r["trial_count"]}
            for r in pipeline
        ]

        # Patent info
        patent_row = await conn.fetchrow("""
            SELECT MIN(expiry_date) as earliest, COUNT(*) as cnt
            FROM mol_silver.patents WHERE molecule_id::text = $1
        """, molecule_id)

        # Determine lifecycle stage from max phase
        stage = _phase_to_lifecycle(mol.get("max_phase"))

        # Count data sources
        source_counts = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM mol_silver.clinical_trials WHERE molecule_id::text = $1) as trials,
                (SELECT COUNT(*) FROM mol_silver.drug_labels WHERE molecule_id::text = $1) as labels,
                (SELECT COUNT(*) FROM mol_silver.adverse_events WHERE molecule_id::text = $1) as aes,
                (SELECT COUNT(*) FROM mol_silver.molecule_publications mp
                 WHERE mp.molecule_id::text = $1) as pubs
        """, molecule_id)

        data_sources = {}
        if source_counts:
            if source_counts["trials"]:
                data_sources["clinical_trials"] = source_counts["trials"]
            if source_counts["labels"]:
                data_sources["drug_labels"] = source_counts["labels"]
            if source_counts["aes"]:
                data_sources["adverse_events"] = source_counts["aes"]
            if source_counts["pubs"]:
                data_sources["publications"] = source_counts["pubs"]

        total_sources = sum(1 for v in data_sources.values() if v > 0)
        completeness = min(1.0, total_sources / 5.0)

        # Upsert gold.molecule_profile (PK = molecule_id TEXT)
        try:
            await conn.execute("""
                INSERT INTO mol_gold.molecule_profile
                (molecule_id, molecule_name, molecule_type, inchi_key,
                 lifecycle_stage, lifecycle_stage_confidence, lifecycle_last_detected,
                 drugbank_id, chembl_id, pubchem_cid,
                 pipeline_indications, serious_ae_count, ae_summary,
                 therapeutic_area, mechanism_of_action,
                 earliest_patent_expiry, patent_count,
                 data_completeness_score, data_sources, last_data_update)
                VALUES ($1, $2, $3, $4, $5, 0.8, NOW(),
                        $6, $7, $8, $9::jsonb, $10, $11::jsonb,
                        $12, $13, $14, $15, $16, $17::jsonb, NOW())
                ON CONFLICT (molecule_id) DO UPDATE SET
                    molecule_name = EXCLUDED.molecule_name,
                    lifecycle_stage = EXCLUDED.lifecycle_stage,
                    lifecycle_last_detected = NOW(),
                    pipeline_indications = EXCLUDED.pipeline_indications,
                    serious_ae_count = EXCLUDED.serious_ae_count,
                    ae_summary = EXCLUDED.ae_summary,
                    mechanism_of_action = EXCLUDED.mechanism_of_action,
                    data_completeness_score = EXCLUDED.data_completeness_score,
                    data_sources = EXCLUDED.data_sources,
                    last_data_update = NOW(),
                    updated_at = NOW()
            """,
                molecule_id,
                mol.get("canonical_name") or drug_name,
                mol.get("molecule_type"),
                mol.get("inchi_key"),
                stage,
                id_map.get("drugbank_id"),
                id_map.get("chembl_id"),
                id_map.get("pubchem_cid"),
                json.dumps(pipeline_indications),
                ae_row["serious"] if ae_row else 0,
                json.dumps(ae_summary),
                (mol.get("therapeutic_areas") or [None])[0] if isinstance(mol.get("therapeutic_areas"), list) else None,
                mol.get("mechanism_of_action"),
                str(patent_row["earliest"]) if patent_row and patent_row["earliest"] else None,
                patent_row["cnt"] if patent_row else 0,
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

            # Rebuild from silver
            aes = await conn.fetch("""
                SELECT meddra_pt, meddra_pt_code, report_count,
                       serious_count, death_count, prr, ror
                FROM mol_silver.adverse_events
                WHERE molecule_id::text = $1 AND report_count >= 3
                ORDER BY report_count DESC
                LIMIT 100
            """, molecule_id)

            for ae in aes:
                is_signal = (ae.get("prr") or 0) >= 2.0 or ae["report_count"] >= 10
                await conn.execute("""
                    INSERT INTO mol_gold.safety_signals
                    (id, molecule_id, event_name, event_category,
                     report_count, seriousness, outcome,
                     reaction_name, reaction_meddra_pt,
                     case_count, serious_count, fatal_count,
                     pro_score, ror_score, is_signal)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                """,
                    str(uuid.uuid4()), molecule_id,
                    ae["meddra_pt"],  # event_name
                    'adverse_reaction',  # event_category
                    ae["report_count"],
                    'serious' if ae["serious_count"] > 0 else 'non-serious',  # seriousness
                    'fatal' if ae["death_count"] > 0 else None,  # outcome
                    ae["meddra_pt"],  # reaction_name
                    ae.get("meddra_pt_code"),  # reaction_meddra_pt
                    ae["report_count"],  # case_count
                    ae["serious_count"],
                    ae["death_count"],
                    ae.get("prr"), ae.get("ror"), is_signal,
                )
        except Exception as e:
            logger.warning(f"gold.safety_signals refresh skipped: {e}")

    async def _refresh_gold_lifecycle_stages(self, conn, molecule_id: str) -> None:
        """Refresh gold.lifecycle_stages from silver clinical trials."""
        try:
            # Group trials by phase to build lifecycle stages
            phases = await conn.fetch("""
                SELECT phase, status, COUNT(*) as cnt,
                       jsonb_agg(DISTINCT c) as indications
                FROM mol_silver.clinical_trials,
                     jsonb_array_elements_text(conditions) c
                WHERE molecule_id::text = $1
                GROUP BY phase, status
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
                    (id, molecule_id, stage, event_type, indication,
                     stage_confidence, evidence_count, primary_evidence_type)
                    VALUES ($1, $2, $3, $4, $5, 0.9, $6, 'clinical_trial')
                    ON CONFLICT (molecule_id, indication) DO UPDATE SET
                        stage = EXCLUDED.stage,
                        evidence_count = EXCLUDED.evidence_count,
                        updated_at = NOW()
                """,
                    str(uuid.uuid4()), molecule_id, stage,
                    row["status"] or 'development',
                    indication_str,
                    row["cnt"],
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
                SELECT nct_id, title, phase, status, enrollment, sponsor, conditions
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
                     phase, status, enrollment, sponsor, conditions)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                    ON CONFLICT (nct_id) DO UPDATE SET
                        phase = EXCLUDED.phase,
                        status = EXCLUDED.status,
                        enrollment = EXCLUDED.enrollment,
                        conditions = EXCLUDED.conditions,
                        updated_at = NOW()
                """,
                    str(uuid.uuid4()), molecule_id, nct_id,
                    t.get("title"),  # endpoint_name (using title as summary)
                    t.get("status"),  # result (using status as outcome indicator)
                    t.get("phase"),
                    t.get("status"),
                    t.get("enrollment"),
                    t.get("sponsor"),
                    json.dumps(t["conditions"]) if t.get("conditions") else None,
                )
        except Exception as e:
            logger.warning(f"gold.trial_outcomes refresh skipped: {e}")


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
