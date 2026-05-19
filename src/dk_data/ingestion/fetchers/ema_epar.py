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

# Lowercase substrings; at least ONE must appear in any header cell for the
# header row to be considered valid. Lenient by design — avoids false
# schema_mismatch on minor EMA wording changes.
_EXPECTED_HEADER_TOKENS = ("medicine", "epar", "name", "active_substance", "product")


class _EparParseError(Exception):
    """Downloaded bytes are not a usable workbook (corrupt/short/not-xlsx/no active sheet)."""


class _EparSchemaError(Exception):
    """Workbook opened but the EMA export format changed (bad/absent header row, or 0 data rows from a non-empty file)."""

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

        Status taxonomy:
            success          — downloaded and parsed ≥1 rows.
            source_unavailable — all URLs returned non-200 (EMA server down/unreachable).
            parse_error      — 200 download succeeded but bytes are not a valid workbook.
            schema_mismatch  — workbook opened but header row missing expected columns,
                               or 0 data rows parsed from a non-empty 200 response.
            failed           — unexpected error not covered by the above.
        """
        max_records: int | None = kwargs.get("max_records")

        try:
            resp = None
            used_url = None

            for idx, (url, fmt) in enumerate(_EPAR_URLS):
                logger.info("EMA EPAR: trying %s (%s)", url, fmt)
                try:
                    resp = self.session.get(url, timeout=120)
                    if resp.status_code == 200:
                        used_url = url
                        logger.info("EMA EPAR: success from %s (%d bytes)", url, len(resp.content))
                        break
                    # Non-200 response
                    reason = f"HTTP {resp.status_code}"
                    if idx == 0:
                        logger.error(
                            "EMA EPAR PRIMARY url failed (%s): %s — falling back to known-degraded URLs",
                            url,
                            reason,
                        )
                    else:
                        logger.warning("EMA EPAR: %s returned %d, trying next", url, resp.status_code)
                    resp = None  # mark as failed so we don't use it
                except Exception as exc:
                    reason = str(exc)
                    if idx == 0:
                        logger.error(
                            "EMA EPAR PRIMARY url failed (%s): %s — falling back to known-degraded URLs",
                            url,
                            reason,
                        )
                    else:
                        logger.warning("EMA EPAR: %s failed (%s), trying next", url, exc)
                    resp = None

            if resp is None or resp.status_code != 200:
                logger.error("EMA EPAR: all URLs exhausted, source unavailable")
                result: dict[str, Any] = {
                    "status": "source_unavailable",
                    "records": [],
                    "record_count": 0,
                    "hash": None,
                    "error": "all EMA EPAR URLs returned non-200",
                }
                self.log_fetch_result(result)
                return result

            # Use the successful response
            _EPAR_CSV_URL_USED = used_url  # noqa: F841 — for debug logging
            resp.raise_for_status()

            content = resp.content
            content_hash = hashlib.sha256(content).hexdigest()

            records = self._parse_xlsx(content, max_records)

            logger.info("EMA EPAR: parsed %d assessment report rows", len(records))

            if not records:
                raise _EparSchemaError(
                    f"EMA EPAR: downloaded {len(content)} bytes but parsed 0 rows — EMA format may have changed"
                )

            result = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except _EparParseError as exc:
            logger.error("EMA EPAR parse error: %s", exc)
            result = {
                "status": "parse_error",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

        except _EparSchemaError as exc:
            logger.error("EMA EPAR schema mismatch: %s", exc)
            result = {
                "status": "schema_mismatch",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
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

        Raises:
            _EparParseError: if the bytes cannot be opened as a workbook, or if the
                workbook has no active worksheet.
            _EparSchemaError: if the header row at _HEADER_ROW contains no recognised
                column names (all cells blank or no expected token found).
        """
        try:
            wb = openpyxl.load_workbook(filename=io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise _EparParseError(f"EMA EPAR workbook unreadable: {exc}") from exc

        ws = wb.active
        if ws is None:
            wb.close()
            raise _EparParseError("EMA EPAR workbook has no active worksheet")

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
                # Validate header: at least one cell must contain an expected token
                non_none_headers = [h for h in headers if h]
                if not non_none_headers or not any(
                    token in h for h in non_none_headers for token in _EXPECTED_HEADER_TOKENS
                ):
                    wb.close()
                    raise _EparSchemaError(
                        f"EMA EPAR header-row drift at row {_HEADER_ROW}: {headers!r}"
                    )
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
