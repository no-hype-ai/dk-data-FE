"""EMA EPAR assessment reports fetcher — bulk CSV download.

Fetches the European Public Assessment Reports (EPAR) assessment data
from the EMA medicines download page. This is distinct from the ema_mol
fetcher (which handles the authorised medicines product list) and the
ema_regulatory fetcher (which handles the bulk JSON export).

Primary URL (CSV, refreshed daily by EMA):
  https://www.ema.europa.eu/en/medicines/download-medicine-data

The CSV contains EPAR-specific columns: procedure number, CHMP outcome,
rapporteur, EPAR URL, etc.

Stores one JSONB record per row in mol_raw.ema_epar.
"""

import csv
import hashlib
import io
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_EPAR_CSV_URL = (
    "https://www.ema.europa.eu/en/documents/report/"
    "medicines-output-european-public-assessment-reports_en.csv"
)


class EMAEparFetcher(BaseFetcher):
    """Fetcher for EMA EPAR assessment reports (bulk CSV)."""

    SOURCE_NAME = "ema_epar"
    BASE_URL = "https://www.ema.europa.eu"

    def get_latest_url(self) -> str:
        return _EPAR_CSV_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download the EMA EPAR CSV and parse all assessment report rows.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            logger.info("EMA EPAR: downloading CSV from %s", _EPAR_CSV_URL)
            resp = self.session.get(_EPAR_CSV_URL, timeout=120)
            resp.raise_for_status()

            content = resp.content
            content_hash = hashlib.sha256(content).hexdigest()

            records = self._parse_csv(content, max_records)

            logger.info("EMA EPAR: parsed %d assessment report rows", len(records))

            if not records:
                msg = "EMA EPAR: parsed 0 rows — treating as source_unavailable"
                logger.warning(msg)
                result: Dict[str, Any] = {
                    "status": "source_unavailable",
                    "records": [],
                    "record_count": 0,
                    "hash": None,
                    "error": msg,
                }
                self.log_fetch_result(result)
                return result

            result = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("EMA EPAR fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    @staticmethod
    def _parse_csv(content: bytes, max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Parse the EMA EPAR CSV into row dicts.

        Column names are normalised to lowercase with underscores.
        """
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        records: List[Dict[str, Any]] = []
        for row in reader:
            if max_records and len(records) >= max_records:
                break
            record = {
                k.strip().lower().replace(" ", "_"): (v.strip() if v else None)
                for k, v in row.items()
                if k is not None
            }
            # Skip entirely blank rows
            if all(v is None for v in record.values()):
                continue
            records.append(record)
        return records
