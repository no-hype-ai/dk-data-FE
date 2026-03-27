"""NIH RePORTER grants API fetcher — incremental by date_added."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)

try:
    from dk_data.observability.metrics import record_api_request, record_rate_limit_rejection
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False
    def record_api_request(*a, **kw): pass  # type: ignore
    def record_rate_limit_rejection(*a, **kw): pass  # type: ignore

NIH_REPORTER_API = "https://api.reporter.nih.gov/v2/projects/search"
PAGE_SIZE = 500
MAX_RECORDS = 50000  # safety cap


class NIHReporterFetcher(BaseFetcher):
    SOURCE_NAME = "nih_reporter"
    BASE_URL = NIH_REPORTER_API

    def fetch(self, days_back: int = 30, **kwargs) -> Dict[str, Any]:
        since_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        today = datetime.utcnow().strftime("%Y-%m-%d")

        payload = {
            "criteria": {
                "date_added_filter": {
                    "from_date": since_date,
                    "to_date": today,
                }
            },
            "limit": PAGE_SIZE,
            "offset": 0,
        }

        all_projects: List[Dict] = []

        while True:
            try:
                resp = self.session.post(
                    self.BASE_URL,
                    json=payload,
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()
                record_api_request(self.SOURCE_NAME, "success")
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Too Many Requests" in err_str:
                    record_rate_limit_rejection(self.SOURCE_NAME)
                    record_api_request(self.SOURCE_NAME, "rate_limited")
                else:
                    record_api_request(self.SOURCE_NAME, "error")
                logger.error(f"NIH Reporter fetch error at offset {payload['offset']}: {e}")
                return {"status": "failed", "records": [], "hash": None, "error": err_str}

            results = data.get("results", [])
            if not results:
                break

            all_projects.extend(results)

            total = data.get("meta", {}).get("total", 0)
            next_offset = payload["offset"] + PAGE_SIZE
            if next_offset >= total or next_offset >= MAX_RECORDS:
                break

            payload["offset"] = next_offset

        logger.info(
            f"NIH Reporter fetched {len(all_projects)} projects "
            f"(days_back={days_back}, since={since_date})"
        )
        return {"status": "success", "records": all_projects, "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
