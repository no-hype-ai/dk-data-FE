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
        try:
            if years:
                csv_paths = self._fetch_cms_api_multi_year(
                    self.DATASET_UUID, years, max_records_per_year=max_records
                )
                if not csv_paths:
                    return {"status": "success", "records": 0, "record_count": 0, "hash": None, "extracted_files": []}
                return {
                    "status": "success",
                    "records": len(csv_paths),
                    "record_count": len(csv_paths),
                    "hash": None,
                    "extracted_files": csv_paths,
                }
            tmp_path, count = self._fetch_cms_api_to_csv(self.DATASET_UUID, max_records)
            if not tmp_path:
                return {"status": "success", "records": [], "record_count": 0, "hash": None, "extracted_files": []}
            return {
                "status": "success",
                "records": count,
                "record_count": count,
                "hash": None,
                "extracted_files": [tmp_path],
            }
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
