"""PubChem fetcher — compound data from the NCBI PubChem database.

Fetches drug-relevant compound records from PubChem using the SDQ
(Structured Data Query) agent endpoint. This provides paginated access
to compound property data for pharmaceutical compounds.

API: https://pubchem.ncbi.nlm.nih.gov/sdq/sdqagent.cgi
  Public, no authentication required.
  Rate limit: 5 requests/second.
  Pagination via start/limit parameters in query JSON body.
  Fetches compound property data: CID, MolecularFormula, MolecularWeight,
  CanonicalSMILES, IsomericSMILES, InChIKey, IUPACName, XLogP, TPSA,
  HBondDonorCount, HBondAcceptorCount, Complexity, HeavyAtomCount.

Stores one JSONB record per compound in mol_raw.pubchem.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_SDQ_URL = "https://pubchem.ncbi.nlm.nih.gov/sdq/sdqagent.cgi"
_PAGE_SIZE = 10000
_REQUEST_DELAY = 0.2
_DEFAULT_MAX_RECORDS = 500_000


class PubChemFetcher(BaseFetcher):
    """Fetcher for PubChem compound records via SDQ download endpoint.

    Uses the PubChem SDQ agent to paginate through compound data with
    pharmaceutical relevance. Each record is a compound dict keyed by cid.
    Deduplication at load time uses an expression index on
    response_body->>'cid'.
    """

    SOURCE_NAME = "pubchem"
    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    def get_latest_url(self) -> str:
        return f"{_SDQ_URL}?infmt=json&outfmt=json"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch PubChem compound records via SDQ paginated download.

        Keyword Args:
            max_records: Cap total records. Default: 500,000.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: int = int(kwargs.get("max_records", _DEFAULT_MAX_RECORDS))

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
            logger.exception("PubChem fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_paginated(self, max_records: int) -> List[Dict[str, Any]]:
        """Page through PubChem SDQ endpoint."""
        all_records: List[Dict[str, Any]] = []
        start = 0

        while len(all_records) < max_records:
            remaining = max_records - len(all_records)
            limit = min(_PAGE_SIZE, remaining)

            query = {
                "download": "*",
                "collection": "compound",
                "order": ["cid,asc"],
                "start": start,
                "limit": limit,
            }
            params = {"infmt": "json", "outfmt": "json"}

            logger.debug("PubChem SDQ: start=%d limit=%d", start, limit)

            try:
                resp = self.session.get(
                    _SDQ_URL,
                    params={**params, "query": json.dumps(query)},
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("PubChem SDQ request failed at start=%d: %s", start, exc)
                break

            # SDQ returns a list directly or wraps in a key
            if isinstance(data, list):
                page_records = data
            else:
                page_records = data.get("SDQOutputSet", [])
                if not page_records:
                    # Try alternate response shapes
                    for key in ("rows", "results", "data"):
                        page_records = data.get(key, [])
                        if page_records:
                            break

            if not page_records:
                logger.info("PubChem SDQ: empty page at start=%d — done", start)
                break

            all_records.extend(page_records)
            logger.info(
                "PubChem SDQ: start=%d fetched %d records (running total=%d)",
                start, len(page_records), len(all_records),
            )

            if len(page_records) < limit:
                break

            start += limit
            time.sleep(_REQUEST_DELAY)

        logger.info("PubChem: %d total compounds fetched", len(all_records))
        return all_records
