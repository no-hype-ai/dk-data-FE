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

# Default OpenAlex concept IDs for pharmaceutical sciences
# https://docs.openalex.org/api-entities/concepts
DEFAULT_CONCEPT_FILTER = "concepts.id:C86803240|C71924100|C126322002"
# C86803240 = Pharmaceutical sciences
# C71924100 = Medicine
# C126322002 = Pharmacology

# Maximum records per page (OpenAlex caps at 200)
PAGE_SIZE = 200

# Safety limit: max records per single fetch run
MAX_RECORDS = 10_000


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
            days_back: Number of days to look back (default: 7).
            concept_filter: OpenAlex concept filter string (default: pharma concepts).
            max_records: Maximum records to fetch (default: 10000).

        Returns:
            Dictionary with:
                - status: 'success' or 'failed'
                - records: list of work records
                - record_count: number of records fetched
                - hash: MD5 hash of the result set
                - error: error message (if failed)
        """
        days_back = kwargs.get("days_back", 7)
        concept_filter = kwargs.get("concept_filter", DEFAULT_CONCEPT_FILTER)
        max_records = kwargs.get("max_records", MAX_RECORDS)
        resume = kwargs.get("resume", True)

        manifest = self.load_manifest()
        resume_cursor: Optional[str] = manifest.get("last_cursor") if resume else None

        try:
            logger.info(
                f"Fetching OpenAlex publications (days_back={days_back}, "
                f"concept_filter={concept_filter})"
            )

            from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

            # Build filter string
            filter_str = f"from_publication_date:{from_date},{concept_filter}"

            all_records: List[Dict[str, Any]] = []
            cursor = resume_cursor or "*"  # resume from saved cursor or start fresh

            while cursor and len(all_records) < max_records:
                params = {
                    "filter": filter_str,
                    "per_page": PAGE_SIZE,
                    "cursor": cursor,
                    "select": (
                        "id,doi,title,publication_date,cited_by_count,"
                        "concepts,authorships,primary_location,open_access,"
                        "abstract_inverted_index"
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

                # Persist cursor so an interrupted run can resume
                self.save_manifest(last_cursor=cursor, last_run_status="in_progress")

                logger.debug(
                    f"Fetched page: {len(results)} works, total so far: {len(all_records)}"
                )
                time.sleep(0.11)  # ~9 req/s to stay under rate limits

            # Compute hash of the result set
            content_hash = hashlib.md5(
                str(sorted(r["work_id"] for r in all_records)).encode()
            ).hexdigest()

            self.save_manifest(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_run_status="completed",
                total_records_fetched=len(all_records),
                last_content_hash=content_hash,
                last_cursor=None,  # Reset — run completed cleanly
            )

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
            self.save_manifest(last_run_status="interrupted")
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
