"""TGA Orphan Drug Designations loader.

Target table: mol_raw.tga_orphan_designations (migration 251)
"""

from typing import Any, Dict, List, Optional

from ._tga_common import load_tga_page_blobs

SOURCE_ID = "tga_orphan_designations"
API_ENDPOINT = "https://www.tga.gov.au/resources/orphan-drug-designations"


def load_tga_orphan_designations_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    return load_tga_page_blobs(
        records,
        table="mol_raw.tga_orphan_designations",
        source_id=SOURCE_ID,
        api_endpoint=API_ENDPOINT,
        source_hash=source_hash,
    )
