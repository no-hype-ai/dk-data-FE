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
            status='source_unavailable' when the URL is unreachable.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        for url, fmt in [(_EPAR_XLSX_URL, "xlsx")]:
            try:
                logger.info("EMA: downloading product list from %s", url)
                resp = self.session.get(url, timeout=120)
                if resp.status_code == 404:
                    logger.debug("EMA: 404 at %s, trying next URL", url)
                    continue
                resp.raise_for_status()

                content = resp.content
                content_hash = hashlib.sha256(content).hexdigest()

                records = self._parse_xlsx(content, max_records)

                logger.info("EMA: parsed %d product rows", len(records))

                if not records:
                    logger.warning("EMA: parsed 0 rows from %s — treating as source_unavailable", url)
                    continue

                result: Dict[str, Any] = {
                    "status": "success",
                    "records": records,
                    "record_count": len(records),
                    "hash": content_hash,
                }
                self.log_fetch_result({"status": "success", "records": len(records)})
                return result

            except Exception as exc:
                logger.warning("EMA: fetch failed for %s: %s", url, exc)
                continue

        msg = "EMA: all URLs failed or returned 404. EPAR list unavailable."
        logger.warning(msg)
        result = {"status": "source_unavailable", "records": [], "record_count": 0, "hash": None, "error": msg}
        self.log_fetch_result(result)
        return result

    def _parse_xlsx(self, content: bytes, max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Parse the EMA medicines report XLSX into row dicts.

        The file has metadata rows at the top; column headers appear at
        row index _HEADER_ROW (8). Rows before the header are skipped.
        """
        try:
            import openpyxl
        except ImportError:
            return self._parse_xlsx_pandas(content, max_records)

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        headers: List[str] = []
        records: List[Dict[str, Any]] = []

        for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
            if row_idx < _HEADER_ROW:
                continue
            if row_idx == _HEADER_ROW:
                # Use only non-None header cells; pad with positional names for extras
                headers = [
                    str(c).strip() if c else f"col_{i}"
                    for i, c in enumerate(row)
                ]
                continue
            if max_records and len(records) >= max_records:
                break
            rec = {h: (str(v).strip() if v is not None else None) for h, v in zip(headers, row)}
            # Skip entirely blank rows
            if all(v is None for v in rec.values()):
                continue
            records.append(rec)

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


