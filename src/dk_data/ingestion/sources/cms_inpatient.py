"""Source loader for CMS Medicare Inpatient data (TAVR DRG 266/267 filter)."""
import csv
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_NAME = 'cms_medicare_inpatient'
TABLE = 'hcs_raw.cms_medicare_inpatient'
API_ENDPOINT = 'cms_medicare_inpatient'

# Only ingest TAVR-related DRG codes
TAVR_DRG_CODES = {'266', '267'}


def calculate_file_hash(filepath: str) -> str:
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def load_cms_inpatient_file(
    filepath: str,
    fiscal_year: int,
    batch_size: int = 1000,
) -> Dict[str, Any]:
    """Load CMS Medicare Inpatient CSV into hcs_raw.cms_medicare_inpatient as JSONB.

    Filters to TAVR DRG codes (266/267) and stores raw CSV rows verbatim.
    Column names are discovered dynamically from the CSV header.
    """
    source_hash = calculate_file_hash(filepath)
    source_file = Path(filepath).name
    logger.info(
        "Loading CMS Medicare Inpatient from %s FY%d (hash=%s)",
        source_file, fiscal_year, source_hash,
    )

    inserted = 0
    skipped = 0
    failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as fh:
                reader = csv.DictReader(fh)
                for idx, row in enumerate(reader):
                    try:
                        raw_record = dict(row)

                        # Filter for TAVR DRG codes only
                        drg_code = str(
                            raw_record.get('DRG_Cd')
                            or raw_record.get('drg_code', '')
                        ).strip()
                        if drg_code not in TAVR_DRG_CODES:
                            skipped += 1
                            continue

                        raw_record['fiscal_year'] = fiscal_year
                        raw_record['_source_file'] = source_file
                        raw_record['_source_hash'] = source_hash

                        response_body = json.dumps(raw_record, default=str)
                        response_hash = hashlib.sha256(response_body.encode()).hexdigest()
                        request_id = (
                            raw_record.get('Rndrng_Prvdr_CCN')
                            or raw_record.get('provider_id')
                            or f'{SOURCE_NAME}_{idx}'
                        )

                        cur.execute("""
                            INSERT INTO hcs_raw.cms_medicare_inpatient (
                                request_id, api_endpoint,
                                response_status, response_body, response_body_hash,
                                source_id
                            ) VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (response_body_hash)
                            WHERE response_body_hash IS NOT NULL
                            DO NOTHING
                        """, (
                            str(request_id), API_ENDPOINT,
                            200, response_body, response_hash,
                            SOURCE_NAME,
                        ))
                        inserted += 1

                        if inserted % batch_size == 0:
                            conn.commit()
                    except Exception as e:
                        failed += 1
                        if len(errors) < 10:
                            errors.append({'index': idx, 'error': str(e)[:200]})
                        logger.error("%s record %d failed: %s", SOURCE_NAME, idx, e)

            conn.commit()

    logger.info(
        "%s load: %d inserted, %d skipped (non-TAVR), %d failed",
        SOURCE_NAME, inserted, skipped, failed,
    )
    return {
        'status': 'success' if failed == 0 else 'partial',
        'records_inserted': inserted,
        'records_skipped': skipped,
        'records_failed': failed,
        'source_file': source_file,
        'errors': errors[:10],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Load CMS Medicare Inpatient data')
    parser.add_argument('filepath', help='Path to CMS CSV file')
    parser.add_argument('--fiscal-year', type=int, required=True)
    parser.add_argument('--batch-size', type=int, default=1000)
    args = parser.parse_args()
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    result = load_cms_inpatient_file(args.filepath, args.fiscal_year, args.batch_size)
    print(f"Result: {result}")


if __name__ == '__main__':
    main()
