"""
OpenFDA API Client.

Provides access to FDA public data:
- Drug labels (SPL)
- Adverse events (FAERS)
- NDC directory
- Orange Book (exclusivity/patents)
- Drug applications (NDAs, BLAs, ANDAs)

API Documentation: https://open.fda.gov/apis/
Rate Limit: 240 requests/minute with API key, 40/minute without
"""

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager, DataSource


@dataclass
class DrugLabel:
    """FDA drug label information."""

    # Identifiers
    application_number: str  # NDA/BLA/ANDA number
    product_ndc: List[str] = field(default_factory=list)
    spl_id: Optional[str] = None
    rxcui: List[str] = field(default_factory=list)  # RxNorm CUIs
    unii: List[str] = field(default_factory=list)   # FDA substance identifiers

    # Names
    brand_name: Optional[str] = None
    generic_name: Optional[str] = None
    manufacturer_name: Optional[str] = None

    # Indications and usage
    indications_and_usage: List[str] = field(default_factory=list)

    # Pharmacology
    mechanism_of_action: Optional[str] = None
    pharmacodynamics: Optional[str] = None
    pharmacokinetics: Optional[str] = None
    clinical_pharmacology: List[str] = field(default_factory=list)  # Clinical pharmacology section

    # CLINICAL STUDIES - Contains efficacy data, trial results, response rates
    clinical_studies: List[str] = field(default_factory=list)  # Section 14 - efficacy numbers!

    # Product description
    description: List[str] = field(default_factory=list)  # Drug description

    # Pharmacological classes
    pharm_class_moa: List[str] = field(default_factory=list)  # Mechanism of action
    pharm_class_epc: List[str] = field(default_factory=list)  # Established pharma class
    pharm_class_pe: List[str] = field(default_factory=list)   # Physiologic effect
    pharm_class_cs: List[str] = field(default_factory=list)   # Chemical structure

    # Warnings and Safety
    warnings: List[str] = field(default_factory=list)
    boxed_warning: Optional[str] = None
    contraindications: List[str] = field(default_factory=list)
    adverse_reactions: List[str] = field(default_factory=list)  # From label text
    drug_interactions: List[str] = field(default_factory=list)  # Drug-drug interactions
    precautions: List[str] = field(default_factory=list)  # General precautions

    # Special populations
    pregnancy: List[str] = field(default_factory=list)
    nursing_mothers: List[str] = field(default_factory=list)
    pediatric_use: List[str] = field(default_factory=list)
    geriatric_use: List[str] = field(default_factory=list)

    # Administration
    dosage_and_administration: List[str] = field(default_factory=list)
    dosage_forms_and_strengths: List[str] = field(default_factory=list)
    how_supplied: List[str] = field(default_factory=list)
    route: List[str] = field(default_factory=list)

    # Additional safety
    overdosage: List[str] = field(default_factory=list)
    nonclinical_toxicology: List[str] = field(default_factory=list)

    # Status
    marketing_status: Optional[str] = None
    effective_date: Optional[date] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application_number": self.application_number,
            "product_ndc": self.product_ndc,
            "spl_id": self.spl_id,
            "rxcui": self.rxcui,
            "unii": self.unii,
            "brand_name": self.brand_name,
            "generic_name": self.generic_name,
            "manufacturer_name": self.manufacturer_name,
            "indications_and_usage": self.indications_and_usage,
            "mechanism_of_action": self.mechanism_of_action,
            "pharmacodynamics": self.pharmacodynamics,
            "pharmacokinetics": self.pharmacokinetics,
            "clinical_pharmacology": self.clinical_pharmacology,
            "clinical_studies": self.clinical_studies,
            "description": self.description,
            "pharm_class_moa": self.pharm_class_moa,
            "pharm_class_epc": self.pharm_class_epc,
            "pharm_class_pe": self.pharm_class_pe,
            "pharm_class_cs": self.pharm_class_cs,
            "warnings": self.warnings,
            "boxed_warning": self.boxed_warning,
            "contraindications": self.contraindications,
            "adverse_reactions": self.adverse_reactions,
            "drug_interactions": self.drug_interactions,
            "precautions": self.precautions,
            "pregnancy": self.pregnancy,
            "nursing_mothers": self.nursing_mothers,
            "pediatric_use": self.pediatric_use,
            "geriatric_use": self.geriatric_use,
            "dosage_and_administration": self.dosage_and_administration,
            "dosage_forms_and_strengths": self.dosage_forms_and_strengths,
            "how_supplied": self.how_supplied,
            "route": self.route,
            "overdosage": self.overdosage,
            "nonclinical_toxicology": self.nonclinical_toxicology,
            "marketing_status": self.marketing_status,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
        }


@dataclass
class AdverseEvent:
    """FDA adverse event report from FAERS."""

    report_id: str
    receive_date: Optional[date] = None

    # Patient
    patient_age: Optional[float] = None
    patient_sex: Optional[str] = None
    patient_weight: Optional[float] = None

    # Drug info
    drug_name: Optional[str] = None
    drug_characterization: Optional[str] = None  # "1"=suspect, "2"=concomitant, "3"=interacting

    # Reactions
    reactions: List[str] = field(default_factory=list)
    reaction_outcomes: List[str] = field(default_factory=list)

    # Seriousness
    serious: bool = False
    serious_death: bool = False
    serious_hospitalization: bool = False
    serious_life_threatening: bool = False
    serious_disability: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "receive_date": self.receive_date.isoformat() if self.receive_date else None,
            "patient_age": self.patient_age,
            "patient_sex": self.patient_sex,
            "patient_weight": self.patient_weight,
            "drug_name": self.drug_name,
            "drug_characterization": self.drug_characterization,
            "reactions": self.reactions,
            "reaction_outcomes": self.reaction_outcomes,
            "serious": self.serious,
            "serious_death": self.serious_death,
            "serious_hospitalization": self.serious_hospitalization,
            "serious_life_threatening": self.serious_life_threatening,
            "serious_disability": self.serious_disability,
        }


@dataclass
class OrangeBookEntry:
    """Orange Book entry for exclusivity and patent info."""

    application_number: str
    product_number: str

    # Drug info
    ingredient: Optional[str] = None
    trade_name: Optional[str] = None
    applicant: Optional[str] = None
    dosage_form: Optional[str] = None
    route: Optional[str] = None
    strength: Optional[str] = None

    # Approval
    approval_date: Optional[date] = None
    approval_type: Optional[str] = None  # Standard, Priority, etc.
    therapeutic_equivalence: Optional[str] = None

    # Patents
    patents: List[Dict[str, Any]] = field(default_factory=list)

    # Exclusivity
    exclusivities: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application_number": self.application_number,
            "product_number": self.product_number,
            "ingredient": self.ingredient,
            "trade_name": self.trade_name,
            "applicant": self.applicant,
            "dosage_form": self.dosage_form,
            "route": self.route,
            "strength": self.strength,
            "approval_date": self.approval_date.isoformat() if self.approval_date else None,
            "approval_type": self.approval_type,
            "therapeutic_equivalence": self.therapeutic_equivalence,
            "patents": self.patents,
            "exclusivities": self.exclusivities,
        }


@dataclass
class DrugApplication:
    """FDA drug application (NDA, BLA, ANDA)."""

    application_number: str
    sponsor_name: Optional[str] = None
    application_type: Optional[str] = None  # NDA, BLA, ANDA

    # Products
    products: List[Dict[str, Any]] = field(default_factory=list)

    # Submissions
    submissions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application_number": self.application_number,
            "sponsor_name": self.sponsor_name,
            "application_type": self.application_type,
            "products": self.products,
            "submissions": self.submissions,
        }


class OpenFDAClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for OpenFDA REST API.

    Optional API key from https://open.fda.gov/apis/authentication/
    Set via OPENFDA_API_KEY environment variable.

    Usage:
        client = OpenFDAClient()
        labels = await client.search_drug_labels("aspirin")
        events = await client.get_adverse_events("aspirin", limit=100)
    """

    # Endpoints
    ENDPOINT_DRUG_LABEL = "/drug/label.json"
    ENDPOINT_DRUG_EVENT = "/drug/event.json"
    ENDPOINT_DRUG_NDC = "/drug/ndc.json"
    ENDPOINT_DRUG_APPLICATION = "/drug/drugsfda.json"

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        api_key = os.getenv("OPENFDA_API_KEY")

        config = APIClientConfig(
            base_url="https://api.fda.gov",
            timeout=30.0,
            max_retries=3,
            requests_per_second=4.0 if api_key else 0.67,  # 240/min or 40/min
            cache_ttl=86400,  # 24 hours (labels update daily)
        )
        super().__init__(config, cache_manager)
        self._api_key = api_key

    def _add_api_key(self, params: Optional[Dict] = None) -> Dict:
        """Add API key to request parameters if available."""
        if params is None:
            params = {}
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    async def health_check(self) -> bool:
        """Check if OpenFDA API is accessible."""
        try:
            result = await self._get(
                self.ENDPOINT_DRUG_LABEL,
                params=self._add_api_key({"search": "aspirin", "limit": 1}),
                use_cache=False
            )
            return "results" in result
        except Exception as e:
            logger.error(f"OpenFDA health check failed: {e}")
            return False

    async def search_drug_labels(
        self,
        query: str,
        search_field: str = "openfda.generic_name",
        limit: int = 10
    ) -> List[DrugLabel]:
        """
        Search drug labels.

        Args:
            query: Search term
            search_field: Field to search (generic_name, brand_name, etc.)
            limit: Maximum results

        Returns:
            List of drug labels
        """
        search = f'{search_field}:"{query}"'

        try:
            result = await self._get(
                self.ENDPOINT_DRUG_LABEL,
                params=self._add_api_key({
                    "search": search,
                    "limit": min(limit, 100),
                })
            )

            labels = []
            for item in result.get("results", []):
                openfda = item.get("openfda", {})

                label = DrugLabel(
                    application_number=openfda.get("application_number", [""])[0],
                    product_ndc=openfda.get("product_ndc", []),
                    spl_id=item.get("spl_id"),
                    rxcui=openfda.get("rxcui", []),
                    unii=openfda.get("unii", []),
                    brand_name=openfda.get("brand_name", [None])[0],
                    generic_name=openfda.get("generic_name", [None])[0],
                    manufacturer_name=openfda.get("manufacturer_name", [None])[0],
                    indications_and_usage=item.get("indications_and_usage", []),
                    mechanism_of_action=item.get("mechanism_of_action", [None])[0] if item.get("mechanism_of_action") else None,
                    pharmacodynamics=item.get("pharmacodynamics", [None])[0] if item.get("pharmacodynamics") else None,
                    pharmacokinetics=item.get("pharmacokinetics", [None])[0] if item.get("pharmacokinetics") else None,
                    clinical_pharmacology=item.get("clinical_pharmacology", []),
                    clinical_studies=item.get("clinical_studies", []),  # Section 14 - efficacy data!
                    description=item.get("description", []),
                    pharm_class_moa=openfda.get("pharm_class_moa", []),
                    pharm_class_epc=openfda.get("pharm_class_epc", []),
                    pharm_class_pe=openfda.get("pharm_class_pe", []),
                    pharm_class_cs=openfda.get("pharm_class_cs", []),
                    warnings=item.get("warnings", []) + item.get("warnings_and_cautions", []),
                    boxed_warning=item.get("boxed_warning", [None])[0] if item.get("boxed_warning") else None,
                    contraindications=item.get("contraindications", []),
                    adverse_reactions=item.get("adverse_reactions", []),
                    drug_interactions=item.get("drug_interactions", []),
                    precautions=item.get("precautions", []),
                    pregnancy=item.get("pregnancy", []) + item.get("pregnancy_or_breast_feeding", []),
                    nursing_mothers=item.get("nursing_mothers", []),
                    pediatric_use=item.get("pediatric_use", []),
                    geriatric_use=item.get("geriatric_use", []),
                    dosage_and_administration=item.get("dosage_and_administration", []),
                    dosage_forms_and_strengths=item.get("dosage_forms_and_strengths", []),
                    how_supplied=item.get("how_supplied", []),
                    route=openfda.get("route", []),
                    overdosage=item.get("overdosage", []),
                    nonclinical_toxicology=item.get("nonclinical_toxicology", []),
                )
                labels.append(label)

            return labels
        except Exception as e:
            logger.error(f"Error searching drug labels for '{query}': {e}")
            return []

    async def comprehensive_drug_search(
        self,
        query: str,
        limit: int = 100,
        include_brand_search: bool = True,
    ) -> List[DrugLabel]:
        """
        Comprehensive drug label search across multiple fields.

        Searches both generic_name and brand_name fields, deduplicates results,
        and handles case sensitivity.

        Args:
            query: Drug name (generic or brand)
            limit: Maximum results
            include_brand_search: Also search brand_name field

        Returns:
            List of drug labels
        """
        seen_spl_ids = set()
        all_labels = []
        query_lower = query.lower().strip()

        # Search fields to try (in order of priority)
        search_attempts = [
            # Try exact generic name match first
            (f'openfda.generic_name:"{query_lower}"', "generic_exact"),
            # Try brand name
            (f'openfda.brand_name:"{query}"', "brand_exact") if include_brand_search else None,
            # Try broader search with wildcards
            (f'openfda.generic_name:{query_lower}*', "generic_wildcard"),
            (f'openfda.brand_name:{query}*', "brand_wildcard") if include_brand_search else None,
            # Try substance name
            (f'openfda.substance_name:"{query}"', "substance"),
        ]

        for attempt in search_attempts:
            if attempt is None:
                continue

            search_query, attempt_type = attempt

            try:
                # Use higher limit for comprehensive search
                result = await self._get(
                    self.ENDPOINT_DRUG_LABEL,
                    params=self._add_api_key({
                        "search": search_query,
                        "limit": min(limit, 1000),  # FDA allows up to 1000
                    })
                )

                for item in result.get("results", []):
                    spl_id = item.get("spl_id", "")
                    if spl_id and spl_id in seen_spl_ids:
                        continue
                    if spl_id:
                        seen_spl_ids.add(spl_id)

                    openfda = item.get("openfda", {})

                    label = DrugLabel(
                        application_number=openfda.get("application_number", [""])[0],
                        product_ndc=openfda.get("product_ndc", []),
                        spl_id=spl_id,
                        rxcui=openfda.get("rxcui", []),
                        unii=openfda.get("unii", []),
                        brand_name=openfda.get("brand_name", [None])[0],
                        generic_name=openfda.get("generic_name", [None])[0],
                        manufacturer_name=openfda.get("manufacturer_name", [None])[0],
                        indications_and_usage=item.get("indications_and_usage", []),
                        mechanism_of_action=item.get("mechanism_of_action", [None])[0] if item.get("mechanism_of_action") else None,
                        pharmacodynamics=item.get("pharmacodynamics", [None])[0] if item.get("pharmacodynamics") else None,
                        pharmacokinetics=item.get("pharmacokinetics", [None])[0] if item.get("pharmacokinetics") else None,
                        clinical_pharmacology=item.get("clinical_pharmacology", []),
                        clinical_studies=item.get("clinical_studies", []),  # Section 14 - efficacy data!
                        description=item.get("description", []),
                        pharm_class_moa=openfda.get("pharm_class_moa", []),
                        pharm_class_epc=openfda.get("pharm_class_epc", []),
                        pharm_class_pe=openfda.get("pharm_class_pe", []),
                        pharm_class_cs=openfda.get("pharm_class_cs", []),
                        warnings=item.get("warnings", []) + item.get("warnings_and_cautions", []),
                        boxed_warning=item.get("boxed_warning", [None])[0] if item.get("boxed_warning") else None,
                        contraindications=item.get("contraindications", []),
                        adverse_reactions=item.get("adverse_reactions", []),
                        drug_interactions=item.get("drug_interactions", []),
                        precautions=item.get("precautions", []),
                        pregnancy=item.get("pregnancy", []) + item.get("pregnancy_or_breast_feeding", []),
                        nursing_mothers=item.get("nursing_mothers", []),
                        pediatric_use=item.get("pediatric_use", []),
                        geriatric_use=item.get("geriatric_use", []),
                        dosage_and_administration=item.get("dosage_and_administration", []),
                        dosage_forms_and_strengths=item.get("dosage_forms_and_strengths", []),
                        how_supplied=item.get("how_supplied", []),
                        route=openfda.get("route", []),
                        overdosage=item.get("overdosage", []),
                        nonclinical_toxicology=item.get("nonclinical_toxicology", []),
                    )
                    all_labels.append(label)

                    if len(all_labels) >= limit:
                        break

                logger.debug(f"OpenFDA {attempt_type} search for '{query}': found {len(result.get('results', []))} results")

                # If we found enough results, stop searching
                if len(all_labels) >= limit:
                    break

            except Exception as e:
                logger.debug(f"OpenFDA {attempt_type} search for '{query}' failed: {e}")
                continue

        logger.info(f"OpenFDA comprehensive search for '{query}': found {len(all_labels)} total unique labels")
        return all_labels[:limit]

    async def get_label_by_application(self, application_number: str) -> Optional[DrugLabel]:
        """
        Get drug label by application number (NDA/BLA/ANDA).

        Args:
            application_number: FDA application number

        Returns:
            DrugLabel or None
        """
        labels = await self.search_drug_labels(
            application_number,
            search_field="openfda.application_number",
            limit=1
        )
        return labels[0] if labels else None

    async def get_adverse_events(
        self,
        drug_name: str,
        limit: int = 100,
        serious_only: bool = False
    ) -> List[AdverseEvent]:
        """
        Get adverse event reports for a drug.

        Args:
            drug_name: Drug name to search
            limit: Maximum results
            serious_only: Filter for serious events only

        Returns:
            List of adverse events
        """
        search = f'patient.drug.openfda.generic_name:"{drug_name}"'
        if serious_only:
            search += " AND serious:1"

        try:
            result = await self._get(
                self.ENDPOINT_DRUG_EVENT,
                params=self._add_api_key({
                    "search": search,
                    "limit": min(limit, 100),
                })
            )

            events = []
            for item in result.get("results", []):
                patient = item.get("patient", {})

                # Find the drug info
                drug_info = {}
                for drug in patient.get("drug", []):
                    openfda = drug.get("openfda", {})
                    names = openfda.get("generic_name", []) + openfda.get("brand_name", [])
                    if any(drug_name.lower() in n.lower() for n in names):
                        drug_info = drug
                        break

                # Parse reactions
                reactions = []
                outcomes = []
                for reaction in patient.get("reaction", []):
                    reactions.append(reaction.get("reactionmeddrapt", ""))
                    if reaction.get("reactionoutcome"):
                        outcomes.append(reaction.get("reactionoutcome"))

                event = AdverseEvent(
                    report_id=item.get("safetyreportid", ""),
                    receive_date=self._parse_date(item.get("receivedate")),
                    patient_age=patient.get("patientonsetage"),
                    patient_sex=patient.get("patientsex"),
                    patient_weight=patient.get("patientweight"),
                    drug_name=drug_info.get("medicinalproduct"),
                    drug_characterization=drug_info.get("drugcharacterization"),
                    reactions=reactions,
                    reaction_outcomes=outcomes,
                    serious=item.get("serious") == "1",
                    serious_death=item.get("seriousnessdeath") == "1",
                    serious_hospitalization=item.get("seriousnesshospitalization") == "1",
                    serious_life_threatening=item.get("seriousnesslifethreatening") == "1",
                    serious_disability=item.get("seriousnessdisabling") == "1",
                )
                events.append(event)

            return events
        except Exception as e:
            logger.error(f"Error getting adverse events for '{drug_name}': {e}")
            return []

    async def count_adverse_events(
        self,
        drug_name: str,
        count_field: str = "patient.reaction.reactionmeddrapt.exact"
    ) -> Dict[str, int]:
        """
        Count adverse events by a field.

        Args:
            drug_name: Drug name to search
            count_field: Field to count by

        Returns:
            Dictionary of counts
        """
        search = f'patient.drug.openfda.generic_name:"{drug_name}"'

        try:
            result = await self._get(
                self.ENDPOINT_DRUG_EVENT,
                params=self._add_api_key({
                    "search": search,
                    "count": count_field,
                })
            )

            counts = {}
            for item in result.get("results", []):
                term = item.get("term", "")
                count = item.get("count", 0)
                counts[term] = count

            return counts
        except Exception as e:
            logger.error(f"Error counting adverse events for '{drug_name}': {e}")
            return {}

    async def get_orange_book(
        self,
        ingredient: Optional[str] = None,
        application_number: Optional[str] = None
    ) -> List[OrangeBookEntry]:
        """
        Get Orange Book entries (exclusivity and patent data).

        Note: OpenFDA provides Orange Book data via the drugsfda endpoint.

        Args:
            ingredient: Active ingredient name
            application_number: FDA application number

        Returns:
            List of Orange Book entries
        """
        if ingredient:
            search = f'products.active_ingredients.name:"{ingredient}"'
        elif application_number:
            search = f'application_number:"{application_number}"'
        else:
            return []

        try:
            result = await self._get(
                self.ENDPOINT_DRUG_APPLICATION,
                params=self._add_api_key({
                    "search": search,
                    "limit": 100,
                })
            )

            entries = []
            for item in result.get("results", []):
                app_num = item.get("application_number", "")

                for product in item.get("products", []):
                    entry = OrangeBookEntry(
                        application_number=app_num,
                        product_number=product.get("product_number", ""),
                        ingredient=product.get("active_ingredients", [{}])[0].get("name") if product.get("active_ingredients") else None,
                        trade_name=product.get("brand_name"),
                        applicant=item.get("sponsor_name"),
                        dosage_form=product.get("dosage_form"),
                        route=product.get("route"),
                        strength=product.get("active_ingredients", [{}])[0].get("strength") if product.get("active_ingredients") else None,
                        approval_date=self._parse_date(item.get("submissions", [{}])[0].get("submission_status_date")) if item.get("submissions") else None,
                        therapeutic_equivalence=product.get("te_code"),
                    )
                    entries.append(entry)

            return entries
        except Exception as e:
            logger.error(f"Error getting Orange Book data: {e}")
            return []

    async def get_drug_applications(
        self,
        sponsor_name: Optional[str] = None,
        application_number: Optional[str] = None
    ) -> List[DrugApplication]:
        """
        Get FDA drug applications.

        Args:
            sponsor_name: Sponsor/company name
            application_number: FDA application number

        Returns:
            List of drug applications
        """
        if sponsor_name:
            search = f'sponsor_name:"{sponsor_name}"'
        elif application_number:
            search = f'application_number:"{application_number}"'
        else:
            return []

        try:
            result = await self._get(
                self.ENDPOINT_DRUG_APPLICATION,
                params=self._add_api_key({
                    "search": search,
                    "limit": 100,
                })
            )

            applications = []
            for item in result.get("results", []):
                app = DrugApplication(
                    application_number=item.get("application_number", ""),
                    sponsor_name=item.get("sponsor_name"),
                    application_type=item.get("application_type"),
                    products=item.get("products", []),
                    submissions=item.get("submissions", []),
                )
                applications.append(app)

            return applications
        except Exception as e:
            logger.error(f"Error getting drug applications: {e}")
            return []

    async def get_mechanism_of_action(self, drug_name: str) -> List[str]:
        """
        Get mechanism of action for a drug from labels.

        Args:
            drug_name: Drug name

        Returns:
            List of MOA strings
        """
        labels = await self.search_drug_labels(drug_name, limit=5)

        moas = set()
        for label in labels:
            if label.mechanism_of_action:
                moas.add(label.mechanism_of_action)
            moas.update(label.pharm_class_moa)

        return list(moas)

    async def get_indications(self, drug_name: str) -> List[str]:
        """
        Get indications for a drug from labels.

        Args:
            drug_name: Drug name

        Returns:
            List of indication strings
        """
        labels = await self.search_drug_labels(drug_name, limit=5)

        indications = []
        for label in labels:
            indications.extend(label.indications_and_usage)

        return indications

    async def search_by_pharm_class(
        self,
        pharm_class: str,
        class_type: str = "moa",
        limit: int = 50,
    ) -> "APIResponse":
        """
        Search for drugs by pharmacological class.

        Args:
            pharm_class: Pharmacological class to search for
            class_type: Type of class - "moa" (mechanism of action) or "epc" (established pharmacologic class)
            limit: Maximum results

        Returns:
            APIResponse with drugs matching the pharmacological class
        """
        from .base_client import APIResponse

        try:
            # Build search query based on class type
            if class_type == "moa":
                search_field = "openfda.pharm_class_moa"
            elif class_type == "epc":
                search_field = "openfda.pharm_class_epc"
            else:
                search_field = "openfda.pharm_class_moa"

            # Build search string
            search = f'{search_field}:"{pharm_class}"'

            result = await self._get(
                self.ENDPOINT_DRUG_LABEL,
                params=self._add_api_key({
                    "search": search,
                    "limit": min(limit, 100),
                })
            )

            results = result.get("results", [])

            # Extract drug information
            drugs = []
            seen_names = set()

            for item in results:
                openfda = item.get("openfda", {})

                # Get drug names
                generic_names = openfda.get("generic_name", [])
                brand_names = openfda.get("brand_name", [])
                manufacturers = openfda.get("manufacturer_name", [])

                generic_name = generic_names[0] if generic_names else None
                brand_name = brand_names[0] if brand_names else None
                manufacturer = manufacturers[0] if manufacturers else None

                # Skip duplicates
                name_key = (generic_name or brand_name or "").lower()
                if name_key in seen_names or not name_key:
                    continue
                seen_names.add(name_key)

                drugs.append({
                    "generic_name": generic_name,
                    "brand_name": brand_name,
                    "manufacturer_name": manufacturer,
                    "pharm_class_moa": openfda.get("pharm_class_moa", []),
                    "pharm_class_epc": openfda.get("pharm_class_epc", []),
                    "application_number": openfda.get("application_number", [None])[0],
                })

            return APIResponse(
                success=True,
                data={"drugs": drugs, "total": len(drugs)},
            )

        except Exception as e:
            logger.error(f"Error searching by pharm class: {e}")
            return APIResponse(success=False, error=str(e))

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse OpenFDA date format (YYYYMMDD)."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y%m%d").date()
        except ValueError:
            return None


# Singleton instance
_openfda_client: Optional[OpenFDAClient] = None


async def get_openfda_client(cache_manager: Optional[CacheManager] = None) -> OpenFDAClient:
    """Get or create the OpenFDA client instance."""
    global _openfda_client

    if _openfda_client is None:
        _openfda_client = OpenFDAClient(cache_manager)

    return _openfda_client
