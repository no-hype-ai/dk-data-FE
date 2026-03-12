"""
NORD (National Organization for Rare Disorders) Client.

Provides access to rare disease and patient advocacy information:
- Patient advocacy organization search
- Rare disease database
- Organization details and contact information

Note: NORD does not have a public API, so this client scrapes their
publicly available rare disease database and organization directory.

Website: https://rarediseases.org/
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager


@dataclass
class PatientAdvocacyOrg:
    """Patient advocacy organization information."""

    org_id: str
    name: str

    # Contact info
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

    # Organization details
    description: Optional[str] = None
    mission: Optional[str] = None
    services: List[str] = field(default_factory=list)

    # Associated diseases
    diseases: List[str] = field(default_factory=list)

    # Social media
    facebook: Optional[str] = None
    twitter: Optional[str] = None
    linkedin: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id,
            "name": self.name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "postal_code": self.postal_code,
            "phone": self.phone,
            "email": self.email,
            "website": self.website,
            "description": self.description,
            "mission": self.mission,
            "services": self.services,
            "diseases": self.diseases,
            "facebook": self.facebook,
            "twitter": self.twitter,
            "linkedin": self.linkedin,
        }


@dataclass
class RareDisease:
    """Rare disease information from NORD database."""

    disease_id: str
    name: str

    # Synonyms and classifications
    synonyms: List[str] = field(default_factory=list)
    subdivisions: List[str] = field(default_factory=list)

    # General information
    description: Optional[str] = None

    # Clinical information
    signs_symptoms: Optional[str] = None
    causes: Optional[str] = None
    affected_populations: Optional[str] = None

    # Diagnosis and treatment
    diagnosis: Optional[str] = None
    standard_therapies: Optional[str] = None
    investigational_therapies: Optional[str] = None

    # External references
    icd10_codes: List[str] = field(default_factory=list)
    orphanet_id: Optional[str] = None
    omim_ids: List[str] = field(default_factory=list)

    # Associated organizations
    patient_organizations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "disease_id": self.disease_id,
            "name": self.name,
            "synonyms": self.synonyms,
            "subdivisions": self.subdivisions,
            "description": self.description,
            "signs_symptoms": self.signs_symptoms,
            "causes": self.causes,
            "affected_populations": self.affected_populations,
            "diagnosis": self.diagnosis,
            "standard_therapies": self.standard_therapies,
            "investigational_therapies": self.investigational_therapies,
            "icd10_codes": self.icd10_codes,
            "orphanet_id": self.orphanet_id,
            "omim_ids": self.omim_ids,
            "patient_organizations": self.patient_organizations,
        }


class NORDClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for NORD (National Organization for Rare Disorders).

    Since NORD doesn't have a public API, this client provides
    structured access to their public rare disease database
    by using their search functionality.

    Usage:
        client = NORDClient()
        orgs = await client.search_organizations("Duchenne muscular dystrophy")
        org = await client.get_organization("parent-project-muscular-dystrophy")
        diseases = await client.get_rare_diseases()
    """

    # Base URLs
    BASE_URL = "https://rarediseases.org"
    SEARCH_URL = "/wp-admin/admin-ajax.php"

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url=self.BASE_URL,
            timeout=30.0,
            max_retries=3,
            requests_per_second=1.0,  # Respectful rate limit for web scraping
            cache_ttl=2592000,  # 30 days - rare disease info changes infrequently
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 (compatible; DataKinetic/1.0; +https://datakinetic.io)",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        super().__init__(config, cache_manager)

    async def health_check(self) -> bool:
        """Check if NORD website is accessible."""
        try:
            client = await self._get_client()
            response = await client.get("/rare-diseases/")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"NORD health check failed: {e}")
            return False

    async def search_organizations(
        self,
        disease_name: str,
        limit: int = 20
    ) -> List[PatientAdvocacyOrg]:
        """
        Search for patient advocacy organizations by disease name.

        Args:
            disease_name: Disease or condition name to search
            limit: Maximum organizations to return

        Returns:
            List of patient advocacy organizations
        """
        try:
            # NORD uses WordPress AJAX for search
            # First, search for the disease to find related organizations
            params = {
                "action": "rare_disease_search",
                "s": disease_name,
            }

            # Make search request
            result = await self._post(
                self.SEARCH_URL,
                data=params
            )

            organizations = []

            # Parse search results
            if isinstance(result, dict):
                for item in result.get("results", [])[:limit]:
                    if item.get("type") == "organization":
                        org = self._parse_organization_from_search(item)
                        if org:
                            organizations.append(org)

            # If AJAX search returned no orgs, try scraping the directory page
            if not organizations:
                organizations = await self._get_common_organizations_for_disease(disease_name)

            return organizations[:limit]
        except Exception as e:
            logger.error(f"Error searching NORD organizations for '{disease_name}': {e}")
            return []

    async def get_organization(self, org_id: str) -> Optional[PatientAdvocacyOrg]:
        """
        Get detailed information about a patient advocacy organization.

        Args:
            org_id: Organization identifier (slug or ID)

        Returns:
            PatientAdvocacyOrg or None if not found
        """
        try:
            # Construct organization URL
            org_url = f"/organizations/{org_id}/"

            client = await self._get_client()
            response = await client.get(org_url)

            if response.status_code != 200:
                return None

            # Parse organization details from HTML response
            return self._parse_organization_page(org_id, response.text)
        except Exception as e:
            logger.error(f"Error getting NORD organization {org_id}: {e}")
            return None

    async def get_rare_diseases(
        self,
        letter: Optional[str] = None,
        limit: int = 100
    ) -> List[RareDisease]:
        """
        Get list of rare diseases tracked by NORD.

        Args:
            letter: Filter by starting letter (A-Z, 0-9)
            limit: Maximum diseases to return

        Returns:
            List of rare diseases
        """
        try:
            # NORD has a disease index by letter
            if letter:
                url = f"/rare-diseases/?filter={letter.upper()}"
            else:
                url = "/rare-diseases/"

            client = await self._get_client()
            response = await client.get(url)

            if response.status_code != 200:
                return []

            # Parse disease list from HTML
            diseases = self._parse_disease_list(response.text)
            return diseases[:limit]
        except Exception as e:
            logger.error(f"Error getting NORD rare diseases: {e}")
            return []

    async def search_rare_diseases(
        self,
        query: str,
        limit: int = 20
    ) -> List[RareDisease]:
        """
        Search for rare diseases by name or keyword.

        Args:
            query: Search term
            limit: Maximum results

        Returns:
            List of matching rare diseases
        """
        try:
            params = {
                "action": "rare_disease_search",
                "s": query,
            }

            result = await self._post(
                self.SEARCH_URL,
                data=params
            )

            diseases = []

            if isinstance(result, dict):
                for item in result.get("results", [])[:limit]:
                    if item.get("type") == "disease":
                        disease = self._parse_disease_from_search(item)
                        if disease:
                            diseases.append(disease)

            return diseases
        except Exception as e:
            logger.error(f"Error searching NORD rare diseases for '{query}': {e}")
            return []

    async def get_disease(self, disease_id: str) -> Optional[RareDisease]:
        """
        Get detailed information about a specific rare disease.

        Args:
            disease_id: Disease identifier (slug or ID)

        Returns:
            RareDisease or None if not found
        """
        try:
            disease_url = f"/rare-diseases/{disease_id}/"

            client = await self._get_client()
            response = await client.get(disease_url)

            if response.status_code != 200:
                return None

            return self._parse_disease_page(disease_id, response.text)
        except Exception as e:
            logger.error(f"Error getting NORD disease {disease_id}: {e}")
            return None

    async def _get_common_organizations_for_disease(
        self,
        disease_name: str
    ) -> List[PatientAdvocacyOrg]:
        """Scrape NORD's organization directory for a disease.

        Attempts to find organizations by searching the NORD website
        directly. Returns an empty list if NORD is unreachable.
        """
        try:
            # Try the NORD organization search page directly
            client = await self._get_client()
            response = await client.get(
                f"/organizations/?s={disease_name}",
            )

            if response.status_code != 200:
                logger.warning(
                    f"NORD organization directory returned {response.status_code} "
                    f"for '{disease_name}'"
                )
                return []

            # Parse organization links from the search results page
            # Links may include tracking params: /organizations/{slug}/?_rt=...
            orgs: List[PatientAdvocacyOrg] = []
            # Match anchor tags with org links, capturing slug and link text
            pattern = r'<a[^>]*href="(?:https://rarediseases\.org)?/organizations/([^/?]+)/[^"]*"[^>]*>([^<]+)</a>'
            slugs_seen: set = set()
            for match in re.finditer(pattern, response.text):
                slug = match.group(1)
                link_text = match.group(2).strip()
                if slug and slug not in slugs_seen:
                    slugs_seen.add(slug)
                    # Use link text if available, fall back to slug conversion
                    name = link_text if link_text else slug.replace('-', ' ').title()
                    orgs.append(PatientAdvocacyOrg(
                        org_id=slug,
                        name=name,
                        website=f"https://rarediseases.org/organizations/{slug}/",
                        diseases=[disease_name],
                    ))

            # Fall back to href-only pattern if no anchor text matches found
            if not orgs:
                href_pattern = r'href="(?:https://rarediseases\.org)?/organizations/([^/?]+)/[^"]*"'
                for slug in re.findall(href_pattern, response.text):
                    if slug and slug not in slugs_seen:
                        slugs_seen.add(slug)
                        name = slug.replace('-', ' ').title()
                        orgs.append(PatientAdvocacyOrg(
                            org_id=slug,
                            name=name,
                            website=f"https://rarediseases.org/organizations/{slug}/",
                            diseases=[disease_name],
                        ))

            if not orgs:
                logger.info(
                    f"No NORD organizations found for '{disease_name}'"
                )

            return orgs

        except Exception as e:
            logger.error(f"NORD organization search failed for '{disease_name}': {e}")
            return []

    def _parse_organization_from_search(
        self,
        data: Dict[str, Any]
    ) -> Optional[PatientAdvocacyOrg]:
        """Parse organization from search result."""
        name = data.get("title", "")
        if not name:
            return None

        # Generate ID from title
        org_id = data.get("slug") or re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

        return PatientAdvocacyOrg(
            org_id=org_id,
            name=name,
            description=data.get("excerpt"),
            website=data.get("url"),
        )

    def _parse_organization_page(
        self,
        org_id: str,
        html: str
    ) -> PatientAdvocacyOrg:
        """Parse organization details from HTML page."""
        # Basic HTML parsing for organization info
        # In production, would use BeautifulSoup or similar

        name = self._extract_text_between(html, '<h1 class="entry-title">', '</h1>') or org_id
        description = self._extract_text_between(html, '<div class="entry-content">', '</div>')

        # Extract contact info using regex patterns
        phone = self._extract_pattern(html, r'(?:Phone|Tel):\s*([\d\-\(\)\s]+)')
        email = self._extract_pattern(html, r'(?:Email):\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')
        website = self._extract_pattern(html, r'(?:Website):\s*(https?://[^\s<]+)')

        return PatientAdvocacyOrg(
            org_id=org_id,
            name=name,
            description=description,
            phone=phone,
            email=email,
            website=website,
        )

    def _parse_disease_from_search(
        self,
        data: Dict[str, Any]
    ) -> Optional[RareDisease]:
        """Parse disease from search result."""
        name = data.get("title", "")
        if not name:
            return None

        disease_id = data.get("slug") or re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

        return RareDisease(
            disease_id=disease_id,
            name=name,
            description=data.get("excerpt"),
        )

    def _parse_disease_list(self, html: str) -> List[RareDisease]:
        """Parse list of diseases from embedded JSON data."""
        diseases = []

        # NORD embeds disease data as JSON in: var predictiveSearchData = {...};
        match = re.search(r'var\s+predictiveSearchData\s*=\s*(\{.+?\});', html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                for item in data.get("data", []):
                    title = item.get("title", "")
                    if not title:
                        continue
                    # Extract slug from permalink
                    permalink = item.get("permalink", "")
                    slug_match = re.search(r'/([^/]+)/$', permalink)
                    slug = slug_match.group(1) if slug_match else re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
                    diseases.append(RareDisease(
                        disease_id=slug,
                        name=title,
                        synonyms=item.get("synonyms", []),
                        subdivisions=item.get("subdivisions", []),
                    ))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse NORD predictiveSearchData JSON: {e}")

        return diseases

    def _parse_disease_page(
        self,
        disease_id: str,
        html: str
    ) -> RareDisease:
        """Parse disease details from HTML page."""
        name = self._extract_text_between(html, '<h1 class="entry-title">', '</h1>') or disease_id

        # Extract various sections
        description = self._extract_section(html, "General Discussion")
        signs_symptoms = self._extract_section(html, "Signs & Symptoms")
        causes = self._extract_section(html, "Causes")
        affected_populations = self._extract_section(html, "Affected Populations")
        diagnosis = self._extract_section(html, "Diagnosis")
        standard_therapies = self._extract_section(html, "Standard Therapies")
        investigational_therapies = self._extract_section(html, "Investigational Therapies")

        # Extract synonyms
        synonyms_text = self._extract_section(html, "Synonyms")
        synonyms = [s.strip() for s in synonyms_text.split(',') if s.strip()] if synonyms_text else []

        return RareDisease(
            disease_id=disease_id,
            name=name,
            synonyms=synonyms,
            description=description,
            signs_symptoms=signs_symptoms,
            causes=causes,
            affected_populations=affected_populations,
            diagnosis=diagnosis,
            standard_therapies=standard_therapies,
            investigational_therapies=investigational_therapies,
        )

    def _extract_text_between(
        self,
        html: str,
        start: str,
        end: str
    ) -> Optional[str]:
        """Extract text between two markers."""
        try:
            start_idx = html.find(start)
            if start_idx == -1:
                return None
            start_idx += len(start)

            end_idx = html.find(end, start_idx)
            if end_idx == -1:
                return None

            text = html[start_idx:end_idx]
            # Strip HTML tags
            text = re.sub(r'<[^>]+>', ' ', text)
            return text.strip()
        except Exception:
            return None

    def _extract_pattern(
        self,
        html: str,
        pattern: str
    ) -> Optional[str]:
        """Extract text matching a regex pattern."""
        match = re.search(pattern, html, re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _extract_section(
        self,
        html: str,
        section_name: str
    ) -> Optional[str]:
        """Extract content of a named section."""
        # Look for section headers
        pattern = rf'<h[2-4][^>]*>\s*{re.escape(section_name)}\s*</h[2-4]>'
        match = re.search(pattern, html, re.IGNORECASE)

        if not match:
            return None

        start_idx = match.end()

        # Find next section header or end
        next_header = re.search(r'<h[2-4][^>]*>', html[start_idx:])
        if next_header:
            end_idx = start_idx + next_header.start()
        else:
            end_idx = len(html)

        section_html = html[start_idx:end_idx]

        # Strip HTML tags and clean up
        text = re.sub(r'<[^>]+>', ' ', section_html)
        text = re.sub(r'\s+', ' ', text)
        return text.strip() if text.strip() else None


# Singleton instance
_nord_client: Optional[NORDClient] = None


async def get_nord_client(cache_manager: Optional[CacheManager] = None) -> NORDClient:
    """Get or create the NORD client instance."""
    global _nord_client

    if _nord_client is None:
        _nord_client = NORDClient(cache_manager)

    return _nord_client
