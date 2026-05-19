"""BindingDB Data Fetcher.

BindingDB provides drug-target binding affinity measurements.
Data is distributed as tab-separated value (TSV) files.

Source: https://www.bindingdb.org/rwd/bind/chemsearch/marvin/Download.jsp
Download: BindingDB_All_{YYYYMM}_tsv.zip — date-stamped monthly archive

URL pattern (as of 2026-03):
  https://www.bindingdb.org/rwd/bind/downloads/BindingDB_All_{YYYYMM}_tsv.zip

The fetcher tries the current month and falls back up to 3 prior months to
handle the window between a new release and the previous one aging out.

The fetcher downloads and parses the TSV, yielding one dict per row
with keys matching the TSV column headers verbatim (e.g., "Ki (nM)").
This preserves exact field names so the bronze SQL model can reference
them correctly in response_body JSONB.
"""

import csv
import hashlib
import io
import logging
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class BindingDBFetcher(BaseFetcher):
    """Fetcher for BindingDB binding affinity data."""

    SOURCE_NAME = "bindingdb"
    BASE_URL = "https://www.bindingdb.org/rwd/bind/chemsearch/marvin/Download.jsp"

    # URL pattern for the monthly full-dataset archive.
    # BindingDB switched from a static URL to date-stamped monthly releases.
    _DOWNLOAD_URL_PATTERN = (
        "https://www.bindingdb.org/rwd/bind/downloads/BindingDB_All_{yyyymm}_tsv.zip"
    )

    # Key columns to include in the JSONB record.
    # These are the exact TSV header names BindingDB uses.
    REQUIRED_COLUMNS = {
        "BindingDB Reactant_set_id",
        "Ligand InChIKey",
        "Ligand SMILES",
        "PubChem CID",
        "ChEMBL ID of Ligand",
        "Target Name Assigned by Curator or DataSource",
        "Target Source Organism According to Curator or DataSource",
        "UniProt (SwissProt) Primary ID of Target Chain",
        "Ki (nM)",
        "IC50 (nM)",
        "Kd (nM)",
        "EC50 (nM)",
        "kon (M-1-s-1)",
        "koff (s-1)",
        "pH",
        "Temp (C)",
        "Curation/DataSource",
        "Article DOI",
        "PMID",
        "PDB ID(s) for Ligand-Target Complex",
    }

    @classmethod
    def _candidate_urls(cls) -> List[str]:
        """Return download URL candidates from most-recent to 3 months back.

        BindingDB publishes a new archive monthly.  We try the current month
        first and fall back up to 3 prior months so we don't depend on the
        exact release date.
        """
        now = datetime.now(timezone.utc)
        candidates = []
        for months_back in range(4):
            # Step back ~one month at a time (28-day offset)
            target = now - timedelta(days=28 * months_back)
            yyyymm = target.strftime("%Y%m")
            candidates.append(cls._DOWNLOAD_URL_PATTERN.format(yyyymm=yyyymm))
        # Deduplicate while preserving order (two offsets could land in same month)
        seen = set()
        deduped = []
        for url in candidates:
            if url not in seen:
                seen.add(url)
                deduped.append(url)
        return deduped

    def get_latest_url(self) -> str:
        return self._candidate_urls()[0]

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch BindingDB binding affinity data.

        Keyword Args:
            require_affinity: If True, skip rows with no Ki/IC50/Kd/EC50 value.
            max_records: Stop parsing after this many records (default: all).
            loader_fn: If provided, stream records to this callable in chunks
                instead of accumulating them all in memory. The callable must
                accept (records: List[Dict], source_hash: Optional[str]) and
                return a dict with records_inserted/records_skipped keys.
            chunk_size: Records per chunk when loader_fn is given (default 50000).

        Returns:
            Dict with keys: status, records (or records_inserted), hash, error.
        """
        require_affinity = kwargs.get("require_affinity", True)
        max_records: Optional[int] = kwargs.get("max_records")
        loader_fn = kwargs.get("loader_fn")
        chunk_size: int = int(kwargs.get("chunk_size", 50_000))

        if loader_fn is not None:
            return self._fetch_streaming(
                require_affinity=require_affinity,
                max_records=max_records,
                loader_fn=loader_fn,
                chunk_size=chunk_size,
            )

        try:
            records = self._download_and_parse(require_affinity, max_records=max_records)

            content_hash = hashlib.md5(
                str(len(records)).encode()
            ).hexdigest() if records else None

            result = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result({**result, "records": len(records)})
            return result

        except Exception as e:
            logger.exception(f"BindingDB fetch failed: {e}")
            result = {"status": "failed", "records": [], "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _fetch_streaming(
        self,
        require_affinity: bool,
        max_records: Optional[int],
        loader_fn,
        chunk_size: int,
    ) -> Dict[str, Any]:
        """Stream records from the TSV to loader_fn in chunks of chunk_size.

        Keeps memory usage to ~chunk_size records at a time regardless of
        total dataset size.
        """
        total_inserted = 0
        total_skipped = 0
        total_parsed = 0
        errors: List[Dict[str, Any]] = []
        content_hash = hashlib.md5(b"bindingdb-streaming").hexdigest()

        try:
            candidates = self._candidate_urls()
            last_error: Optional[Exception] = None

            for url in candidates:
                logger.info(f"Trying BindingDB URL (streaming): {url}")
                try:
                    buf = self._download_to_buffer(url)
                    if buf is None:
                        continue

                    for chunk in self._iter_chunks(buf, require_affinity, max_records, chunk_size):
                        total_parsed += len(chunk)
                        r = loader_fn(chunk, source_hash=content_hash)
                        total_inserted += r.get("records_inserted", 0)
                        total_skipped += r.get("records_skipped", 0)
                        errors.extend(r.get("errors", []))
                        logger.info(
                            "BindingDB streaming progress: %d parsed, %d inserted",
                            total_parsed, total_inserted,
                        )
                        if max_records and total_parsed >= max_records:
                            break
                    break  # success — stop trying candidate URLs

                except Exception as exc:
                    last_error = exc
                    logger.warning(f"BindingDB streaming failed for {url}: {exc}")
                    continue
            else:
                raise RuntimeError(
                    f"BindingDB: all candidate URLs failed. Last: {last_error}"
                )

        except Exception as e:
            logger.exception(f"BindingDB streaming fetch failed: {e}")
            result = {
                "status": "failed",
                "records": [],
                "records_inserted": total_inserted,
                "records_skipped": total_skipped,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

        result = {
            "status": "success" if not errors else "partial",
            "records": [],
            "records_inserted": total_inserted,
            "records_skipped": total_skipped,
            "record_count": total_parsed,
            "hash": content_hash,
        }
        self.log_fetch_result({**result, "records": total_parsed})
        return result

    def _download_to_buffer(self, url: str) -> Optional[io.BytesIO]:
        """Download a single URL into an in-memory buffer. Returns None on 404."""
        buf = io.BytesIO()
        downloaded = 0
        with self.session.get(url, stream=True, timeout=600) as response:
            if response.status_code == 404:
                logger.debug(f"BindingDB 404 at {url}, trying next candidate")
                return None
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                buf.write(chunk)
                downloaded += len(chunk)
                if downloaded % (100 * 1024 * 1024) == 0:
                    logger.info(
                        f"BindingDB download progress: {downloaded / 1024 / 1024:.0f} MB"
                    )
        logger.info(f"Downloaded {downloaded / 1024 / 1024:.1f} MB from {url}")
        buf.seek(0)
        return buf

    def _download_and_parse(
        self, require_affinity: bool, max_records: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Try candidate monthly URLs, download the zip, and parse all rows."""
        candidates = self._candidate_urls()
        last_error: Optional[Exception] = None

        for url in candidates:
            logger.info(f"Trying BindingDB URL: {url}")
            try:
                buf = self._download_to_buffer(url)
                if buf is None:
                    continue
                return self._parse_zip(buf, require_affinity, max_records=max_records)
            except Exception as exc:
                last_error = exc
                logger.warning(f"BindingDB download failed for {url}: {exc}")
                continue

        raise RuntimeError(
            f"BindingDB: all candidate URLs failed. Last error: {last_error}. "
            f"Tried: {candidates}"
        )

    def _iter_chunks(
        self,
        buf: io.BytesIO,
        require_affinity: bool,
        max_records: Optional[int],
        chunk_size: int,
    ):
        """Yield successive chunk_size-record batches from the zip buffer.

        Reads the TSV row by row so only one chunk is in memory at a time.
        """
        affinity_cols = {"Ki (nM)", "IC50 (nM)", "Kd (nM)", "EC50 (nM)"}
        total = 0
        chunk: List[Dict[str, Any]] = []

        with zipfile.ZipFile(buf) as zf:
            tsv_names = [n for n in zf.namelist() if n.endswith(".tsv")]
            if not tsv_names:
                raise ValueError("No TSV file found in BindingDB zip archive")

            tsv_name = tsv_names[0]
            logger.info(f"Streaming {tsv_name} in chunks of {chunk_size}")

            with zf.open(tsv_name) as tsv_bytes:
                text = io.TextIOWrapper(tsv_bytes, encoding="utf-8", errors="replace")
                reader = csv.DictReader(text, delimiter="\t")

                for row in reader:
                    if max_records is not None and total >= max_records:
                        break

                    reactant_id = row.get("BindingDB Reactant_set_id", "").strip()
                    if not reactant_id:
                        continue

                    if require_affinity:
                        has_affinity = any(
                            row.get(col, "").strip() not in ("", "N/A", "NA", "None")
                            for col in affinity_cols
                        )
                        if not has_affinity:
                            continue

                    record: Dict[str, Any] = {}
                    for col in self.REQUIRED_COLUMNS:
                        val = row.get(col, "").strip()
                        record[col] = val if val not in ("", "N/A", "NA", "None") else None

                    chunk.append(record)
                    total += 1

                    if len(chunk) >= chunk_size:
                        yield chunk
                        chunk = []

        if chunk:
            yield chunk

    def _parse_zip(
        self,
        buf: io.BytesIO,
        require_affinity: bool,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Parse a BindingDB TSV zip from an in-memory buffer.

        Args:
            buf: In-memory zip buffer.
            require_affinity: Skip rows with no affinity measurement.
            max_records: Stop after this many records (None = parse all).
        """
        records: List[Dict[str, Any]] = []
        affinity_cols = {"Ki (nM)", "IC50 (nM)", "Kd (nM)", "EC50 (nM)"}

        with zipfile.ZipFile(buf) as zf:
            tsv_names = [n for n in zf.namelist() if n.endswith(".tsv")]
            if not tsv_names:
                raise ValueError("No TSV file found in BindingDB zip archive")

            tsv_name = tsv_names[0]
            logger.info(f"Parsing {tsv_name} (max_records={max_records})")

            with zf.open(tsv_name) as tsv_bytes:
                text = io.TextIOWrapper(tsv_bytes, encoding="utf-8", errors="replace")
                reader = csv.DictReader(text, delimiter="\t")

                for row in reader:
                    if max_records is not None and len(records) >= max_records:
                        logger.info(f"BindingDB: reached max_records={max_records}, stopping")
                        break

                    reactant_id = row.get("BindingDB Reactant_set_id", "").strip()
                    if not reactant_id:
                        continue

                    if require_affinity:
                        has_affinity = any(
                            row.get(col, "").strip() not in ("", "N/A", "NA", "None")
                            for col in affinity_cols
                        )
                        if not has_affinity:
                            continue

                    record: Dict[str, Any] = {}
                    for col in self.REQUIRED_COLUMNS:
                        val = row.get(col, "").strip()
                        record[col] = val if val not in ("", "N/A", "NA", "None") else None

                    records.append(record)

                    if len(records) % 100_000 == 0:
                        logger.info(f"BindingDB parse progress: {len(records):,} records")

        logger.info(f"Parsed {len(records):,} BindingDB records")
        return records
