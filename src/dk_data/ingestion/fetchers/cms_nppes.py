"""CMS NPPES NPI Registry fetcher — weekly incremental file.

The full monthly dissemination is ~1 GB. The weekly incremental files are
6-8 MB each and contain new/updated NPI records since the previous week.

Weekly files are published at download.cms.gov/nppes/ with date-range filenames.
This fetcher automatically finds the most recent weekly file by scanning the
NPI_Files.html page.

Full monthly baseline (if needed):
  https://download.cms.gov/nppes/NPPES_Data_Dissemination_March_2026_V2.zip (1 GB)
"""
import logging
import os
import re
import tempfile
import zipfile
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_NPI_FILES_PAGE = "https://download.cms.gov/nppes/NPI_Files.html"
_WEEKLY_PATTERN = re.compile(r'NPPES_Data_Dissemination_\d{6}_\d{6}_Weekly_V\d+\.zip', re.IGNORECASE)
_MONTHLY_PATTERN = re.compile(r'NPPES_Data_Dissemination_\w+_\d{4}_V\d+\.zip', re.IGNORECASE)


class CMSNPPESFetcher(BaseFetcher):
    SOURCE_NAME = "cms_nppes"
    BASE_URL = _NPI_FILES_PAGE

    def get_latest_url(self) -> str:
        return self._find_latest_weekly_url() or _NPI_FILES_PAGE

    def _find_latest_weekly_url(self) -> Optional[str]:
        """Parse the NPI files page to find the most recent weekly incremental ZIP."""
        try:
            resp = self.session.get(_NPI_FILES_PAGE, timeout=30)
            resp.raise_for_status()
            matches = _WEEKLY_PATTERN.findall(resp.text)
            if not matches:
                # Fall back to monthly if no weekly files
                matches = _MONTHLY_PATTERN.findall(resp.text)
            if matches:
                # Last match is typically the most recent
                return f"https://download.cms.gov/nppes/{matches[-1]}"
        except Exception as e:
            logger.warning("[%s] Could not find latest URL: %s", self.SOURCE_NAME, e)
        return None

    def fetch(self, **kwargs) -> Dict[str, Any]:
        try:
            url = self._find_latest_weekly_url()
            if not url:
                return {"status": "source_unavailable", "error": "Could not find NPPES weekly file", "records": [], "record_count": 0, "hash": None}

            fname = url.split("/")[-1]
            logger.info("[%s] Downloading %s", self.SOURCE_NAME, fname)
            zip_path = self.download_file(url, fname)

            csv_files: List[str] = []
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for name in zf.namelist():
                    if name.lower().endswith('.csv') and 'npidata' in name.lower():
                        extract_dir = tempfile.mkdtemp(prefix="cms_nppes_")
                        zf.extract(name, extract_dir)
                        csv_files.append(os.path.join(extract_dir, name))

            if not csv_files:
                logger.warning("[%s] No NPI CSV files found in ZIP", self.SOURCE_NAME)
                return {"status": "success", "records": 0, "record_count": 0, "hash": None, "extracted_files": []}

            return {
                "status": "success",
                "records": len(csv_files),
                "record_count": 0,
                "hash": self.calculate_hash(zip_path),
                "extracted_files": csv_files,
            }
        except Exception as e:
            logger.exception("%s fetch failed: %s", self.SOURCE_NAME, e)
            return {"status": "failed", "error": str(e), "records": [], "record_count": 0, "hash": None}
