"""
NIH Reporter API Client.

Provides access to NIH RePORTER (Research Portfolio Online Reporting Tools)
for grant and project information:
- Grant/project search
- Principal investigator lookup
- Funded research projects
- Publications linked to grants

API Documentation: https://api.reporter.nih.gov/
Rate Limit: 1 request per second (no authentication required)
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager


@dataclass
class PrincipalInvestigator:
    """Principal Investigator information."""

    profile_id: Optional[int] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    title: Optional[str] = None

    # Organization
    org_name: Optional[str] = None
    org_city: Optional[str] = None
    org_state: Optional[str] = None
    org_country: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "first_name": self.first_name,
            "middle_name": self.middle_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "email": self.email,
            "title": self.title,
            "org_name": self.org_name,
            "org_city": self.org_city,
            "org_state": self.org_state,
            "org_country": self.org_country,
        }


@dataclass
class NIHProject:
    """NIH funded project/grant."""

    # Identifiers
    appl_id: int
    project_number: str
    project_serial_num: Optional[str] = None
    core_project_num: Optional[str] = None

    # Basic info
    project_title: Optional[str] = None
    abstract_text: Optional[str] = None
    phr_text: Optional[str] = None  # Public Health Relevance

    # Funding
    fiscal_year: Optional[int] = None
    award_amount: Optional[float] = None
    total_cost: Optional[float] = None
    direct_cost: Optional[float] = None
    indirect_cost: Optional[float] = None

    # Dates
    project_start_date: Optional[date] = None
    project_end_date: Optional[date] = None
    budget_start_date: Optional[date] = None
    budget_end_date: Optional[date] = None

    # Organization
    org_name: Optional[str] = None
    org_city: Optional[str] = None
    org_state: Optional[str] = None
    org_country: Optional[str] = None

    # Funding source
    agency_ic_fundings: List[Dict[str, Any]] = field(default_factory=list)
    funding_mechanism: Optional[str] = None
    activity_code: Optional[str] = None

    # Principal investigators
    principal_investigators: List[PrincipalInvestigator] = field(default_factory=list)

    # Classification
    terms: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "appl_id": self.appl_id,
            "project_number": self.project_number,
            "project_serial_num": self.project_serial_num,
            "core_project_num": self.core_project_num,
            "project_title": self.project_title,
            "abstract_text": self.abstract_text,
            "phr_text": self.phr_text,
            "fiscal_year": self.fiscal_year,
            "award_amount": self.award_amount,
            "total_cost": self.total_cost,
            "direct_cost": self.direct_cost,
            "indirect_cost": self.indirect_cost,
            "project_start_date": self.project_start_date.isoformat() if self.project_start_date else None,
            "project_end_date": self.project_end_date.isoformat() if self.project_end_date else None,
            "budget_start_date": self.budget_start_date.isoformat() if self.budget_start_date else None,
            "budget_end_date": self.budget_end_date.isoformat() if self.budget_end_date else None,
            "org_name": self.org_name,
            "org_city": self.org_city,
            "org_state": self.org_state,
            "org_country": self.org_country,
            "agency_ic_fundings": self.agency_ic_fundings,
            "funding_mechanism": self.funding_mechanism,
            "activity_code": self.activity_code,
            "principal_investigators": [pi.to_dict() for pi in self.principal_investigators],
            "terms": self.terms,
        }


@dataclass
class NIHPublication:
    """Publication linked to an NIH project."""

    pmid: str
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    publication_date: Optional[date] = None
    citation_count: Optional[int] = None
    relative_citation_ratio: Optional[float] = None

    # Link to project
    core_project_num: Optional[str] = None
    appl_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pmid": self.pmid,
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "citation_count": self.citation_count,
            "relative_citation_ratio": self.relative_citation_ratio,
            "core_project_num": self.core_project_num,
            "appl_id": self.appl_id,
        }


class NIHReporterClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for NIH RePORTER API.

    Provides access to NIH funded research projects and grants.
    No authentication required.

    Usage:
        client = NIHReporterClient()
        grants = await client.search_grants("cancer immunotherapy", fiscal_year=2024)
        project = await client.get_project("R01CA123456")
        pubs = await client.get_publications_for_project("R01CA123456")
    """

    # API version
    API_VERSION = "v2"

    # Endpoints
    ENDPOINT_PROJECTS = "/projects/search"
    ENDPOINT_PUBLICATIONS = "/publications/search"

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url=f"https://api.reporter.nih.gov/{self.API_VERSION}",
            timeout=60.0,  # NIH API can be slow
            max_retries=3,
            requests_per_second=1.0,  # Strict rate limit
            cache_ttl=604800,  # 7 days - grant data updates weekly
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        super().__init__(config, cache_manager)

    async def health_check(self) -> bool:
        """Check if NIH Reporter API is accessible."""
        try:
            result = await self._post(
                self.ENDPOINT_PROJECTS,
                json_data={
                    "criteria": {"project_nums": ["R01CA123456"]},
                    "limit": 1,
                }
            )
            return "results" in result or "meta" in result
        except Exception as e:
            logger.error(f"NIH Reporter health check failed: {e}")
            return False

    async def search_grants(
        self,
        query: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        fiscal_years: Optional[List[int]] = None,
        activity_codes: Optional[List[str]] = None,
        agencies: Optional[List[str]] = None,
        org_names: Optional[List[str]] = None,
        pi_names: Optional[List[str]] = None,
        include_active_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[NIHProject]:
        """
        Search for NIH grants/projects.

        Args:
            query: Free-text search (searches title, abstract, terms)
            fiscal_year: Single fiscal year to search
            fiscal_years: List of fiscal years to search
            activity_codes: Activity codes (R01, R21, U01, etc.)
            agencies: Funding agencies (NCI, NIAID, etc.)
            org_names: Organization/institution names
            pi_names: Principal investigator names
            include_active_only: Only include active projects
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of NIH projects
        """
        criteria = {}

        if query:
            criteria["advanced_text_search"] = {
                "operator": "and",
                "search_field": "all",
                "search_text": query
            }

        if fiscal_year:
            criteria["fiscal_years"] = [fiscal_year]
        elif fiscal_years:
            criteria["fiscal_years"] = fiscal_years

        if activity_codes:
            criteria["activity_codes"] = activity_codes

        if agencies:
            criteria["agencies"] = agencies

        if org_names:
            criteria["org_names"] = org_names

        if pi_names:
            criteria["pi_names"] = [{"any_name": name} for name in pi_names]

        if include_active_only:
            criteria["include_active_projects"] = True
            criteria["exclude_subprojects"] = True

        try:
            result = await self._post(
                self.ENDPOINT_PROJECTS,
                json_data={
                    "criteria": criteria,
                    "limit": min(limit, 500),
                    "offset": offset,
                }
            )

            projects = []
            for item in result.get("results", []):
                project = self._parse_project(item)
                if project:
                    projects.append(project)

            return projects
        except Exception as e:
            logger.error(f"Error searching NIH grants: {e}")
            return []

    async def get_project(self, project_number: str) -> Optional[NIHProject]:
        """
        Get a specific NIH project by project number.

        Args:
            project_number: NIH project number (e.g., "R01CA123456")

        Returns:
            NIHProject or None if not found
        """
        try:
            result = await self._post(
                self.ENDPOINT_PROJECTS,
                json_data={
                    "criteria": {"project_nums": [project_number]},
                    "limit": 10,
                }
            )

            results = result.get("results", [])
            if results:
                # Return the most recent fiscal year
                return self._parse_project(results[0])

            return None
        except Exception as e:
            logger.error(f"Error getting NIH project {project_number}: {e}")
            return None

    async def get_pi_projects(
        self,
        pi_name: str,
        fiscal_years: Optional[List[int]] = None,
        include_active_only: bool = False,
        limit: int = 100
    ) -> List[NIHProject]:
        """
        Get all projects for a principal investigator.

        Args:
            pi_name: PI name (first and/or last name)
            fiscal_years: Filter by fiscal years
            include_active_only: Only include active projects
            limit: Maximum results

        Returns:
            List of NIH projects
        """
        criteria = {
            "pi_names": [{"any_name": pi_name}]
        }

        if fiscal_years:
            criteria["fiscal_years"] = fiscal_years

        if include_active_only:
            criteria["include_active_projects"] = True

        try:
            result = await self._post(
                self.ENDPOINT_PROJECTS,
                json_data={
                    "criteria": criteria,
                    "limit": min(limit, 500),
                }
            )

            projects = []
            for item in result.get("results", []):
                project = self._parse_project(item)
                if project:
                    projects.append(project)

            return projects
        except Exception as e:
            logger.error(f"Error getting projects for PI {pi_name}: {e}")
            return []

    async def get_publications_for_project(
        self,
        project_number: str,
        limit: int = 100
    ) -> List[NIHPublication]:
        """
        Get publications linked to a specific NIH project.

        Args:
            project_number: NIH project number (e.g., "R01CA123456")
            limit: Maximum results

        Returns:
            List of publications
        """
        try:
            result = await self._post(
                self.ENDPOINT_PUBLICATIONS,
                json_data={
                    "criteria": {"core_project_nums": [project_number]},
                    "limit": min(limit, 500),
                }
            )

            publications = []
            for item in result.get("results", []):
                pub = self._parse_publication(item)
                if pub:
                    publications.append(pub)

            return publications
        except Exception as e:
            logger.error(f"Error getting publications for project {project_number}: {e}")
            return []

    def _parse_project(self, data: Dict[str, Any]) -> Optional[NIHProject]:
        """Parse NIH project data into NIHProject object."""
        appl_id = data.get("appl_id")
        project_num = data.get("project_num", "")

        if not appl_id or not project_num:
            return None

        # Parse principal investigators
        pis = []
        for pi_data in data.get("principal_investigators", []):
            pi = PrincipalInvestigator(
                profile_id=pi_data.get("profile_id"),
                first_name=pi_data.get("first_name"),
                middle_name=pi_data.get("middle_name"),
                last_name=pi_data.get("last_name"),
                full_name=pi_data.get("full_name"),
                email=pi_data.get("email"),
                title=pi_data.get("title"),
            )
            pis.append(pi)

        # Parse organization info
        org = data.get("organization", {})

        return NIHProject(
            appl_id=appl_id,
            project_number=project_num,
            project_serial_num=data.get("project_serial_num"),
            core_project_num=data.get("core_project_num"),
            project_title=data.get("project_title"),
            abstract_text=data.get("abstract_text"),
            phr_text=data.get("phr_text"),
            fiscal_year=data.get("fiscal_year"),
            award_amount=data.get("award_amount"),
            total_cost=data.get("total_cost"),
            direct_cost=data.get("direct_cost_amt"),
            indirect_cost=data.get("indirect_cost_amt"),
            project_start_date=self._parse_date(data.get("project_start_date")),
            project_end_date=self._parse_date(data.get("project_end_date")),
            budget_start_date=self._parse_date(data.get("budget_start")),
            budget_end_date=self._parse_date(data.get("budget_end")),
            org_name=org.get("org_name"),
            org_city=org.get("org_city"),
            org_state=org.get("org_state"),
            org_country=org.get("org_country"),
            agency_ic_fundings=data.get("agency_ic_fundings", []),
            funding_mechanism=data.get("funding_mechanism"),
            activity_code=data.get("activity_code"),
            principal_investigators=pis,
            terms=data.get("terms", "").split(";") if data.get("terms") else [],
        )

    def _parse_publication(self, data: Dict[str, Any]) -> Optional[NIHPublication]:
        """Parse publication data into NIHPublication object."""
        pmid = data.get("pmid")
        if not pmid:
            return None

        authors = []
        for author in data.get("authors", []):
            name = author.get("name", "")
            if name:
                authors.append(name)

        return NIHPublication(
            pmid=str(pmid),
            title=data.get("title"),
            authors=authors,
            journal=data.get("journal"),
            publication_date=self._parse_date(data.get("pub_date")),
            citation_count=data.get("citation_count"),
            relative_citation_ratio=data.get("relative_citation_ratio"),
            core_project_num=data.get("coreproject"),
            appl_id=data.get("applid"),
        )

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse NIH Reporter date string."""
        if not date_str:
            return None

        try:
            # NIH Reporter uses ISO format or MM/DD/YYYY
            if "T" in date_str:
                return date.fromisoformat(date_str.split("T")[0])
            elif "/" in date_str:
                parts = date_str.split("/")
                if len(parts) == 3:
                    return date(int(parts[2]), int(parts[0]), int(parts[1]))
            else:
                return date.fromisoformat(date_str)
        except (ValueError, IndexError):
            return None


# Singleton instance
_nih_reporter_client: Optional[NIHReporterClient] = None


async def get_nih_reporter_client(cache_manager: Optional[CacheManager] = None) -> NIHReporterClient:
    """Get or create the NIH Reporter client instance."""
    global _nih_reporter_client

    if _nih_reporter_client is None:
        _nih_reporter_client = NIHReporterClient(cache_manager)

    return _nih_reporter_client
