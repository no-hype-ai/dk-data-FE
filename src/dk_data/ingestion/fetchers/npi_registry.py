"""NPI Registry fetcher — CMS National Provider Identifier registry.

Fetches provider records from the NPPES bulk data dissemination file.
The NPPES REST search API (npiregistry.cms.hhs.gov/api) requires search
criteria per request and does not support bulk enumeration, so this fetcher
uses the monthly full-replacement bulk download instead:

  https://download.cms.gov/nppes/NPPES_Data_Dissemination_{Month}_{Year}.zip

The zip contains a large CSV (npidata_pfile_*.csv, ~4.5 GB uncompressed)
with one row per NPI. Each row is stored as a JSONB blob in mol_raw.npi_registry
with the column 'NPI' renamed to 'number' for index compatibility.

Stores one JSONB record per NPI in mol_raw.npi_registry.

Checkpoint/resume:
  Writes to meta.fetch_checkpoints after every CHECKPOINT_INTERVAL rows so
  that a pod restart can resume from the last committed CSV offset instead of
  re-downloading and re-parsing from scratch.
  Checkpoint is cleared on successful completion.
"""

import csv
import hashlib
import io
import json
import logging
import zipfile
from typing import Any, Dict, List, Optional

import requests

from .base import BaseFetcher
from ..utils.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from ..sources.npi_registry import load_npi_registry_data

logger = logging.getLogger(__name__)

_BULK_BASE_URL = "https://download.cms.gov/nppes"
_BATCH_SIZE = 1_000       # rows inserted per DB transaction
_CHECKPOINT_INTERVAL = 100_000  # save checkpoint every 100k rows
_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Rename CSV column 'NPI' to 'number' to match the expression index
# on mol_raw.npi_registry (response_body->>'number').
_NPI_COLUMN = "NPI"
_NPI_KEY = "number"


class NPIRegistryFetcher(BaseFetcher):
    """Fetcher for CMS NPI Registry provider records via monthly bulk download.

    Downloads and parses the NPPES full-replacement monthly CSV (~1 GB zip,
    ~4.5 GB uncompressed) and inserts all active NPIs as JSONB blobs.
    Supports checkpoint/resume so pod restarts resume from the last
    committed row offset rather than re-downloading.
    """

    SOURCE_NAME = "npi_registry"
    BASE_URL = _BULK_BASE_URL

    def get_latest_url(self) -> str:
        """Return the URL for the most recently available NPPES bulk download."""
        return self._find_latest_url() or f"{_BULK_BASE_URL}/NPI_Files.html"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download and load NPPES bulk NPI data, resuming from checkpoint if present.

        Keyword Args:
            max_records: Cap total records (for testing). Default: None (all).

        Returns:
            Dict with keys: status, records, record_count, hash, error.
            records is always [] — data is streamed directly to DB.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            total_inserted = self._fetch_and_load(max_records=max_records)
            content_hash = hashlib.md5(
                json.dumps(total_inserted).encode()
            ).hexdigest()
            clear_checkpoint(self.SOURCE_NAME)

            result: Dict[str, Any] = {
                "status": "success",
                "records": [],
                "record_count": total_inserted,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": total_inserted})
            return result

        except Exception as exc:
            logger.exception("NPI Registry fetch failed: %s", exc)
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

    def _find_latest_url(self) -> Optional[str]:
        """Try recent months to find the latest available NPPES bulk download."""
        import datetime
        today = datetime.date.today()
        # Try current month and up to 4 prior months
        for delta in range(5):
            month_idx = today.month - 1 - delta
            year = today.year + month_idx // 12
            month_idx = month_idx % 12
            month_name = _MONTH_NAMES[month_idx]
            url = f"{_BULK_BASE_URL}/NPPES_Data_Dissemination_{month_name}_{year}.zip"
            try:
                resp = requests.head(url, timeout=15, allow_redirects=True)
                if resp.status_code == 200:
                    logger.info("NPI Registry: found bulk file %s", url)
                    return url
            except Exception:
                continue
        return None

    def _fetch_and_load(self, max_records: Optional[int]) -> int:
        """Download bulk file, parse CSV, and load into DB with checkpointing.

        Returns total records inserted/updated.
        """
        cp = load_checkpoint(self.SOURCE_NAME)
        resume_row = cp.get("rows_processed", 0) if cp else 0
        total_inserted = cp.get("records_inserted", 0) if cp else 0
        bulk_url = cp.get("bulk_url") if cp else None

        if resume_row > 0:
            logger.info(
                "NPI Registry: resuming from checkpoint rows_processed=%d (%d inserted)",
                resume_row, total_inserted,
            )

        if not bulk_url:
            bulk_url = self._find_latest_url()
            if not bulk_url:
                raise RuntimeError(
                    "NPI Registry: no NPPES bulk file found for recent months. "
                    "Check https://download.cms.gov/nppes/NPI_Files.html"
                )

        logger.info("NPI Registry: downloading bulk file %s", bulk_url)
        resp = requests.get(bulk_url, stream=True, timeout=300)
        resp.raise_for_status()

        # Stream into memory-mapped zip without writing to disk
        # (zip requires seekable stream, so buffer in chunks)
        logger.info("NPI Registry: streaming zip download...")
        zip_buffer = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
            zip_buffer.write(chunk)
        zip_buffer.seek(0)
        logger.info("NPI Registry: download complete, parsing zip...")

        with zipfile.ZipFile(zip_buffer) as zf:
            # Find the main NPI data CSV (npidata_pfile_*.csv)
            csv_name = next(
                (n for n in zf.namelist() if n.startswith("npidata_pfile") and n.endswith(".csv")),
                None,
            )
            if not csv_name:
                raise RuntimeError(
                    f"NPI Registry: main CSV not found in zip. Contents: {zf.namelist()}"
                )
            logger.info("NPI Registry: parsing %s", csv_name)

            with zf.open(csv_name) as csv_file:
                reader = csv.DictReader(
                    io.TextIOWrapper(csv_file, encoding="utf-8", errors="replace")
                )
                total_inserted = self._stream_csv(
                    reader,
                    bulk_url=bulk_url,
                    resume_row=resume_row,
                    total_inserted=total_inserted,
                    max_records=max_records,
                )

        logger.info("NPI Registry: complete — %d total inserted/updated", total_inserted)
        return total_inserted

    def _stream_csv(
        self,
        reader: csv.DictReader,
        bulk_url: str,
        resume_row: int,
        total_inserted: int,
        max_records: Optional[int],
    ) -> int:
        """Stream-parse CSV rows and insert to DB in batches."""
        batch: List[Dict[str, Any]] = []
        rows_processed = 0
        rows_since_checkpoint = 0

        for row in reader:
            rows_processed += 1

            # Skip rows already processed before checkpoint
            if rows_processed <= resume_row:
                continue

            # Convert CSV row → JSONB dict, renaming NPI → number
            record: Dict[str, Any] = {}
            for k, v in row.items():
                key = _NPI_KEY if k == _NPI_COLUMN else k
                record[key] = v if v != "" else None
            batch.append(record)

            # Flush batch
            if len(batch) >= _BATCH_SIZE:
                result = load_npi_registry_data(batch)
                total_inserted += result.get("records_inserted", 0)
                batch = []
                rows_since_checkpoint += _BATCH_SIZE

                if rows_since_checkpoint >= _CHECKPOINT_INTERVAL:
                    save_checkpoint(self.SOURCE_NAME, {
                        "bulk_url": bulk_url,
                        "rows_processed": rows_processed,
                        "records_inserted": total_inserted,
                    })
                    logger.info(
                        "NPI Registry: checkpoint rows=%d inserted=%d",
                        rows_processed, total_inserted,
                    )
                    rows_since_checkpoint = 0

            if max_records and total_inserted >= max_records:
                logger.info("NPI Registry: reached max_records=%d", max_records)
                break

        # Flush remaining
        if batch:
            result = load_npi_registry_data(batch)
            total_inserted += result.get("records_inserted", 0)

        logger.info(
            "NPI Registry: CSV parse complete — %d rows processed, %d inserted",
            rows_processed, total_inserted,
        )
        return total_inserted
