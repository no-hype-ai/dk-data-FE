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

Checkpoint/resume:
  Writes to meta.fetch_checkpoints after every CHECKPOINT_INTERVAL pages so
  that a pod restart or OOMKill can resume from the last committed offset.
  Checkpoint is cleared on successful completion.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from ..sources.pubchem import load_pubchem_data

logger = logging.getLogger(__name__)

_SDQ_URL = "https://pubchem.ncbi.nlm.nih.gov/sdq/sdqagent.cgi"
_PAGE_SIZE = 10000
_REQUEST_DELAY = 0.2
_DEFAULT_MAX_RECORDS = 500_000
_CHECKPOINT_INTERVAL = 10  # save checkpoint every 10 pages (= 100k records)


class PubChemFetcher(BaseFetcher):
    """Fetcher for PubChem compound records via SDQ download endpoint.

    Uses the PubChem SDQ agent to paginate through compound data with
    pharmaceutical relevance. Commits to DB and saves a checkpoint every
    CHECKPOINT_INTERVAL pages so runs can resume after pod restarts.
    """

    SOURCE_NAME = "pubchem"
    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    def get_latest_url(self) -> str:
        return f"{_SDQ_URL}?infmt=json&outfmt=json"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch and load PubChem compound records, resuming from checkpoint if present.

        Keyword Args:
            max_records: Cap total records. Default: 500,000.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
            records is always [] — data is streamed directly to DB per page batch.
        """
        max_records: int = int(kwargs.get("max_records", _DEFAULT_MAX_RECORDS))

        try:
            total_inserted = self._fetch_and_load(max_records=max_records)
            content_hash = hashlib.md5(
                json.dumps(total_inserted).encode()
            ).hexdigest()
            clear_checkpoint(self.SOURCE_NAME)

            result: Dict[str, Any] = {
                "status": "success",
                "records": [],   # streamed directly to DB — not held in memory
                "record_count": total_inserted,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": total_inserted})
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

    def _fetch_and_load(self, max_records: int) -> int:
        """Page through PubChem SDQ endpoint, committing each batch to DB and checkpointing.

        Returns total records inserted/updated.
        """
        # Resume from checkpoint if available
        cp = load_checkpoint(self.SOURCE_NAME)
        start = cp.get("start", 0) if cp else 0
        total_inserted = cp.get("records_inserted", 0) if cp else 0

        if start > 0:
            logger.info(
                "PubChem: resuming from checkpoint start=%d (%d already inserted)",
                start, total_inserted,
            )

        record_buffer: List[Dict[str, Any]] = []
        pages_since_checkpoint = 0
        total_fetched = start  # total records attempted so far

        while total_fetched < max_records:
            remaining = max_records - total_fetched
            limit = min(_PAGE_SIZE, remaining)

            query = {
                "download": "*",
                "collection": "compound",
                "order": ["cid,asc"],
                "start": total_fetched,
                "limit": limit,
            }
            params = {"infmt": "json", "outfmt": "json"}

            logger.debug("PubChem SDQ: start=%d limit=%d", total_fetched, limit)

            try:
                resp = self.session.get(
                    _SDQ_URL,
                    params={**params, "query": json.dumps(query)},
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "PubChem SDQ request failed at start=%d: %s", total_fetched, exc
                )
                break

            # SDQ returns a list directly or wraps in a key
            if isinstance(data, list):
                page_records = data
            else:
                page_records = data.get("SDQOutputSet", [])
                if not page_records:
                    for key in ("rows", "results", "data"):
                        page_records = data.get(key, [])
                        if page_records:
                            break

            if not page_records:
                logger.info("PubChem SDQ: empty page at start=%d — done", total_fetched)
                break

            record_buffer.extend(page_records)
            total_fetched += len(page_records)
            pages_since_checkpoint += 1

            logger.info(
                "PubChem SDQ: start=%d fetched %d records (running total=%d)",
                total_fetched - len(page_records), len(page_records), total_fetched,
            )

            # Commit and checkpoint every CHECKPOINT_INTERVAL pages
            if pages_since_checkpoint >= _CHECKPOINT_INTERVAL:
                result = load_pubchem_data(record_buffer)
                total_inserted += result.get("records_inserted", 0)
                record_buffer = []
                pages_since_checkpoint = 0
                save_checkpoint(self.SOURCE_NAME, {
                    "start": total_fetched,
                    "records_inserted": total_inserted,
                })
                logger.info(
                    "PubChem: checkpoint saved start=%d total_inserted=%d",
                    total_fetched, total_inserted,
                )

            if len(page_records) < limit:
                break

            time.sleep(_REQUEST_DELAY)

        # Flush remaining buffer
        if record_buffer:
            result = load_pubchem_data(record_buffer)
            total_inserted += result.get("records_inserted", 0)

        logger.info("PubChem: complete — %d total inserted/updated", total_inserted)
        return total_inserted
