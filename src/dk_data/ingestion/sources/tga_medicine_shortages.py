"""TGA Medicine Shortages loader — Medicine Shortages Information portal (MSI).

Target table: mol_raw.tga_medicine_shortages (migration 251)
"""

from typing import Any, Dict, List, Optional

from ._tga_common import load_tga_page_blobs

SOURCE_ID = "tga_medicine_shortages"
API_ENDPOINT = "https://apps.tga.gov.au/prod/MSI/search"


def load_tga_medicine_shortages_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    return load_tga_page_blobs(
        records,
        table="mol_raw.tga_medicine_shortages",
        source_id=SOURCE_ID,
        api_endpoint=API_ENDPOINT,
        source_hash=source_hash,
    )
