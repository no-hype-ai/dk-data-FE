"""SIDER Side Effect Resource Data Fetcher.

SIDER (Side Effect Resource) contains drug side effect information extracted
from public drug package inserts (drug labels).

Original source: http://sideeffects.embl.de/
Status: EMBL server permanently offline as of 2026 (connection refused).
        denbi.de service page links back to the dead EMBL server.

Data files (TSV, no authentication required when server was live):
  meddra_all_se.tsv — all side effects per drug (4 columns):
    stitch_id_flat | stitch_id_stereo | umls_cui_side_effect | side_effect_name

  meddra_freq.tsv — side effects with frequency information (10 columns):
    stitch_id_flat | stitch_id_stereo | umls_cui_side_effect | placebo |
    frequency | lower_bound_freq | upper_bound_freq | meddra_concept_type |
    umls_cui_from_label | side_effect_name

The fetcher tries the EMBL URLs and any known mirrors.  If all are
unreachable it returns status='source_unavailable' rather than raising,
so the pipeline can continue without this optional source.
"""

import csv
import gzip
import hashlib
import io
import logging
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known URL candidates — EMBL first (original), then mirrors.
# EMBL has been offline since at least early 2026; add mirror URLs below
# when a confirmed working mirror is identified.
# ---------------------------------------------------------------------------
_EMBL_BASE = "http://sideeffects.embl.de/media/files"

# GitHub mirror of SIDER 4.1 — archived by dhimmel/SIDER4 after EMBL went offline.
# This is the last published version of the SIDER dataset (static, no updates).
_GITHUB_MIRROR = "https://raw.githubusercontent.com/dhimmel/SIDER4/master/download"

_FREQ_URLS = [
    f"{_GITHUB_MIRROR}/meddra_freq.tsv.gz",  # GitHub mirror (SIDER 4.1 archive)
    f"{_EMBL_BASE}/meddra_freq.tsv.gz",       # Original EMBL URL (offline since 2026)
]

_ALL_SE_URLS = [
    f"{_GITHUB_MIRROR}/meddra_all_se.tsv.gz",  # GitHub mirror (SIDER 4.1 archive)
    f"{_EMBL_BASE}/meddra_all_se.tsv.gz",       # Original EMBL URL (offline since 2026)
]


class SIDERFetcher(BaseFetcher):
    """Fetcher for SIDER drug side effect data."""

    SOURCE_NAME = "sider"
    BASE_URL = _EMBL_BASE

    # Column definitions matching exact SIDER TSV headers (no header row in file)
    ALL_SE_COLUMNS = [
        "stitch_id_flat",
        "stitch_id_stereo",
        "umls_cui_side_effect",
        "side_effect_name",
    ]

    FREQ_COLUMNS = [
        "stitch_id_flat",
        "stitch_id_stereo",
        "umls_cui_side_effect",
        "placebo",
        "frequency",
        "lower_bound_freq",
        "upper_bound_freq",
        "meddra_concept_type",
        "umls_cui_from_label",
        "side_effect_name",
    ]

    def get_latest_url(self) -> str:
        return _FREQ_URLS[0]

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch SIDER side effect data.

        Keyword Args:
            source: Which file(s) to load: 'both' (default), 'freq', or 'all_se'.

        Returns:
            Dict with keys: status, records, hash, error (on failure).
            status='source_unavailable' when the SIDER server cannot be reached.
        """
        source = kwargs.get("source", "both")

        try:
            records: List[Dict[str, Any]] = []

            if source in ("freq", "both"):
                freq_records = self._fetch_file_with_fallback(
                    _FREQ_URLS,
                    self.FREQ_COLUMNS,
                    source_file="meddra_freq.tsv",
                )
                records.extend(freq_records)

            if source in ("all_se", "both"):
                all_se_records = self._fetch_file_with_fallback(
                    _ALL_SE_URLS,
                    self.ALL_SE_COLUMNS,
                    source_file="meddra_all_se.tsv",
                )
                records.extend(all_se_records)

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

        except _SourceUnavailableError as e:
            msg = (
                f"SIDER source unavailable: {e}. "
                "The EMBL server (sideeffects.embl.de) has been offline since 2026. "
                "Add a working mirror URL to _FREQ_URLS / _ALL_SE_URLS in sider.py."
            )
            logger.warning(msg)
            result = {"status": "source_unavailable", "records": [], "hash": None, "error": msg}
            self.log_fetch_result(result)
            return result

        except Exception as e:
            logger.exception(f"SIDER fetch failed: {e}")
            result = {"status": "failed", "records": [], "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _fetch_file_with_fallback(
        self,
        urls: List[str],
        columns: List[str],
        source_file: str,
    ) -> List[Dict[str, Any]]:
        """Try each URL in order; raise _SourceUnavailableError if all fail."""
        last_error: Exception | None = None

        for url in urls:
            try:
                return self._fetch_file(url, columns, source_file)
            except (ConnectionError, OSError) as exc:
                logger.debug(f"SIDER connection error for {url}: {exc}")
                last_error = exc
                continue
            except Exception as exc:
                logger.debug(f"SIDER fetch error for {url}: {exc}")
                last_error = exc
                continue

        raise _SourceUnavailableError(
            f"All SIDER URLs failed for {source_file}. "
            f"Last error: {last_error}. Tried: {urls}"
        )

    def _fetch_file(
        self,
        url: str,
        columns: List[str],
        source_file: str,
    ) -> List[Dict[str, Any]]:
        """Download and parse one SIDER TSV.gz file (no row cap)."""
        logger.info(f"Downloading SIDER file: {url}")
        response = self.session.get(url, stream=True, timeout=300)
        response.raise_for_status()

        raw_bytes = response.content
        logger.info(f"Downloaded {len(raw_bytes) / 1024 / 1024:.1f} MB")

        records: List[Dict[str, Any]] = []

        with gzip.open(io.BytesIO(raw_bytes), "rt", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter="\t")

            for row in reader:
                # SIDER TSV files have no header row — use positional columns
                if len(row) < len(columns):
                    continue

                record: Dict[str, Any] = {}
                for col, val in zip(columns, row):
                    stripped = val.strip()
                    record[col] = stripped if stripped else None

                if not record.get("stitch_id_flat"):
                    continue

                record["source_file"] = source_file
                records.append(record)

        logger.info(f"Parsed {len(records):,} records from {source_file}")
        return records


class _SourceUnavailableError(RuntimeError):
    """Raised when all known URLs for a SIDER file are unreachable."""
