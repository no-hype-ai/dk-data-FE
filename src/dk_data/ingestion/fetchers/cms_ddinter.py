"""DDInter (Drug-Drug Interaction) Fetcher.

Fetches drug-drug interaction data from the DDInter database.
DDInter uses a Django DataTables-style POST API:
- Drug list: POST /ddinter/data-source/
- Interactions per drug: POST /ddinter/inter-source/ with submit_id=<drug_index>

Source: https://ddinter.scbdd.com
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

import urllib3

from .base import BaseFetcher

# DDInter server has an expired SSL certificate as of 2026-03.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

LEVEL_SEVERITY = {1: "Minor", 2: "Moderate", 3: "Major", 4: "Contraindicated", 5: "Unknown"}


class CMSDDInterFetcher(BaseFetcher):
    """Fetcher for Drug-Drug Interaction data from DDInter."""

    SOURCE_NAME = "cms_ddinter"
    BASE_URL = "https://ddinter.scbdd.com"

    def get_latest_url(self) -> str:
        return f"{self.BASE_URL}/ddinter/inter-source/"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch drug-drug interactions from DDInter.

        Strategy: iterate through drugs, fetch each drug's interactions.
        Drug A = queried drug name, drug B is extracted from the interaction
        description (first sentence typically names the interacting drug).
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records", 5000)

        try:
            logger.info("Fetching drug-drug interactions from %s", self.BASE_URL)

            # Step 1: Get drug list
            drugs = self._fetch_drugs()
            logger.info("DDInter drug index: %d drugs", len(drugs))

            # Step 2: Iterate through drugs, collect interactions
            records: List[Dict[str, Any]] = []
            seen_pairs: set = set()

            for drug_idx, drug_name in drugs:
                if max_records and len(records) >= max_records:
                    break

                drug_interactions = self._fetch_drug_interactions(drug_idx, drug_name)
                for rec in drug_interactions:
                    # Deduplicate symmetric pairs
                    pair_key = tuple(sorted([rec["drug_a"], rec["drug_b"]]))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        records.append(rec)

                    if max_records and len(records) >= max_records:
                        break

            records = records[:max_records] if max_records else records

            content_hash = hashlib.md5(
                str(len(records)).encode()
            ).hexdigest() if records else None

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("DDInter fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_drugs(self) -> List[tuple]:
        """Fetch all drugs. Returns list of (index, name) tuples."""
        drugs = []
        start = 0
        page_size = 500

        while True:
            resp = self.session.post(
                f"{self.BASE_URL}/ddinter/data-source/",
                data={"draw": 1, "start": start, "length": page_size},
                timeout=60,
                verify=False,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", [])
            if not items:
                break

            for item in items:
                internal_id = item.get("internalID", "")
                name = item.get("name", "")
                if internal_id and name:
                    idx_str = internal_id.replace("DDInter", "")
                    try:
                        drugs.append((int(idx_str), name))
                    except (ValueError, TypeError):
                        pass

            if len(items) < page_size:
                break
            start += page_size

        return drugs

    def _fetch_drug_interactions(
        self, drug_idx: int, drug_name: str
    ) -> List[Dict[str, Any]]:
        """Fetch interactions for a single drug."""
        records = []

        try:
            resp = self.session.post(
                f"{self.BASE_URL}/ddinter/inter-source/",
                data={"draw": 1, "start": 0, "length": 1000, "submit_id": drug_idx},
                timeout=60,
                verify=False,
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("data", []):
                record = self._normalise(item, drug_name)
                if record:
                    records.append(record)

        except Exception as exc:
            logger.debug("DDInter interactions for %s failed: %s", drug_name, exc)

        return records

    @staticmethod
    def _normalise(item: Dict[str, Any], drug_a_name: str) -> Optional[Dict[str, Any]]:
        """Normalize a DDInter interaction record."""
        description = item.get("interaction_description", "")
        if not description:
            return None

        level = item.get("level", 0)
        severity = LEVEL_SEVERITY.get(level, f"Level {level}")

        # Build interaction type from mechanism flags
        mechanisms = []
        for mech in ("absorption", "distribution", "metabolism", "excretion",
                      "synergistic_effect", "antagonistic_effect"):
            if str(item.get(mech, "0")) == "1":
                mechanisms.append(mech.replace("_", " ").title())
        interaction_type = ", ".join(mechanisms) if mechanisms else "Pharmacodynamic"

        # Drug B name: not directly in API response, use interaction idx as reference
        idx = item.get("idx", "unknown")

        return {
            "drug_a": drug_a_name,
            "drug_b": f"DDInter#{idx}",
            "interaction_type": interaction_type,
            "severity": severity,
            "description": description[:2000] if description else None,
        }
