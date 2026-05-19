"""CMS PECOS (Provider Enrollment, Chain, and Ownership System) Fetcher.

Fetches Medicare provider/supplier enrollment data from the PECOS API.
Provides NPI-to-organization linkage and enrollment status.

Feature: 016-cms-puf-datasource-integration (Phase 3)

Source: https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment

Streams records directly to DB in batches (no full-list memory accumulation).
Supports checkpoint/resume so pod restarts continue from the last committed offset.
"""

import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from ..sources.cms_pecos import load_cms_pecos_data

logger = logging.getLogger(__name__)

# Mapping from CMS API field names to normalised output field names
API_FIELD_MAP: Dict[str, str] = {
    "NPI": "npi",
    "ENRLMT_ID": "enrollment_id",
    "ORG_NAME": "organization_name",
    "STATE_CD": "state",
    "PROVIDER_TYPE_DESC": "enrollment_type",
    "FIRST_NAME": "first_name",
    "LAST_NAME": "last_name",
}

# Pagination settings
DEFAULT_PAGE_SIZE = 500
FLUSH_EVERY_PAGES = 20          # flush to DB every 20 pages (10k records)
CHECKPOINT_EVERY_PAGES = 100    # checkpoint every 100 pages (50k records)


class CMSPECOSFetcher(BaseFetcher):
    """Fetcher for CMS PECOS Medicare enrollment data.

    Streams records to DB per batch (no full in-memory accumulation).
    Supports checkpoint/resume via meta.fetch_checkpoints.
    """

    SOURCE_NAME = "cms_pecos"
    BASE_URL = "https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment"

    # API endpoint (UUID-based — slug endpoints return empty)
    API_ENDPOINT = "https://data.cms.gov/data-api/v1/dataset/2457ea29-fc82-48b0-86ec-3b0755de7515/data"

    def get_latest_url(self) -> str:
        return f"{self.API_ENDPOINT}?size={DEFAULT_PAGE_SIZE}&offset=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch PECOS enrollment records via paginated JSON API, streaming to DB.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, record_count, hash, error.
            records is always [] — data is streamed directly to DB.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            total_inserted = self._fetch_and_stream(max_records=max_records)
            clear_checkpoint(self.SOURCE_NAME)

            result: Dict[str, Any] = {
                "status": "success",
                "records": [],
                "record_count": total_inserted,
                "hash": None,
            }
            self.log_fetch_result({"status": "success", "records": total_inserted})
            return result

        except Exception as exc:
            logger.exception("PECOS fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_and_stream(self, max_records: Optional[int]) -> int:
        """Page through PECOS API, flushing each batch to DB and checkpointing.

        Returns total records inserted/updated.
        """
        # Resume from checkpoint if available
        cp = load_checkpoint(self.SOURCE_NAME)
        offset = cp.get("offset", 0) if cp else 0
        total_inserted = cp.get("records_inserted", 0) if cp else 0

        if offset > 0:
            logger.info(
                "PECOS: resuming from checkpoint offset=%d (%d already inserted)",
                offset, total_inserted,
            )

        page_size = DEFAULT_PAGE_SIZE
        batch: List[Dict[str, Any]] = []
        pages_since_flush = 0
        pages_since_checkpoint = 0

        while True:
            if max_records and total_inserted >= max_records:
                break

            params = {"size": page_size, "offset": offset}
            logger.debug("PECOS: fetching offset=%d", offset)

            try:
                data = self.fetch_json(self.API_ENDPOINT, params=params)
            except Exception as exc:
                logger.warning("PECOS page fetch error at offset %d: %s", offset, exc)
                break

            page_records = data if isinstance(data, list) else data.get("results", data.get("data", []))

            if not page_records:
                logger.info("PECOS: empty page at offset=%d — done", offset)
                break

            for row in page_records:
                batch.append(self._normalise(row))

            offset += len(page_records)
            pages_since_flush += 1
            pages_since_checkpoint += 1

            logger.info(
                "PECOS: offset=%d fetched %d records (batch size=%d)",
                offset, len(page_records), len(batch),
            )

            # Flush batch to DB
            if pages_since_flush >= FLUSH_EVERY_PAGES:
                result = load_cms_pecos_data(batch)
                total_inserted += result.get("records_inserted", 0)
                batch = []
                pages_since_flush = 0

            # Save checkpoint
            if pages_since_checkpoint >= CHECKPOINT_EVERY_PAGES:
                save_checkpoint(self.SOURCE_NAME, {
                    "offset": offset,
                    "records_inserted": total_inserted,
                })
                logger.info(
                    "PECOS: checkpoint saved offset=%d total_inserted=%d",
                    offset, total_inserted,
                )
                pages_since_checkpoint = 0

            if len(page_records) < page_size:
                logger.info("PECOS: last page reached at offset=%d", offset)
                break

        # Flush remaining batch
        if batch:
            result = load_cms_pecos_data(batch)
            total_inserted += result.get("records_inserted", 0)

        logger.info("PECOS: complete — %d total inserted/updated", total_inserted)
        return total_inserted

    @staticmethod
    def _normalise(row: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key fields from a raw API row."""
        record: Dict[str, Any] = {}
        for api_field, output_field in API_FIELD_MAP.items():
            value = row.get(api_field) or row.get(output_field)
            record[output_field] = value
        return record
