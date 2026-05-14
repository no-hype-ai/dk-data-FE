"""TAVR catalog discovery: Data.gov CKAN.

Phase 0 of the TAVR Benchmark Lab catalog manifest. Hits the public CKAN
`package_search` API on catalog.data.gov with a curated list of healthcare
queries and yields one record per matching package.

Records land in `hcs_bronze.tavr_catalog_raw`. Silver dedupes by
(publisher, catalog_package_id); gold applies provenance discipline.

Spec: .dk/specs/006-tavr-catalog-candidate-manifest-provisioning/spec.md
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

CKAN_ENDPOINT = "https://catalog.data.gov/api/3/action/package_search"
PUBLISHER = "data_gov"

# Curated discovery queries. Phase 0 is breadth-first; structured search
# moves to silver-layer dedup. Keep this list short and high-signal.
DEFAULT_QUERIES = [
    "tavr",
    "transcatheter aortic valve",
    "aortic stenosis",
    "cardiac surgery outcomes",
    "hospital readmissions",
    "cardiovascular procedures",
    "medicare hospital quality",
    "cms hospital compare",
]

DEFAULT_ROWS_PER_QUERY = 100


class TavrCatalogDataGovFetcher(BaseFetcher):
    """Catalog discovery fetcher for catalog.data.gov via CKAN package_search."""

    SOURCE_NAME = "tavr_catalog_data_gov"
    BASE_URL = CKAN_ENDPOINT

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Run package_search for each seed query and aggregate results.

        Keyword Args:
            queries: list of seed queries. Default: DEFAULT_QUERIES.
            rows_per_query: max rows per query. Default: 100.
            max_records: hard cap across all queries. Default: None.
        """
        queries: List[str] = kwargs.get("queries") or DEFAULT_QUERIES
        rows_per_query: int = kwargs.get("rows_per_query") or DEFAULT_ROWS_PER_QUERY
        max_records: Optional[int] = kwargs.get("max_records")

        seen_ids: set[str] = set()
        records: List[Dict[str, Any]] = []

        try:
            for query in queries:
                params = {"q": query, "rows": rows_per_query}
                logger.info("[%s] CKAN package_search q=%r rows=%d", self.SOURCE_NAME, query, rows_per_query)
                payload = self.fetch_json(CKAN_ENDPOINT, params=params)
                result = payload.get("result") if isinstance(payload, dict) else None
                if not result:
                    logger.warning("[%s] empty result for q=%r", self.SOURCE_NAME, query)
                    continue
                for pkg in result.get("results", []):
                    pkg_id = pkg.get("id") or pkg.get("name")
                    if not pkg_id or pkg_id in seen_ids:
                        continue
                    seen_ids.add(pkg_id)
                    records.append({"_search_query": query, "_package": pkg})
                    if max_records is not None and len(records) >= max_records:
                        break
                if max_records is not None and len(records) >= max_records:
                    break

            content_hash = hashlib.md5(
                json.dumps(sorted(seen_ids)).encode()
            ).hexdigest()

            result_obj: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result_obj

        except Exception as exc:
            logger.exception("[%s] fetch failed: %s", self.SOURCE_NAME, exc)
            result_obj = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result_obj)
            return result_obj
