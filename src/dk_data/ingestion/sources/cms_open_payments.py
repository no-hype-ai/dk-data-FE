"""CMS Open Payments (Sunshine Act) loader. Loads to hcs_raw.cms_open_payments."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSOpenPaymentsRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    # Recipient identification
    # Legacy file-based (Title_Case) AND API (snake_case) column names both supported.
    # The API (openpaymentsdata.cms.gov) uses covered_recipient_* prefix instead of Physician_*.
    'Covered_Recipient_Type': 'covered_recipient_type',
    'Teaching_Hospital_CCN': 'teaching_hospital_ccn',
    'Teaching_Hospital_ID': 'teaching_hospital_id',
    'Teaching_Hospital_Name': 'teaching_hospital_name',
    # Legacy CSV names — physician identity
    'Physician_Profile_ID': 'physician_profile_id',
    'Physician_First_Name': 'physician_first_name',
    'Physician_Middle_Name': 'physician_middle_name',
    'Physician_Last_Name': 'physician_last_name',
    'Physician_Name_Suffix': 'physician_name_suffix',
    'Physician_Primary_Type': 'physician_primary_type',
    'Physician_Specialty': 'physician_specialty',
    'Physician_NPI': 'physician_npi',
    'Physician_Specialty_2': 'physician_specialty_2',
    # API-specific names (openpaymentsdata.cms.gov DKAN format)
    'covered_recipient_profile_id': 'physician_profile_id',
    'covered_recipient_first_name': 'physician_first_name',
    'covered_recipient_middle_name': 'physician_middle_name',
    'covered_recipient_last_name': 'physician_last_name',
    'covered_recipient_name_suffix': 'physician_name_suffix',
    'covered_recipient_primary_type_1': 'physician_primary_type',
    'covered_recipient_specialty_1': 'physician_specialty',
    'covered_recipient_npi': 'physician_npi',
    'covered_recipient_specialty_2': 'physician_specialty_2',
    # Recipient address
    'Recipient_Primary_Business_Street_Address_Line1': 'recipient_primary_business_street_address_line_1',
    'Recipient_Primary_Business_Street_Address_Line2': 'recipient_primary_business_street_address_line_2',
    'Recipient_City': 'recipient_city',
    'Recipient_State': 'recipient_state',
    'Recipient_Zip_Code': 'recipient_zip_code',
    'Recipient_Country': 'recipient_country',
    'Recipient_Postal_Code': 'recipient_postal_code',
    'Recipient_Province': 'recipient_province',
    # Payer / manufacturer
    'Submitting_Applicable_Manufacturer_or_Applicable_GPO_Name': 'submitting_applicable_manufacturer_or_applicable_gpo_name',
    'Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_ID': 'applicable_manufacturer_or_applicable_gpo_making_payment_id',
    'Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name': 'applicable_manufacturer_or_gpo_name',
    'Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_State': 'applicable_manufacturer_or_applicable_gpo_making_payment_state',
    'Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Country': 'applicable_manufacturer_or_applicable_gpo_making_payment_country',
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
    'Change_Type': 'change_type',
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
    # Product indication slots (1-5)
    'Product_Indication_1': 'product_indication_1',
    'Product_Indication_2': 'product_indication_2',
    'Product_Indication_3': 'product_indication_3',
    'Product_Indication_4': 'product_indication_4',
    'Product_Indication_5': 'product_indication_5',
    # NDC slots — structural join key to mol_silver.ndc_molecule_bridge
    'Associated_Drug_or_Biological_NDC_1': 'associated_drug_or_biological_ndc_1',
    'Associated_Drug_or_Biological_NDC_2': 'associated_drug_or_biological_ndc_2',
    'Associated_Drug_or_Biological_NDC_3': 'associated_drug_or_biological_ndc_3',
    'Associated_Drug_or_Biological_NDC_4': 'associated_drug_or_biological_ndc_4',
    'Associated_Drug_or_Biological_NDC_5': 'associated_drug_or_biological_ndc_5',
}

TABLE = 'cms_open_payments'
SCHEMA = 'hcs_raw'


def load_cms_open_payments(filepath: Optional[str] = None, rows: Optional[List[Dict]] = None, source_year: int = 2023, max_records: int = 0, source_hash: Optional[str] = None) -> dict:
    """Load CMS Open Payments data from CSV file."""
    logger.info(f"Loading CMS Open Payments (year={source_year})")

    if rows is not None:
        # Streaming mode: rows passed directly from API, no file needed
        normalized = [{k: ('' if v is None else str(v)) for k, v in row.items()} for row in rows]
        df = pd.DataFrame(normalized) if normalized else pd.DataFrame()
        _source_hash = source_hash or f"api_stream_{source_year}"
        source_file = f"api_stream_{source_year}"
    else:
        if filepath is None:
            raise ValueError("Either filepath or rows must be provided")
        source_file = Path(filepath).name
        hash_md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_md5.update(chunk)
        _source_hash = source_hash or hash_md5.hexdigest()

        with get_cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE _source_hash = %s",
                (_source_hash,)
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
                # Physician identity (T022)
                physician_npi=row.get('physician_npi') or None,
                physician_middle_name=row.get('physician_middle_name') or None,
                physician_name_suffix=row.get('physician_name_suffix') or None,
                physician_primary_type=row.get('physician_primary_type') or None,
                physician_specialty_2=row.get('physician_specialty_2') or None,
                # Teaching hospitals (T022)
                teaching_hospital_ccn=row.get('teaching_hospital_ccn') or None,
                teaching_hospital_id=row.get('teaching_hospital_id') or None,
                teaching_hospital_name=row.get('teaching_hospital_name') or None,
                # Recipient geography (T022)
                recipient_country=row.get('recipient_country') or None,
                recipient_primary_business_street_address_line_1=row.get('recipient_primary_business_street_address_line_1') or None,
                recipient_primary_business_street_address_line_2=row.get('recipient_primary_business_street_address_line_2') or None,
                recipient_postal_code=row.get('recipient_postal_code') or None,
                recipient_province=row.get('recipient_province') or None,
                # Publication / dispute metadata (T022)
                dispute_status_for_publication=row.get('dispute_status_for_publication') or None,
                delay_in_publication_indicator=row.get('delay_in_publication_indicator') or None,
                change_type=row.get('change_type') or None,
                # Manufacturer identity (T022)
                applicable_manufacturer_or_applicable_gpo_making_payment_id=row.get('applicable_manufacturer_or_applicable_gpo_making_payment_id') or None,
                applicable_manufacturer_or_applicable_gpo_making_payment_state=row.get('applicable_manufacturer_or_applicable_gpo_making_payment_state') or None,
                applicable_manufacturer_or_applicable_gpo_making_payment_country=row.get('applicable_manufacturer_or_applicable_gpo_making_payment_country') or None,
                # Product category / therapeutic area slots (T022)
                product_category_or_therapeutic_area_1=row.get('product_category_or_therapeutic_area_1') or None,
                product_category_or_therapeutic_area_2=row.get('product_category_or_therapeutic_area_2') or None,
                product_category_or_therapeutic_area_3=row.get('product_category_or_therapeutic_area_3') or None,
                product_category_or_therapeutic_area_4=row.get('product_category_or_therapeutic_area_4') or None,
                product_category_or_therapeutic_area_5=row.get('product_category_or_therapeutic_area_5') or None,
                # Product indication slots (T022)
                product_indication_1=row.get('product_indication_1') or None,
                product_indication_2=row.get('product_indication_2') or None,
                product_indication_3=row.get('product_indication_3') or None,
                product_indication_4=row.get('product_indication_4') or None,
                product_indication_5=row.get('product_indication_5') or None,
                # Travel details (T022)
                city_of_travel=row.get('city_of_travel') or None,
                state_of_travel=row.get('state_of_travel') or None,
                country_of_travel=row.get('country_of_travel') or None,
                # Flags (T022)
                physician_ownership_indicator=row.get('physician_ownership_indicator') or None,
                third_party_payment_recipient_indicator=row.get('third_party_payment_recipient_indicator') or None,
                charity_indicator=row.get('charity_indicator') or None,
                contextual_information=row.get('contextual_information') or None,
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
            d['_source_hash'] = _source_hash
            d['_source_file'] = source_file
            d['_loaded_at'] = loaded_at
            d['_source_year'] = source_year
            records.append(d)
        except (ValidationError, Exception) as e:
            errors.append(f"Row {idx}: {e}")

    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['record_id', '_source_year'],
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
