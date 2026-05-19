"""KEGG Drug REST API fetcher.

Feature: 019-cms-puf-platform-reconciliation

Fetches drug entries from the KEGG REST API (https://rest.kegg.jp).
No credentials required — KEGG REST is a public API.

Fetch strategy:
  1. GET /list/drug  → tab-delimited list of all drug IDs and names
  2. Batch GET /get/{id1}+{id2}+...  → KEGG flat-file text for up to 10 drugs per call
  3. Parse each flat-file entry into a structured dict

KEGG flat-file format example::

    ENTRY       D00001                    Drug
    NAME        4-Aminosalicylic acid
    FORMULA     C7H7NO3
    EXACT_MASS  153.0426
    MOL_WEIGHT  153.1354
    ...
    ///

Multi-value fields (PATHWAY, TARGET, CLASS, REMARK, etc.) are collected as lists.
Each batch response (up to 10 drugs) is stored as one record with an ``entries``
key containing the list of parsed drug dicts.

Stores raw records in mol_raw.kegg_drug (JSONB envelope).
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from ..sources.kegg_drug import load_kegg_drug_data
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from .base import BaseFetcher

logger = logging.getLogger(__name__)

BASE_URL = "https://rest.kegg.jp"
SOURCE_NAME = "kegg_drug"

# Fields that may appear multiple times in a single KEGG flat-file entry
# and should therefore be collected as lists rather than overwritten.
_MULTI_VALUE_FIELDS = {
    "pathway",
    "target",
    "class",
    "remark",
    "comment",
    "interaction",
    "stdinchi",
    "stdinchikey",
    "source",
    "component",
    "efficacy",
    "disease",
    "drug_interaction",
    "metabolism",
    "activity",
    "sequence",
    "dblinks",
    "atom",
    "bond",
}

# Delay between batch HTTP calls (seconds) to respect KEGG rate limits.
# Official KEGG docs: "limit your API calls up to 3 times per second."
# 0.3s = 3.33 req/s which marginally exceeds that — use 0.34s to stay safely under.
_BATCH_DELAY = 0.34


def _parse_kegg_flat_file(text: str) -> List[Dict[str, Any]]:
    """Parse a KEGG flat-file response that may contain multiple entries.

    Entries are separated by ``///`` lines.  Each entry is parsed into a
    dict where the keys are lower-cased KEGG field names.  Fields that can
    appear multiple times (PATHWAY, TARGET, etc.) become lists; all others
    are scalars (the last value wins if there are unexpected duplicates of
    a scalar field).

    Args:
        text: Raw KEGG REST response text from a /get endpoint call.

    Returns:
        List of parsed drug dicts (one per ``///`` block).
    """
    entries: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    current_field: Optional[str] = None

    for raw_line in text.splitlines():
        # Strip trailing whitespace only; leading whitespace is significant
        # (continuation lines start with spaces/tabs)
        line = raw_line.rstrip()

        if line == "///":
            # End of entry — flush current and start fresh
            if current:
                entries.append(current)
            current = {}
            current_field = None
            continue

        if not line:
            continue

        # Continuation line: starts with whitespace and current_field is set
        if line[0] in (" ", "\t") and current_field:
            value = line.strip()
            if not value:
                continue
            existing = current.get(current_field)
            if current_field in _MULTI_VALUE_FIELDS:
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    current[current_field] = [value]
            else:
                # For scalar fields, treat continuation as appended text
                if existing:
                    current[current_field] = f"{existing} {value}"
                else:
                    current[current_field] = value
            continue

        # New field line: first 12 chars are the field tag (left-justified),
        # remainder is the value.
        tag_raw = line[:12].strip()
        value = line[12:].strip() if len(line) > 12 else ""

        if not tag_raw:
            continue

        field = tag_raw.lower()
        current_field = field

        if field == "entry":
            # ENTRY line: "D00001                    Drug"
            # Extract just the ID token
            parts = value.split()
            current["entry"] = parts[0] if parts else value
        elif field in _MULTI_VALUE_FIELDS:
            existing = current.get(field)
            if isinstance(existing, list):
                existing.append(value)
            else:
                current[field] = [value] if value else []
        else:
            current[field] = value

    # Handle file that doesn't end with ///
    if current:
        entries.append(current)

    return entries


class KEGGDrugFetcher(BaseFetcher):
    """Fetcher for the KEGG Drug database via the KEGG REST API.

    The KEGG REST API is public and requires no authentication.
    Batch mode: up to 10 drug IDs joined with ``+`` per /get call.
    """

    SOURCE_NAME = SOURCE_NAME
    BASE_URL = BASE_URL

    def get_latest_url(self) -> str:
        """Return the URL for the full KEGG Drug ID list."""
        return f"{BASE_URL}/list/drug"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch all KEGG Drug entries in batches.

        Keyword Args:
            max_entries (int): Maximum number of drug entries to fetch.
                               Default: 5000.
            batch_size (int):  Number of drug IDs per /get request (max 10).
                               Default: 10.

        Returns:
            Dict with keys:
                status (str):         ``"success"`` or ``"failed"``
                records (list):       List of batch dicts, each with an
                                      ``entries`` key (list of drug dicts).
                record_count (int):   Total number of individual drug entries
                                      across all batches.
                hash (str):           MD5 hex digest of all drug IDs fetched.
                error (str):          Present only on failure.
        """
        max_entries: int = kwargs.get("max_entries", 20_000)  # KEGG Drug has ~11K entries; 20K covers all
        batch_size: int = min(kwargs.get("batch_size", 10), 10)

        try:
            drug_ids = self._fetch_drug_id_list(max_entries)
            logger.info(
                "[kegg_drug] Fetched %d drug IDs from /list/drug", len(drug_ids)
            )

            # Resume from checkpoint if available
            cp = load_checkpoint(self.SOURCE_NAME)
            resume_batch_start = 0
            total_entries = 0
            if cp:
                resume_batch_start = cp.get("batch_start", 0)
                total_entries = cp.get("total_fetched", 0)
                logger.info(
                    "[kegg_drug] Resuming from checkpoint batch_start=%d total=%d",
                    resume_batch_start, total_entries,
                )

            for batch_start in range(resume_batch_start, len(drug_ids), batch_size):
                batch_ids = drug_ids[batch_start : batch_start + batch_size]
                batch_entries = self._fetch_batch(batch_ids)

                if batch_entries:
                    # Flush directly to DB — bounded memory
                    load_kegg_drug_data([{"entries": batch_entries}])
                    total_entries += len(batch_entries)

                logger.debug(
                    "[kegg_drug] Batch %d-%d: %d entries parsed",
                    batch_start,
                    batch_start + len(batch_ids) - 1,
                    len(batch_entries),
                )

                # Checkpoint after each batch
                next_batch = batch_start + batch_size
                save_checkpoint(self.SOURCE_NAME, {
                    "batch_start": next_batch,
                    "total_fetched": total_entries,
                })

                if next_batch < len(drug_ids):
                    time.sleep(_BATCH_DELAY)

            clear_checkpoint(self.SOURCE_NAME)

            content_hash = hashlib.md5(
                json.dumps(drug_ids, sort_keys=True).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": [],  # already in DB
                "record_count": total_entries,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": total_entries})
            return result

        except Exception as exc:
            logger.exception("[kegg_drug] Fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_drug_id_list(self, max_entries: int) -> List[str]:
        """Fetch all KEGG drug IDs from /list/drug.

        Args:
            max_entries: Cap on the number of IDs returned.

        Returns:
            List of KEGG drug IDs (e.g. ``["dr:D00001", "dr:D00002", ...]``).
        """
        url = f"{BASE_URL}/list/drug"
        response = self.session.get(url, timeout=60)
        response.raise_for_status()

        drug_ids: List[str] = []
        for line in response.text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 1)
            drug_id = parts[0].strip()
            if drug_id:
                drug_ids.append(drug_id)
            if len(drug_ids) >= max_entries:
                break

        return drug_ids

    def _fetch_batch(self, drug_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch and parse a batch of up to 10 KEGG drug entries.

        Tries the batch endpoint first (/get/id1+id2+...).  If that returns
        403 (KEGG now restricts multi-ID batch access), falls back to
        individual single-ID requests with a short inter-request delay.

        Args:
            drug_ids: List of KEGG drug IDs (with ``dr:`` prefix).

        Returns:
            List of parsed drug dicts for the batch.
        """
        batch_param = "+".join(drug_ids)
        url = f"{BASE_URL}/get/{batch_param}"

        try:
            response = self.session.get(url, timeout=60)
            if response.status_code == 403 and len(drug_ids) > 1:
                logger.debug(
                    "[kegg_drug] Batch 403 for %d IDs — falling back to single requests",
                    len(drug_ids),
                )
                return self._fetch_individually(drug_ids)
            response.raise_for_status()
            return _parse_kegg_flat_file(response.text)
        except Exception as exc:
            logger.warning(
                "[kegg_drug] Batch fetch failed for %s: %s", batch_param, exc
            )
            return []

    def _fetch_individually(self, drug_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch KEGG entries one at a time (fallback when batch returns 403).

        Args:
            drug_ids: List of KEGG drug IDs (with ``dr:`` prefix).

        Returns:
            List of parsed drug dicts; silently skips IDs that fail.
        """
        entries: List[Dict[str, Any]] = []
        for drug_id in drug_ids:
            url = f"{BASE_URL}/get/{drug_id}"
            try:
                response = self.session.get(url, timeout=60)
                response.raise_for_status()
                parsed = _parse_kegg_flat_file(response.text)
                entries.extend(parsed)
            except Exception as exc:
                logger.debug("[kegg_drug] Single fetch failed for %s: %s", drug_id, exc)
            time.sleep(_BATCH_DELAY)
        return entries
