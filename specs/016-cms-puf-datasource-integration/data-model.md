# Data Model: CMS PUF Data Source Integration

**Phase 1 Output** | **Date**: 2026-03-01

## Entities

### 1. Provider

**Canonical Key**: `npi` (VARCHAR(10), Luhn-validated)
**Source of Truth**: NPPES (demographics), supplemented by Care Compare, Physician PUF, Part D, Open Payments
**Entity Types**: `individual` (Type 1 NPI), `organization` (Type 2 NPI) — stored as `entity_type TEXT`

#### Raw Layer: `raw.cms_nppes`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | UUID | NOT NULL | PK, `gen_random_uuid()` |
| request_id | VARCHAR(100) | YES | MCP request correlation ID |
| request_timestamp | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()` |
| api_endpoint | VARCHAR(500) | YES | API URL for MCP path |
| request_params | JSONB | YES | MCP request parameters |
| response_status | INTEGER | NOT NULL | `DEFAULT 200` |
| response_body | JSONB | NOT NULL | Full API response |
| processed_to_bronze | BOOLEAN | NOT NULL | `DEFAULT FALSE` |
| ingested_at | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()` |
| npi | VARCHAR(10) | YES | Direct loader column |
| entity_type | VARCHAR(20) | YES | Direct loader column |
| provider_name | VARCHAR(500) | YES | Direct loader column |

**Indexes**: `idx_cms_nppes_npi` ON (npi), `idx_cms_nppes_processed` ON (processed_to_bronze) WHERE processed_to_bronze = FALSE
**Unique Constraint**: `uq_cms_nppes_npi` ON (npi) — loader path upsert

#### Bronze Layer: `bronze.cms_nppes`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | UUID | NOT NULL | PK |
| raw_id | UUID | NOT NULL | FK → raw.cms_nppes.id |
| npi | VARCHAR(10) | NOT NULL | National Provider Identifier |
| entity_type | VARCHAR(20) | NOT NULL | 'individual' or 'organization' |
| provider_name | VARCHAR(500) | NOT NULL | Legal business name or provider name |
| credential | VARCHAR(100) | YES | MD, DO, NP, etc. |
| specialty_code | VARCHAR(20) | YES | Primary taxonomy code |
| specialty_description | VARCHAR(300) | YES | Taxonomy description |
| address_line1 | VARCHAR(300) | YES | Practice location |
| address_line2 | VARCHAR(300) | YES | Practice location line 2 |
| city | VARCHAR(100) | YES | Practice city |
| state | VARCHAR(2) | YES | Practice state |
| zip | VARCHAR(10) | YES | Practice ZIP |
| phone | VARCHAR(20) | YES | Practice phone |
| enumeration_date | DATE | YES | Date NPI was assigned |
| deactivation_date | DATE | YES | NULL if active |
| reactivation_date | DATE | YES | NULL if never deactivated |
| raw_json | JSONB | YES | Full response for extension |
| source | VARCHAR(50) | NOT NULL | `'cms_nppes'` |
| processed_to_silver | BOOLEAN | NOT NULL | `DEFAULT FALSE` |
| created_at | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()` |

#### Silver Layer: `silver.providers`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| npi | VARCHAR(10) | NOT NULL | PK |
| entity_type | TEXT | NOT NULL | 'individual' or 'organization' |
| provider_name | VARCHAR(500) | NOT NULL | From NPPES (precedence 1) |
| credential | VARCHAR(100) | YES | MD, DO, NP, etc. |
| specialty_code | VARCHAR(20) | YES | Primary taxonomy code |
| specialty_description | VARCHAR(300) | YES | From NUCC taxonomy |
| address_line1 | VARCHAR(300) | YES | Practice address |
| city | VARCHAR(100) | YES | Practice city |
| state | VARCHAR(2) | YES | Practice state |
| zip | VARCHAR(10) | YES | Practice ZIP |
| phone | VARCHAR(20) | YES | Practice phone |
| enumeration_date | DATE | YES | NPI assignment date |
| deactivation_date | DATE | YES | NULL if active |
| mips_final_score | NUMERIC(5,2) | YES | From Care Compare |
| mips_attestation | VARCHAR(50) | YES | From Care Compare |
| total_services | INTEGER | YES | From Physician PUF Summary |
| total_beneficiaries | INTEGER | YES | From Physician PUF Summary |
| total_charges | NUMERIC(14,2) | YES | From Physician PUF Summary |
| phone_verified | BOOLEAN | YES | From ContactVerification agent |
| address_verified | BOOLEAN | YES | From ContactVerification agent |
| verification_date | TIMESTAMPTZ | YES | Last verification timestamp |
| primary_source | VARCHAR(50) | NOT NULL | Source of demographics |
| source_precedence | INTEGER | NOT NULL | 1=NPPES, 2=CareCompare, 3=PhysicianPUF |
| updated_at | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()` |

**Resolution Rule**: `DISTINCT ON (npi) ORDER BY source_precedence ASC` — NPPES wins for demographics

#### Gold Layer: `gold.provider_profile`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| npi | VARCHAR(10) | NOT NULL | PK |
| entity_type | TEXT | NOT NULL | 'individual' or 'organization' |
| provider_name | VARCHAR(500) | NOT NULL | Legal name |
| credential | VARCHAR(100) | YES | Credential string |
| specialty | VARCHAR(300) | YES | Primary specialty |
| address | JSONB | YES | `{line1, city, state, zip}` |
| phone | VARCHAR(20) | YES | Practice phone |
| mips_score | NUMERIC(5,2) | YES | MIPS final score |
| top_drugs | JSONB | YES | Top 10 prescribed drugs (from prescribing_profiles) |
| top_procedures | JSONB | YES | Top 10 procedures (from procedure_profiles) |
| total_payments | NUMERIC(14,2) | YES | Total Open Payments received |
| top_payers | JSONB | YES | Top 5 payers by amount |
| payment_summary | JSONB | YES | `{general, research, ownership}` totals |
| phone_verified | BOOLEAN | YES | Contact verification status |
| address_verified | BOOLEAN | YES | Address verification status |
| _generation_source | TEXT | NOT NULL | Provenance tracking |
| _refreshed_at | TIMESTAMPTZ | NOT NULL | Last gold refresh |
| _source_freshness | JSONB | NOT NULL | Per-source freshness timestamps |

**JSONB Structure — `top_drugs`**:
```json
[
  {
    "drug_name": "atorvastatin",
    "generic_name": "atorvastatin calcium",
    "total_claims": 1234,
    "total_cost": 56789.12,
    "beneficiary_count": 890,
    "year": 2023
  }
]
```

**JSONB Structure — `top_procedures`**:
```json
[
  {
    "hcpcs_code": "99213",
    "description": "Office visit, established patient",
    "total_services": 4567,
    "total_charges": 123456.78,
    "year": 2023
  }
]
```

---

### 2. Facility

**Canonical Key**: `ccn` (VARCHAR(6), CMS Certification Number)
**Source of Truth**: Provider of Services (demographics), supplemented by Hospital Quality, Inpatient PUF, PECOS/CHOW (affiliation)

#### Raw Layer: `raw.cms_provider_of_services`

Standard MCP raw pattern (id, request_id, request_timestamp, api_endpoint, request_params, response_status, response_body, processed_to_bronze, ingested_at) plus:

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| ccn | VARCHAR(6) | YES | Direct loader column |
| facility_name | VARCHAR(500) | YES | Direct loader column |
| facility_type | VARCHAR(100) | YES | Direct loader column |

#### Silver Layer: `silver.healthcare_facilities`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| ccn | VARCHAR(6) | NOT NULL | PK |
| facility_name | VARCHAR(500) | NOT NULL | Facility legal name |
| facility_type | VARCHAR(100) | YES | Hospital, SNF, HHA, etc. |
| address | JSONB | YES | `{line1, city, state, zip}` |
| bed_count | INTEGER | YES | Licensed beds |
| ownership_type | VARCHAR(100) | YES | Government, Non-profit, For-profit |
| teaching_status | BOOLEAN | YES | Teaching hospital flag |
| emergency_services | BOOLEAN | YES | Has ED |
| organization_npi | VARCHAR(10) | YES | FK → silver.health_systems |
| system_name | VARCHAR(500) | YES | Parent health system |
| magnet_status | BOOLEAN | YES | From ANCC |
| magnet_designation_date | DATE | YES | From ANCC |
| overall_star_rating | INTEGER | YES | 1-5, from Hospital Quality |
| updated_at | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()` |

#### Gold Layer: `gold.facility_profile`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| ccn | VARCHAR(6) | NOT NULL | PK |
| facility_name | VARCHAR(500) | NOT NULL | Legal name |
| facility_type | VARCHAR(100) | YES | Type classification |
| address | JSONB | YES | Location |
| bed_count | INTEGER | YES | Licensed beds |
| ownership_type | VARCHAR(100) | YES | Ownership category |
| teaching_status | BOOLEAN | YES | Teaching flag |
| overall_star_rating | INTEGER | YES | CMS star rating |
| quality_scores | JSONB | YES | `{mortality, readmission, safety, experience, timely}` |
| top_drgs | JSONB | YES | Top 10 DRGs by volume |
| case_mix_index | NUMERIC(5,3) | YES | Weighted CMI |
| system_affiliation | JSONB | YES | `{org_npi, system_name, hierarchy_level}` |
| service_lines | JSONB | YES | Agent-inferred service lines |
| magnet_status | BOOLEAN | YES | ANCC designation |
| staffing | JSONB | YES | Agent-decomposed staffing data |
| _generation_source | TEXT | NOT NULL | Provenance |
| _refreshed_at | TIMESTAMPTZ | NOT NULL | Last refresh |
| _source_freshness | JSONB | NOT NULL | Per-source freshness |

---

### 3. Prescribing Profile

**Canonical Key**: `(npi, drug_name, year)`
**Source**: Part D Prescribers PUF

#### Raw Layer: `raw.cms_part_d_prescribers` (PARTITIONED BY RANGE year)

Standard MCP raw pattern plus year-partitioned:

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| year | INTEGER | NOT NULL | Partition key (2015-2025) |
| npi | VARCHAR(10) | YES | Provider NPI |
| drug_name | VARCHAR(500) | YES | Generic drug name |

**Partitions**: `raw.cms_part_d_prescribers_y2015` through `raw.cms_part_d_prescribers_y2025`

#### Silver Layer: `silver.prescribing_profiles`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| npi | VARCHAR(10) | NOT NULL | PK (composite) |
| drug_name | VARCHAR(500) | NOT NULL | PK (composite) |
| year | INTEGER | NOT NULL | PK (composite) |
| generic_name | VARCHAR(500) | YES | Generic drug name |
| brand_name | VARCHAR(500) | YES | Brand drug name |
| total_claims | INTEGER | YES | Total Rx claims |
| total_30day_fills | NUMERIC(10,2) | YES | Total 30-day fill equivalents |
| total_drug_cost | NUMERIC(14,2) | YES | Total drug cost |
| total_beneficiaries | INTEGER | YES | Unique beneficiaries |
| suppressed | BOOLEAN | NOT NULL | `DEFAULT FALSE` (CMS suppression flag) |
| updated_at | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()` |

---

### 4. Procedure Profile

**Canonical Key**: `(npi, hcpcs_code, year)`
**Source**: Physician/Supplier PUF

#### Raw Layer: `raw.cms_physician_puf` (PARTITIONED BY RANGE year)

Standard MCP raw pattern plus year-partitioned.

#### Silver Layer: `silver.procedure_profiles`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| npi | VARCHAR(10) | NOT NULL | PK (composite) |
| hcpcs_code | VARCHAR(10) | NOT NULL | PK (composite) |
| year | INTEGER | NOT NULL | PK (composite) |
| hcpcs_description | VARCHAR(500) | YES | Procedure description |
| place_of_service | VARCHAR(1) | YES | F=Facility, O=Office |
| total_services | INTEGER | YES | Services rendered |
| total_beneficiaries | INTEGER | YES | Unique beneficiaries |
| total_charges | NUMERIC(14,2) | YES | Submitted charges |
| total_medicare_payment | NUMERIC(14,2) | YES | Medicare allowed |
| suppressed | BOOLEAN | NOT NULL | `DEFAULT FALSE` |
| updated_at | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()` |

---

### 5. Open Payments

**Canonical Key**: `record_id`
**Source**: CMS Open Payments

#### Silver Layer: `silver.open_payments`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| record_id | VARCHAR(50) | NOT NULL | PK |
| npi | VARCHAR(10) | NOT NULL | Covered recipient NPI |
| payment_type | VARCHAR(20) | NOT NULL | 'general', 'research', 'ownership' |
| payer_name | VARCHAR(500) | NOT NULL | Company name |
| amount | NUMERIC(14,2) | NOT NULL | Payment amount |
| date_of_payment | DATE | YES | Payment date |
| nature_of_payment | VARCHAR(200) | YES | Payment category |
| dispute_status | VARCHAR(20) | YES | 'disputed', 'resolved', NULL |
| program_year | INTEGER | NOT NULL | Year of payment |
| updated_at | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()` |

---

### 6. Health System (IDN)

**Canonical Key**: `organization_npi` (Type 2 NPI)
**Sources**: PECOS + CHOW + Facility Affiliation

#### Silver Layer: `silver.health_systems`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| organization_npi | VARCHAR(10) | NOT NULL | PK (Type 2 NPI) |
| system_name | VARCHAR(500) | NOT NULL | Legal business name |
| parent_org_npi | VARCHAR(10) | YES | FK self-reference (multi-level) |
| hierarchy_level | INTEGER | NOT NULL | 1=top, 2=sub, 3=facility |
| affiliated_facilities | JSONB | YES | Array of CCNs |
| total_facilities | INTEGER | YES | Count of affiliated facilities |
| total_beds | INTEGER | YES | Sum of beds across facilities |
| geographic_footprint | JSONB | YES | States/regions covered |
| chow_history | JSONB | YES | Change of ownership timeline |
| confidence_source | VARCHAR(50) | NOT NULL | 'deterministic', 'heuristic', 'agent' |
| confidence_score | NUMERIC(3,2) | YES | Agent confidence (NULL if deterministic) |
| updated_at | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()` |

---

### 7. Drug Market

**Canonical Key**: `(drug_name, year)`
**Sources**: Part D Spending + Part B Spending + FDA NDC + Formulary + USP + RBCS

#### Gold Layer: `gold.drug_market_profile`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| drug_name | VARCHAR(500) | NOT NULL | PK (composite) |
| generic_name | VARCHAR(500) | NOT NULL | PK (composite) |
| part_d_total_spending | NUMERIC(14,2) | YES | Medicare Part D total |
| part_d_beneficiaries | INTEGER | YES | Part D beneficiary count |
| part_d_claims | INTEGER | YES | Part D claim count |
| part_d_cost_per_unit | NUMERIC(10,4) | YES | Part D cost/unit |
| part_b_avg_payment | NUMERIC(10,4) | YES | Part B avg payment/dose |
| part_b_utilization | INTEGER | YES | Part B utilization count |
| formulary_coverage_pct | NUMERIC(5,2) | YES | % of Part D plans covering |
| tier_distribution | JSONB | YES | `{tier1: 10, tier2: 25, ...}` |
| ndc_details | JSONB | YES | Manufacturer, forms, strengths |
| usp_class | VARCHAR(200) | YES | USP therapeutic class |
| atc_code | VARCHAR(20) | YES | WHO ATC code |
| rbcs_category | VARCHAR(200) | YES | BETOS classification |
| spending_trend | JSONB | YES | Year-over-year spending array |
| top_prescribers | JSONB | YES | Top 10 NPIs by claims |
| _generation_source | TEXT | NOT NULL | Provenance |
| _refreshed_at | TIMESTAMPTZ | NOT NULL | Last refresh |
| _source_freshness | JSONB | NOT NULL | Per-source freshness |

---

### 8. Geographic Analytics

**Canonical Key**: `(geo_level, geo_code, year)`
**Sources**: Geographic Variation PUF + Chronic Conditions PUF

#### Gold Layer: `gold.market_analytics`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| geo_level | VARCHAR(20) | NOT NULL | PK: 'state', 'hrr', 'county' |
| geo_code | VARCHAR(20) | NOT NULL | PK: FIPS code or HRR ID |
| year | INTEGER | NOT NULL | PK |
| geo_name | VARCHAR(200) | YES | State/HRR/County name |
| total_beneficiaries | INTEGER | YES | Medicare beneficiary count |
| demographics | JSONB | YES | Age/sex/race distribution |
| spending_per_capita | JSONB | YES | `{total, ip, op, snf, hha, hospice, dme}` |
| chronic_conditions | JSONB | YES | `{diabetes: 0.28, heart_failure: 0.14, ...}` |
| provider_density | JSONB | YES | NPIs per 100K by specialty |
| facility_landscape | JSONB | YES | `{hospitals, beds, avg_quality}` |
| _generation_source | TEXT | NOT NULL | Provenance |
| _refreshed_at | TIMESTAMPTZ | NOT NULL | Last refresh |
| _source_freshness | JSONB | NOT NULL | Per-source freshness |

---

### 9. Provider Network

**Canonical Key**: `(source_npi, dest_npi, relationship_type)`
**Source**: Agent-produced (ReferralNetworkInferenceAgent)

#### Gold Layer: `gold.provider_network`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| source_npi | VARCHAR(10) | NOT NULL | PK (composite) |
| dest_npi | VARCHAR(10) | NOT NULL | PK (composite) |
| relationship_type | VARCHAR(50) | NOT NULL | PK: 'referral', 'affiliation', 'group_practice' |
| confidence_score | NUMERIC(3,2) | NOT NULL | 0.00-1.00 |
| evidence_sources | JSONB | YES | Which data sources contributed |
| strength | NUMERIC(8,4) | YES | Relationship strength metric |
| bidirectional | BOOLEAN | NOT NULL | `DEFAULT FALSE` |
| needs_review | BOOLEAN | NOT NULL | `DEFAULT FALSE` |
| _generation_source | TEXT | NOT NULL | Provenance |
| _refreshed_at | TIMESTAMPTZ | NOT NULL | Last refresh |
| _source_freshness | JSONB | NOT NULL | Per-source freshness |

**Downstream filter**: `WHERE confidence_score >= 0.50`

---

### 10. Agent Execution Log

**Table**: `meta.agent_execution_log`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | UUID | NOT NULL | PK |
| agent_name | VARCHAR(100) | NOT NULL | e.g., 'service_line_inference' |
| execution_start | TIMESTAMPTZ | NOT NULL | Run start time |
| execution_end | TIMESTAMPTZ | YES | Run end time |
| status | VARCHAR(20) | NOT NULL | 'running', 'completed', 'failed' |
| records_processed | INTEGER | NOT NULL | `DEFAULT 0` |
| records_written | INTEGER | NOT NULL | `DEFAULT 0` |
| records_quarantined | INTEGER | NOT NULL | `DEFAULT 0` |
| model_used | VARCHAR(100) | NOT NULL | e.g., 'claude-haiku-4-5-20251001' |
| total_input_tokens | INTEGER | YES | API token count |
| total_output_tokens | INTEGER | YES | API token count |
| estimated_cost_usd | NUMERIC(8,4) | YES | Estimated cost |
| error_message | TEXT | YES | Error details if failed |
| created_at | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()` |

---

### 11. Agent Quarantine

**Table**: `meta.agent_quarantine`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | UUID | NOT NULL | PK |
| agent_name | VARCHAR(100) | NOT NULL | Source agent |
| entity_key | VARCHAR(100) | NOT NULL | NPI, CCN, etc. |
| entity_type | VARCHAR(50) | NOT NULL | 'provider', 'facility', etc. |
| raw_llm_output | TEXT | NOT NULL | Full LLM response |
| confidence_score | NUMERIC(3,2) | NOT NULL | Score that triggered quarantine |
| rejection_reason | VARCHAR(200) | NOT NULL | Why quarantined |
| review_status | VARCHAR(20) | NOT NULL | `DEFAULT 'pending'` |
| reviewed_by | VARCHAR(100) | YES | Reviewer identity |
| reviewed_at | TIMESTAMPTZ | YES | Review timestamp |
| created_at | TIMESTAMPTZ | NOT NULL | `DEFAULT NOW()` |

---

## Relationships

```text
silver.providers (npi)
  ├── 1:N → silver.prescribing_profiles (npi)
  ├── 1:N → silver.procedure_profiles (npi)
  ├── 1:N → silver.open_payments (npi)
  ├── N:1 → silver.health_systems (organization_npi)
  └── 1:1 → gold.provider_profile (npi)

silver.healthcare_facilities (ccn)
  ├── N:1 → silver.health_systems (organization_npi)
  ├── 1:N → silver.facility_service_lines (ccn)
  └── 1:1 → gold.facility_profile (ccn)

silver.health_systems (organization_npi)
  ├── 1:N → silver.healthcare_facilities (via organization_npi)
  └── self-referencing (parent_org_npi → organization_npi)

silver.drug_market (drug_name, year)
  └── 1:1 → gold.drug_market_profile (drug_name, generic_name)

gold.provider_network (source_npi, dest_npi, relationship_type)
  ├── N:1 → silver.providers (source_npi → npi)
  └── N:1 → silver.providers (dest_npi → npi)
```

## Validation Rules

1. **NPI Validation**: 10-digit numeric string, passes Luhn check digit algorithm
2. **CCN Validation**: 6-character alphanumeric (first 2 = state code, next 4 = facility sequence)
3. **Year Validation**: Integer, range 2015-2025 for current data
4. **CMS Suppression**: Rows with <11 beneficiaries have NULL numeric fields + `suppressed = TRUE`
5. **Confidence Score**: NUMERIC(3,2), range 0.00-1.00; ≥0.80 = direct write, 0.50-0.79 = needs_review, <0.50 = quarantine
6. **Payment Amount**: NUMERIC(14,2), rounded to 2 decimal places
7. **Entity Type**: TEXT, must be exactly `'individual'` or `'organization'`
8. **Gold Provenance**: `_generation_source` TEXT, values: `'sql_aggregate'`, `'agent:{agent_name}'`, or `'sql_aggregate+agent:{agent_name}'`

## State Transitions

### Agent Output Lifecycle

```text
pending (meta.agent_quarantine, review_status='pending')
  → approved (written to silver/gold, quarantine entry updated)
  → rejected (quarantine entry updated, data discarded)
```

### Provider Verification Status

```text
unverified (phone_verified=NULL, address_verified=NULL)
  → verified (phone_verified=TRUE, address_verified=TRUE)
  → partial (one TRUE, one FALSE or NULL)
  → mismatch (phone_verified=FALSE or address_verified=FALSE)
```

### Data Freshness States

```text
fresh (staleness < threshold)
  → stale (staleness >= threshold, alert triggered)
  → critical (staleness >= 2x threshold)
```
