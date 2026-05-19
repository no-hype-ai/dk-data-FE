"""EMA authorized medicines fetcher — full EPAR product list.

Fetches European Medicines Agency (EMA) authorized medicines from their
download-medicine-data page XLSX export.

Primary URL (XLSX, refreshed daily by EMA, ~2,600 products):
  https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx

The file has metadata rows at the top; actual column headers are at row 8
(0-indexed). Columns include: Category, Name of medicine, EMA product number,
Medicine status, INN, Active substance, Therapeutic area, ATC code, etc.

Legacy URL (now 404 since early 2026):
  https://www.ema.europa.eu/sites/default/files/Medicines_output_european_public_assessment_reports.xlsx

Stores one JSONB record per row in mol_raw.ema (mol_raw schema, migration 096).
"""

import hashlib
import io
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Lowercase substrings; at least ONE must appear in any header cell for the
# header row to be considered valid.  Lenient by design.
_EXPECTED_HEADER_TOKENS = ("medicine", "category", "name", "active", "substance", "product", "area", "status")


class _EmaMolParseError(Exception):
    """Downloaded bytes are not a usable workbook (corrupt/short/not-xlsx/no active sheet)."""


class _EmaMolSchemaError(Exception):
    """Workbook opened but the EMA export format changed (bad/absent header row, or 0 data rows from a non-empty file)."""


# EMA medicines report — primary URL (updated daily)
_EPAR_XLSX_URL = (
    "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx"
)
# Legacy URL (404 as of early 2026, kept for reference)
_LEGACY_XLSX_URL = (
    "https://www.ema.europa.eu/sites/default/files/Medicines_output_european_public_assessment_reports.xlsx"
)
# Row index (0-based) where actual column headers appear in the new file format
_HEADER_ROW = 8


class EMAMolFetcher(BaseFetcher):
    """Fetcher for EMA authorized medicines (EPAR product list)."""

    SOURCE_NAME = "ema"
    BASE_URL = "https://www.ema.europa.eu"

    def get_latest_url(self) -> str:
        return _EPAR_XLSX_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download the EMA medicines report XLSX and parse all product rows.

        Returns:
            Dict with keys: status, records, record_count, hash, error.

        Status taxonomy:
            success          — downloaded and parsed ≥1 rows.
            source_unavailable — URL returned non-200 (EMA server down/unreachable).
            parse_error      — 200 download succeeded but bytes are not a valid workbook.
            schema_mismatch  — workbook opened but header row missing expected columns,
                               or 0 data rows parsed from a non-empty 200 response.
            failed           — unexpected error not covered by the above.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            url = _EPAR_XLSX_URL
            logger.info("EMA: downloading product list from %s", url)
            try:
                resp = self.session.get(url, timeout=120)
                if resp.status_code != 200:
                    # Primary (only) URL failed — must log at ERROR
                    logger.error(
                        "EMA PRIMARY url failed (%s): HTTP %d — source unavailable",
                        url,
                        resp.status_code,
                    )
                    result: Dict[str, Any] = {
                        "status": "source_unavailable",
                        "records": [],
                        "record_count": 0,
                        "hash": None,
                        "error": f"EMA: primary URL {url!r} returned HTTP {resp.status_code}",
                    }
                    self.log_fetch_result(result)
                    return result
            except Exception as exc:
                logger.error(
                    "EMA PRIMARY url failed (%s): %s — source unavailable",
                    url,
                    exc,
                )
                result = {
                    "status": "source_unavailable",
                    "records": [],
                    "record_count": 0,
                    "hash": None,
                    "error": f"EMA: primary URL {url!r} unreachable: {exc}",
                }
                self.log_fetch_result(result)
                return result

            resp.raise_for_status()
            content = resp.content
            content_hash = hashlib.sha256(content).hexdigest()

            records = self._parse_xlsx(content, max_records)

            logger.info("EMA: parsed %d product rows", len(records))

            if not records:
                raise _EmaMolSchemaError(
                    f"EMA: downloaded {len(content)} bytes from {url!r} but parsed 0 rows — EMA format may have changed"
                )

            result = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except _EmaMolParseError as exc:
            logger.error("EMA parse error: %s", exc)
            result = {
                "status": "parse_error",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

        except _EmaMolSchemaError as exc:
            logger.error("EMA schema mismatch: %s", exc)
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
            logger.exception("EMA fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _parse_xlsx(self, content: bytes, max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Parse the EMA medicines report XLSX into row dicts.

        The file has metadata rows at the top; column headers appear at
        row index _HEADER_ROW (8). Rows before the header are skipped.

        Raises:
            _EmaMolParseError: if bytes cannot be opened as a workbook or no active sheet.
            _EmaMolSchemaError: if the header row contains no recognised column names.
        """
        try:
            import openpyxl
        except ImportError:
            return self._parse_xlsx_pandas(content, max_records)

        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise _EmaMolParseError(f"EMA medicines workbook unreadable: {exc}") from exc

        ws = wb.active
        if ws is None:
            wb.close()
            raise _EmaMolParseError("EMA medicines workbook has no active worksheet")

        headers: List[str] = []
        records: List[Dict[str, Any]] = []

        for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
            if row_idx < _HEADER_ROW:
                continue
            if row_idx == _HEADER_ROW:
                headers = [
                    str(c).strip() if c else None
                    for c in row
                ]
                # Validate header: at least one cell must contain an expected token
                non_none = [h.lower() for h in headers if h]
                if not non_none or not any(
                    token in h for h in non_none for token in _EXPECTED_HEADER_TOKENS
                ):
                    wb.close()
                    raise _EmaMolSchemaError(
                        f"EMA medicines header-row drift at row {_HEADER_ROW}: {headers!r}"
                    )
                continue
            if max_records and len(records) >= max_records:
                break
            rec = {
                h: (str(v).strip() if v is not None else None)
                for h, v in zip(headers, row)
                if h is not None
            }
            # Skip entirely blank rows
            if all(v is None for v in rec.values()):
                continue
            records.append(rec)

        wb.close()
        return records

    def _parse_xlsx_pandas(self, content: bytes, max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Parse XLSX via pandas, skipping the EMA metadata preamble rows."""
        import pandas as pd
        df = pd.read_excel(io.BytesIO(content), header=_HEADER_ROW, dtype=str)
        if max_records:
            df = df.head(max_records)
        df = df.fillna("").astype(str)
        # Drop columns that are entirely empty (the trailing None columns)
        df = df.loc[:, ~df.columns.str.startswith("Unnamed:")]
        return df.to_dict(orient="records")


