"""TGA SARA Recalls loader — System for Australian Recall Actions.

Covers both medicine and device recalls. Each record carries regulatory_type
which silver layer uses to split into mol_silver.tga_medicine_recalls vs
dev_silver.tga_device_recalls.

Target table: mol_raw.tga_sara_recalls (migration 251)
"""

from typing import Any, Dict, List, Optional

from ._tga_common import load_tga_page_blobs

SOURCE_ID = "tga_sara_recalls"
API_ENDPOINT = "https://apps.tga.gov.au/prod/sara/"


def load_tga_sara_recalls_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    return load_tga_page_blobs(
        records,
        table="mol_raw.tga_sara_recalls",
        source_id=SOURCE_ID,
        api_endpoint=API_ENDPOINT,
        source_hash=source_hash,
    )
