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
    # Taxonomy codes 1-15 (T026)
    **{f'Healthcare Provider Taxonomy Code_{i}': f'healthcare_provider_taxonomy_code_{i}' for i in range(1, 16)},
    # Primary taxonomy switch 1-15 (T026)
    **{f'Healthcare Provider Primary Taxonomy Switch_{i}': f'healthcare_provider_primary_taxonomy_switch_{i}' for i in range(1, 16)},
    # Provider license numbers 1-15 (T026)
    **{f'Provider License Number_{i}': f'provider_license_number_{i}' for i in range(1, 16)},
    # Provider license number state codes 1-15 (T026)
    **{f'Provider License Number State Code_{i}': f'provider_license_number_state_code_{i}' for i in range(1, 16)},
    # Other provider identifiers 1-50 (T026)
    **{f'Other Provider Identifier_{i}': f'other_provider_identifier_{i}' for i in range(1, 51)},
    **{f'Other Provider Identifier Type Code_{i}': f'other_provider_identifier_type_code_{i}' for i in range(1, 51)},
    **{f'Other Provider Identifier State_{i}': f'other_provider_identifier_state_{i}' for i in range(1, 51)},
    **{f'Other Provider Identifier Issuer_{i}': f'other_provider_identifier_issuer_{i}' for i in range(1, 51)},
    # Authorized official details (T026)
    'Authorized Official Last Name': 'authorized_official_last_name',
    'Authorized Official First Name': 'authorized_official_first_name',
    'Authorized Official Middle Name': 'authorized_official_middle_name',
    'Authorized Official Title or Position': 'authorized_official_title_or_position',
    'Authorized Official Telephone Number': 'authorized_official_telephone_number',
    'Authorized Official Name Prefix Text': 'authorized_official_name_prefix_text',
    'Authorized Official Name Suffix Text': 'authorized_official_name_suffix_text',
    'Authorized Official Credential Text': 'authorized_official_credential_text',
    # Deactivation status (T026)
    'NPI Deactivation Reason Code': 'npi_deactivation_reason_code',
    'NPI Deactivation Date': 'npi_deactivation_date',
    'NPI Reactivation Date': 'npi_reactivation_date',
    # Entity-type-specific (T026)
    'Is Sole Proprietor': 'is_sole_proprietor',
    'Is Organization Subpart': 'is_organization_subpart',
    'Parent Organization LBN': 'parent_organization_lbn',
    'Parent Organization TIN': 'parent_organization_tin',
    # Other (T026)
    'Provider Enumeration Date': 'provider_enumeration_date',
    'Last Update Date': 'last_update_date',
    'Certification Date': 'certification_date',
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

    # Build the set of all target column names from COLUMN_MAPPING values
    _all_target_cols = set(COLUMN_MAPPING.values())

    for idx, row in df.iterrows():
        try:
            # Dynamically build kwargs for all mapped columns present in the row
            kwargs = {}
            for col in _all_target_cols:
                val = row.get(col)
                if val is not None and val != '':
                    kwargs[col] = val
            kwargs['_source_year'] = source_year

            rec = CMSNPPESRecord(**kwargs)
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
