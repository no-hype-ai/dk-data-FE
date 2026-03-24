"""DEPRECATED: On-demand Raw → Bronze transformer.

THIS MODULE IS DEPRECATED. Use BronzeIngestionService from
data_platform/bronze_ingestion.py instead. This module only extracts
a SUBSET of columns with WRONG names (e.g., 'title' instead of
'brief_title', 'sponsor' instead of 'lead_sponsor_name').

BronzeIngestionService extracts ALL columns with correct API-derived names.

Source-specific extraction logic maps raw JSONB → bronze typed columns.
"""

import json
import uuid
from datetime import datetime
from typing import Optional

from loguru import logger


class BronzeTransformer:
    """Transforms raw API responses into typed bronze tables."""

    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def transform(self, source_name: str, raw_record_id: str, api_response: dict) -> int:
        """Transform a raw record into bronze rows.

        Returns the number of bronze rows inserted.
        """
        handler = self._HANDLERS.get(source_name)
        if handler is None:
            logger.debug(f"No bronze handler for source: {source_name}")
            return 0

        try:
            count = await handler(self, raw_record_id, api_response)
            # Mark raw record as processed
            await self._mark_processed(source_name, raw_record_id)
            logger.info(f"Bronze transform: {source_name} → {count} rows")
            return count
        except Exception as e:
            logger.error(f"Bronze transform error for {source_name}: {e}")
            return 0

    async def _mark_processed(self, source_name: str, raw_record_id: str) -> None:
        """Mark the raw record as processed to bronze."""
        schema = _RAW_SCHEMA_MAP.get(source_name, "raw")
        table = source_name
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    f"UPDATE {schema}.{table} SET processed_to_bronze = TRUE WHERE id = $1",
                    raw_record_id,
                )
        except Exception as e:
            logger.warning(f"Failed to mark raw record processed: {e}")

    # -------------------------------------------------------------------------
    # Source-specific handlers
    # -------------------------------------------------------------------------

    async def _transform_clinicaltrials(self, raw_id: str, response: dict) -> int:
        """Extract clinical trials from ClinicalTrials.gov API response."""
        studies = response.get("studies", [])
        if not studies:
            return 0

        rows = []
        for study in studies:
            proto = study.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status_mod = proto.get("statusModule", {})
            design = proto.get("designModule", {})
            sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
            conditions_mod = proto.get("conditionsModule", {})
            interventions_mod = proto.get("armsInterventionsModule", {})

            nct_id = ident.get("nctId")
            if not nct_id:
                continue

            # Parse dates safely
            start_date = _parse_date(status_mod.get("startDateStruct", {}).get("date"))
            completion_date = _parse_date(
                status_mod.get("completionDateStruct", {}).get("date")
            )

            # Extract phases
            phases = design.get("phases", [])
            phase = phases[0] if phases else None

            enrollment_info = design.get("enrollmentInfo", {})
            enrollment = enrollment_info.get("count")

            lead_sponsor = sponsor_mod.get("leadSponsor", {})
            sponsor_name = lead_sponsor.get("name")

            conditions = conditions_mod.get("conditions", [])
            interventions = [
                i.get("name") for i in interventions_mod.get("interventions", [])
            ]

            rows.append((
                str(uuid.uuid4()), raw_id, nct_id,
                ident.get("officialTitle") or ident.get("briefTitle"),
                phase, enrollment, sponsor_name,
                status_mod.get("overallStatus"),
                json.dumps(conditions), json.dumps(interventions),
                start_date, completion_date,
            ))

        if not rows:
            return 0

        async with self.db_pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO mol_bronze.clinicaltrials
                (id, raw_id, nct_id, brief_title, phase, enrollment_count, lead_sponsor_name,
                 overall_status, conditions, interventions, start_date, completion_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11, $12)
                ON CONFLICT (nct_id) DO UPDATE SET
                    brief_title = EXCLUDED.brief_title,
                    phase = EXCLUDED.phase,
                    enrollment_count = EXCLUDED.enrollment_count,
                    lead_sponsor_name = EXCLUDED.lead_sponsor_name,
                    overall_status = EXCLUDED.overall_status,
                    conditions = EXCLUDED.conditions,
                    interventions = EXCLUDED.interventions,
                    start_date = EXCLUDED.start_date,
                    completion_date = EXCLUDED.completion_date
            """, rows)
        return len(rows)

    async def _transform_openfda_labels(self, raw_id: str, response: dict) -> int:
        """Extract drug labels from OpenFDA Labels API response.

        Carries ALL label fields forward from raw to bronze — no column dropping.
        """
        results = response.get("results", [])
        if not results:
            return 0

        rows = []
        for r in results:
            set_id = r.get("set_id")
            if not set_id:
                continue

            openfda = r.get("openfda", {})
            brand_names = openfda.get("brand_name", [])
            generic_names = openfda.get("generic_name", [])
            manufacturers = openfda.get("manufacturer_name", [])
            routes = openfda.get("route", [])
            dosage_forms = openfda.get("dosage_form", [])
            application_numbers = openfda.get("application_number", [])

            rows.append((
                str(uuid.uuid4()), raw_id, set_id,
                r.get("spl_id"),
                r.get("version"),
                brand_names[0] if brand_names else None,
                generic_names[0] if generic_names else None,
                manufacturers[0] if manufacturers else None,
                application_numbers[0] if application_numbers else None,
                r.get("product_type"),
                json.dumps(routes) if routes else None,                     # route as jsonb
                _join_text(r.get("indications_and_usage")),
                _join_text(r.get("dosage_and_administration")),
                _join_text(r.get("contraindications")),
                _join_text(r.get("warnings_and_cautions") or r.get("warnings")),
                _join_text(r.get("boxed_warning")),
                _join_text(r.get("adverse_reactions")),
                _join_text(r.get("drug_interactions")),
                _join_text(r.get("mechanism_of_action")),
                r.get("effective_time"),
            ))

        if not rows:
            return 0

        async with self.db_pool.acquire() as conn:
            # Use existing bronze.openfda_labels column names (47 columns already exist)
            await conn.executemany("""
                INSERT INTO mol_bronze.openfda_labels
                (id, raw_id, set_id, spl_id, version,
                 brand_name, generic_name, manufacturer_name, application_number,
                 product_type, route, indications_and_usage,
                 dosage_and_administration, contraindications, warnings_and_cautions,
                 boxed_warning, adverse_reactions, drug_interactions,
                 mechanism_of_action, effective_time)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
                ON CONFLICT (set_id) DO UPDATE SET
                    brand_name = EXCLUDED.brand_name,
                    generic_name = EXCLUDED.generic_name,
                    manufacturer_name = EXCLUDED.manufacturer_name,
                    application_number = EXCLUDED.application_number,
                    indications_and_usage = EXCLUDED.indications_and_usage,
                    dosage_and_administration = EXCLUDED.dosage_and_administration,
                    adverse_reactions = EXCLUDED.adverse_reactions,
                    route = EXCLUDED.route,
                    warnings_and_cautions = EXCLUDED.warnings_and_cautions,
                    boxed_warning = EXCLUDED.boxed_warning,
                    drug_interactions = EXCLUDED.drug_interactions,
                    mechanism_of_action = EXCLUDED.mechanism_of_action,
                    effective_time = EXCLUDED.effective_time
            """, rows)
        return len(rows)

    async def _transform_openfda_faers(self, raw_id: str, response: dict) -> int:
        """Extract adverse event reports from OpenFDA FAERS API response."""
        results = response.get("results", [])
        if not results:
            return 0

        rows = []
        for r in results:
            report_id = r.get("safetyreportid")
            if not report_id:
                continue

            patient = r.get("patient", {})
            reactions = [rx.get("reactionmeddrapt") for rx in patient.get("reaction", [])]
            outcomes = [rx.get("reactionoutcome") for rx in patient.get("reaction", [])]
            drugs = [
                {"name": d.get("medicinalproduct"), "role": d.get("drugcharacterization")}
                for d in patient.get("drug", [])
            ]

            rows.append((
                str(uuid.uuid4()), raw_id, report_id,
                json.dumps(reactions), json.dumps(outcomes),
                r.get("serious"), json.dumps(drugs),
            ))

        if not rows:
            return 0

        async with self.db_pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO mol_bronze.openfda_faers
                (id, raw_id, safety_report_id, reactions, outcomes, serious, drugs)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7::jsonb)
                ON CONFLICT (safety_report_id) DO UPDATE SET
                    reactions = EXCLUDED.reactions,
                    outcomes = EXCLUDED.outcomes,
                    serious = EXCLUDED.serious,
                    drugs = EXCLUDED.drugs
            """, rows)
        return len(rows)

    async def _transform_chembl(self, raw_id: str, response: dict) -> int:
        """Extract molecule data from ChEMBL API response."""
        molecules = response.get("molecules", [])
        if not molecules:
            return 0

        rows = []
        for m in molecules:
            chembl_id = m.get("molecule_chembl_id")
            if not chembl_id:
                continue

            props = m.get("molecule_properties", {}) or {}
            rows.append((
                str(uuid.uuid4()), raw_id, chembl_id,
                m.get("pref_name"),
                m.get("max_phase"),
                props.get("full_mwt"),
                m.get("molecule_structures", {}).get("canonical_smiles") if m.get("molecule_structures") else None,
                m.get("molecule_type"),
            ))

        if not rows:
            return 0

        async with self.db_pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO mol_bronze.chembl
                (id, raw_id, chembl_id, pref_name, max_phase,
                 molecular_weight, canonical_smiles, molecule_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (chembl_id) DO UPDATE SET
                    pref_name = EXCLUDED.pref_name,
                    max_phase = EXCLUDED.max_phase,
                    molecular_weight = EXCLUDED.molecular_weight,
                    canonical_smiles = EXCLUDED.canonical_smiles,
                    molecule_type = EXCLUDED.molecule_type
            """, rows)
        return len(rows)

    async def _transform_pubmed(self, raw_id: str, response: dict) -> int:
        """Extract articles from PubMed/NCBI API response."""
        articles = response.get("articles", response.get("results", []))
        if not articles:
            return 0

        rows = []
        for a in articles:
            pmid = str(a.get("pmid", a.get("uid", "")))
            if not pmid:
                continue

            pub_date = _parse_date(a.get("pubdate") or a.get("pub_date"))
            authors = a.get("authors", [])

            rows.append((
                str(uuid.uuid4()), raw_id, pmid,
                a.get("title"),
                a.get("abstract"),
                json.dumps(authors) if authors else None,
                a.get("source") or a.get("journal"),
                pub_date,
            ))

        if not rows:
            return 0

        async with self.db_pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO mol_bronze.pubmed
                (id, raw_id, pmid, title, abstract, authors, journal, pub_date)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
                ON CONFLICT (pmid) DO UPDATE SET
                    title = EXCLUDED.title,
                    abstract = EXCLUDED.abstract,
                    authors = EXCLUDED.authors,
                    journal = EXCLUDED.journal
            """, rows)
        return len(rows)

    async def _transform_openalex(self, raw_id: str, response: dict) -> int:
        """Extract works from OpenAlex API response."""
        results = response.get("results", [])
        if not results:
            return 0

        rows = []
        for w in results:
            work_id = w.get("id", "")
            if not work_id:
                continue

            authorships = w.get("authorships", [])
            authors = [
                {
                    "name": a.get("author", {}).get("display_name"),
                    "institution": (a.get("institutions", [{}]) or [{}])[0].get("display_name"),
                }
                for a in authorships
            ]

            rows.append((
                str(uuid.uuid4()), raw_id, work_id,
                w.get("title"),
                w.get("doi"),
                json.dumps(authors),
                w.get("cited_by_count", 0),
                w.get("publication_year"),
            ))

        if not rows:
            return 0

        async with self.db_pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO mol_bronze.openalex
                (id, raw_id, work_id, title, doi, authors, cited_by_count, publication_year)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
                ON CONFLICT (work_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    doi = EXCLUDED.doi,
                    authors = EXCLUDED.authors,
                    cited_by_count = EXCLUDED.cited_by_count
            """, rows)
        return len(rows)

    async def _transform_orange_book(self, raw_id: str, response: dict) -> int:
        """Extract products from FDA Orange Book API response."""
        results = response.get("results", [])
        if not results:
            return 0

        rows = []
        for r in results:
            app_no = r.get("application_number") or r.get("appl_no")
            if not app_no:
                continue

            approval_date = _parse_date(r.get("approval_date"))

            rows.append((
                str(uuid.uuid4()), raw_id, app_no,
                r.get("trade_name") or r.get("product_name"),
                r.get("active_ingredient") or r.get("ingredient"),
                approval_date,
                r.get("applicant"),
            ))

        if not rows:
            return 0

        async with self.db_pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO mol_bronze.orange_book
                (id, raw_id, application_number, product_name, active_ingredient,
                 approval_date, applicant)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, rows)
        return len(rows)

    async def _transform_drugbank(self, raw_id: str, response: dict) -> int:
        """Extract drugs from DrugBank response."""
        drugs = response.get("drugs", [])
        if not drugs:
            return 0

        rows = []
        for d in drugs:
            db_id = d.get("drugbank_id") or d.get("drugbank-id")
            if not db_id:
                continue

            rows.append((
                str(uuid.uuid4()), raw_id, db_id,
                d.get("name"),
                d.get("description"),
                d.get("indication"),
                d.get("pharmacodynamics"),
            ))

        if not rows:
            return 0

        async with self.db_pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO mol_bronze.drugbank
                (id, raw_id, drugbank_id, name, description, indication, pharmacodynamics)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (drugbank_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    indication = EXCLUDED.indication,
                    pharmacodynamics = EXCLUDED.pharmacodynamics
            """, rows)
        return len(rows)

    async def _transform_pubchem(self, raw_id: str, response: dict) -> int:
        """Extract compound data from PubChem API response."""
        # PubChem responses vary in structure
        props = response.get("PropertyTable", {}).get("Properties", [])
        compounds = response.get("PC_Compounds", props)
        if not compounds:
            return 0

        rows = []
        for c in compounds:
            cid = str(c.get("CID", c.get("cid", "")))
            if not cid:
                continue

            rows.append((
                str(uuid.uuid4()), raw_id, cid,
                c.get("IUPACName") or c.get("iupac_name"),
                c.get("CanonicalSMILES") or c.get("canonical_smiles"),
                c.get("MolecularFormula") or c.get("molecular_formula"),
                c.get("MolecularWeight") or c.get("molecular_weight"),
            ))

        if not rows:
            return 0

        async with self.db_pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO mol_bronze.pubchem
                (id, raw_id, cid, iupac_name, canonical_smiles,
                 molecular_formula, molecular_weight)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (cid) DO UPDATE SET
                    iupac_name = EXCLUDED.iupac_name,
                    canonical_smiles = EXCLUDED.canonical_smiles,
                    molecular_formula = EXCLUDED.molecular_formula,
                    molecular_weight = EXCLUDED.molecular_weight
            """, rows)
        return len(rows)

    # Handler registry
    _HANDLERS = {
        "clinicaltrials": _transform_clinicaltrials,
        "openfda_labels": _transform_openfda_labels,
        "openfda_faers": _transform_openfda_faers,
        "chembl": _transform_chembl,
        "pubmed": _transform_pubmed,
        "openalex": _transform_openalex,
        "orange_book": _transform_orange_book,
        "drugbank": _transform_drugbank,
        "pubchem": _transform_pubchem,
    }


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

# Maps source_name → raw schema (mol_raw for molecule sources, raw for others)
_RAW_SCHEMA_MAP = {
    "clinicaltrials": "mol_raw",
    "openfda_faers": "mol_raw",
    "openfda_labels": "mol_raw",
    "chembl": "mol_raw",
    "drugbank": "mol_raw",
    "pubchem": "mol_raw",
    "uniprot": "mol_raw",
    "pdb": "mol_raw",
    "openalex": "mol_raw",
    "sider": "mol_raw",
    "pubmed": "raw",
    "orange_book": "raw",
    "ema": "raw",
    "sec_edgar": "raw",
    "who_icd": "raw",
    "hta_decisions": "raw",
    "cochrane": "raw",
    "epo_patents": "raw",
    "uspto_patents": "raw",
    # CMS sources (raw schema)
    "cms_nppes": "raw",
    "cms_part_d_prescriber": "raw",
    "cms_physician_puf": "raw",
    "cms_open_payments": "raw",
    "cms_care_compare": "raw",
    "cms_pos": "raw",
    "cms_pecos": "raw",
    "cms_chow": "raw",
    "cms_hospital_affiliation": "raw",
    "cms_inpatient_puf": "raw",
    "cms_outpatient_puf": "raw",
    "cms_hospital_quality": "raw",
    "cms_hospital_general_info": "raw",
    "cms_hcris": "raw",
    "cms_magnet": "raw",
    "cms_ndc": "raw",
    "cms_part_d_spending": "raw",
    "cms_part_b_spending": "raw",
    "cms_formulary": "raw",
    "cms_rbcs": "raw",
    "cms_usp": "raw",
    "cms_nucc": "raw",
    "cms_geographic_variation": "raw",
    "cms_chronic_conditions": "raw",
    "cms_post_acute": "raw",
    "cms_dmepos": "raw",
    "cms_ddinter": "raw",
    "cms_stabilis": "raw",
}


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Best-effort date parsing from various API date formats."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y", "%B %d, %Y", "%B %Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _join_text(field) -> Optional[str]:
    """Join OpenFDA text arrays into a single string."""
    if isinstance(field, list):
        return " ".join(field)
    if isinstance(field, str):
        return field
    return None
