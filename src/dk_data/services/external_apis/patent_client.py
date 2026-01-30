"""
PatentsView API Client.

Implements T023: PatentsViewClient for USPTO patent data

PatentsView API Status (as of January 2025):
- Legacy API (api.patentsview.org) has been discontinued
- New API (search.patentsview.org) requires API key registration
- Register at: https://patentsview-support.atlassian.net/servicedesk/customer/portals

Alternative patent data sources:
- USPTO PatFT/AppFT (public search, no API)
- Google Patents (public, no API)
- EPO Open Patent Services (requires registration)
- Lens.org (requires registration)
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
import aiohttp
from loguru import logger

from .base_client import BaseAPIClient, APIResponse


@dataclass
class Patent:
    """Patent data structure."""
    patent_number: str
    title: str
    abstract: Optional[str] = None
    grant_date: Optional[datetime] = None
    application_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    assignees: List[str] = field(default_factory=list)
    inventors: List[str] = field(default_factory=list)
    claims_count: int = 0
    patent_type: str = "utility"
    cpc_codes: List[str] = field(default_factory=list)
    citations_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "patent_number": self.patent_number,
            "title": self.title,
            "abstract": self.abstract,
            "grant_date": self.grant_date.isoformat() if self.grant_date else None,
            "application_date": self.application_date.isoformat() if self.application_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "assignees": self.assignees,
            "inventors": self.inventors,
            "claims_count": self.claims_count,
            "patent_type": self.patent_type,
            "cpc_codes": self.cpc_codes,
            "citations_count": self.citations_count,
        }


class PatentsViewClient(BaseAPIClient):
    """
    Client for USPTO PatentsView API.

    The PatentsView API requires API key authentication.
    Set PATENTSVIEW_API_KEY environment variable to enable patent searches.

    To obtain an API key:
    1. Visit https://patentsview-support.atlassian.net/servicedesk/customer/portals
    2. Request API access
    3. Set the API key in your environment

    Alternative free patent data sources (no API key required):
    - USPTO PatFT/AppFT: https://patft.uspto.gov/ (manual search)
    - Google Patents: https://patents.google.com/ (manual search)
    - Lens.org: https://www.lens.org/ (registration required for API)

    Rate limit: ~45 requests/minute (with valid API key)
    """

    # New API endpoint
    NEW_API_URL = "https://search.patentsview.org/api/v1/patent/"

    # API authentication status
    API_KEY_REQUIRED = True
    REGISTRATION_URL = "https://patentsview-support.atlassian.net/servicedesk/customer/portals"
    AUTH_REQUIRED_MESSAGE = (
        "PatentsView API requires an API key. "
        f"Register at: https://patentsview-support.atlassian.net/servicedesk/customer/portals "
        "and set PATENTSVIEW_API_KEY environment variable."
    )

    # Legacy API URL (no longer functional)
    LEGACY_API_URL = "https://api.patentsview.org/patents/query"
    BASE_URL = NEW_API_URL

    # Common indication term mappings for patent search optimization
    # Maps medical terms to patent-friendly search terms
    INDICATION_SEARCH_TERMS: Dict[str, List[str]] = {
        "atopic dermatitis": ["atopic dermatitis", "eczema", "dermatitis"],
        "asthma": ["asthma", "airway inflammation", "bronchial"],
        "rheumatoid arthritis": ["rheumatoid arthritis", "arthritis", "inflammatory joint"],
        "psoriasis": ["psoriasis", "plaque psoriasis", "skin inflammation"],
        "chronic rhinosinusitis": ["rhinosinusitis", "nasal polyps", "sinusitis"],
        "eosinophilic esophagitis": ["eosinophilic esophagitis", "esophagitis"],
        "chronic spontaneous urticaria": ["urticaria", "hives"],
        "prurigo nodularis": ["prurigo nodularis", "prurigo"],
    }

    @staticmethod
    def extract_mechanism_search_terms(pharm_class_moa: Optional[List[str]]) -> List[str]:
        """
        Extract patent search terms from FDA pharmacologic class MoA.

        Args:
            pharm_class_moa: List from FDA label openfda.pharm_class_moa

        Returns:
            List of search terms for patent title/abstract
        """
        if not pharm_class_moa:
            return []

        search_terms = []
        for moa in pharm_class_moa:
            # Remove "[MoA]" suffix if present
            clean_moa = moa.replace(" [MoA]", "").replace("[MoA]", "").strip()

            # Add the full term
            search_terms.append(clean_moa)

            # Extract key components for additional search terms
            # e.g., "Interleukin 4 Receptor alpha Antagonists" ->
            # ["IL-4R antagonist", "interleukin-4 receptor", "IL-4 receptor"]
            lower_moa = clean_moa.lower()

            # Handle interleukin patterns
            import re
            il_match = re.search(r"interleukin[- ]?(\d+)", lower_moa, re.IGNORECASE)
            if il_match:
                il_num = il_match.group(1)
                search_terms.append(f"IL-{il_num}")
                search_terms.append(f"interleukin-{il_num}")
                search_terms.append(f"IL-{il_num}R")  # receptor variant

            # Handle common mechanism keywords
            if "antagonist" in lower_moa:
                base = clean_moa.replace("Antagonists", "").replace("antagonist", "").strip()
                search_terms.append(f"{base} antagonist")
                search_terms.append(f"{base} inhibitor")
                search_terms.append(f"anti-{base} antibody")
            elif "inhibitor" in lower_moa:
                base = clean_moa.replace("Inhibitors", "").replace("inhibitor", "").strip()
                search_terms.append(f"{base} inhibitor")
                search_terms.append(f"{base} antagonist")
            elif "agonist" in lower_moa:
                base = clean_moa.replace("Agonists", "").replace("agonist", "").strip()
                search_terms.append(f"{base} agonist")
                search_terms.append(f"{base} receptor agonist")

        # Deduplicate while preserving order
        seen = set()
        unique_terms = []
        for term in search_terms:
            if term.lower() not in seen:
                seen.add(term.lower())
                unique_terms.append(term)

        return unique_terms

    @staticmethod
    def extract_indication_search_terms(indications_text: Optional[str]) -> List[str]:
        """
        Extract patent search terms from FDA indications text.

        Args:
            indications_text: Text from FDA label indications_and_usage

        Returns:
            List of indication search terms
        """
        if not indications_text:
            return []

        search_terms = []
        text_lower = indications_text.lower()

        # Check for known indications
        known_indications = [
            "atopic dermatitis", "asthma", "rheumatoid arthritis", "psoriasis",
            "chronic rhinosinusitis", "nasal polyps", "eosinophilic esophagitis",
            "chronic spontaneous urticaria", "prurigo nodularis", "ulcerative colitis",
            "crohn", "lupus", "multiple sclerosis", "cancer", "melanoma", "lymphoma",
            "leukemia", "breast cancer", "lung cancer", "diabetes", "obesity",
        ]

        for indication in known_indications:
            if indication in text_lower:
                search_terms.append(indication)

        return search_terms

    @staticmethod
    def extract_company_search_term(manufacturer_name: Optional[str]) -> Optional[str]:
        """
        Extract primary company name for patent search.

        Args:
            manufacturer_name: Manufacturer name from FDA label

        Returns:
            Simplified company name for patent search
        """
        if not manufacturer_name:
            return None

        # Common mappings for parent companies
        company_mappings = {
            "sanofi": "Sanofi",
            "regeneron": "Regeneron",
            "pfizer": "Pfizer",
            "merck": "Merck",
            "abbvie": "AbbVie",
            "abbott": "Abbott",
            "novartis": "Novartis",
            "roche": "Roche",
            "genentech": "Genentech",
            "johnson": "Johnson",
            "janssen": "Janssen",
            "bristol": "Bristol-Myers",
            "lilly": "Lilly",
            "novo nordisk": "Novo Nordisk",
            "astrazeneca": "AstraZeneca",
            "glaxo": "GlaxoSmithKline",
            "gsk": "GlaxoSmithKline",
            "amgen": "Amgen",
            "biogen": "Biogen",
            "gilead": "Gilead",
        }

        name_lower = manufacturer_name.lower()
        for key, value in company_mappings.items():
            if key in name_lower:
                return value

        # Return first word as fallback
        return manufacturer_name.split()[0] if manufacturer_name else None

    def __init__(self, api_key: Optional[str] = None, cache_ttl: int = 86400):
        """
        Initialize PatentsView client.

        Args:
            api_key: PatentsView API key. If not provided, will check
                     PATENTSVIEW_API_KEY environment variable.
            cache_ttl: Cache time-to-live in seconds (default 24 hours)
        """
        from .base_client import APIClientConfig

        self.api_key = api_key or os.environ.get("PATENTSVIEW_API_KEY")

        config = APIClientConfig(
            base_url=self.NEW_API_URL,
            requests_per_second=0.75,  # ~45 req/min
            cache_ttl=cache_ttl,
        )
        super().__init__(config)

    def has_api_key(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    async def health_check(self) -> bool:
        """Check if PatentsView API is accessible."""
        if not self.has_api_key():
            logger.warning(self.AUTH_REQUIRED_MESSAGE)
            return False
        try:
            # Try a minimal search to verify API key works
            result = await self.search_patents(query="pharmaceutical", per_page=1)
            return result.success
        except Exception as e:
            logger.error(f"PatentsView health check failed: {e}")
            return False

    async def search_patents(
        self,
        query: str,
        assignee: Optional[str] = None,
        cpc_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        per_page: int = 25,
        page: int = 1,
    ) -> APIResponse:
        """
        Search patents by various criteria.

        Args:
            query: Text query for title/abstract search
            assignee: Filter by assignee organization
            cpc_code: Filter by CPC classification code
            start_date: Filter patents granted after this date (YYYY-MM-DD)
            end_date: Filter patents granted before this date (YYYY-MM-DD)
            per_page: Results per page
            page: Page number

        Returns:
            APIResponse with patent list
        """
        # Build query criteria
        criteria = []

        if query:
            criteria.append({
                "_or": [
                    {"_text_any": {"patent_title": query}},
                    {"_text_any": {"patent_abstract": query}},
                ]
            })

        if assignee:
            # Use nested field name and _text_phrase for partial matching
            criteria.append({"_text_phrase": {"assignees.assignee_organization": assignee}})

        if cpc_code:
            # Use nested field name for CPC codes
            criteria.append({"_begins": {"cpc_current.cpc_subgroup_id": cpc_code}})

        if start_date:
            criteria.append({"_gte": {"patent_date": start_date}})

        if end_date:
            criteria.append({"_lte": {"patent_date": end_date}})

        # Check if API key is configured
        if not self.has_api_key():
            logger.warning(self.AUTH_REQUIRED_MESSAGE)
            return APIResponse(
                success=False,
                error=self.AUTH_REQUIRED_MESSAGE,
                source="patentsview",
                data={
                    "patents": [],
                    "total_count": 0,
                    "api_status": "api_key_required",
                    "registration_url": self.REGISTRATION_URL,
                },
            )

        # Default to recent patents if no criteria
        if not criteria:
            criteria.append({"_gte": {"patent_date": "2020-01-01"}})

        query_obj = {"_and": criteria} if len(criteria) > 1 else criteria[0]

        payload = {
            "q": query_obj,
            "f": [
                "patent_number",
                "patent_title",
                "patent_abstract",
                "patent_date",
                "patent_type",
                "assignee_organization",
                "inventor_first_name",
                "inventor_last_name",
                "cpc_subgroup_id",
            ],
            "o": {
                "page": page,
                "per_page": per_page,
            },
            "s": [{"patent_date": "desc"}],
        }

        # Build headers with API key authentication
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.NEW_API_URL,
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        patents = self._parse_patents(data.get("patents", []))
                        return APIResponse(
                            success=True,
                            data={
                                "patents": [p.to_dict() for p in patents],
                                "total_count": data.get("total_patent_count", 0),
                                "page": page,
                                "per_page": per_page,
                            },
                            source="patentsview",
                        )
                    elif response.status == 403:
                        error_text = await response.text()
                        logger.error(f"PatentsView API authentication failed: {error_text}")
                        return APIResponse(
                            success=False,
                            error="Invalid API key or authentication failed",
                            source="patentsview",
                            data={"api_status": "auth_failed"},
                        )
                    else:
                        error_text = await response.text()
                        logger.error(f"PatentsView API error: {error_text}")
                        return APIResponse(
                            success=False,
                            error=f"API error: {response.status}",
                            source="patentsview",
                        )
        except Exception as e:
            logger.error(f"PatentsView request failed: {e}")
            return APIResponse(success=False, error=str(e), source="patentsview")

    async def get_patent(self, patent_number: str) -> APIResponse:
        """
        Get detailed information for a specific patent.

        Args:
            patent_number: USPTO patent number

        Returns:
            APIResponse with patent details
        """
        if not self.has_api_key():
            logger.warning(self.AUTH_REQUIRED_MESSAGE)
            return APIResponse(
                success=False,
                error=self.AUTH_REQUIRED_MESSAGE,
                source="patentsview",
                data={
                    "api_status": "api_key_required",
                    "registration_url": self.REGISTRATION_URL,
                },
            )

        payload = {
            "q": {"patent_number": patent_number},
            "f": [
                "patent_number",
                "patent_title",
                "patent_abstract",
                "patent_date",
                "patent_type",
                "patent_num_claims",
                "assignee_organization",
                "assignee_type",
                "inventor_first_name",
                "inventor_last_name",
                "inventor_city",
                "inventor_country",
                "cpc_subgroup_id",
                "cpc_subgroup_title",
                "cited_patent_number",
                "citedby_patent_number",
            ],
        }

        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.NEW_API_URL,
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        patents = data.get("patents", [])
                        if patents:
                            patent = self._parse_patent_detail(patents[0])
                            return APIResponse(
                                success=True,
                                data=patent.to_dict(),
                                source="patentsview",
                            )
                        return APIResponse(
                            success=False,
                            error="Patent not found",
                            source="patentsview",
                        )
                    elif response.status == 403:
                        return APIResponse(
                            success=False,
                            error="Invalid API key or authentication failed",
                            source="patentsview",
                            data={"api_status": "auth_failed"},
                        )
                    else:
                        return APIResponse(
                            success=False,
                            error=f"API error: {response.status}",
                            source="patentsview",
                        )
        except Exception as e:
            logger.error(f"PatentsView request failed: {e}")
            return APIResponse(success=False, error=str(e), source="patentsview")

    async def search_by_drug(
        self,
        drug_name: str,
        company: Optional[str] = None,
        brand_name: Optional[str] = None,
        mechanisms: Optional[List[str]] = None,
        indications: Optional[List[str]] = None,
        fda_label_data: Optional[Dict[str, Any]] = None,
    ) -> APIResponse:
        """
        Search for patents related to a drug using multiple strategies.

        Patents rarely contain drug names directly - they use mechanism descriptions
        like "IL-4R antagonist" instead of "dupilumab". This method searches using:
        1. Drug generic name and brand name
        2. Mechanism of action terms (e.g., "IL-4R antagonist", "PD-1 inhibitor")
        3. Therapeutic indications (e.g., "atopic dermatitis")
        4. Company/assignee name

        Best results when fda_label_data is provided - will extract:
        - Mechanism terms from openfda.pharm_class_moa
        - Indications from indications_and_usage
        - Company from openfda.manufacturer_name

        Args:
            drug_name: Generic name of the drug (e.g., "dupilumab")
            company: Company name (assignee) - e.g., "Regeneron"
            brand_name: Brand name - e.g., "Dupixent"
            mechanisms: List of mechanism terms - e.g., ["IL-4R antagonist"]
            indications: List of therapeutic indications - e.g., ["atopic dermatitis"]
            fda_label_data: FDA label data dict with openfda fields (optional but recommended)

        Returns:
            APIResponse with related patents
        """
        if not self.has_api_key():
            logger.warning(self.AUTH_REQUIRED_MESSAGE)
            return APIResponse(
                success=False,
                error=self.AUTH_REQUIRED_MESSAGE,
                source="patentsview",
                data={
                    "patents": [],
                    "total_count": 0,
                    "api_status": "api_key_required",
                },
            )

        # Extract search terms from FDA label data if provided
        if fda_label_data:
            openfda = fda_label_data.get("openfda", {})

            # Extract brand name
            if not brand_name and openfda.get("brand_name"):
                brand_name = openfda["brand_name"][0] if isinstance(openfda["brand_name"], list) else openfda["brand_name"]

            # Extract mechanism terms from pharm_class_moa
            if not mechanisms:
                mechanisms = self.extract_mechanism_search_terms(openfda.get("pharm_class_moa"))
                logger.info(f"Extracted mechanism terms from FDA label: {mechanisms}")

            # Extract indications
            if not indications:
                indications_text = fda_label_data.get("indications_and_usage", [""])[0] if fda_label_data.get("indications_and_usage") else ""
                indications = self.extract_indication_search_terms(indications_text)
                logger.info(f"Extracted indications from FDA label: {indications}")

            # Extract company
            if not company:
                manufacturer = openfda.get("manufacturer_name", [""])[0] if openfda.get("manufacturer_name") else ""
                company = self.extract_company_search_term(manufacturer)
                logger.info(f"Extracted company from FDA label: {company}")

        # Build search terms for title/abstract
        search_terms = [drug_name]
        if brand_name:
            search_terms.append(brand_name)
        if mechanisms:
            search_terms.extend(mechanisms)

        # Build the query
        criteria = []

        # Text search in title OR abstract for any of our terms
        text_conditions = []
        for term in search_terms:
            text_conditions.append({"_text_any": {"patent_title": term}})
            text_conditions.append({"_text_any": {"patent_abstract": term}})

        # Add indication searches (use phrase matching for multi-word terms)
        if indications:
            for indication in indications:
                text_conditions.append({"_text_phrase": {"patent_title": indication}})
                text_conditions.append({"_text_phrase": {"patent_abstract": indication}})

        criteria.append({"_or": text_conditions})

        # Add company filter if provided - this significantly improves precision
        if company:
            criteria.append({"_text_phrase": {"assignees.assignee_organization": company}})

        # Note: CPC code filtering removed - it was too restrictive and
        # mechanism + company filtering already provides good precision.
        # The company filter is the key to getting relevant results.

        query_obj = {"_and": criteria}

        payload = {
            "q": query_obj,
            "f": [
                "patent_id",
                "patent_title",
                "patent_abstract",
                "patent_date",
                "patent_type",
                "assignees.assignee_organization",
                "inventors.inventor_first_name",
                "inventors.inventor_last_name",
                "cpc_current.cpc_subgroup_id",
            ],
            "o": {
                "page": 1,
                "per_page": 50,
            },
            "s": [{"patent_date": "desc"}],
        }

        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.NEW_API_URL,
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        patents = self._parse_patents(data.get("patents", []))
                        return APIResponse(
                            success=True,
                            data={
                                "patents": [p.to_dict() for p in patents],
                                "total_count": data.get("total_hits", 0),
                                "search_terms": search_terms,
                                "mechanisms_used": mechanisms,
                                "indications_used": indications,
                                "company_filter": company,
                            },
                            source="patentsview",
                        )
                    else:
                        error_text = await response.text()
                        logger.error(f"PatentsView drug search error: {error_text}")
                        return APIResponse(
                            success=False,
                            error=f"API error: {response.status}",
                            source="patentsview",
                        )
        except Exception as e:
            logger.error(f"PatentsView drug search failed: {e}")
            return APIResponse(success=False, error=str(e), source="patentsview")

    async def search_by_drug_with_fda_lookup(
        self,
        drug_name: str,
        additional_companies: Optional[List[str]] = None,
    ) -> APIResponse:
        """
        Search for patents with automatic FDA label lookup for mechanism/indication extraction.

        This is the recommended method for patent searches - it automatically:
        1. Fetches FDA label data for the drug
        2. Extracts mechanism of action terms (from pharm_class_moa)
        3. Extracts indications (from indications_and_usage)
        4. Extracts manufacturer/company info
        5. Performs an intelligent patent search using all extracted terms

        Args:
            drug_name: Generic name of the drug (e.g., "dupilumab")
            additional_companies: Extra company names to search (e.g., ["Regeneron"])
                                  Useful when manufacturer differs from patent assignee

        Returns:
            APIResponse with related patents and metadata about search terms used
        """
        if not self.has_api_key():
            logger.warning(self.AUTH_REQUIRED_MESSAGE)
            return APIResponse(
                success=False,
                error=self.AUTH_REQUIRED_MESSAGE,
                source="patentsview",
                data={"api_status": "api_key_required"},
            )

        # Fetch FDA label data
        fda_label_data = None
        try:
            async with aiohttp.ClientSession() as session:
                fda_url = f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:{drug_name}&limit=1"
                async with session.get(fda_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            fda_label_data = data["results"][0]
                            logger.info(f"Fetched FDA label data for {drug_name}")
        except Exception as e:
            logger.warning(f"Failed to fetch FDA label for {drug_name}: {e}")

        # Search with FDA data
        result = await self.search_by_drug(
            drug_name=drug_name,
            fda_label_data=fda_label_data,
        )

        # If we have additional companies and got few results, try searching with those
        if additional_companies and result.success:
            current_count = result.data.get("total_count", 0)
            if current_count < 10:
                for company in additional_companies:
                    additional_result = await self.search_by_drug(
                        drug_name=drug_name,
                        company=company,
                        fda_label_data=fda_label_data,
                    )
                    if additional_result.success:
                        # Merge results
                        existing_ids = {p["patent_number"] for p in result.data.get("patents", [])}
                        for patent in additional_result.data.get("patents", []):
                            if patent["patent_number"] not in existing_ids:
                                result.data["patents"].append(patent)
                                existing_ids.add(patent["patent_number"])
                        result.data["total_count"] = len(result.data["patents"])
                        result.data["additional_company_searched"] = company

        return result

    def _parse_patents(self, patents_data: List[Dict]) -> List[Patent]:
        """Parse patent list from API response."""
        patents = []
        for p in patents_data:
            try:
                # Extract assignees
                assignees = []
                if p.get("assignees"):
                    for a in p["assignees"]:
                        if a.get("assignee_organization"):
                            assignees.append(a["assignee_organization"])

                # Extract inventors
                inventors = []
                if p.get("inventors"):
                    for i in p["inventors"]:
                        name = f"{i.get('inventor_first_name', '')} {i.get('inventor_last_name', '')}".strip()
                        if name:
                            inventors.append(name)

                # Extract CPC codes
                cpc_codes = []
                if p.get("cpcs"):
                    for c in p["cpcs"]:
                        if c.get("cpc_subgroup_id"):
                            cpc_codes.append(c["cpc_subgroup_id"])

                patent = Patent(
                    patent_number=p.get("patent_number", ""),
                    title=p.get("patent_title", ""),
                    abstract=p.get("patent_abstract"),
                    grant_date=self._parse_date(p.get("patent_date")),
                    patent_type=p.get("patent_type", "utility"),
                    assignees=assignees,
                    inventors=inventors,
                    cpc_codes=cpc_codes,
                )
                patents.append(patent)
            except Exception as e:
                logger.warning(f"Failed to parse patent: {e}")
                continue

        return patents

    def _parse_patent_detail(self, p: Dict) -> Patent:
        """Parse detailed patent from API response."""
        # Extract assignees
        assignees = []
        if p.get("assignees"):
            for a in p["assignees"]:
                if a.get("assignee_organization"):
                    assignees.append(a["assignee_organization"])

        # Extract inventors
        inventors = []
        if p.get("inventors"):
            for i in p["inventors"]:
                name = f"{i.get('inventor_first_name', '')} {i.get('inventor_last_name', '')}".strip()
                if name:
                    inventors.append(name)

        # Extract CPC codes
        cpc_codes = []
        if p.get("cpcs"):
            for c in p["cpcs"]:
                if c.get("cpc_subgroup_id"):
                    cpc_codes.append(c["cpc_subgroup_id"])

        # Count citations
        citations_count = len(p.get("cited_patents", [])) if p.get("cited_patents") else 0
        cited_by_count = len(p.get("citedby_patents", [])) if p.get("citedby_patents") else 0

        return Patent(
            patent_number=p.get("patent_number", ""),
            title=p.get("patent_title", ""),
            abstract=p.get("patent_abstract"),
            grant_date=self._parse_date(p.get("patent_date")),
            patent_type=p.get("patent_type", "utility"),
            assignees=assignees,
            inventors=inventors,
            cpc_codes=cpc_codes,
            claims_count=p.get("patent_num_claims", 0),
            citations_count=citations_count + cited_by_count,
        )

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return None
