#!/usr/bin/env python3
"""Seed CMS hcs_raw tables with 1000 synthetic records each.

Generates realistic-looking synthetic data directly into hcs_raw.* tables.
Uses PostgreSQL generate_series for efficiency.
"""

import hashlib
import os
import sys
import random
import psycopg2
from datetime import datetime, timezone, date

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5433")),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
}

TARGET_ROWS = 1000
SOURCE_YEAR = 2023
LOADED_AT = "2026-03-29 00:00:00+00"

STATES = ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"]
PROVIDER_TYPES = ["Internal Medicine","Family Practice","Cardiology","Neurology","Orthopedics","Oncology","Radiology","Anesthesiology","Ophthalmology","General Surgery","Psychiatry","Dermatology","Emergency Medicine","Pathology","Gastroenterology"]
HCPCS_CODES = ["99213","99214","99215","93000","93306","71046","70553","27447","62322","43239","45378","90837","20610","29827","64483"]
DRUGS = [("LISINOPRIL","Lisinopril"),("METFORMIN","Metformin"),("ATORVASTATIN","Lipitor"),("AMLODIPINE","Norvasc"),("OMEPRAZOLE","Prilosec"),("LEVOTHYROXINE","Synthroid"),("METOPROLOL","Lopressor"),("GABAPENTIN","Neurontin"),("ALBUTEROL","ProAir"),("LOSARTAN","Cozaar")]
CITIES = ["New York","Los Angeles","Chicago","Houston","Phoenix","Philadelphia","San Antonio","San Diego","Dallas","San Jose","Austin","Jacksonville","Fort Worth","Columbus","San Francisco","Charlotte","Indianapolis","Seattle","Denver","Nashville"]


def make_hash(seed: str) -> str:
    return hashlib.md5(seed.encode()).hexdigest()


def seed_table(cur, schema: str, table: str, rows: list[dict]) -> int:
    """Insert rows into table, skip conflicts."""
    if not rows:
        return 0
    cols = [k for k in rows[0].keys() if k != "id"]
    placeholders = ", ".join(["%s"] * len(cols))
    col_str = ", ".join(cols)
    inserted = 0
    for row in rows:
        vals = [row[c] for c in cols]
        try:
            cur.execute(
                f"INSERT INTO {schema}.{table} ({col_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                vals
            )
            inserted += cur.rowcount
        except Exception as e:
            print(f"  [warn] {table} row insert error: {e}", file=sys.stderr)
            cur.connection.rollback()
            # re-open transaction
            cur.execute("BEGIN") if False else None
    return inserted


def generate_cms_part_d_spending():
    rows = []
    for i in range(TARGET_ROWS):
        gnrc, brnd = DRUGS[i % len(DRUGS)]
        h = make_hash(f"part_d_{i}_{SOURCE_YEAR}")
        rows.append({
            "brnd_name": f"{brnd} {10+i}mg",
            "gnrc_name": f"{gnrc}_{i}",
            "tot_mftr": random.randint(1, 20),
            "tot_spndng": round(random.uniform(100000, 5000000), 2),
            "tot_dsg_unts": round(random.uniform(10000, 1000000), 2),
            "tot_clms": random.randint(1000, 500000),
            "tot_benes": random.randint(100, 50000),
            "avg_spnd_per_dsg_unt_wghtd": round(random.uniform(0.1, 100), 2),
            "avg_spnd_per_clm": round(random.uniform(10, 500), 2),
            "avg_spnd_per_bene": round(random.uniform(50, 2000), 2),
            "outlier_flag": "N",
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_part_d_spending_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_part_b_spending():
    rows = []
    for i in range(TARGET_ROWS):
        h = make_hash(f"part_b_{i}_{SOURCE_YEAR}")
        rows.append({
            "hcpcs_cd": HCPCS_CODES[i % len(HCPCS_CODES)] + f"_{i}",
            "hcpcs_desc": f"Procedure description {i}",
            "tot_mftr": random.randint(1, 10),
            "mftr_name": f"Manufacturer {i % 50}",
            "tot_spndng": round(random.uniform(50000, 2000000), 2),
            "tot_dsg_unts": round(random.uniform(5000, 500000), 2),
            "tot_benes": random.randint(50, 20000),
            "tot_clms": random.randint(500, 200000),
            "avg_spnd_per_dsg_unt": round(random.uniform(5, 200), 2),
            "avg_spnd_per_clm": round(random.uniform(20, 1000), 2),
            "avg_spnd_per_bene": round(random.uniform(100, 3000), 2),
            "outlier_flag": "N",
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_part_b_spending_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_chronic_conditions():
    rows = []
    # unique on (bene_geo_cd, bene_age_lvl, bene_cond, _source_year)
    # 34 geo_cds × 3 age_lvls × 10 conditions = 1020 unique combinations
    conditions = ["Diabetes","Hypertension","COPD","CHF","CKD","Depression","Atrial_Fib","Cancer","Alzheimers","Asthma"]
    age_lvls = ["All","LT65","GTE65"]
    seen = set()
    geo_idx = 0
    geo_count = 34  # 34 counties × 3 × 10 = 1020 unique combos
    for cond in conditions:
        for age_lvl in age_lvls:
            for g in range(geo_count):
                key = (f"{g:02d}000", age_lvl, cond)
                if key in seen:
                    continue
                seen.add(key)
                if len(rows) >= TARGET_ROWS:
                    break
                h = make_hash(f"chronic_{key}_{SOURCE_YEAR}")
                rows.append({
                    "bene_geo_lvl": "County",
                    "bene_geo_desc": f"County {g}",
                    "bene_geo_cd": f"{g:02d}000",
                    "bene_age_lvl": age_lvl,
                    "bene_demo_lvl": "All",
                    "bene_demo_desc": "All Beneficiaries",
                    "bene_cond": cond,
                    "prvlnc": round(random.uniform(0.05, 0.40), 4),
                    "tot_mdcr_stdzd_pymt_pc": round(random.uniform(5000, 25000), 2),
                    "tot_mdcr_pymt_pc": round(random.uniform(5500, 27000), 2),
                    "hosp_readmsn_rate": round(random.uniform(0.10, 0.25), 4),
                    "ed_visits_per_1000_benes": round(random.uniform(200, 800), 1),
                    "_source_year": SOURCE_YEAR,
                    "_source_hash": h,
                    "_source_file": f"cms_chronic_conditions_{SOURCE_YEAR}.csv",
                    "_loaded_at": LOADED_AT,
                })
            if len(rows) >= TARGET_ROWS:
                break
        if len(rows) >= TARGET_ROWS:
            break
    return rows[:TARGET_ROWS]


def generate_cms_claim_type_puf():
    rows = []
    # unique on (clm_type, bene_geo_lvl, _source_year)
    # Use geo_desc as state-level breakdown to maximize rows:
    # 9 claim types × 50 states × 3 years = 1350 unique combos (using state as bene_geo_lvl value)
    # Actually the unique key is (clm_type, bene_geo_lvl, _source_year)
    # If bene_geo_lvl is "State-CA", "State-TX", etc, these are distinct values
    claim_types = ["01","20","30","40","50","60","71","72","82"]
    years = [2021, 2022, 2023]
    seen = set()
    # Use full state names as the geo level values
    for year in years:
        for state in STATES:
            for ct in claim_types:
                geo_lvl_val = f"State-{state}"
                key = (ct, geo_lvl_val, year)
                if key in seen:
                    continue
                seen.add(key)
                if len(rows) >= TARGET_ROWS:
                    break
                h = make_hash(f"claim_type_{ct}_{state}_{year}")
                rows.append({
                    "bene_geo_lvl": geo_lvl_val,
                    "bene_geo_desc": state,
                    "clm_type": ct,
                    "clm_type_desc": f"Claim Type {ct}",
                    "tot_clms": random.randint(10000, 5000000),
                    "tot_benes": random.randint(1000, 500000),
                    "tot_mdcr_pymt_amt": round(random.uniform(1000000, 50000000), 2),
                    "avg_mdcr_pymt_amt": round(random.uniform(100, 5000), 2),
                    "_source_year": year,
                    "_source_hash": h,
                    "_source_file": f"cms_claim_type_puf_{year}.csv",
                    "_loaded_at": LOADED_AT,
                })
            if len(rows) >= TARGET_ROWS:
                break
        if len(rows) >= TARGET_ROWS:
            break
    return rows[:TARGET_ROWS]


def generate_cms_cost_reports_puf():
    rows = []
    for i in range(TARGET_ROWS):
        h = make_hash(f"cost_reports_{i}_{SOURCE_YEAR}")
        beds = random.randint(25, 800)
        rows.append({
            "provider_id": f"{100000 + i:06d}",
            "hospital_name": f"General Hospital {i}",
            "city": CITIES[i % len(CITIES)],
            "state": STATES[i % len(STATES)],
            "zip_code": f"{10000 + i % 90000:05d}",
            "fiscal_year_begin": f"{SOURCE_YEAR-1}-10-01",
            "fiscal_year_end": f"{SOURCE_YEAR}-09-30",
            "total_beds": beds,
            "total_discharges": random.randint(beds * 20, beds * 80),
            "net_patient_revenue": round(random.uniform(10000000, 500000000), 2),
            "total_operating_expenses": round(random.uniform(9000000, 480000000), 2),
            "operating_margin": round(random.uniform(-0.05, 0.12), 4),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_cost_reports_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_cost_reports_puf_lines():
    rows = []
    # unique on (provider_id, line_item_code, _source_year)
    # Use 125 providers × 8 line codes × 1 year = 1000 unique combos
    line_codes = ["A100","B200","C300","D400","E500","F600","G700","H800"]
    seen = set()
    for p in range(125):
        for lc in line_codes:
            key = (f"{100000 + p:06d}", lc, SOURCE_YEAR)
            if key in seen:
                continue
            seen.add(key)
            if len(rows) >= TARGET_ROWS:
                break
            h = make_hash(f"cost_reports_lines_{p}_{lc}_{SOURCE_YEAR}")
            rows.append({
                "provider_id": f"{100000 + p:06d}",
                "facility_type": "Hospital",
                "line_item_code": lc,
                "line_item_description": f"Line item {lc}",
                "reported_hours_fte": round(random.uniform(0, 5000), 2),
                "total_salaries": round(random.uniform(0, 50000000), 2),
                "source_year": SOURCE_YEAR,
                "_source_year": SOURCE_YEAR,
                "_source_hash": h,
                "_source_file": f"cms_cost_reports_puf_lines_{SOURCE_YEAR}.csv",
                "_loaded_at": LOADED_AT,
            })
        if len(rows) >= TARGET_ROWS:
            break
    return rows[:TARGET_ROWS]


def generate_cms_dme_puf():
    rows = []
    dme_types = ["E0601","E0620","E1390","K0001","K0800","A6216","A4253","E0260","E0291","B4087"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"dme_{i}_{SOURCE_YEAR}")
        rows.append({
            "npi": f"{1000000000 + i:010d}",
            "provider_last_org_name": f"DME Provider {i}",
            "provider_first_name": f"First{i % 100}",
            "provider_city": CITIES[i % len(CITIES)],
            "provider_state": STATES[i % len(STATES)],
            "provider_state_fips": f"{i % 50 + 1:02d}",
            "provider_zip5": f"{10000 + i % 90000:05d}",
            "provider_ruca": str(random.randint(1, 10)),
            "provider_type": "DME Supplier",
            "hcpcs_cd": dme_types[i % len(dme_types)],
            "hcpcs_desc": f"DME item {i}",
            "suplr_rentl_ind": "R" if i % 3 == 0 else "P",
            "tot_suplrs": random.randint(1, 50),
            "tot_suplr_benes": random.randint(10, 5000),
            "tot_suplr_clms": random.randint(20, 10000),
            "tot_suplr_srvcs": random.randint(20, 15000),
            "avg_suplr_sbmtd_chrg": round(random.uniform(50, 5000), 2),
            "avg_suplr_mdcr_alowd_amt": round(random.uniform(30, 3000), 2),
            "avg_suplr_mdcr_pymt_amt": round(random.uniform(20, 2500), 2),
            "avg_suplr_mdcr_stdzd_amt": round(random.uniform(20, 2500), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_dme_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_dual_eligible():
    rows = []
    # unique on (state_cd, dual_elgbl_lvl, _source_year)
    # 50 states × 2 lvls × 10 years = 1000 unique combos
    lvls = ["Full", "Partial"]
    years = list(range(2015, 2025))  # 10 years
    seen = set()
    for year in years:
        for i, state in enumerate(STATES):
            for lvl in lvls:
                state_cd = f"{i + 1:02d}"
                key = (state_cd, lvl, year)
                if key in seen:
                    continue
                seen.add(key)
                if len(rows) >= TARGET_ROWS:
                    break
                h = make_hash(f"dual_eligible_{state}_{lvl}_{year}")
                rows.append({
                    "state_cd": state_cd,
                    "state_name": state,
                    "dual_elgbl_lvl": lvl,
                    "dual_elgbl_desc": f"{lvl} dual eligible",
                    "tot_benes": random.randint(10000, 500000),
                    "ffs_benes": random.randint(5000, 250000),
                    "ma_benes": random.randint(1000, 100000),
                    "dual_elgbl_full_benes": random.randint(5000, 200000),
                    "dual_elgbl_prtl_benes": random.randint(1000, 50000),
                    "non_dual_benes": random.randint(2000, 100000),
                    "lis_benes": random.randint(1000, 80000),
                    "_source_year": year,
                    "_source_hash": h,
                    "_source_file": f"cms_dual_eligible_{year}.csv",
                    "_loaded_at": LOADED_AT,
                })
            if len(rows) >= TARGET_ROWS:
                break
        if len(rows) >= TARGET_ROWS:
            break
    return rows[:TARGET_ROWS]


def generate_cms_enrollment_puf():
    rows = []
    for i in range(TARGET_ROWS):
        state = STATES[i % len(STATES)]
        h = make_hash(f"enrollment_{i}_{SOURCE_YEAR}")
        rows.append({
            "state_cd": f"{i % 50 + 1:02d}",
            "county_cd": f"{i % 500:03d}",
            "county_desc": f"County {i % 500}",
            "bene_demo_lvl": "All",
            "bene_demo_desc": "All Beneficiaries",
            "bene_age_lvl": "All" if i % 3 == 0 else ("LT65" if i % 3 == 1 else "GTE65"),
            "tot_benes": random.randint(1000, 100000),
            "orgnl_mdcr_benes": random.randint(500, 60000),
            "ma_benes": random.randint(200, 40000),
            "esrd_benes": random.randint(50, 5000),
            "dsbl_benes": random.randint(100, 20000),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_enrollment_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_geographic_variation():
    rows = []
    geo_levels = ["National", "State", "County"]
    for i in range(TARGET_ROWS):
        geo = geo_levels[i % 3]
        h = make_hash(f"geo_var_{geo}_{i}_{SOURCE_YEAR}")
        rows.append({
            "bene_geo_lvl": geo,
            "bene_geo_desc": f"Geography {i}",
            "bene_geo_cd": f"{i % 1000:05d}",
            "bene_age_lvl": "All",
            "bene_demo_lvl": "All",
            "bene_demo_desc": "All Beneficiaries",
            "bene_mcc_lvl": str(random.randint(0, 6)),
            "year": SOURCE_YEAR,
            "tot_benes": random.randint(500, 200000),
            "ip_cvrd_stays_per_1000_benes": round(random.uniform(100, 500), 2),
            "er_visits_per_1000_benes": round(random.uniform(200, 800), 2),
            "hosp_readmsn_rate": round(random.uniform(0.10, 0.25), 4),
            "acute_hosp_readmsn_rate": round(random.uniform(0.08, 0.20), 4),
            "tot_mdcr_stdzd_pymt_pc": round(random.uniform(7000, 15000), 2),
            "tot_mdcr_stdzd_pymt_pct_chg": round(random.uniform(-0.05, 0.10), 4),
            "tot_mdcr_pymt_pc": round(random.uniform(7500, 16000), 2),
            "tot_mdcr_alowd_amt_pc": round(random.uniform(8000, 18000), 2),
            "ma_prtcptn_rate": round(random.uniform(0.10, 0.60), 4),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_geographic_variation_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_home_health():
    rows = []
    srvc_codes = ["1HHHH","2HHHH","3HHHH","4HHHH","5HHHH"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"home_health_{i}_{SOURCE_YEAR}")
        rows.append({
            "provider_id": f"{200000 + i:06d}",
            "provider_name": f"Home Health Agency {i}",
            "provider_city": CITIES[i % len(CITIES)],
            "provider_state": STATES[i % len(STATES)],
            "provider_zip5": f"{10000 + i % 90000:05d}",
            "hh_srvc_cd": srvc_codes[i % len(srvc_codes)],
            "hh_srvc_desc": f"Home health service {i % 5}",
            "tot_epsd_stay": random.randint(50, 5000),
            "tot_benes": random.randint(30, 3000),
            "avg_hh_mdcr_pymt_amt": round(random.uniform(1000, 5000), 2),
            "avg_hh_outlier_pymt": round(random.uniform(0, 500), 2),
            "avg_age": round(random.uniform(65, 85), 1),
            "female_pct": round(random.uniform(0.50, 0.75), 4),
            "dual_pct": round(random.uniform(0.10, 0.40), 4),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_home_health_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_hospice_puf():
    rows = []
    hospice_codes = ["651","652","653","654","655"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"hospice_{i}_{SOURCE_YEAR}")
        rows.append({
            "provider_id": f"{300000 + i:06d}",
            "provider_name": f"Hospice Provider {i}",
            "provider_city": CITIES[i % len(CITIES)],
            "provider_state": STATES[i % len(STATES)],
            "provider_zip5": f"{10000 + i % 90000:05d}",
            "hspce_cd": hospice_codes[i % len(hospice_codes)],
            "hspce_desc": f"Hospice level of care {i % 5}",
            "tot_benes": random.randint(20, 2000),
            "tot_mdcr_alowd_amt": round(random.uniform(500000, 10000000), 2),
            "tot_mdcr_pymt_amt": round(random.uniform(480000, 9800000), 2),
            "avg_mdcr_pymt_amt": round(random.uniform(2000, 15000), 2),
            "avg_age": round(random.uniform(70, 88), 1),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_hospice_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_hospital_general_info():
    rows = []
    hospital_types = ["Acute Care Hospitals","Critical Access Hospitals","Childrens","Psychiatric","Rehabilitation"]
    ownership_types = ["Government - Federal","Government - State","Voluntary non-profit - Private","Proprietary"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"hosp_general_{i}_{SOURCE_YEAR}")
        rows.append({
            "facility_id": f"{100000 + i:06d}",
            "facility_name": f"Medical Center {i}",
            "address": f"{100 + i} Main St",
            "city_town": CITIES[i % len(CITIES)],
            "state": STATES[i % len(STATES)],
            "zip_code": f"{10000 + i % 90000:05d}",
            "county_parish": f"County {i % 200}",
            "telephone_number": f"555{1000000 + i:07d}",
            "hospital_type": hospital_types[i % len(hospital_types)],
            "hospital_ownership": ownership_types[i % len(ownership_types)],
            "emergency_services": "Yes" if i % 4 != 0 else "No",
            "hospital_overall_rating": random.randint(1, 5),
            "hospital_overall_rating_footnote": None,
            "meets_criteria_for_birthing_friendly_designation": "Y" if i % 3 == 0 else "N",
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_hospital_general_info_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_imaging_puf():
    rows = []
    imaging_codes = ["70553","71046","73721","74177","75574","76817","93306","78816"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"imaging_{i}_{SOURCE_YEAR}")
        rows.append({
            "npi": f"{1000000000 + i:010d}",
            "provider_last_org_name": f"Imaging Provider {i}",
            "provider_city": CITIES[i % len(CITIES)],
            "provider_state": STATES[i % len(STATES)],
            "provider_zip5": f"{10000 + i % 90000:05d}",
            "provider_type": PROVIDER_TYPES[i % len(PROVIDER_TYPES)],
            "hcpcs_cd": imaging_codes[i % len(imaging_codes)],
            "hcpcs_desc": f"Imaging procedure {i}",
            "tot_benes": random.randint(20, 5000),
            "tot_srvcs": random.randint(25, 6000),
            "tot_mdcr_alowd_amt": round(random.uniform(5000, 500000), 2),
            "avg_mdcr_alowd_amt": round(random.uniform(100, 2000), 2),
            "avg_mdcr_pymt_amt": round(random.uniform(80, 1800), 2),
            "avg_mdcr_stdzd_amt": round(random.uniform(80, 1800), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_imaging_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_inpatient_puf():
    rows = []
    drgs = ["470","292","291","293","690","194","065","066","064","291"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"inpatient_{i}_{SOURCE_YEAR}")
        rows.append({
            "drg_cd": drgs[i % len(drgs)],
            "drg_definition": f"DRG {drgs[i % len(drgs)]} - Medical procedure {i}",
            "provider_id": f"{400000 + i:06d}",
            "provider_name": f"General Hospital {i}",
            "provider_street_address": f"{100 + i} Hospital Dr",
            "provider_city": CITIES[i % len(CITIES)],
            "provider_state": STATES[i % len(STATES)],
            "provider_state_fips": f"{i % 50 + 1:02d}",
            "provider_zip_code": f"{10000 + i % 90000:05d}",
            "provider_ruca": str(random.randint(1, 10)),
            "hospital_referral_region_desc": f"HRR {i % 100}",
            "total_discharges": random.randint(10, 5000),
            "average_covered_charges": round(random.uniform(5000, 100000), 2),
            "average_total_payments": round(random.uniform(3000, 60000), 2),
            "average_medicare_payments": round(random.uniform(2500, 55000), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_inpatient_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_lab_services():
    rows = []
    lab_codes = ["80053","80061","85025","36415","82947","82950","84443","85027","85610","86003"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"lab_{i}_{SOURCE_YEAR}")
        rows.append({
            "npi": f"{1000000000 + i:010d}",
            "provider_last_org_name": f"Lab Services {i}",
            "provider_city": CITIES[i % len(CITIES)],
            "provider_state": STATES[i % len(STATES)],
            "provider_zip5": f"{10000 + i % 90000:05d}",
            "provider_type": "Clinical Laboratory",
            "hcpcs_cd": lab_codes[i % len(lab_codes)],
            "hcpcs_desc": f"Lab test {i}",
            "tot_benes": random.randint(50, 10000),
            "tot_srvcs": random.randint(60, 12000),
            "tot_mdcr_alowd_amt": round(random.uniform(1000, 100000), 2),
            "avg_mdcr_alowd_amt": round(random.uniform(5, 200), 2),
            "avg_mdcr_pymt_amt": round(random.uniform(4, 180), 2),
            "avg_mdcr_stdzd_amt": round(random.uniform(4, 180), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_lab_services_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_medicaid_drug_spending():
    rows = []
    for i in range(TARGET_ROWS):
        gnrc, brnd = DRUGS[i % len(DRUGS)]
        h = make_hash(f"medicaid_drug_{i}_{SOURCE_YEAR}")
        rows.append({
            "brnd_name": f"{brnd} {i % 5 + 1}mg",
            "gnrc_name": f"{gnrc}_{i}",
            "tot_mftr": random.randint(1, 15),
            "util_type": "FFS" if i % 2 == 0 else "MCO",
            "tot_spndng": round(random.uniform(100000, 10000000), 2),
            "medicaid_spndng_per_dosage_unit": round(random.uniform(0.1, 100), 2),
            "medicaid_spndng_per_prescription": round(random.uniform(20, 500), 2),
            "unit_type": "EACH" if i % 3 == 0 else "GM",
            "tot_dosage_units": round(random.uniform(10000, 1000000), 2),
            "tot_prescriptions": random.randint(1000, 200000),
            "tot_benes": random.randint(500, 100000),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_medicaid_drug_spending_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_medicare_advantage():
    rows = []
    org_types = ["HMO","PPO","PFFS","MSA","SNP","COST"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"ma_{i}_{SOURCE_YEAR}")
        rows.append({
            "contract_id": f"H{1000 + i % 200:04d}",
            "organization_name": f"MA Plan Organization {i % 100}",
            "organization_type": org_types[i % len(org_types)],
            "plan_id": f"{100 + i % 999:03d}",
            "plan_name": f"Plan Name {i}",
            "segment_id": str(i % 10),
            "enrollment_data_period": f"{SOURCE_YEAR}-06",
            "fips_cd": f"{i % 1000:05d}",
            "state_fips": f"{i % 50 + 1:02d}",
            "county_fips": f"{i % 1000:05d}",
            "enrollment": random.randint(100, 50000),
            "avg_age": round(random.uniform(68, 80), 1),
            "pct_female": round(random.uniform(0.50, 0.70), 4),
            "avg_risk_score": round(random.uniform(0.8, 1.5), 4),
            "ma_participation_rate": round(random.uniform(0.20, 0.70), 4),
            "star_rating": round(random.uniform(2.5, 5.0) * 2) / 2,
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_medicare_advantage_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_mental_health_puf():
    rows = []
    mh_codes = ["90832","90834","90837","90839","90840","90847","90853","H0001","H0002","H2011"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"mh_{i}_{SOURCE_YEAR}")
        rows.append({
            "npi": f"{1000000000 + i:010d}",
            "provider_last_org_name": f"MH Provider {i}",
            "provider_first_name": f"Dr. First{i % 100}",
            "provider_city": CITIES[i % len(CITIES)],
            "provider_state": STATES[i % len(STATES)],
            "provider_zip5": f"{10000 + i % 90000:05d}",
            "provider_type": "Psychiatry" if i % 3 == 0 else "Psychology",
            "hcpcs_cd": mh_codes[i % len(mh_codes)],
            "hcpcs_desc": f"Mental health service {i}",
            "mh_srvc_ind": "Y",
            "tot_benes": random.randint(20, 3000),
            "tot_srvcs": round(random.uniform(25, 5000), 1),
            "tot_mdcr_alowd_amt": round(random.uniform(2000, 200000), 2),
            "avg_mdcr_alowd_amt": round(random.uniform(50, 300), 2),
            "avg_mdcr_pymt_amt": round(random.uniform(40, 270), 2),
            "avg_mdcr_stdzd_amt": round(random.uniform(40, 270), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_mental_health_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_nppes():
    rows = []
    taxonomy_codes = ["207Q00000X","207R00000X","208D00000X","2086S0122X","207RC0200X","2084P0800X","207X00000X","208600000X"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"nppes_{i}_{SOURCE_YEAR}")
        rows.append({
            "npi": f"{1000000000 + i:010d}",
            "entity_type_code": "1" if i % 5 != 0 else "2",
            "provider_last_name": f"Smith{i % 500}" if i % 5 != 0 else None,
            "provider_first_name": f"John{i % 100}" if i % 5 != 0 else None,
            "provider_organization_name": None if i % 5 != 0 else f"Medical Group {i // 5}",
            "provider_credential_text": "M.D." if i % 3 == 0 else "D.O.",
            "provider_first_line_business_mailing_address": f"{100 + i} Medical Blvd",
            "provider_second_line_business_mailing_address": None,
            "provider_business_mailing_address_city_name": CITIES[i % len(CITIES)],
            "provider_business_mailing_address_state_name": STATES[i % len(STATES)],
            "provider_business_mailing_address_postal_code": f"{10000 + i % 90000:05d}",
            "provider_business_mailing_address_telephone_number": f"555{1000000 + i:07d}",
            "provider_first_line_business_practice_location_address": f"{100 + i} Medical Blvd",
            "provider_second_line_business_practice_location_address": None,
            "provider_business_practice_location_address_city_name": CITIES[i % len(CITIES)],
            "provider_business_practice_location_address_state_name": STATES[i % len(STATES)],
            "provider_business_practice_location_address_postal_code": f"{10000 + i % 90000:05d}",
            "provider_business_practice_location_address_country_code": "US",
            "provider_business_practice_location_address_telephone_number": f"555{1000000 + i:07d}",
            "provider_business_practice_location_address_fax_number": None,
            "healthcare_provider_taxonomy_code_1": taxonomy_codes[i % len(taxonomy_codes)],
            "healthcare_provider_taxonomy_code_2": None,
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_nppes_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
            "provider_middle_name": None,
            "provider_name_prefix_text": "Dr." if i % 3 == 0 else None,
            "provider_name_suffix_text": None,
            "provider_business_mailing_address_country_code": "US",
            "provider_business_mailing_address_fax_number": None,
            "npi_deactivation_date": None,
            "npi_reactivation_date": None,
        })
    return rows


def generate_cms_open_payments():
    rows = []
    payment_natures = ["Food and Beverage","Travel and Lodging","Consulting Fee","Speaking Fee","Education","Research","Grant","Royalty or License"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"open_payments_{i}_{SOURCE_YEAR}")
        gnrc, brnd = DRUGS[i % len(DRUGS)]
        rows.append({
            "covered_recipient_type": "Covered Recipient Physician" if i % 5 != 0 else "Covered Recipient Teaching Hospital",
            "physician_profile_id": f"{1000000 + i}",
            "physician_first_name": f"First{i % 200}",
            "physician_last_name": f"Last{i % 500}",
            "physician_specialty": PROVIDER_TYPES[i % len(PROVIDER_TYPES)],
            "applicable_manufacturer_or_gpo_name": f"Pharma Co {i % 100}",
            "total_amount_of_payment_usdollars": round(random.uniform(10, 50000), 2),
            "date_of_payment": f"{SOURCE_YEAR}-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
            "nature_of_payment_or_transfer_of_value": payment_natures[i % len(payment_natures)],
            "recipient_city": CITIES[i % len(CITIES)],
            "recipient_state": STATES[i % len(STATES)],
            "recipient_zip_code": f"{10000 + i % 90000:05d}",
            "payment_publication_date": f"{SOURCE_YEAR}-03-31",
            "record_id": f"REC{i:08d}",
            "program_year": SOURCE_YEAR,
            "name_of_drug_or_biological_or_device_or_medical_supply_1": brnd,
            "name_of_drug_or_biological_or_device_or_medical_supply_2": None,
            "name_of_drug_or_biological_or_device_or_medical_supply_3": None,
            "name_of_drug_or_biological_or_device_or_medical_supply_4": None,
            "name_of_drug_or_biological_or_device_or_medical_supply_5": None,
            "associated_drug_or_biological_ndc_1": None,
            "associated_drug_or_biological_ndc_2": None,
            "associated_drug_or_biological_ndc_3": None,
            "associated_drug_or_biological_ndc_4": None,
            "associated_drug_or_biological_ndc_5": None,
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_open_payments_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
            # NOTE: drug_name_*_normalized are GENERATED columns — do not insert
            "number_of_payments_included_in_total_amount": random.randint(1, 10),
            "form_of_payment_or_transfer_of_value": "Cash or cash equivalent",
        })
    return rows


def generate_cms_opioid_puf():
    rows = []
    opioid_drugs = [("OXYCODONE","OxyContin"),("HYDROCODONE","Vicodin"),("MORPHINE","MS Contin"),("TRAMADOL","Ultram"),("CODEINE","Tylenol/Cod")]
    for i in range(TARGET_ROWS):
        gnrc, brnd = opioid_drugs[i % len(opioid_drugs)]
        h = make_hash(f"opioid_{i}_{SOURCE_YEAR}")
        is_opioid = i % 3 != 0
        rows.append({
            "prscrbr_npi": f"{1000000000 + i:010d}",
            "prscrbr_last_org_name": f"Prescriber {i}",
            "prscrbr_first_name": f"Dr{i % 200}",
            "prscrbr_city": CITIES[i % len(CITIES)],
            "prscrbr_state_abrvtn": STATES[i % len(STATES)],
            "prscrbr_state_fips": f"{i % 50 + 1:02d}",
            "prscrbr_type": PROVIDER_TYPES[i % len(PROVIDER_TYPES)],
            "prscrbr_type_src": "T",
            "brnd_name": brnd,
            "gnrc_name": gnrc,
            "opioid_drug_flag": "Y" if is_opioid else "N",
            "la_opioid_drug_flag": "Y" if is_opioid and i % 5 == 0 else "N",
            "tot_clms": random.randint(10, 5000),
            "tot_30day_fills": round(random.uniform(10, 5500), 1),
            "tot_day_suply": random.randint(300, 150000),
            "tot_drug_cst": round(random.uniform(500, 100000), 2),
            "tot_benes": random.randint(5, 2000),
            "opioid_clms": random.randint(0, 3000) if is_opioid else 0,
            "opioid_benes": random.randint(0, 1500) if is_opioid else 0,
            "la_opioid_clms": random.randint(0, 500) if is_opioid and i % 5 == 0 else 0,
            "la_opioid_benes": random.randint(0, 200) if is_opioid and i % 5 == 0 else 0,
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_opioid_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_ordering_providers():
    rows = []
    for i in range(TARGET_ROWS):
        h = make_hash(f"ordering_{i}_{SOURCE_YEAR}")
        rows.append({
            "rndrng_npi": f"{1000000000 + i:010d}",
            "rndrng_prvdr_last_org_name": f"Rendering Provider {i}",
            "rndrng_prvdr_first_name": f"First{i % 200}",
            "rndrng_prvdr_city": CITIES[i % len(CITIES)],
            "rndrng_prvdr_state_abrvtn": STATES[i % len(STATES)],
            "rndrng_prvdr_zip5": f"{10000 + i % 90000:05d}",
            "rndrng_prvdr_type": PROVIDER_TYPES[i % len(PROVIDER_TYPES)],
            "rfrd_npi": f"{2000000000 + i:010d}",
            "rfrd_prvdr_last_org_name": f"Ordering Physician {i % 500}",
            "rfrd_prvdr_type": PROVIDER_TYPES[(i + 3) % len(PROVIDER_TYPES)],
            "tot_srvcs": random.randint(10, 5000),
            "tot_benes": random.randint(5, 2000),
            "tot_mdcr_alowd_amt": round(random.uniform(1000, 500000), 2),
            "tot_mdcr_pymt_amt": round(random.uniform(800, 450000), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_ordering_providers_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_outpatient_puf():
    rows = []
    apcs = ["5521","5522","5051","0073","0634","5722","5301","0695"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"outpatient_{i}_{SOURCE_YEAR}")
        rows.append({
            "provider_id": f"{500000 + i:06d}",
            "provider_name": f"Outpatient Center {i}",
            "provider_street_address": f"{100 + i} Medical Dr",
            "provider_city": CITIES[i % len(CITIES)],
            "provider_state": STATES[i % len(STATES)],
            "provider_state_fips": f"{i % 50 + 1:02d}",
            "provider_zip_code": f"{10000 + i % 90000:05d}",
            "provider_ruca": str(random.randint(1, 10)),
            "apc": apcs[i % len(apcs)],
            "apc_desc": f"APC Description {i}",
            "total_services": random.randint(50, 50000),
            "bene_cnt": random.randint(30, 30000),
            "comp_asgn_pymt_cnt": random.randint(30, 30000),
            "average_estimated_submitted_charges": round(random.uniform(200, 10000), 2),
            "average_medicare_allowed_amt": round(random.uniform(100, 5000), 2),
            "average_total_payments": round(random.uniform(80, 4500), 2),
            "average_medicare_payments": round(random.uniform(60, 4000), 2),
            "average_medicare_stnd_amt": round(random.uniform(60, 4000), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_outpatient_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_physician_puf():
    rows = []
    for i in range(TARGET_ROWS):
        h = make_hash(f"physician_{i}_{SOURCE_YEAR}")
        rows.append({
            "npi": f"{1000000000 + i:010d}",
            "nppes_provider_last_org_name": f"Provider {i}",
            "nppes_provider_first_name": f"First{i % 200}",
            "nppes_provider_mi": None,
            "nppes_credentials": "M.D.",
            "nppes_provider_gender": "M" if i % 3 != 0 else "F",
            "nppes_entity_code": "I",
            "nppes_provider_street1": f"{100 + i} Medical Blvd",
            "nppes_provider_street2": None,
            "nppes_provider_city": CITIES[i % len(CITIES)],
            "nppes_provider_state": STATES[i % len(STATES)],
            "nppes_provider_state_fips": f"{i % 50 + 1:02d}",
            "nppes_provider_zip": f"{10000 + i % 90000:05d}",
            "nppes_provider_ruca": str(random.randint(1, 10)),
            "nppes_provider_country": "US",
            "provider_type": PROVIDER_TYPES[i % len(PROVIDER_TYPES)],
            "medicare_participation_indicator": "Y" if i % 10 != 0 else "N",
            "number_of_hcpcs": random.randint(1, 50),
            "total_services": round(random.uniform(50, 20000), 1),
            "total_unique_benes": random.randint(20, 5000),
            "total_submitted_chrg_amt": round(random.uniform(10000, 5000000), 2),
            "total_medicare_allowed_amt": round(random.uniform(5000, 2000000), 2),
            "total_medicare_payment_amt": round(random.uniform(4000, 1800000), 2),
            "total_medicare_stnd_amt": round(random.uniform(4000, 1800000), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_physician_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_physician_puf_services():
    rows = []
    pos_types = ["11","22","23","24","31","32"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"physician_svc_{i}_{SOURCE_YEAR}")
        rows.append({
            "npi": f"{1000000000 + (i % 500):010d}",
            "hcpcs_code": HCPCS_CODES[i % len(HCPCS_CODES)],
            "hcpcs_description": f"HCPCS Description {i}",
            "place_of_service": pos_types[i % len(pos_types)],
            "line_srvc_cnt": round(random.uniform(11, 5000), 1),
            "bene_unique_cnt": random.randint(11, 3000),
            "bene_day_srvc_cnt": random.randint(11, 5000),
            "average_medicare_allowed_amt": round(random.uniform(20, 2000), 2),
            "average_submitted_chrg_amt": round(random.uniform(30, 3000), 2),
            "average_medicare_payment_amt": round(random.uniform(15, 1800), 2),
            "average_medicare_stnd_amt": round(random.uniform(15, 1800), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_physician_puf_services_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
            "hcpcs_drug_ind": "Y" if i % 10 == 0 else "N",
        })
    return rows


def generate_cms_referring_providers():
    rows = []
    for i in range(TARGET_ROWS):
        h = make_hash(f"referring_{i}_{SOURCE_YEAR}")
        rows.append({
            "rndrng_npi": f"{1000000000 + i:010d}",
            "rndrng_prvdr_last_org_name": f"Rendering Provider {i}",
            "rndrng_prvdr_first_name": f"First{i % 200}",
            "rndrng_prvdr_city": CITIES[i % len(CITIES)],
            "rndrng_prvdr_state_abrvtn": STATES[i % len(STATES)],
            "rndrng_prvdr_zip5": f"{10000 + i % 90000:05d}",
            "rndrng_prvdr_type": PROVIDER_TYPES[i % len(PROVIDER_TYPES)],
            "rfrd_npi": f"{3000000000 + i:010d}",
            "rfrd_prvdr_last_org_name": f"Referring Physician {i % 500}",
            "rfrd_prvdr_type": PROVIDER_TYPES[(i + 5) % len(PROVIDER_TYPES)],
            "tot_srvcs": random.randint(10, 5000),
            "tot_benes": random.randint(5, 2000),
            "tot_mdcr_alowd_amt": round(random.uniform(1000, 500000), 2),
            "tot_mdcr_pymt_amt": round(random.uniform(800, 450000), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_referring_providers_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_snf_puf():
    rows = []
    rug_codes = ["RUX","RUL","RVX","RVL","RHX","RHL","RMX","RML","RLX"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"snf_{i}_{SOURCE_YEAR}")
        rows.append({
            "provider_id": f"{600000 + i:06d}",
            "provider_name": f"Skilled Nursing Facility {i}",
            "provider_city": CITIES[i % len(CITIES)],
            "provider_state": STATES[i % len(STATES)],
            "provider_zip5": f"{10000 + i % 90000:05d}",
            "rug_cd": rug_codes[i % len(rug_codes)],
            "rug_desc": f"RUG Description {i}",
            "tot_benes": random.randint(10, 2000),
            "tot_cvrd_days": random.randint(100, 50000),
            "avg_cvrd_days": round(random.uniform(5, 60), 1),
            "tot_mdcr_alowd_amt": round(random.uniform(10000, 5000000), 2),
            "avg_mdcr_alowd_amt": round(random.uniform(200, 2000), 2),
            "tot_mdcr_pymt_amt": round(random.uniform(9000, 4800000), 2),
            "avg_mdcr_pymt_amt": round(random.uniform(180, 1900), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_snf_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_telehealth_puf():
    rows = []
    th_codes = ["99213","99214","99441","99442","99443","G0425","G0426","G0427"]
    for i in range(TARGET_ROWS):
        h = make_hash(f"telehealth_{i}_{SOURCE_YEAR}")
        rows.append({
            "npi": f"{1000000000 + i:010d}",
            "provider_last_org_name": f"Telehealth Provider {i}",
            "provider_first_name": f"Dr{i % 200}",
            "provider_city": CITIES[i % len(CITIES)],
            "provider_state": STATES[i % len(STATES)],
            "provider_zip5": f"{10000 + i % 90000:05d}",
            "provider_type": PROVIDER_TYPES[i % len(PROVIDER_TYPES)],
            "hcpcs_cd": th_codes[i % len(th_codes)],
            "hcpcs_desc": f"Telehealth service {i}",
            "th_srvc_ind": "Y",
            "tot_benes": random.randint(20, 3000),
            "tot_srvcs": round(random.uniform(25, 5000), 1),
            "tot_mdcr_alowd_amt": round(random.uniform(2000, 200000), 2),
            "avg_mdcr_alowd_amt": round(random.uniform(50, 300), 2),
            "avg_mdcr_pymt_amt": round(random.uniform(40, 270), 2),
            "avg_mdcr_stdzd_amt": round(random.uniform(40, 270), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_telehealth_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_utilization_puf():
    rows = []
    geo_levels = ["National", "State", "County"]
    for i in range(TARGET_ROWS):
        geo = geo_levels[i % 3]
        h = make_hash(f"utilization_{geo}_{i}_{SOURCE_YEAR}")
        rows.append({
            "bene_geo_lvl": geo,
            "bene_geo_desc": f"Utilization Geography {i}",
            "bene_geo_cd": f"{i % 1000:05d}",
            "bene_age_lvl": "All" if i % 3 == 0 else ("LT65" if i % 3 == 1 else "GTE65"),
            "bene_demo_lvl": "All",
            "bene_demo_desc": "All Beneficiaries",
            "srvcs_per_bene": round(random.uniform(20, 80), 2),
            "ip_cvrd_stays_per_1000_benes": round(random.uniform(100, 400), 2),
            "avg_ip_los": round(random.uniform(3, 8), 2),
            "er_visits_per_1000_benes": round(random.uniform(200, 700), 2),
            "phy_visits_per_bene": round(random.uniform(5, 25), 2),
            "tot_mdcr_pymt_pc": round(random.uniform(7000, 16000), 2),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_utilization_puf_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


def generate_cms_part_d_prescriber():
    rows = []
    for i in range(TARGET_ROWS):
        gnrc, brnd = DRUGS[i % len(DRUGS)]
        h = make_hash(f"part_d_prescriber_{i}_{SOURCE_YEAR}")
        rows.append({
            "prscrbr_npi": f"{1000000000 + i:010d}",
            "prscrbr_last_org_name": f"Prescriber {i}",
            "prscrbr_first_name": f"Dr{i % 200}",
            "prscrbr_city": CITIES[i % len(CITIES)],
            "prscrbr_state_abrvtn": STATES[i % len(STATES)],
            "prscrbr_state_fips": f"{i % 50 + 1:02d}",
            "prscrbr_type": PROVIDER_TYPES[i % len(PROVIDER_TYPES)],
            "prscrbr_type_src": "T",
            "gnrc_name": gnrc,
            "brnd_name": brnd,
            "tot_clms": random.randint(11, 10000),
            "tot_30day_fills": round(random.uniform(11, 12000), 1),
            "tot_day_suply": random.randint(330, 365000),
            "tot_drug_cst": round(random.uniform(1000, 500000), 2),
            "tot_benes": random.randint(11, 5000),
            "ge65_sprsn_flag": None,
            "ge65_tot_clms": random.randint(5, 5000),
            "ge65_tot_30day_fills": round(random.uniform(5, 6000), 1),
            "ge65_tot_drug_cst": round(random.uniform(500, 250000), 2),
            "ge65_tot_day_suply": random.randint(150, 180000),
            "ge65_bene_sprsn_flag": None,
            "ge65_tot_benes": random.randint(5, 2500),
            "_source_year": SOURCE_YEAR,
            "_source_hash": h,
            "_source_file": f"cms_part_d_prescriber_{SOURCE_YEAR}.csv",
            "_loaded_at": LOADED_AT,
        })
    return rows


TABLES_TO_SEED = [
    ("cms_part_d_spending", generate_cms_part_d_spending),
    ("cms_part_b_spending", generate_cms_part_b_spending),
    ("cms_chronic_conditions", generate_cms_chronic_conditions),
    ("cms_claim_type_puf", generate_cms_claim_type_puf),
    ("cms_cost_reports_puf", generate_cms_cost_reports_puf),
    ("cms_cost_reports_puf_lines", generate_cms_cost_reports_puf_lines),
    ("cms_dme_puf", generate_cms_dme_puf),
    ("cms_dual_eligible", generate_cms_dual_eligible),
    ("cms_enrollment_puf", generate_cms_enrollment_puf),
    ("cms_geographic_variation", generate_cms_geographic_variation),
    ("cms_home_health", generate_cms_home_health),
    ("cms_hospice_puf", generate_cms_hospice_puf),
    ("cms_hospital_general_info", generate_cms_hospital_general_info),
    ("cms_imaging_puf", generate_cms_imaging_puf),
    ("cms_inpatient_puf", generate_cms_inpatient_puf),
    ("cms_lab_services", generate_cms_lab_services),
    ("cms_medicaid_drug_spending", generate_cms_medicaid_drug_spending),
    ("cms_medicare_advantage", generate_cms_medicare_advantage),
    ("cms_mental_health_puf", generate_cms_mental_health_puf),
    ("cms_nppes", generate_cms_nppes),
    ("cms_open_payments", generate_cms_open_payments),
    ("cms_opioid_puf", generate_cms_opioid_puf),
    ("cms_ordering_providers", generate_cms_ordering_providers),
    ("cms_outpatient_puf", generate_cms_outpatient_puf),
    ("cms_physician_puf", generate_cms_physician_puf),
    ("cms_physician_puf_services", generate_cms_physician_puf_services),
    ("cms_referring_providers", generate_cms_referring_providers),
    ("cms_snf_puf", generate_cms_snf_puf),
    ("cms_telehealth_puf", generate_cms_telehealth_puf),
    ("cms_utilization_puf", generate_cms_utilization_puf),
    ("cms_part_d_prescriber", generate_cms_part_d_prescriber),
]


def main():
    print(f"Connecting to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
    except Exception as e:
        print(f"ERROR: Cannot connect to database: {e}", file=sys.stderr)
        sys.exit(1)

    results = {}
    cur = conn.cursor()

    for table_name, generator in TABLES_TO_SEED:
        print(f"  Seeding hcs_raw.{table_name}...", end="", flush=True)
        try:
            # Check existing count
            cur.execute(f"SELECT COUNT(*) FROM hcs_raw.{table_name}")
            existing = cur.fetchone()[0]

            if existing >= TARGET_ROWS:
                print(f" SKIP ({existing} rows already exist)")
                results[table_name] = {"status": "skipped", "existing": existing, "inserted": 0}
                continue

            rows = generator()
            cols = [k for k in rows[0].keys() if k != "id"]
            col_str = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))
            sql = f"INSERT INTO hcs_raw.{table_name} ({col_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

            inserted = 0
            for row in rows:
                vals = [row[c] for c in cols]
                cur.execute(sql, vals)
                inserted += cur.rowcount

            conn.commit()
            cur.execute(f"SELECT COUNT(*) FROM hcs_raw.{table_name}")
            final_count = cur.fetchone()[0]
            print(f" OK ({inserted} inserted, {final_count} total)")
            results[table_name] = {"status": "ok", "inserted": inserted, "total": final_count}

        except Exception as e:
            conn.rollback()
            print(f" ERROR: {e}", file=sys.stderr)
            results[table_name] = {"status": "error", "error": str(e)}

    cur.close()
    conn.close()

    # Summary
    print("\n=== SEED SUMMARY ===")
    ok = [t for t, r in results.items() if r["status"] == "ok"]
    skipped = [t for t, r in results.items() if r["status"] == "skipped"]
    errors = [t for t, r in results.items() if r["status"] == "error"]
    print(f"OK: {len(ok)} tables")
    print(f"Skipped (already had data): {len(skipped)} tables")
    print(f"Errors: {len(errors)} tables")
    for t in errors:
        print(f"  ERROR {t}: {results[t]['error']}")
    return len(errors)


if __name__ == "__main__":
    sys.exit(main())
