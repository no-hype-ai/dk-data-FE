"""NLM RxNorm REST API Fetcher.

Feature: 019-cms-puf-platform-reconciliation

Fetches drug concept data from the NLM RxNorm REST API (public, no credentials
required).  Two fetch strategies are supported:

  bulk        — GET /allconcepts.json?tty=IN  (ingredients)
                GET /allconcepts.json?tty=BN  (brand names)
                Each response is stored as a single JSONB record.

  properties  — For each rxcui in the supplied ``rxcui_list`` kwarg,
                GET /rxcui/{rxcui}/properties.json
                Each response is stored as a separate JSONB record.
                A 0.1 s delay is applied between per-ID requests to be
                a polite citizen of the public API.

Default strategy (no kwargs): bulk — calls both tty=IN and tty=BN endpoints,
stores 2 records.

Stores raw API responses in mol_raw.rxnorm (see migration 089_entity_linking_gaps.sql).
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

BASE_URL = "https://rxnav.nlm.nih.gov/REST"

# Delay between per-ID property requests (seconds) — be polite to the public API
_PER_ID_DELAY = 0.1


class RxNormFetcher(BaseFetcher):
    """Fetcher for the NLM RxNorm REST API (public, no credentials required)."""

    SOURCE_NAME = "rxnorm"
    BASE_URL = BASE_URL

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "application/json",
        })

    def get_latest_url(self) -> str:
        return f"{BASE_URL}/allconcepts.json?tty=IN"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch RxNorm data from the NLM REST API.

        Keyword Args:
            strategy: ``"bulk"`` (default), ``"properties"``, or ``"related"``.
            rxcui_list: List of RxCUI strings to enrich (used when
                        strategy="properties" or strategy="related").

        Returns:
            Dict with keys:
                status       — "success" or "failed"
                records      — list of raw API response dicts
                record_count — len(records)
                hash         — MD5 hex digest of the serialised records
                api_version  — "v3"
        """
        strategy = kwargs.get("strategy", "bulk")
        rxcui_list: List[str] = kwargs.get("rxcui_list", [])

        try:
            if strategy == "properties" and rxcui_list:
                records = self._fetch_properties(rxcui_list)
            elif strategy == "related" and rxcui_list:
                records = self._fetch_related(rxcui_list)
            else:
                records = self._fetch_bulk()

            content_hash = hashlib.md5(
                json.dumps(records, sort_keys=True).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
                "api_version": "v3",
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("RxNorm fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "api_version": "v3",
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Bulk strategy
    # ------------------------------------------------------------------

    def _fetch_bulk(self) -> List[Dict[str, Any]]:
        """Fetch all ingredient (IN) and brand-name (BN) concepts in bulk.

        Calls two endpoints and returns one JSONB envelope per response,
        so ``records`` will contain exactly 2 items on success.
        """
        records: List[Dict[str, Any]] = []

        for tty in ("IN", "BN"):
            url = f"{BASE_URL}/allconcepts.json?tty={tty}"
            logger.info("RxNorm bulk fetch: tty=%s  url=%s", tty, url)
            response = self.session.get(url, timeout=60)
            response.raise_for_status()
            data = response.json()
            # Annotate so the loader can identify the tty without parsing deep
            data["_tty"] = tty
            records.append(data)

        return records

    # ------------------------------------------------------------------
    # Related concepts enrichment strategy
    # ------------------------------------------------------------------

    def _fetch_related(self, rxcui_list: List[str]) -> List[Dict[str, Any]]:
        """Fetch /rxcui/{rxcui}/related.json for each RxCUI.

        Captures ingredient (IN/MIN), brand-name (BN/SBD), NDC, ATC, and
        drug-class relationships.  Each response stores a ``relatedGroup``
        structure that the bronze SQL model joins to populate ``ingredients``,
        ``brand_names``, ``atc_codes``, and ``drug_classes``.

        A 0.1 s delay is applied between requests.

        Args:
            rxcui_list: RxCUI identifiers to enrich.

        Returns:
            List of raw related response dicts (one per RxCUI).
        """
        records: List[Dict[str, Any]] = []
        total = len(rxcui_list)

        for idx, rxcui in enumerate(rxcui_list, start=1):
            url = f"{BASE_URL}/rxcui/{rxcui}/related.json"
            logger.info(
                "RxNorm related fetch [%d/%d]: rxcui=%s", idx, total, rxcui
            )
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()
                data["_rxcui"] = rxcui
                data["_strategy"] = "related"
                records.append(data)
            except Exception as exc:
                logger.warning(
                    "RxNorm related fetch failed for rxcui=%s: %s", rxcui, exc
                )

            if idx < total:
                time.sleep(_PER_ID_DELAY)

        return records

    # ------------------------------------------------------------------
    # Properties enrichment strategy
    # ------------------------------------------------------------------

    def _fetch_properties(self, rxcui_list: List[str]) -> List[Dict[str, Any]]:
        """Fetch /rxcui/{rxcui}/properties.json for each RxCUI in the list.

        A 0.1 s delay is applied between requests.

        Args:
            rxcui_list: RxCUI identifiers to fetch properties for.

        Returns:
            List of raw properties response dicts (one per RxCUI).
        """
        records: List[Dict[str, Any]] = []
        total = len(rxcui_list)

        for idx, rxcui in enumerate(rxcui_list, start=1):
            url = f"{BASE_URL}/rxcui/{rxcui}/properties.json"
            logger.info(
                "RxNorm properties fetch [%d/%d]: rxcui=%s", idx, total, rxcui
            )
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()
                # Annotate with the requested rxcui so the loader can build
                # the request_id without re-parsing the response envelope
                data["_rxcui"] = rxcui
                records.append(data)
            except Exception as exc:
                logger.warning(
                    "RxNorm properties fetch failed for rxcui=%s: %s", rxcui, exc
                )

            if idx < total:
                time.sleep(_PER_ID_DELAY)

        return records
