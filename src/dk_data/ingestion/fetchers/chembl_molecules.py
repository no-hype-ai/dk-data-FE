"""ChEMBL Molecules fetcher — chemical entities of biological interest.

Fetches small-molecule compound records from the ChEMBL REST API. ChEMBL
is the authoritative source for medicinal chemistry compounds with
bioactivity data.

API: https://www.ebi.ac.uk/chembl/api/data/molecule.json
  Public, no authentication required.
  Pagination via offset/limit (limit=1000 per request).
  Total: ~2.4M compounds.
  Response: {"molecules": [...], "page_meta": {"total_count": N, "limit": L, "offset": O}}

Stores one JSONB record per compound in mol_raw.chembl.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_API_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
_PAGE_SIZE = 1000
_REQUEST_DELAY = 0.2


class ChEMBLMoleculesFetcher(BaseFetcher):
    """Fetcher for ChEMBL compound records via the ChEMBL REST API.

    Paginates through all molecules using offset/limit. Each record is a
    molecule dict keyed by molecule_chembl_id. Deduplication at load time
    uses an expression index on response_body->>'molecule_chembl_id'.
    """

    SOURCE_NAME = "chembl_molecules"
    BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"

    def get_latest_url(self) -> str:
        return f"{_API_URL}?format=json&limit={_PAGE_SIZE}&offset=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch ChEMBL molecule records via paginated REST API.

        Keyword Args:
            max_records: Cap total records fetched. Default: None (all ~2.4M).

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            records = self._fetch_paginated(max_records=max_records)
            content_hash = hashlib.md5(
                json.dumps(len(records)).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("ChEMBL molecules fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_paginated(
        self, max_records: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Page through the ChEMBL molecule API using offset pagination."""
        all_records: List[Dict[str, Any]] = []
        offset = 0
        total: Optional[int] = None

        while True:
            params: Dict[str, Any] = {
                "format": "json",
                "limit": _PAGE_SIZE,
                "offset": offset,
            }

            logger.debug("ChEMBL: offset=%d", offset)
            resp = self.session.get(_API_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            if total is None:
                page_meta = data.get("page_meta", {})
                total = page_meta.get("total_count", 0)
                logger.info("ChEMBL: total_count=%d", total)

            molecules = data.get("molecules", [])
            if not molecules:
                break

            all_records.extend(molecules)
            logger.info(
                "ChEMBL: fetched %d records (offset=%d, running total=%d)",
                len(molecules), offset, len(all_records),
            )

            if max_records and len(all_records) >= max_records:
                all_records = all_records[:max_records]
                break

            # ChEMBL uses 'next' URL in page_meta when more pages exist
            page_meta = data.get("page_meta", {})
            if not page_meta.get("next"):
                break

            offset += _PAGE_SIZE
            if total and offset >= total:
                break

            time.sleep(_REQUEST_DELAY)

        logger.info("ChEMBL: %d total molecules fetched", len(all_records))
        return all_records
