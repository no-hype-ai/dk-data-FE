"""CMS Hospital Provider Cost Reports PUF fetcher."""
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSCostReportsPUFFetcher(BaseFetcher):
    """Fetches CMS Hospital Provider Cost Reports PUF (summary rows)."""
    SOURCE_NAME = "cms_cost_reports_puf"
    # Canonical UUID — fetches most recent available year.
    # Pass years=[2021, 2022, 2023] to backfill multiple years dynamically.
    DATASET_UUID = "44060663-47d8-4ced-a115-b53b4c270acb"

    def get_latest_url(self) -> str:
        return f"https://data.cms.gov/data-api/v1/dataset/{self.DATASET_UUID}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        years: Optional[List[int]] = kwargs.get("years")
        source_year = int(kwargs.get("fiscal_year") or kwargs.get("source_year") or 2023)
        try:
            from ..sources.cms_cost_reports_puf import load_cms_cost_reports_puf
            from ..utils.checkpoint import clear_checkpoint
            if years:
                total_fetched, total_inserted = self._stream_cms_api_multi_year_to_db(
                    self.DATASET_UUID, load_cms_cost_reports_puf, years=years, max_records_per_year=max_records
                )
            else:
                total_fetched, total_inserted = self._stream_cms_api_to_db(
                    self.DATASET_UUID, load_cms_cost_reports_puf, source_year=source_year, max_records=max_records
                )
            clear_checkpoint(self.SOURCE_NAME)
            return {"status": "success", "records": [], "record_count": total_inserted, "hash": None}
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}


class CMSCostReportsPUFLinesFetcher(CMSCostReportsPUFFetcher):
    """Fetches CMS Hospital Provider Cost Reports PUF (worksheet line items).

    Shares the same CMS dataset as CMSCostReportsPUFFetcher — the loader
    (load_cms_cost_reports_puf_lines) extracts the worksheet-level rows.
    Subclass exists solely to give this source its own SOURCE_NAME so that
    logs and metrics are correctly attributed to cms_cost_reports_puf_lines.
    """
    SOURCE_NAME = "cms_cost_reports_puf_lines"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = kwargs.get("max_records")
        years: Optional[List[int]] = kwargs.get("years")
        source_year = int(kwargs.get("fiscal_year") or kwargs.get("source_year") or 2023)
        try:
            from ..sources.cms_cost_reports_puf_lines import load_cms_cost_reports_puf_lines
            from ..utils.checkpoint import clear_checkpoint
            if years:
                total_fetched, total_inserted = self._stream_cms_api_multi_year_to_db(
                    self.DATASET_UUID, load_cms_cost_reports_puf_lines, years=years, max_records_per_year=max_records
                )
            else:
                total_fetched, total_inserted = self._stream_cms_api_to_db(
                    self.DATASET_UUID, load_cms_cost_reports_puf_lines, source_year=source_year, max_records=max_records
                )
            clear_checkpoint(self.SOURCE_NAME)
            return {"status": "success", "records": [], "record_count": total_inserted, "hash": None}
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
