"""TGA ARTG Medical Devices loader — dev_ domain (12th hub).

Target table: dev_raw.tga_artg_devices (migration 251)
"""

from typing import Any, Dict, List, Optional

from ._tga_common import load_tga_page_blobs

SOURCE_ID = "tga_artg_devices"
API_ENDPOINT = "https://www.tga.gov.au/resources/artg/artg-search-visualisation-tool"


def load_tga_artg_devices_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    return load_tga_page_blobs(
        records,
        table="dev_raw.tga_artg_devices",
        source_id=SOURCE_ID,
        api_endpoint=API_ENDPOINT,
        source_hash=source_hash,
    )
