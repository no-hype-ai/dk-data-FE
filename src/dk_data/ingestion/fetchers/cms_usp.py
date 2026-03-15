"""CMS USP (United States Pharmacopeia) Drug Classification Fetcher.

Parses the USP Medicare Model Guidelines v9.0 Alignment File (Excel)
to extract RxCUI-to-USP Category/Class mappings. The alignment file
is bundled as a seed file since it requires one-time registration at
https://go.usp.org/MMG_v9.0 and updates only tri-annually.

Source: https://www.usp.org/health-quality-safety/usp-medicare-model-guidelines
"""

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Default data file location — mirrors DrugBank pattern:
# repo: data/usp/ → Docker: /app/data/usp/ (COPY in Dockerfile)
_DATA_DIR = Path(__file__).resolve().parents[4] / "data" / "usp"
# In-container path (Dockerfile copies to /app/data/usp/)
_CONTAINER_DIR = Path("/app/data/usp")
DEFAULT_ALIGNMENT_FILE = (
    _CONTAINER_DIR / "usp_mmg_v9_alignment.xlsx"
    if _CONTAINER_DIR.exists()
    else _DATA_DIR / "usp_mmg_v9_alignment.xlsx"
)


class CMSUSPFetcher(BaseFetcher):
    """Fetcher for USP Drug Classification data from the MMG Alignment File."""

    SOURCE_NAME = "cms_usp"
    BASE_URL = "https://www.usp.org/health-quality-safety/usp-medicare-model-guidelines"

    def get_latest_url(self) -> str:
        """Return the seed file path."""
        return str(self._get_alignment_path())

    def _get_alignment_path(self) -> Path:
        """Resolve the alignment file path from params or default."""
        custom = self.params.get("alignment_file")
        if custom:
            return Path(custom)
        return DEFAULT_ALIGNMENT_FILE

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Parse USP alignment file and return RxCUI-to-category/class records.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            filepath = self._get_alignment_path()

            if not filepath.exists():
                raise FileNotFoundError(
                    f"USP alignment file not found at {filepath}. "
                    "Download from https://go.usp.org/MMG_v9.0 and place in "
                    f"{_DATA_DIR}/usp_mmg_v9_alignment.xlsx"
                )

            logger.info("Parsing USP alignment file: %s", filepath)

            records = self._parse_alignment(filepath, max_records=max_records)

            content_hash = hashlib.md5(filepath.read_bytes()[:8192]).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("USP fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    @staticmethod
    def _parse_alignment(
        filepath: Path, max_records: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Parse the MMG v9.0 Alignment File Excel sheet."""
        import openpyxl

        wb = openpyxl.load_workbook(filepath, read_only=True)
        ws = wb.active
        records: List[Dict[str, Any]] = []

        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if header is None:
            wb.close()
            return records

        # Map header to indices
        col_map = {str(h).strip().lower(): i for i, h in enumerate(header) if h}

        rxcui_idx = col_map.get("rxcui", col_map.get("rxcui", 0))
        tty_idx = col_map.get("tty", 1)
        name_idx = col_map.get("branded name", 2)
        bn_idx = col_map.get("related bn", 3)
        df_idx = col_map.get("related df", 4)
        cat_idx = col_map.get("category", 5)
        cls_idx = col_map.get("class", 6)

        for row in rows:
            rxcui = row[rxcui_idx] if rxcui_idx < len(row) else None
            category = row[cat_idx] if cat_idx < len(row) else None
            usp_class = row[cls_idx] if cls_idx < len(row) else None

            if not rxcui or not category or not usp_class:
                continue

            records.append({
                "rxcui": str(rxcui).strip(),
                "tty": str(row[tty_idx]).strip() if tty_idx < len(row) and row[tty_idx] else None,
                "branded_name": str(row[name_idx]).strip() if name_idx < len(row) and row[name_idx] else None,
                "related_bn": str(row[bn_idx]).strip() if bn_idx < len(row) and row[bn_idx] else None,
                "related_df": str(row[df_idx]).strip() if df_idx < len(row) and row[df_idx] else None,
                "usp_category": str(category).strip(),
                "usp_class": str(usp_class).strip(),
            })

            if max_records and len(records) >= max_records:
                break

        wb.close()
        logger.info("Parsed %d USP alignment records from %s", len(records), filepath.name)
        return records
