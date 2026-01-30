"""
ORCID API Client.

Provides access to ORCID (Open Researcher and Contributor ID) public data
for KOL (Key Opinion Leader) identification:
- Researcher profiles and biographies
- Publications and works
- Affiliations and employment history
- Research areas and keywords

API Documentation: https://info.orcid.org/documentation/
Public API Rate Limit: 24 requests/second (per IP)
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager


@dataclass
class Affiliation:
    """Researcher affiliation (employment, education, etc.)."""

    organization_name: str
    role_title: Optional[str] = None
    department: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    affiliation_type: str = "employment"  # employment, education, membership, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "organization_name": self.organization_name,
            "role_title": self.role_title,
            "department": self.department,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "city": self.city,
            "region": self.region,
            "country": self.country,
            "affiliation_type": self.affiliation_type,
        }


@dataclass
class Work:
    """Publication or other work associated with a researcher."""

    title: str
    put_code: Optional[str] = None
    work_type: Optional[str] = None  # journal-article, book, conference-paper, etc.
    publication_date: Optional[date] = None
    journal_title: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    url: Optional[str] = None
    citation_count: Optional[int] = None
    contributors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "put_code": self.put_code,
            "work_type": self.work_type,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "journal_title": self.journal_title,
            "doi": self.doi,
            "pmid": self.pmid,
            "url": self.url,
            "citation_count": self.citation_count,
            "contributors": self.contributors,
        }


@dataclass
class ResearcherProfile:
    """ORCID researcher profile."""

    orcid_id: str
    given_names: Optional[str] = None
    family_name: Optional[str] = None
    credit_name: Optional[str] = None  # Preferred name for publications
    biography: Optional[str] = None

    # Research areas
    keywords: List[str] = field(default_factory=list)
    research_areas: List[str] = field(default_factory=list)

    # External identifiers
    researcher_urls: List[Dict[str, str]] = field(default_factory=list)
    other_ids: Dict[str, str] = field(default_factory=dict)  # Scopus, ResearcherID, etc.

    # Affiliations
    current_affiliations: List[Affiliation] = field(default_factory=list)
    past_affiliations: List[Affiliation] = field(default_factory=list)

    # Metrics
    works_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "orcid_id": self.orcid_id,
            "given_names": self.given_names,
            "family_name": self.family_name,
            "credit_name": self.credit_name,
            "biography": self.biography,
            "keywords": self.keywords,
            "research_areas": self.research_areas,
            "researcher_urls": self.researcher_urls,
            "other_ids": self.other_ids,
            "current_affiliations": [a.to_dict() for a in self.current_affiliations],
            "past_affiliations": [a.to_dict() for a in self.past_affiliations],
            "works_count": self.works_count,
        }

    @property
    def full_name(self) -> str:
        """Get the full name of the researcher."""
        if self.credit_name:
            return self.credit_name
        parts = [self.given_names, self.family_name]
        return " ".join(p for p in parts if p)


@dataclass
class ResearcherSearchResult:
    """Search result for researcher lookup."""

    orcid_id: str
    given_names: Optional[str] = None
    family_name: Optional[str] = None
    credit_name: Optional[str] = None
    current_institution: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "orcid_id": self.orcid_id,
            "given_names": self.given_names,
            "family_name": self.family_name,
            "credit_name": self.credit_name,
            "current_institution": self.current_institution,
        }


class ORCIDClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for ORCID Public API.

    The public API provides read-only access to public ORCID data.
    No authentication required for public data.

    Usage:
        client = ORCIDClient()
        profile = await client.get_researcher("0000-0002-1825-0097")
        works = await client.get_works("0000-0002-1825-0097")
        results = await client.search_researchers("oncology", "MD Anderson")
    """

    # API version
    API_VERSION = "v3.0"

    # Endpoints
    ENDPOINT_SEARCH = "/search"

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url=f"https://pub.orcid.org/{self.API_VERSION}",
            timeout=30.0,
            max_retries=3,
            requests_per_second=20.0,  # Conservative limit under 24/sec
            cache_ttl=604800,  # 7 days - researcher profiles don't change frequently
            headers={
                "Accept": "application/json",
            },
        )
        super().__init__(config, cache_manager)

    async def health_check(self) -> bool:
        """Check if ORCID API is accessible."""
        try:
            # Search for a known test ORCID
            result = await self._get(
                self.ENDPOINT_SEARCH,
                params={"q": "orcid:0000-0002-1825-0097"},
                use_cache=False
            )
            return "result" in result or "num-found" in result
        except Exception as e:
            logger.error(f"ORCID health check failed: {e}")
            return False

    async def get_researcher(self, orcid_id: str) -> Optional[ResearcherProfile]:
        """
        Get a researcher's full profile by ORCID ID.

        Args:
            orcid_id: The ORCID identifier (e.g., "0000-0002-1825-0097")

        Returns:
            ResearcherProfile or None if not found
        """
        # Normalize ORCID ID (remove any URL prefix)
        orcid_id = self._normalize_orcid(orcid_id)

        try:
            result = await self._get(f"/{orcid_id}/record")
            return self._parse_researcher_profile(orcid_id, result)
        except Exception as e:
            logger.error(f"Error getting ORCID profile for {orcid_id}: {e}")
            return None

    async def search_researchers(
        self,
        query: Optional[str] = None,
        therapeutic_area: Optional[str] = None,
        affiliation: Optional[str] = None,
        given_names: Optional[str] = None,
        family_name: Optional[str] = None,
        limit: int = 20
    ) -> List[ResearcherSearchResult]:
        """
        Search for researchers by name, affiliation, or research area.

        Args:
            query: Free-text search query
            therapeutic_area: Research/therapeutic area keyword
            affiliation: Institution/organization name
            given_names: First name
            family_name: Last name
            limit: Maximum results to return

        Returns:
            List of researcher search results
        """
        # Build ORCID search query
        query_parts = []

        if query:
            query_parts.append(query)
        if therapeutic_area:
            query_parts.append(f"keyword:{therapeutic_area}")
        if affiliation:
            query_parts.append(f"affiliation-org-name:{affiliation}")
        if given_names:
            query_parts.append(f"given-names:{given_names}")
        if family_name:
            query_parts.append(f"family-name:{family_name}")

        if not query_parts:
            return []

        search_query = " AND ".join(query_parts)

        try:
            result = await self._get(
                self.ENDPOINT_SEARCH,
                params={
                    "q": search_query,
                    "rows": min(limit, 100),
                }
            )

            results = []
            for item in result.get("result", []):
                orcid_id = item.get("orcid-identifier", {}).get("path", "")
                if not orcid_id:
                    continue

                # Get basic info from expanded search result
                person = item.get("person", {})
                name = person.get("name", {})

                # Get current institution from activities
                activities = item.get("activities-summary", {})
                employments = activities.get("employments", {}).get("affiliation-group", [])
                current_institution = None
                if employments:
                    first_emp = employments[0].get("summaries", [{}])[0]
                    org = first_emp.get("employment-summary", {}).get("organization", {})
                    current_institution = org.get("name")

                search_result = ResearcherSearchResult(
                    orcid_id=orcid_id,
                    given_names=name.get("given-names", {}).get("value"),
                    family_name=name.get("family-name", {}).get("value"),
                    credit_name=name.get("credit-name", {}).get("value"),
                    current_institution=current_institution,
                )
                results.append(search_result)

            return results
        except Exception as e:
            logger.error(f"Error searching ORCID researchers: {e}")
            return []

    async def get_works(
        self,
        orcid_id: str,
        limit: int = 50
    ) -> List[Work]:
        """
        Get publications and other works for a researcher.

        Args:
            orcid_id: The ORCID identifier
            limit: Maximum works to return

        Returns:
            List of works/publications
        """
        orcid_id = self._normalize_orcid(orcid_id)

        try:
            result = await self._get(f"/{orcid_id}/works")

            works = []
            work_groups = result.get("group", [])[:limit]

            for group in work_groups:
                work_summaries = group.get("work-summary", [])
                if not work_summaries:
                    continue

                # Use the first summary (most recent/preferred version)
                summary = work_summaries[0]

                title = summary.get("title", {}).get("title", {}).get("value", "")
                if not title:
                    continue

                # Parse external IDs
                doi = None
                pmid = None
                for ext_id in group.get("external-ids", {}).get("external-id", []):
                    id_type = ext_id.get("external-id-type", "")
                    id_value = ext_id.get("external-id-value", "")
                    if id_type == "doi":
                        doi = id_value
                    elif id_type == "pmid":
                        pmid = id_value

                work = Work(
                    title=title,
                    put_code=str(summary.get("put-code", "")),
                    work_type=summary.get("type"),
                    publication_date=self._parse_orcid_date(summary.get("publication-date")),
                    journal_title=summary.get("journal-title", {}).get("value") if summary.get("journal-title") else None,
                    doi=doi,
                    pmid=pmid,
                    url=summary.get("url", {}).get("value") if summary.get("url") else None,
                )
                works.append(work)

            return works
        except Exception as e:
            logger.error(f"Error getting works for ORCID {orcid_id}: {e}")
            return []

    async def get_affiliations(self, orcid_id: str) -> List[Affiliation]:
        """
        Get all affiliations (employment, education, etc.) for a researcher.

        Args:
            orcid_id: The ORCID identifier

        Returns:
            List of affiliations
        """
        orcid_id = self._normalize_orcid(orcid_id)

        try:
            result = await self._get(f"/{orcid_id}/activities")

            affiliations = []

            # Parse employments
            employments = result.get("employments", {}).get("affiliation-group", [])
            for group in employments:
                for summary in group.get("summaries", []):
                    emp = summary.get("employment-summary", {})
                    aff = self._parse_affiliation(emp, "employment")
                    if aff:
                        affiliations.append(aff)

            # Parse educations
            educations = result.get("educations", {}).get("affiliation-group", [])
            for group in educations:
                for summary in group.get("summaries", []):
                    edu = summary.get("education-summary", {})
                    aff = self._parse_affiliation(edu, "education")
                    if aff:
                        affiliations.append(aff)

            # Parse memberships
            memberships = result.get("memberships", {}).get("affiliation-group", [])
            for group in memberships:
                for summary in group.get("summaries", []):
                    mem = summary.get("membership-summary", {})
                    aff = self._parse_affiliation(mem, "membership")
                    if aff:
                        affiliations.append(aff)

            return affiliations
        except Exception as e:
            logger.error(f"Error getting affiliations for ORCID {orcid_id}: {e}")
            return []

    def _normalize_orcid(self, orcid_id: str) -> str:
        """Normalize ORCID ID by removing URL prefix if present."""
        if "orcid.org/" in orcid_id:
            orcid_id = orcid_id.split("orcid.org/")[-1]
        return orcid_id.strip()

    def _parse_researcher_profile(
        self,
        orcid_id: str,
        data: Dict[str, Any]
    ) -> ResearcherProfile:
        """Parse ORCID record into ResearcherProfile."""
        person = data.get("person", {})
        activities = data.get("activities-summary", {})

        # Parse name
        name = person.get("name", {})
        given_names = name.get("given-names", {}).get("value")
        family_name = name.get("family-name", {}).get("value")
        credit_name = name.get("credit-name", {}).get("value")

        # Parse biography
        bio = person.get("biography", {})
        biography = bio.get("content") if bio else None

        # Parse keywords
        keywords = []
        for kw in person.get("keywords", {}).get("keyword", []):
            content = kw.get("content", "")
            if content:
                keywords.append(content)

        # Parse researcher URLs
        researcher_urls = []
        for url_item in person.get("researcher-urls", {}).get("researcher-url", []):
            url_entry = {
                "name": url_item.get("url-name", ""),
                "url": url_item.get("url", {}).get("value", ""),
            }
            if url_entry["url"]:
                researcher_urls.append(url_entry)

        # Parse external identifiers
        other_ids = {}
        for ext_id in person.get("external-identifiers", {}).get("external-identifier", []):
            id_type = ext_id.get("external-id-type", "")
            id_value = ext_id.get("external-id-value", "")
            if id_type and id_value:
                other_ids[id_type] = id_value

        # Parse affiliations
        current_affiliations = []
        past_affiliations = []

        for group in activities.get("employments", {}).get("affiliation-group", []):
            for summary in group.get("summaries", []):
                emp = summary.get("employment-summary", {})
                aff = self._parse_affiliation(emp, "employment")
                if aff:
                    if aff.end_date is None:
                        current_affiliations.append(aff)
                    else:
                        past_affiliations.append(aff)

        # Count works
        works_summary = activities.get("works", {})
        works_count = len(works_summary.get("group", []))

        return ResearcherProfile(
            orcid_id=orcid_id,
            given_names=given_names,
            family_name=family_name,
            credit_name=credit_name,
            biography=biography,
            keywords=keywords,
            research_areas=keywords,  # Keywords often represent research areas
            researcher_urls=researcher_urls,
            other_ids=other_ids,
            current_affiliations=current_affiliations,
            past_affiliations=past_affiliations,
            works_count=works_count,
        )

    def _parse_affiliation(
        self,
        data: Dict[str, Any],
        affiliation_type: str
    ) -> Optional[Affiliation]:
        """Parse affiliation data from ORCID response."""
        org = data.get("organization", {})
        org_name = org.get("name")
        if not org_name:
            return None

        address = org.get("address", {})

        return Affiliation(
            organization_name=org_name,
            role_title=data.get("role-title"),
            department=data.get("department-name"),
            start_date=self._parse_orcid_date(data.get("start-date")),
            end_date=self._parse_orcid_date(data.get("end-date")),
            city=address.get("city"),
            region=address.get("region"),
            country=address.get("country"),
            affiliation_type=affiliation_type,
        )

    def _parse_orcid_date(self, date_obj: Optional[Dict]) -> Optional[date]:
        """Parse ORCID date object into Python date."""
        if not date_obj:
            return None

        try:
            year = date_obj.get("year", {}).get("value")
            month = date_obj.get("month", {}).get("value") or "01"
            day = date_obj.get("day", {}).get("value") or "01"

            if not year:
                return None

            return date(int(year), int(month), int(day))
        except (ValueError, TypeError):
            return None


# Singleton instance
_orcid_client: Optional[ORCIDClient] = None


async def get_orcid_client(cache_manager: Optional[CacheManager] = None) -> ORCIDClient:
    """Get or create the ORCID client instance."""
    global _orcid_client

    if _orcid_client is None:
        _orcid_client = ORCIDClient(cache_manager)

    return _orcid_client
