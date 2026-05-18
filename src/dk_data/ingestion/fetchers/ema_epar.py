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

import hashlib
import io
import logging
from typing import Any

import openpyxl

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_HEADER_ROW = 8

_EPAR_URLS = [
    # Primary: /system/files/ path (confirmed working 2026-04-18, XLSX 607KB)
    ("https://www.ema.europa.eu/system/files/documents/other/"
     "medicines_output_european_public_assessment_reports_en.xlsx", "xlsx"),
    # Fallback: /en/documents/report/ path (returned 404/429 as of 2026-04-17)
    ("https://www.ema.europa.eu/en/documents/report/"
     "medicines-output-european-public-assessment-reports_en.xlsx", "xlsx"),
    # Legacy: old /sites/default/files/ path
    ("https://www.ema.europa.eu/sites/default/files/"
     "Medicines_output_european_public_assessment_reports.xlsx", "xlsx"),
]
# Keep single-URL compat for source_url property
_EPAR_CSV_URL = _EPAR_URLS[0][0]
_EPAR_PRIMARY_URL = (
    "https://www.ema.europa.eu/en/documents/report/"
    "medicines-output-european-public-assessment-reports_en.xlsx"
)


class EMAEparFetcher(BaseFetcher):
    """Fetcher for EMA EPAR assessment reports (bulk CSV)."""

    SOURCE_NAME: str = "ema_epar"
    BASE_URL: str = "https://www.ema.europa.eu"

    def get_latest_url(self) -> str:
        return _EPAR_CSV_URL

    def fetch(self, **kwargs) -> dict[str, Any]:
        """Download the EMA EPAR CSV and parse all assessment report rows.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: int | None = kwargs.get("max_records")

        try:
            resp = None
            used_url = None
            for url, fmt in _EPAR_URLS:
                logger.info("EMA EPAR: trying %s (%s)", url, fmt)
                try:
                    resp = self.session.get(url, timeout=120)
                    if resp.status_code == 200:
                        used_url = url
                        logger.info("EMA EPAR: success from %s (%d bytes)", url, len(resp.content))
                        break
                    logger.warning("EMA EPAR: %s returned %d, trying next", url, resp.status_code)
                except Exception as exc:
                    logger.warning("EMA EPAR: %s failed (%s), trying next", url, exc)
            if resp is None or resp.status_code != 200:
                logger.error("EMA EPAR: all URLs exhausted, source unavailable")
                return {"status": "source_unavailable", "records": [], "error": "all EMA EPAR URLs returned non-200"}
            # Use the successful response
            _EPAR_CSV_URL_USED = used_url  # noqa: F841 — for debug logging
            resp.raise_for_status()

            content = resp.content
            content_hash = hashlib.sha256(content).hexdigest()

            records = self._parse_xlsx(content, max_records)

            logger.info("EMA EPAR: parsed %d assessment report rows", len(records))

            if not records:
                msg = "EMA EPAR: parsed 0 rows — treating as source_unavailable"
                logger.warning(msg)
                result: dict[str, Any] = {
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
    def _parse_xlsx(content: bytes, max_records: int | None) -> list[dict[str, Any]]:
        """Parse EMA EPAR XLSX bytes into row dicts.

        Column names are normalised to lowercase with underscores.
        """
        wb = openpyxl.load_workbook(filename=io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        assert ws is not None

        headers: list[str] = []
        records: list[dict[str, Any]] = []

        for row_idx, raw_row in enumerate(ws.iter_rows(values_only=True)):
            if row_idx < _HEADER_ROW:
                continue
            if row_idx == _HEADER_ROW:
                headers = [
                    (str(c).strip().lower().replace(" ", "_") if c is not None else None)
                    for c in raw_row
                ]
                continue

            if max_records and len(records) >= max_records:
                break

            record = {
                h: (str(v).strip() if v is not None else None)
                for h, v in zip(headers, raw_row)
                if h is not None
            }
            if all(v is None for v in record.values()):
                continue
            records.append(record)

        wb.close()
        return records
