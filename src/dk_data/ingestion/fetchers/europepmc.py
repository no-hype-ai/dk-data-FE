"""EuropePMC API fetcher — incremental by update_date."""
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


class EuropePMCFetcher(BaseFetcher):
    SOURCE_NAME = "europepmc"
    BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def fetch(self, days_back: int = 30, **kwargs) -> Dict[str, Any]:
        since = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        query = f'UPDATE_DATE:[{since} TO *] AND (ABSTRACT:"clinical trial" OR MESH:"Pharmaceutical Preparations")'
        params = {
            "query": query,
            "format": "json",
            "pageSize": 100,
            "resultType": "core",
            "cursorMark": "*",
        }
        all_records: List[Dict] = []
        while True:
            try:
                resp = self.fetch_json(self.BASE_URL, params=params)
                record_api_request(self.SOURCE_NAME, "success")
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Too Many Requests" in err_str:
                    record_rate_limit_rejection(self.SOURCE_NAME)
                    record_api_request(self.SOURCE_NAME, "rate_limited")
                else:
                    record_api_request(self.SOURCE_NAME, "error")
                logger.error(f"EuropePMC fetch error: {e}")
                return {"status": "failed", "records": [], "hash": None, "error": err_str}

            results = resp.get("resultList", {}).get("result", [])
            all_records.extend(results)

            next_cursor = resp.get("nextCursorMark")
            if not next_cursor or next_cursor == params["cursorMark"] or not results:
                break
            params["cursorMark"] = next_cursor

            if len(all_records) >= 10000:  # safety cap
                break

        logger.info(f"EuropePMC fetched {len(all_records)} records (days_back={days_back})")
        return {"status": "success", "records": all_records, "hash": None}

    def get_latest_url(self) -> str:
        return self.BASE_URL
