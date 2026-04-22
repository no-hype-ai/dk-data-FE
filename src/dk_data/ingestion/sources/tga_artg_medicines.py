"""TGA ARTG Medicines loader — prescription + OTC + biologicals + complementary.

Writes to mol_raw.tga_artg_medicines. Each page blob carries a medicine_type
field inside response_body to distinguish the four therapeutic classes;
the bronze model promotes this to a typed column.

Target table: mol_raw.tga_artg_medicines (migration 251)
"""

from typing import Any, Dict, List, Optional

from ._tga_common import load_tga_page_blobs

SOURCE_ID = "tga_artg_medicines"
API_ENDPOINT = "https://www.tga.gov.au/resources/artg/artg-search-visualisation-tool"


def load_tga_artg_medicines_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    return load_tga_page_blobs(
        records,
        table="mol_raw.tga_artg_medicines",
        source_id=SOURCE_ID,
        api_endpoint=API_ENDPOINT,
        source_hash=source_hash,
    )
