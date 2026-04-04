"""OpenAlex CI (Competitive Intelligence) Fetcher.

Feature: 011-datasource-integration
Task: Tier 4 CI source — OpenAlex publications

Fetches pharma-relevant academic publications from the OpenAlex API
using cursor-based pagination. Authenticates via OPENALEX_API_KEY
(required since Feb 2026; the old mailto polite pool is deprecated).

Register for a free API key at: https://openalex.org/settings/api
Set via OPENALEX_API_KEY environment variable (stored in Doppler).

Source: https://api.openalex.org
Docs: https://docs.openalex.org
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Default OpenAlex subfield IDs for pharmaceutical sciences
# https://docs.openalex.org/api-entities/topics
# concepts.id filter was deprecated by OpenAlex in 2024; use primary_topic.subfield.id instead.
DEFAULT_CONCEPT_FILTER = "primary_topic.subfield.id:subfields/2736|subfields/3004"
# subfields/2736 = Pharmacology (Medicine field)
# subfields/3004 = Pharmacology (Biochemistry field)

# Maximum records per page (OpenAlex caps at 200)
PAGE_SIZE = 200

# Safety limit: max records per single fetch run — None means unlimited
MAX_RECORDS = None

# OpenAlex rate limit: 10 req/s authenticated (API key), stricter for unauthenticated.
# 0.1s gives ~10 req/s with key; 0.5s is used without key to avoid IP throttling.
REQUEST_DELAY_WITH_KEY = 0.1   # seconds between cursor pages (authenticated)
REQUEST_DELAY_NO_KEY   = 0.5   # seconds between cursor pages (unauthenticated)


class OpenAlexCIFetcher(BaseFetcher):
    """Fetcher for OpenAlex academic publications (CI scope).

    Performs daily broad ingest of pharma-relevant publications using
    the OpenAlex /works endpoint with cursor-based pagination.
    """

    SOURCE_NAME = "openalex_ci"
    BASE_URL = "https://api.openalex.org"

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the OpenAlex CI fetcher.

        Reads OPENALEX_API_KEY from the environment (required since Feb 2026).

        Args:
            data_dir: Directory to store downloaded files.
        """
        super().__init__(data_dir)

        self.api_key: Optional[str] = os.environ.get("OPENALEX_API_KEY")
        # mailto kept for User-Agent identification (best practice)
        mailto = os.environ.get("OPENALEX_MAILTO", "data-platform@datakinetic.com")
        self.session.headers.update({
            "User-Agent": f"DK-Data-Platform/1.0 (mailto:{mailto})",
            "Accept": "application/json",
        })

        if self.api_key:
            logger.info("OpenAlex API key detected; using authenticated access")
        else:
            logger.warning(
                "No OPENALEX_API_KEY set — OpenAlex requires API keys since Feb 2026. "
                "Register at https://openalex.org/settings/api"
            )

    def get_latest_url(self) -> str:
        """Get the OpenAlex /works API endpoint URL."""
        return f"{self.BASE_URL}/works"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch pharma-relevant publications from OpenAlex.

        Uses cursor-based pagination to retrieve recent publications
        filtered by pharmaceutical concepts.

        Keyword Args:
            days_back: Number of days to look back (default: None — no date filter,
                fetch all pharma publications). Pass an integer for incremental runs.
            concept_filter: OpenAlex concept filter string (default: pharma concepts).
            max_records: Maximum records to fetch (default: None — unlimited).

        Returns:
            Dictionary with:
                - status: 'success' or 'failed'
                - records: list of work records
                - record_count: number of records fetched
                - hash: MD5 hash of the result set
                - error: error message (if failed)
        """
        raw_days_back = kwargs.get("days_back", None)
        days_back = int(raw_days_back) if raw_days_back is not None else None
        concept_filter = kwargs.get("concept_filter", DEFAULT_CONCEPT_FILTER)
        raw_max = kwargs.get("max_records", MAX_RECORDS)
        max_records = int(raw_max) if raw_max is not None else None

        try:
            logger.info(
                f"Fetching OpenAlex publications (days_back={days_back}, "
                f"concept_filter={concept_filter})"
            )

            # Build filter string — date filter only when days_back is set
            if days_back is not None:
                from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
                filter_str = f"from_publication_date:{from_date},{concept_filter}"
            else:
                filter_str = concept_filter

            all_records: List[Dict[str, Any]] = []
            cursor = "*"  # initial cursor for first page

            while cursor and (max_records is None or len(all_records) < max_records):
                params = {
                    "filter": filter_str,
                    "per_page": PAGE_SIZE,
                    "cursor": cursor,
                    "select": (
                        "id,doi,title,publication_date,cited_by_count,"
                        "concepts,authorships,primary_location,open_access,"
                        "abstract_inverted_index,"
                        "ids,type,language,biblio,topics,keywords,mesh,"
                        "counts_by_year,referenced_works,related_works,"
                        "sustainable_development_goals,best_oa_location,"
                        "is_retracted,is_paratext,cited_by_percentile_year"
                    ),
                }
                if self.api_key:
                    params["api_key"] = self.api_key

                data = self.fetch_json(self.get_latest_url(), params=params)
                results = data.get("results", [])

                if not results:
                    logger.info("No more results from OpenAlex API")
                    break

                for work in results:
                    record = self._normalize_work(work)
                    all_records.append(record)

                # Advance cursor
                meta = data.get("meta", {})
                next_cursor = meta.get("next_cursor")

                if next_cursor == cursor or next_cursor is None:
                    # No more pages
                    break
                cursor = next_cursor

                logger.debug(
                    f"Fetched page: {len(results)} works, total so far: {len(all_records)}"
                )
                time.sleep(REQUEST_DELAY_WITH_KEY if self.api_key else REQUEST_DELAY_NO_KEY)

            # Compute hash of the result set
            content_hash = hashlib.md5(
                str(sorted(r["work_id"] for r in all_records)).encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": all_records,
                "record_count": len(all_records),
                "hash": content_hash,
            }

            logger.info(f"OpenAlex fetch complete: {len(all_records)} records")
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception(f"Failed to fetch OpenAlex data: {e}")
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    def _normalize_work(self, work: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize an OpenAlex work record for database storage.

        Extracts the short work ID (e.g. 'W1234567890' from the full URL),
        reconstructs the abstract from the inverted index, and maps fields
        to the raw.openalex_ci schema.

        Args:
            work: Raw work record from the OpenAlex API.

        Returns:
            Normalized record dictionary matching the raw.openalex_ci schema.
        """
        # Extract short work ID from full URL
        # e.g. "https://openalex.org/W1234567890" -> "W1234567890"
        full_id = work.get("id", "")
        work_id = full_id.split("/")[-1] if "/" in full_id else full_id

        # Reconstruct abstract from inverted index
        abstract = self._reconstruct_abstract(work.get("abstract_inverted_index"))

        # Trim concepts to relevant fields
        concepts = None
        raw_concepts = work.get("concepts")
        if raw_concepts:
            concepts = [
                {
                    "id": c.get("id"),
                    "display_name": c.get("display_name"),
                    "level": c.get("level"),
                    "score": c.get("score"),
                }
                for c in raw_concepts
            ]

        # Extract external IDs (ids object contains pmid, pmcid, mag, openalex, etc.)
        ids_obj = work.get("ids") or {}
        pmid_raw = ids_obj.get("pmid")
        pmid = pmid_raw.split("/")[-1] if pmid_raw and "/" in pmid_raw else pmid_raw
        pmcid_raw = ids_obj.get("pmcid")
        pmcid = pmcid_raw.split("/")[-1] if pmcid_raw and "/" in pmcid_raw else pmcid_raw
        mag_id = ids_obj.get("mag")

        # Bibliographic info (volume, issue, pages) from biblio object
        biblio = work.get("biblio") or {}

        # Topics (newer OpenAlex field replacing concepts in some contexts)
        topics = work.get("topics")

        # Keywords
        keywords = work.get("keywords")

        # MeSH terms
        mesh_terms = work.get("mesh")

        # Citation counts by year
        citation_counts_by_year = work.get("counts_by_year")

        # Related work lists
        referenced_works = work.get("referenced_works")
        related_works = work.get("related_works")

        # SDGs
        sustainable_development_goals = work.get("sustainable_development_goals")

        # Best OA location
        best_oa_location = work.get("best_oa_location")

        # Cited by percentile
        cited_by_percentile_obj = work.get("cited_by_percentile_year") or {}
        cited_by_percentile = cited_by_percentile_obj.get("max")  # use max percentile

        return {
            "work_id": work_id,
            "doi": work.get("doi"),
            "title": work.get("title"),
            "abstract": abstract,
            "publication_date": work.get("publication_date"),
            "cited_by_count": work.get("cited_by_count"),
            "concepts": concepts,
            "authorships": work.get("authorships"),
            "primary_location": work.get("primary_location"),
            "open_access": work.get("open_access"),
            # Extended fields
            "pmid": pmid,
            "pmcid": pmcid,
            "mag_id": mag_id,
            "work_type": work.get("type"),
            "language": work.get("language"),
            "volume": biblio.get("volume"),
            "issue": biblio.get("issue"),
            "first_page": biblio.get("first_page"),
            "last_page": biblio.get("last_page"),
            "topics": topics,
            "keywords": keywords,
            "mesh_terms": mesh_terms,
            "cited_by_percentile": cited_by_percentile,
            "citation_counts_by_year": citation_counts_by_year,
            "referenced_works": referenced_works,
            "related_works": related_works,
            "sustainable_development_goals": sustainable_development_goals,
            "best_oa_location": best_oa_location,
            "is_retracted": work.get("is_retracted"),
            "is_paratext": work.get("is_paratext"),
        }

    @staticmethod
    def _reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> Optional[str]:
        """Reconstruct abstract text from OpenAlex inverted index format.

        OpenAlex stores abstracts as an inverted index mapping words to
        their positions. This reconstructs the original text.

        Args:
            inverted_index: Mapping of word -> list of positions.

        Returns:
            Reconstructed abstract string, or None if not available.
        """
        if not inverted_index:
            return None

        try:
            # Build position -> word mapping
            positions: Dict[int, str] = {}
            for word, indices in inverted_index.items():
                for idx in indices:
                    positions[idx] = word

            if not positions:
                return None

            # Reconstruct by joining words in position order
            max_pos = max(positions.keys())
            words = [positions.get(i, "") for i in range(max_pos + 1)]
            return " ".join(w for w in words if w)

        except Exception as e:
            logger.warning(f"Failed to reconstruct abstract: {e}")
            return None
