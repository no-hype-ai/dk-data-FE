"""USPTO Patents Data Fetcher.

Feature: 011-datasource-integration
Task: Phase 6 / US4 — credential-gated source (USPTO PatentsView)

Fetches pharmaceutical patent data from the PatentSearch API using
API key authentication. Filters by CPC codes A61K, A61P, C07D
for pharma-relevant patents. Weekly refresh cadence.

Migration (March 20, 2026 — issue #131): search.patentsview.org → api.uspto.gov
  New endpoint: https://api.uspto.gov/api/v1/patent/applications/search
  New query format: string boolean (was JSON q/f/o); header X-API-KEY (was X-Api-Key)
  Override via env: PATENTSVIEW_API_URL

Source: https://api.uspto.gov/api/v1/patent/applications/search
Docs: https://data.uspto.gov/apis/getting-started
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CPC codes for pharmaceutical patents
PHARMA_CPC_CODES = ["A61K", "A61P", "C07D"]

# PatentSearch API page size (max 1000)
PAGE_SIZE = 100

# Safety limit: max records per fetch run
MAX_RECORDS = 10_000


class USPTOPatentsFetcher(BaseFetcher):
    """Fetcher for USPTO PatentSearch pharmaceutical patents."""

    SOURCE_NAME = "uspto_patents"
    BASE_URL = "https://api.uspto.gov"

    # USPTO ODP endpoint (migrated from search.patentsview.org on 2026-03-20)
    # Override via PATENTSVIEW_API_URL env var.
    PATENTS_API = "https://api.uspto.gov/api/v1/patent/applications/search"

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the USPTO Patents fetcher.

        Reads USPTO_API_KEY from the environment.

        Args:
            data_dir: Directory to store downloaded files.
        """
        super().__init__(data_dir)
        raw_key: Optional[str] = os.environ.get("USPTO_API_KEY")
        # Treat placeholder / unset keys as absent
        if raw_key and not raw_key.lower().startswith("changeme"):
            self.api_key: Optional[str] = raw_key
            logger.info("USPTO API key detected")
        else:
            self.api_key = None
            if raw_key:
                logger.warning(
                    "USPTO_API_KEY is a placeholder ('%s...'); "
                    "set a real key from developer.uspto.gov to enable this source",
                    raw_key[:12],
                )
            else:
                logger.warning(
                    "No USPTO_API_KEY set; USPTO Patents fetch will return source_unavailable"
                )

    def get_latest_url(self) -> str:
        """Get the USPTO ODP patent search endpoint URL."""
        return os.environ.get("PATENTSVIEW_API_URL", self.PATENTS_API)

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch pharmaceutical patents from the PatentSearch API.

        Keyword Args:
            days_back: Number of days to look back for grants (default: 7).
            cpc_codes: List of CPC codes to filter by (default: pharma codes).
            max_records: Maximum records to fetch (default: 10000).

        Returns:
            Dictionary with:
                - status: 'success' or 'failed'
                - records: list of patent record dicts
                - record_count: number of records fetched
                - hash: SHA-256 hash of the content
                - error: error message (if failed)
        """
        days_back = kwargs.get("days_back", 7)
        cpc_codes = kwargs.get("cpc_codes", PHARMA_CPC_CODES)
        max_records = kwargs.get("max_records", MAX_RECORDS)

        if not self.api_key:
            msg = (
                "USPTO_API_KEY not set or is a placeholder. "
                "Obtain a key from https://developer.uspto.gov and set USPTO_API_KEY in Doppler."
            )
            logger.warning(msg)
            result = {
                "status": "source_unavailable",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": msg,
            }
            self.log_fetch_result(result)
            return result

        try:
            logger.info(
                "Fetching USPTO patents (days_back=%d, CPC codes=%s)",
                days_back,
                cpc_codes,
            )

            all_records: List[Dict[str, Any]] = []
            offset = 0

            while len(all_records) < max_records:
                data = self._fetch_page(
                    days_back=days_back,
                    cpc_codes=cpc_codes,
                    offset=offset,
                )

                # USPTO ODP returns patents under 'patents' or 'results'
                patents = data.get("patents") or data.get("results") or []
                if not patents:
                    logger.info("No more patents from USPTO ODP")
                    break

                for patent in patents:
                    record = self._normalize_patent(patent)
                    if record:
                        all_records.append(record)

                if len(patents) < PAGE_SIZE:
                    break

                offset += PAGE_SIZE
                if len(all_records) >= max_records:
                    all_records = all_records[:max_records]
                    break

            # Compute content hash
            content_hash = hashlib.sha256(
                str(sorted(r["patent_number"] for r in all_records)).encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": all_records,
                "record_count": len(all_records),
                "hash": content_hash,
            }

            logger.info("USPTO Patents fetch complete: %d records", len(all_records))
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("Failed to fetch USPTO Patents data: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_page(
        self,
        days_back: int = 7,
        cpc_codes: Optional[List[str]] = None,
        after: Optional[str] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Fetch a single page of patents from the USPTO ODP API.

        Args:
            days_back: Look-back window in days.
            cpc_codes: CPC code prefixes to filter.
            after: Unused (kept for signature compat); use offset instead.
            offset: Page offset for pagination.

        Returns:
            Raw API response dict.
        """
        if cpc_codes is None:
            cpc_codes = PHARMA_CPC_CODES

        since_date = (
            datetime.utcnow() - timedelta(days=days_back)
        ).strftime("%Y-%m-%d")

        # USPTO ODP uses string boolean query format (RSQL/Lucene style).
        # cpcInventionFlat matches CPC codes; grantDate filters by date range.
        cpc_terms = " OR ".join(f"{code}*" for code in cpc_codes)
        q_string = f"(cpcInventionFlat:({cpc_terms})) AND grantDate:[{since_date} TO *]"

        payload = {
            "q": q_string,
            "fields": (
                "patentNumber,patentTitle,abstractText,grantDate,filingDate,"
                "patentType,inventorName,assigneeEntityName,cpcInventionFlat,"
                "numberOfClaims"
            ),
            "sort": "grantDate:desc",
            "limit": PAGE_SIZE,
            "offset": offset,
        }

        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["X-API-KEY"] = self.api_key

        logger.debug("USPTO ODP request offset=%d", offset)
        response = self.session.post(
            self.get_latest_url(),
            json=payload,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()

        return response.json()

    def _normalize_patent(self, patent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a PatentSearch patent record.

        Args:
            patent: Raw patent dict from the PatentSearch API.

        Returns:
            Normalized record dict, or None if patent_id is missing.
        """
        # ODP field: patentNumber; old field: patent_id
        patent_number = patent.get("patentNumber") or patent.get("patent_id")
        if not patent_number:
            return None
        patent_number = str(patent_number).strip()

        # Inventors: ODP returns inventorName as string or list; old API used nested objects
        inventors = None
        raw_inventors = patent.get("inventors") or patent.get("inventorName")
        if raw_inventors:
            if isinstance(raw_inventors, list) and raw_inventors and isinstance(raw_inventors[0], dict):
                inventors = [
                    {
                        "name_first": inv.get("inventor_name_first"),
                        "name_last": inv.get("inventor_name_last"),
                        "city": inv.get("inventor_city"),
                        "state": inv.get("inventor_state"),
                        "country": inv.get("inventor_country"),
                    }
                    for inv in raw_inventors
                ]
            else:
                # ODP may return flat string or list of strings
                names = raw_inventors if isinstance(raw_inventors, list) else [raw_inventors]
                inventors = [{"name_full": n} for n in names if n]

        # Assignees: ODP uses assigneeEntityName (string/list)
        assignees = None
        raw_assignees = patent.get("assignees") or patent.get("assigneeEntityName")
        if raw_assignees:
            if isinstance(raw_assignees, list) and raw_assignees and isinstance(raw_assignees[0], dict):
                assignees = [
                    {
                        "organization": asg.get("assignee_organization"),
                        "city": asg.get("assignee_city"),
                        "state": asg.get("assignee_state"),
                        "country": asg.get("assignee_country"),
                    }
                    for asg in raw_assignees
                ]
            else:
                names = raw_assignees if isinstance(raw_assignees, list) else [raw_assignees]
                assignees = [{"organization": n} for n in names if n]

        # CPC codes: ODP uses cpcInventionFlat (list of strings); old used cpc_current
        cpc_codes = None
        raw_cpcs = patent.get("cpcInventionFlat") or patent.get("cpc_current")
        if raw_cpcs and isinstance(raw_cpcs, list):
            if raw_cpcs and isinstance(raw_cpcs[0], dict):
                cpc_codes = list({c.get("cpc_subgroup_id") for c in raw_cpcs if c.get("cpc_subgroup_id")})
            else:
                cpc_codes = list({str(c) for c in raw_cpcs if c})

        # Dates: ODP uses grantDate/filingDate; old used patent_date/application.filing_date
        grant_date = patent.get("grantDate") or patent.get("patent_date")
        filing_date = patent.get("filingDate") or (patent.get("application") or {}).get("filing_date")

        # Claims: ODP uses numberOfClaims; old used patent_num_claims
        claims_count = patent.get("numberOfClaims") or patent.get("patent_num_claims")
        if claims_count is not None:
            try:
                claims_count = int(claims_count)
            except (ValueError, TypeError):
                claims_count = None

        # --- T055/T056 expansion fields ---
        # Citations
        cited_patents = patent.get("citedPatents") or patent.get("cited_patents")
        citing_patents = patent.get("citingPatents") or patent.get("citing_patents")
        npl_citations = patent.get("nplCitations") or patent.get("npl_citations")

        # Continuity
        parent_application = patent.get("parentApplication") or patent.get("parent_application")
        child_applications = patent.get("childApplications") or patent.get("child_applications")
        continuation_type = patent.get("continuationType") or patent.get("continuation_type")

        # Claims full text
        claims_full_text = patent.get("claimsText") or patent.get("claims_full_text")

        # Assignments
        assignment_events = patent.get("assignmentEvents") or patent.get("assignment_events")

        # Examiner
        examiner_first_name = patent.get("examinerFirstName") or patent.get("examiner_first_name")
        examiner_last_name = patent.get("examinerLastName") or patent.get("examiner_last_name")
        examiner_art_unit = patent.get("examinerArtUnit") or patent.get("examiner_art_unit")

        # Family
        family_id = patent.get("familyId") or patent.get("family_id")
        equivalent_foreign_patents = (
            patent.get("equivalentForeignPatents")
            or patent.get("equivalent_foreign_patents")
        )

        # Additional identifiers
        application_number = patent.get("applicationNumber") or patent.get("application_number")
        publication_number = patent.get("publicationNumber") or patent.get("publication_number")
        priority_date = patent.get("priorityDate") or patent.get("priority_date")

        # IPC codes
        ipc_codes = patent.get("ipcCodes") or patent.get("ipc_codes")
        if ipc_codes and isinstance(ipc_codes, list) and ipc_codes and isinstance(ipc_codes[0], dict):
            ipc_codes = list({c.get("ipc_code") for c in ipc_codes if c.get("ipc_code")})

        return {
            "patent_number": patent_number,
            "title": patent.get("patentTitle") or patent.get("patent_title"),
            "abstract": patent.get("abstractText") or patent.get("patent_abstract"),
            "patent_type": patent.get("patentType") or patent.get("patent_type"),
            "inventors": inventors,
            "assignees": assignees,
            "filing_date": filing_date,
            "grant_date": grant_date,
            "cpc_codes": cpc_codes,
            "claims_count": claims_count,
            # T055/T056 expansion fields
            "cited_patents": cited_patents,
            "citing_patents": citing_patents,
            "npl_citations": npl_citations,
            "parent_application": parent_application,
            "child_applications": child_applications,
            "continuation_type": continuation_type,
            "claims_full_text": claims_full_text,
            "assignment_events": assignment_events,
            "examiner_first_name": examiner_first_name,
            "examiner_last_name": examiner_last_name,
            "examiner_art_unit": examiner_art_unit,
            "family_id": family_id,
            "equivalent_foreign_patents": equivalent_foreign_patents,
            "application_number": application_number,
            "publication_number": publication_number,
            "priority_date": priority_date,
            "ipc_codes": ipc_codes,
        }
