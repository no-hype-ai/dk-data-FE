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
from typing import Any, Dict, List

from .base import BaseFetcher
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from ..sources.pubchem import load_pubchem_data

logger = logging.getLogger(__name__)

_SDQ_URL = "https://pubchem.ncbi.nlm.nih.gov/sdq/sdqagent.cgi"
_PAGE_SIZE = 10000
_REQUEST_DELAY = 0.2
_DEFAULT_MAX_RECORDS = None  # No cap — fetch all ~123M PubChem compounds
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
            max_records: Cap total records. Default: None (unlimited — fetches all ~123M compounds).

        Returns:
            Dict with keys: status, records, record_count, hash, error.
            records is always [] — data is streamed directly to DB per page batch.
        """
        raw_max = kwargs.get("max_records", _DEFAULT_MAX_RECORDS)
        max_records = int(raw_max) if raw_max is not None else None

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

    def _fetch_and_load(self, max_records) -> int:
        """Page through PubChem SDQ endpoint using CID-range pagination.

        Uses WHERE cid > last_cid to advance through the dataset reliably.
        Offset-based (start=N) pagination is not used because the SDQ endpoint
        returns empty responses for certain offset values, causing early termination.

        Returns total records inserted/updated.
        """
        # Resume from checkpoint if available — checkpoint stores last_cid
        cp = load_checkpoint(self.SOURCE_NAME)
        last_cid = cp.get("last_cid", 0) if cp else 0
        total_inserted = cp.get("records_inserted", 0) if cp else 0

        if last_cid > 0:
            logger.info(
                "PubChem: resuming from checkpoint last_cid=%d (%d already inserted)",
                last_cid, total_inserted,
            )

        record_buffer: List[Dict[str, Any]] = []
        pages_since_checkpoint = 0
        total_fetched = 0
        consecutive_empty = 0
        _MAX_CONSECUTIVE_EMPTY = 3  # retry up to 3 times before declaring end of data

        while max_records is None or total_fetched < max_records:
            remaining = (max_records - total_fetched) if max_records is not None else _PAGE_SIZE
            limit = min(_PAGE_SIZE, remaining)

            # CID-range filter: advance by fetching compounds with cid > last_cid
            where_clause: Dict = {}
            if last_cid > 0:
                where_clause = {"ands": [{"cid": f">{last_cid}"}]}

            query: Dict[str, Any] = {
                "select": "*",
                "collection": "compound",
                "order": ["cid,asc"],
                "start": 1,
                "limit": limit,
            }
            if where_clause:
                query["where"] = where_clause

            params = {"infmt": "json", "outfmt": "json"}

            logger.debug("PubChem SDQ: last_cid=%d limit=%d", last_cid, limit)

            try:
                resp = self.session.get(
                    _SDQ_URL,
                    params={**params, "query": json.dumps(query)},
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error(
                    "PubChem SDQ request failed at last_cid=%d: %s", last_cid, exc
                )
                # Flush any buffered records before re-raising so partial progress is saved
                if record_buffer:
                    result = load_pubchem_data(record_buffer)
                    total_inserted += result.get("records_inserted", 0)
                    record_buffer = []
                    save_checkpoint(self.SOURCE_NAME, {
                        "last_cid": last_cid,
                        "records_inserted": total_inserted,
                    })
                raise

            # SDQ response shape: {"SDQOutputSet": [{"rows": [...compounds...], ...}]}
            sdq_output = data.get("SDQOutputSet", []) if isinstance(data, dict) else []
            if sdq_output and isinstance(sdq_output, list):
                page_records = sdq_output[0].get("rows", [])
            elif isinstance(data, list):
                page_records = data
            else:
                page_records = []

            if not page_records:
                consecutive_empty += 1
                if consecutive_empty >= _MAX_CONSECUTIVE_EMPTY:
                    logger.info(
                        "PubChem SDQ: %d consecutive empty pages after cid=%d — done",
                        consecutive_empty, last_cid,
                    )
                    break
                logger.warning(
                    "PubChem SDQ: empty page after cid=%d (attempt %d/%d), retrying in 5s",
                    last_cid, consecutive_empty, _MAX_CONSECUTIVE_EMPTY,
                )
                time.sleep(5)
                continue

            consecutive_empty = 0

            # Advance the CID cursor to the last CID on this page
            last_cid_raw = page_records[-1].get("cid", 0)
            last_cid = int(last_cid_raw) if last_cid_raw else last_cid

            record_buffer.extend(page_records)
            total_fetched += len(page_records)
            pages_since_checkpoint += 1

            logger.info(
                "PubChem SDQ: fetched %d records (last_cid=%d, running total=%d)",
                len(page_records), last_cid, total_fetched,
            )

            # Commit and checkpoint every CHECKPOINT_INTERVAL pages
            if pages_since_checkpoint >= _CHECKPOINT_INTERVAL:
                result = load_pubchem_data(record_buffer)
                total_inserted += result.get("records_inserted", 0)
                record_buffer = []
                pages_since_checkpoint = 0
                save_checkpoint(self.SOURCE_NAME, {
                    "last_cid": last_cid,
                    "records_inserted": total_inserted,
                })
                logger.info(
                    "PubChem: checkpoint saved last_cid=%d total_inserted=%d",
                    last_cid, total_inserted,
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
