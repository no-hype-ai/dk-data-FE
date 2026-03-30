"""CMS NPPES National Provider Identifier loader. Loads to hcs_raw.cms_nppes."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSNPPESRecord

logger = logging.getLogger(__name__)

# NPPES files use exact column names in the header; map to our snake_case
COLUMN_MAPPING = {
    'NPI': 'npi',
    'Entity Type Code': 'entity_type_code',
    'Replacement NPI': 'replacement_npi',
    'Employer Identification Number (EIN)': 'employer_identification_number',
    # Individual provider names
    'Provider Last Name (Legal Name)': 'provider_last_name',
    'Provider First Name': 'provider_first_name',
    'Provider Middle Name': 'provider_middle_name',
    'Provider Name Prefix Text': 'provider_name_prefix_text',
    'Provider Name Suffix Text': 'provider_name_suffix_text',
    'Provider Credential Text': 'provider_credential_text',
    # Organization name
    'Provider Organization Name (Legal Business Name)': 'provider_organization_name',
    # Mailing address fields (used by idn_hierarchy agent)
    'Provider First Line Business Mailing Address': 'provider_first_line_business_mailing_address',
    'Provider Second Line Business Mailing Address': 'provider_second_line_business_mailing_address',
    'Provider Business Mailing Address City Name': 'provider_business_mailing_address_city_name',
    'Provider Business Mailing Address State Name': 'provider_business_mailing_address_state_name',
    'Provider Business Mailing Address Postal Code': 'provider_business_mailing_address_postal_code',
    'Provider Business Mailing Address Country Code (If outside U.S.)': 'provider_business_mailing_address_country_code',
    'Provider Business Mailing Address Telephone Number': 'provider_business_mailing_address_telephone_number',
    'Provider Business Mailing Address Fax Number': 'provider_business_mailing_address_fax_number',
    # Practice location fields (used by contact_verification agent)
    'Provider First Line Business Practice Location Address': 'provider_first_line_business_practice_location_address',
    'Provider Second Line Business Practice Location Address': 'provider_second_line_business_practice_location_address',
    'Provider Business Practice Location Address City Name': 'provider_business_practice_location_address_city_name',
    'Provider Business Practice Location Address State Name': 'provider_business_practice_location_address_state_name',
    'Provider Business Practice Location Address Postal Code': 'provider_business_practice_location_address_postal_code',
    'Provider Business Practice Location Address Country Code (If outside U.S.)': 'provider_business_practice_location_address_country_code',
    'Provider Business Practice Location Address Telephone Number': 'provider_business_practice_location_address_telephone_number',
    'Provider Business Practice Location Address Fax Number': 'provider_business_practice_location_address_fax_number',
    # Taxonomy codes 1-15
    'Healthcare Provider Taxonomy Code_1': 'healthcare_provider_taxonomy_code_1',
    'Healthcare Provider Taxonomy Code_2': 'healthcare_provider_taxonomy_code_2',
    'Healthcare Provider Taxonomy Code_3': 'healthcare_provider_taxonomy_code_3',
    'Healthcare Provider Taxonomy Code_4': 'healthcare_provider_taxonomy_code_4',
    'Healthcare Provider Taxonomy Code_5': 'healthcare_provider_taxonomy_code_5',
    'Healthcare Provider Taxonomy Code_6': 'healthcare_provider_taxonomy_code_6',
    'Healthcare Provider Taxonomy Code_7': 'healthcare_provider_taxonomy_code_7',
    'Healthcare Provider Taxonomy Code_8': 'healthcare_provider_taxonomy_code_8',
    'Healthcare Provider Taxonomy Code_9': 'healthcare_provider_taxonomy_code_9',
    'Healthcare Provider Taxonomy Code_10': 'healthcare_provider_taxonomy_code_10',
    'Healthcare Provider Taxonomy Code_11': 'healthcare_provider_taxonomy_code_11',
    'Healthcare Provider Taxonomy Code_12': 'healthcare_provider_taxonomy_code_12',
    'Healthcare Provider Taxonomy Code_13': 'healthcare_provider_taxonomy_code_13',
    'Healthcare Provider Taxonomy Code_14': 'healthcare_provider_taxonomy_code_14',
    'Healthcare Provider Taxonomy Code_15': 'healthcare_provider_taxonomy_code_15',
    # Deactivation status
    'NPI Deactivation Date': 'npi_deactivation_date',
    'NPI Reactivation Date': 'npi_reactivation_date',
}

TABLE = 'cms_nppes'
SCHEMA = 'hcs_raw'


def load_cms_nppes(filepath: str, source_year: int = 2023, max_records: int = 0) -> dict:
    """Load CMS NPPES registry data from CSV file."""
    logger.info(f"Loading CMS NPPES from {filepath} (year={source_year})")

    source_file = Path(filepath).name
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    source_hash = hash_md5.hexdigest()

    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE _source_hash = %s",
            (source_hash,)
        )
        if cur.fetchone()[0] > 0:
            logger.info(f"File {source_file} already loaded. Skipping.")
            return {"status": "skipped", "records_fetched": 0, "records_inserted": 0, "records_updated": 0, "errors": []}

    df = pd.read_csv(filepath, dtype=str, low_memory=False, nrows=max_records if max_records > 0 else None)
    df = apply_column_mapping(df, COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSNPPESRecord(
                npi=row.get('npi'),
                entity_type_code=row.get('entity_type_code'),
                provider_last_name=row.get('provider_last_name'),
                provider_first_name=row.get('provider_first_name'),
                provider_organization_name=row.get('provider_organization_name'),
                provider_credential_text=row.get('provider_credential_text'),
                # Mailing address fields
                provider_first_line_business_mailing_address=row.get(
                    'provider_first_line_business_mailing_address'
                ),
                provider_second_line_business_mailing_address=row.get(
                    'provider_second_line_business_mailing_address'
                ),
                provider_business_mailing_address_city_name=row.get(
                    'provider_business_mailing_address_city_name'
                ),
                provider_business_mailing_address_state_name=row.get(
                    'provider_business_mailing_address_state_name'
                ),
                provider_business_mailing_address_postal_code=row.get(
                    'provider_business_mailing_address_postal_code'
                ),
                provider_business_mailing_address_telephone_number=row.get(
                    'provider_business_mailing_address_telephone_number'
                ),
                # Practice location fields
                provider_business_practice_location_address_state_name=row.get(
                    'provider_business_practice_location_address_state_name'
                ),
                provider_business_practice_location_address_telephone_number=row.get(
                    'provider_business_practice_location_address_telephone_number'
                ),
                provider_business_practice_location_address_fax_number=row.get(
                    'provider_business_practice_location_address_fax_number'
                ),
                provider_first_line_business_practice_location_address=row.get(
                    'provider_first_line_business_practice_location_address'
                ),
                provider_second_line_business_practice_location_address=row.get(
                    'provider_second_line_business_practice_location_address'
                ),
                provider_business_practice_location_address_city_name=row.get(
                    'provider_business_practice_location_address_city_name'
                ),
                provider_business_practice_location_address_postal_code=row.get(
                    'provider_business_practice_location_address_postal_code'
                ),
                provider_business_practice_location_address_country_code=row.get(
                    'provider_business_practice_location_address_country_code'
                ),
                # Taxonomy codes
                healthcare_provider_taxonomy_code_1=row.get('healthcare_provider_taxonomy_code_1'),
                healthcare_provider_taxonomy_code_2=row.get('healthcare_provider_taxonomy_code_2'),
                # Deactivation status
                npi_deactivation_date=row.get('npi_deactivation_date') or None,
                npi_reactivation_date=row.get('npi_reactivation_date') or None,
                _source_year=source_year,
            )
            d = rec.model_dump(by_alias=True)
            d['_source_hash'] = source_hash
            d['_source_file'] = source_file
            d['_loaded_at'] = loaded_at
            d['_source_year'] = source_year
            records.append(d)
        except (ValidationError, Exception) as e:
            errors.append(f"Row {idx}: {e}")

    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['npi', '_source_year'],
        update_columns=['entity_type_code', 'provider_last_name', 'provider_first_name',
                        'provider_organization_name', '_loaded_at'],
    )

    logger.info(f"NPPES load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
