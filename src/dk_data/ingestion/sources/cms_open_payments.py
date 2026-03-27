"""CMS Open Payments (Sunshine Act) loader. Loads to hcs_raw.cms_open_payments."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSOpenPaymentsRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    # Recipient identification
    'Covered_Recipient_Type': 'covered_recipient_type',
    'Teaching_Hospital_CCN': 'teaching_hospital_ccn',
    'Teaching_Hospital_ID': 'teaching_hospital_id',
    'Teaching_Hospital_Name': 'teaching_hospital_name',
    'Physician_Profile_ID': 'physician_profile_id',
    'Physician_First_Name': 'physician_first_name',
    'Physician_Middle_Name': 'physician_middle_name',
    'Physician_Last_Name': 'physician_last_name',
    'Physician_Name_Suffix': 'physician_name_suffix',
    'Physician_Primary_Type': 'physician_primary_type',
    'Physician_Specialty': 'physician_specialty',
    # Recipient address
    'Recipient_Primary_Business_Street_Address_Line1': 'recipient_primary_business_street_address_line1',
    'Recipient_City': 'recipient_city',
    'Recipient_State': 'recipient_state',
    'Recipient_Zip_Code': 'recipient_zip_code',
    'Recipient_Country': 'recipient_country',
    # Payer / manufacturer
    'Submitting_Applicable_Manufacturer_or_Applicable_GPO_Name': 'submitting_applicable_manufacturer_or_applicable_gpo_name',
    'Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_ID': 'applicable_manufacturer_or_applicable_gpo_making_payment_id',
    'Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name': 'applicable_manufacturer_or_gpo_name',
    # Payment details
    'Total_Amount_of_Payment_USDollars': 'total_amount_of_payment_usdollars',
    'Date_of_Payment': 'date_of_payment',
    'Number_of_Payments_Included_in_Total_Amount': 'number_of_payments_included_in_total_amount',
    'Form_of_Payment_or_Transfer_of_Value': 'form_of_payment_or_transfer_of_value',
    'Nature_of_Payment_or_Transfer_of_Value': 'nature_of_payment_or_transfer_of_value',
    'City_of_Travel': 'city_of_travel',
    'State_of_Travel': 'state_of_travel',
    'Country_of_Travel': 'country_of_travel',
    # Administrative
    'Physician_Ownership_Indicator': 'physician_ownership_indicator',
    'Third_Party_Payment_Recipient_Indicator': 'third_party_payment_recipient_indicator',
    'Name_of_Third_Party_Entity_Receiving_Payment_or_Transfer_of_Value': 'name_of_third_party_entity_receiving_payment_or_transfer_of_value',
    'Charity_Indicator': 'charity_indicator',
    'Third_Party_Equals_Covered_Recipient_Indicator': 'third_party_equals_covered_recipient_indicator',
    'Contextual_Information': 'contextual_information',
    'Delay_in_Publication_Indicator': 'delay_in_publication_indicator',
    'Record_ID': 'record_id',
    'Dispute_Status_for_Publication': 'dispute_status_for_publication',
    'Related_Product_Indicator': 'related_product_indicator',
    # Program
    'Program_Year': 'program_year',
    'Payment_Publication_Date': 'payment_publication_date',
    # Drug/biological slots (1-5) — exact CMS column names
    # CMS header: "Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_N"
    'Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_1': 'name_of_drug_or_biological_or_device_or_medical_supply_1',
    'Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_2': 'name_of_drug_or_biological_or_device_or_medical_supply_2',
    'Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_3': 'name_of_drug_or_biological_or_device_or_medical_supply_3',
    'Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_4': 'name_of_drug_or_biological_or_device_or_medical_supply_4',
    'Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_5': 'name_of_drug_or_biological_or_device_or_medical_supply_5',
    # Additional product classification slots
    'Covered_or_Noncovered_Indicator_1': 'covered_or_noncovered_indicator_1',
    'Covered_or_Noncovered_Indicator_2': 'covered_or_noncovered_indicator_2',
    'Covered_or_Noncovered_Indicator_3': 'covered_or_noncovered_indicator_3',
    'Covered_or_Noncovered_Indicator_4': 'covered_or_noncovered_indicator_4',
    'Covered_or_Noncovered_Indicator_5': 'covered_or_noncovered_indicator_5',
    'Indicate_Drug_or_Biological_or_Device_or_Medical_Supply_1': 'indicate_drug_or_biological_or_device_or_medical_supply_1',
    'Indicate_Drug_or_Biological_or_Device_or_Medical_Supply_2': 'indicate_drug_or_biological_or_device_or_medical_supply_2',
    'Indicate_Drug_or_Biological_or_Device_or_Medical_Supply_3': 'indicate_drug_or_biological_or_device_or_medical_supply_3',
    'Indicate_Drug_or_Biological_or_Device_or_Medical_Supply_4': 'indicate_drug_or_biological_or_device_or_medical_supply_4',
    'Indicate_Drug_or_Biological_or_Device_or_Medical_Supply_5': 'indicate_drug_or_biological_or_device_or_medical_supply_5',
    'Product_Category_or_Therapeutic_Area_1': 'product_category_or_therapeutic_area_1',
    'Product_Category_or_Therapeutic_Area_2': 'product_category_or_therapeutic_area_2',
    'Product_Category_or_Therapeutic_Area_3': 'product_category_or_therapeutic_area_3',
    'Product_Category_or_Therapeutic_Area_4': 'product_category_or_therapeutic_area_4',
    'Product_Category_or_Therapeutic_Area_5': 'product_category_or_therapeutic_area_5',
    # NDC slots — structural join key to mol_silver.ndc_molecule_bridge
    'Associated_Drug_or_Biological_NDC_1': 'associated_drug_or_biological_ndc_1',
    'Associated_Drug_or_Biological_NDC_2': 'associated_drug_or_biological_ndc_2',
    'Associated_Drug_or_Biological_NDC_3': 'associated_drug_or_biological_ndc_3',
    'Associated_Drug_or_Biological_NDC_4': 'associated_drug_or_biological_ndc_4',
    'Associated_Drug_or_Biological_NDC_5': 'associated_drug_or_biological_ndc_5',
}

TABLE = 'cms_open_payments'
SCHEMA = 'hcs_raw'


def load_cms_open_payments(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Open Payments data from CSV file."""
    logger.info(f"Loading CMS Open Payments from {filepath} (year={source_year})")

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

    df = pd.read_csv(filepath, dtype=str, low_memory=False)
    df = df.rename(columns=COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSOpenPaymentsRecord(
                covered_recipient_type=row.get('covered_recipient_type'),
                physician_profile_id=row.get('physician_profile_id'),
                physician_first_name=row.get('physician_first_name') or None,
                physician_last_name=row.get('physician_last_name') or None,
                physician_specialty=row.get('physician_specialty') or None,
                applicable_manufacturer_or_gpo_name=row.get('applicable_manufacturer_or_gpo_name'),
                total_amount_of_payment_usdollars=row.get('total_amount_of_payment_usdollars') or None,
                date_of_payment=row.get('date_of_payment') or None,
                nature_of_payment_or_transfer_of_value=row.get('nature_of_payment_or_transfer_of_value'),
                recipient_city=row.get('recipient_city') or None,
                recipient_state=row.get('recipient_state'),
                recipient_zip_code=row.get('recipient_zip_code') or None,
                payment_publication_date=row.get('payment_publication_date'),
                record_id=row.get('record_id'),
                program_year=row.get('program_year'),
                # Drug/biological name slots — exact CMS field name is
                # "Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_N"
                name_of_drug_or_biological_or_device_or_medical_supply_1=row.get('name_of_drug_or_biological_or_device_or_medical_supply_1') or None,
                name_of_drug_or_biological_or_device_or_medical_supply_2=row.get('name_of_drug_or_biological_or_device_or_medical_supply_2') or None,
                name_of_drug_or_biological_or_device_or_medical_supply_3=row.get('name_of_drug_or_biological_or_device_or_medical_supply_3') or None,
                name_of_drug_or_biological_or_device_or_medical_supply_4=row.get('name_of_drug_or_biological_or_device_or_medical_supply_4') or None,
                name_of_drug_or_biological_or_device_or_medical_supply_5=row.get('name_of_drug_or_biological_or_device_or_medical_supply_5') or None,
                # NDC slots — structural bridge to mol_silver.ndc_molecule_bridge
                associated_drug_or_biological_ndc_1=row.get('associated_drug_or_biological_ndc_1') or None,
                associated_drug_or_biological_ndc_2=row.get('associated_drug_or_biological_ndc_2') or None,
                associated_drug_or_biological_ndc_3=row.get('associated_drug_or_biological_ndc_3') or None,
                associated_drug_or_biological_ndc_4=row.get('associated_drug_or_biological_ndc_4') or None,
                associated_drug_or_biological_ndc_5=row.get('associated_drug_or_biological_ndc_5') or None,
                _source_year=source_year,
            )
            d = rec.model_dump(by_alias=True)
            d['_source_hash'] = source_hash
            d['_source_file'] = source_file
            d['_loaded_at'] = loaded_at
            records.append(d)
        except (ValidationError, Exception) as e:
            errors.append(f"Row {idx}: {e}")

    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['_source_hash', 'record_id', '_source_year'],
        update_columns=['total_amount_of_payment_usdollars', 'nature_of_payment_or_transfer_of_value', '_loaded_at'],
    )

    logger.info(f"Open Payments load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
