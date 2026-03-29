"""EMA authorized medicines fetcher — full EPAR product list.

Fetches European Medicines Agency (EMA) authorized medicines from their
Open Data CSV export via the EU Open Data Portal.

Primary URL (CSV, refreshed weekly by EMA):
  https://www.ema.europa.eu/sites/default/files/Medicines_output_european_public_assessment_reports.xlsx

The XLSX contains all human and veterinary EPARs (~1600 products).
Columns include: Medicine name, Therapeutic area, INN (common name),
Company, Marketing authorisation date, Condition/indication, etc.

Stores one JSONB record per row in mol_raw.ema (mol_raw schema, migration 096).
"""

import hashlib
import io
import logging
from typing import Any, Dict, List, Optional

import requests
from .base import BaseFetcher

logger = logging.getLogger(__name__)

# EMA EPAR list — publicly available XLSX, updated weekly
_EPAR_XLSX_URL = (
    "https://www.ema.europa.eu/sites/default/files/Medicines_output_european_public_assessment_reports.xlsx"
)
# Fallback: EU Open Data Portal canonical CSV (ODP dataset ef-862f4adb)
_ODP_CSV_URL = (
    "https://data.europa.eu/api/hub/store/data/medicines-output-european-public-assessment-reports.csv"
)


class EMAMolFetcher(BaseFetcher):
    """Fetcher for EMA authorized medicines (EPAR product list)."""

    SOURCE_NAME = "ema"
    BASE_URL = "https://www.ema.europa.eu"

    def get_latest_url(self) -> str:
        return _EPAR_XLSX_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download the EMA EPAR XLSX and parse all product rows.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
            status='source_unavailable' when neither URL is reachable.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        for url, fmt in [(_EPAR_XLSX_URL, "xlsx"), (_ODP_CSV_URL, "csv")]:
            try:
                logger.info("EMA: downloading product list from %s", url)
                resp = self.session.get(url, timeout=120)
                if resp.status_code == 404:
                    logger.debug("EMA: 404 at %s, trying next URL", url)
                    continue
                resp.raise_for_status()

                content = resp.content
                content_hash = hashlib.sha256(content).hexdigest()

                if fmt == "xlsx":
                    records = self._parse_xlsx(content, max_records)
                else:
                    records = self._parse_csv(content, max_records)

                logger.info("EMA: parsed %d product rows", len(records))
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
        """Parse the EMA EPAR XLSX into row dicts."""
        try:
            import openpyxl
        except ImportError:
            # openpyxl not installed — fall back to openpyxl-free approach via pandas
            return self._parse_xlsx_pandas(content, max_records)

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        headers: List[str] = []
        records: List[Dict[str, Any]] = []

        for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
            if row_idx == 0:
                headers = [str(c).strip() if c else f"col_{i}" for i, c in enumerate(row)]
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
        """Parse XLSX via pandas when openpyxl is directly importable through it."""
        import pandas as pd
        df = pd.read_excel(io.BytesIO(content), dtype=str)
        if max_records:
            df = df.head(max_records)
        df = df.fillna("").astype(str)
        return df.to_dict(orient="records")

    def _parse_csv(self, content: bytes, max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Parse EMA CSV fallback."""
        import csv
        text = content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        records: List[Dict[str, Any]] = []
        for row in reader:
            if max_records and len(records) >= max_records:
                break
            records.append({k.strip(): (v.strip() or None) for k, v in row.items()})
        return records
