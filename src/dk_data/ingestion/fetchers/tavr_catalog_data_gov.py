"""TAVR catalog discovery: Data.gov Catalog Search API.

Phase 0 of the TAVR Benchmark Lab catalog manifest. Hits the public
catalog.data.gov search API with a curated list of healthcare queries and
yields one record per matching dataset.

NOTE: data.gov retired the legacy CKAN Action API
(`/api/3/action/package_search`, now HTTP 404 for every query) in 2026. This
fetcher now targets the replacement `https://catalog.data.gov/search`
endpoint. Each new-API record is normalized into a CKAN-compatible `pkg`
dict so the downstream silver/gold loader
(`sources/tavr_catalog_data_gov.py`) stays byte-compatible and untouched.

The endpoint is env-overridable (DATA_GOV_CATALOG_SEARCH_URL) because
data.gov has documented an imminent base-URL migration to api.data.gov.

Records land in `hcs_bronze.tavr_catalog_raw`. Silver dedupes by
(publisher, catalog_package_id); gold applies provenance discipline.

Spec: .dk/specs/006-tavr-catalog-candidate-manifest-provisioning/spec.md
"""

import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# data.gov retired the CKAN Action API in 2026. The live replacement is the
# Catalog Search API. Overridable via env var because data.gov has documented
# an imminent base-URL migration to api.data.gov.
DEFAULT_CATALOG_SEARCH_URL = "https://catalog.data.gov/search"


def _catalog_search_url() -> str:
    """Resolve the Catalog Search endpoint, honoring the env override."""
    return os.environ.get("DATA_GOV_CATALOG_SEARCH_URL", DEFAULT_CATALOG_SEARCH_URL)


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


def _normalize_to_ckan_pkg(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a data.gov Catalog Search record into a CKAN-compatible dict.

    The downstream silver/gold loader (`sources/tavr_catalog_data_gov.py`)
    parses `rec["_package"]` with CKAN keys. To keep the blast radius to this
    fetcher only, each new-API record is mapped onto the exact `pkg.get(...)`
    keys the loader reads. The original record is preserved under
    `_data_gov_raw` so nothing is lost for future silver work (the loader
    json.dumps the whole pkg into bronze — that is fine/desirable).
    """
    dcat = item.get("dcat") or {}

    resources: List[Dict[str, Any]] = []
    for d in dcat.get("distribution", []) or []:
        url = d.get("downloadURL") or d.get("accessURL")
        if not url:
            # Mirror the loader's own `if not url: continue`.
            continue
        resources.append(
            {
                "url": url,
                "format": d.get("format") or d.get("mediaType"),
                "name": d.get("title"),
                "size": d.get("byteSize"),
            }
        )

    pkg: Dict[str, Any] = {
        "id": item.get("identifier"),
        "name": item.get("slug"),
        "title": item.get("title") or dcat.get("title"),
        # New API exposes a single license string/URL; leave license_title absent.
        "license_id": dcat.get("license"),
        "resources": resources,
        # New API provides only the combined temporal range; leave
        # temporal_start/temporal_end absent (loader tolerates that).
        "temporal": dcat.get("temporal"),
        # Not provided by the new API; loader tolerates None.
        "data_dictionary_url": None,
        # Forward-compat extras (harmless; loader ignores them).
        "notes": item.get("description"),
        "tags": [{"name": k} for k in item.get("keyword", []) or []],
        # Preserve the full original record for future silver work.
        "_data_gov_raw": item,
    }
    return pkg


class TavrCatalogDataGovFetcher(BaseFetcher):
    """Catalog discovery fetcher for catalog.data.gov via the Catalog Search API."""

    SOURCE_NAME = "tavr_catalog_data_gov"
    BASE_URL = DEFAULT_CATALOG_SEARCH_URL

    def get_latest_url(self) -> str:
        return _catalog_search_url()

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Run a Catalog Search query for each seed query and aggregate results.

        Keyword Args:
            queries: list of seed queries. Default: DEFAULT_QUERIES.
            rows_per_query: max rows per query. Default: 100.
            max_records: hard cap across all queries. Default: None.
        """
        queries: List[str] = kwargs.get("queries") or DEFAULT_QUERIES
        rows_per_query: int = kwargs.get("rows_per_query") or DEFAULT_ROWS_PER_QUERY
        max_records: Optional[int] = kwargs.get("max_records")

        search_url = _catalog_search_url()
        seen_ids: set[str] = set()
        records: List[Dict[str, Any]] = []

        try:
            for query in queries:
                params = {"q": query, "per_page": rows_per_query}
                logger.info(
                    "[%s] catalog search q=%r per_page=%d url=%s",
                    self.SOURCE_NAME,
                    query,
                    rows_per_query,
                    search_url,
                )
                payload = self.fetch_json(search_url, params=params)
                results = (
                    payload.get("results", []) if isinstance(payload, dict) else None
                )
                if not results:
                    logger.warning("[%s] empty result for q=%r", self.SOURCE_NAME, query)
                    continue
                for item in results:
                    rec_id = item.get("identifier") or item.get("slug")
                    if not rec_id or rec_id in seen_ids:
                        continue
                    seen_ids.add(rec_id)
                    pkg = _normalize_to_ckan_pkg(item)
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
