"""Source loader for CMS Hospital General Information (file-based)."""
import csv
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_NAME = 'cms_hospital_info'
TABLE = 'hcs_raw.cms_hospital_info'
API_ENDPOINT = 'cms_hospital_info'


def calculate_file_hash(filepath: str) -> str:
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def load_cms_hospital_info(
    filepath: str,
    batch_size: int = 1000,
) -> Dict[str, Any]:
    """Load CMS Hospital Info CSV into hcs_raw.cms_hospital_info as JSONB.

    Stores raw CSV rows verbatim; column names are discovered dynamically
    from the CSV header rather than being hard-coded.
    """
    source_hash = calculate_file_hash(filepath)
    source_file = Path(filepath).name
    logger.info("Loading CMS Hospital Info from %s (hash=%s)", source_file, source_hash)

    inserted = 0
    failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as fh:
                reader = csv.DictReader(fh)
                for idx, row in enumerate(reader):
                    try:
                        raw_record = dict(row)
                        raw_record['_source_file'] = source_file
                        raw_record['_source_hash'] = source_hash

                        response_body = json.dumps(raw_record, default=str)
                        response_hash = hashlib.sha256(response_body.encode()).hexdigest()
                        request_id = (
                            raw_record.get('Facility ID')
                            or raw_record.get('provider_id')
                            or f'{SOURCE_NAME}_{idx}'
                        )

                        cur.execute("""
                            INSERT INTO hcs_raw.cms_hospital_info (
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

    logger.info("%s load: %d inserted, %d failed", SOURCE_NAME, inserted, failed)
    return {
        'status': 'success' if failed == 0 else 'partial',
        'records_inserted': inserted,
        'records_failed': failed,
        'source_file': source_file,
        'errors': errors[:10],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Load CMS Hospital General Information')
    parser.add_argument('filepath', help='Path to CMS CSV file')
    parser.add_argument('--batch-size', type=int, default=1000)
    args = parser.parse_args()
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    result = load_cms_hospital_info(args.filepath, args.batch_size)
    print(f"Result: {result}")


if __name__ == '__main__':
    main()
