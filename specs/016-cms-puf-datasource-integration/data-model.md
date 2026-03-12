# Data Model: CMS PUF Data Source Integration

**Revised**: 2026-03-11 | **Schema strategy**: Existing medallion schemas with `cms_` table prefix

## Schema Placement

All CMS data uses existing schemas. No new schemas created.

| Layer | Schema | Naming | Purpose |
|-------|--------|--------|---------|
| Raw | `raw` | `raw.cms_*` | Ingested CSV/API data with metadata columns |
| Bronze | `bronze` | `bronze.cms_*` | Type-cast, normalized columns |
| Silver | `silver` | `silver.cms_*` | Joined, deduplicated, entity-linked |
| Gold | `gold` | `gold.cms_*` | Aggregated analytics views (PostgREST-exposed) |
| Meta | `meta` | `meta.agent_*` | Agent execution logs, quarantine |

---

## Entities

### 1. Provider (NPI-keyed)

**Raw**: `raw.cms_nppes`
**Bronze**: `bronze.cms_nppes`
**Silver**: `silver.cms_provider_profile`
**Gold**: `gold.cms_provider_360`

| Column | Type | Source |
|--------|------|--------|
| `npi` | TEXT PK | NPPES |
| `entity_type` | TEXT | NPPES (individual/organization) |
| `name_first` | TEXT | NPPES |
| `name_last` | TEXT | NPPES |
| `credential` | TEXT | NPPES |
| `specialty_primary` | TEXT | NPPES taxonomy code |
| `specialty_secondary` | TEXT[] | NPPES |
| `practice_address` | JSONB | NPPES |
| `mailing_address` | JSONB | NPPES |
| `phone` | TEXT | NPPES |
| `gender` | TEXT | NPPES |
| `enumeration_date` | DATE | NPPES |
| `last_updated` | DATE | NPPES |

### 2. Prescribing Profile

**Raw**: `raw.cms_part_d_prescriber`
**Bronze**: `bronze.cms_part_d_prescriber`
**Silver**: joined into `silver.cms_provider_profile`

| Column | Type | Source |
|--------|------|--------|
| `npi` | TEXT FK | Part D Prescriber |
| `drug_name` | TEXT | Part D Prescriber |
| `generic_name` | TEXT | Part D Prescriber |
| `total_claims` | INTEGER | Part D Prescriber |
| `total_30_day_fills` | NUMERIC | Part D Prescriber |
| `total_drug_cost` | NUMERIC | Part D Prescriber |
| `total_beneficiaries` | INTEGER | Part D Prescriber |
| `year` | INTEGER | Part D Prescriber (partition key) |

### 3. Procedure Profile

**Raw**: `raw.cms_physician_puf`
**Bronze**: `bronze.cms_physician_puf`
**Silver**: joined into `silver.cms_provider_profile`

| Column | Type | Source |
|--------|------|--------|
| `npi` | TEXT FK | Physician PUF |
| `hcpcs_code` | TEXT | Physician PUF |
| `hcpcs_description` | TEXT | Physician PUF |
| `line_srvc_cnt` | NUMERIC | Physician PUF |
| `bene_unique_cnt` | INTEGER | Physician PUF |
| `avg_medicare_payment` | NUMERIC | Physician PUF |
| `year` | INTEGER | Physician PUF (partition key) |

### 4. Open Payments

**Raw**: `raw.cms_open_payments_general`, `raw.cms_open_payments_research`, `raw.cms_open_payments_ownership`
**Bronze**: `bronze.cms_open_payments`
**Silver**: joined into `silver.cms_provider_profile`

| Column | Type | Source |
|--------|------|--------|
| `record_id` | TEXT PK | Open Payments |
| `physician_npi` | TEXT FK | Open Payments |
| `payer_name` | TEXT | Open Payments |
| `payment_amount` | NUMERIC | Open Payments |
| `payment_nature` | TEXT | Open Payments |
| `payment_form` | TEXT | Open Payments |
| `payment_type` | TEXT | general/research/ownership |
| `program_year` | INTEGER | Open Payments |

### 5. Facility

**Raw**: `raw.cms_pos`, `raw.cms_hospital_general_info`, `raw.cms_hospital_quality`
**Bronze**: `bronze.cms_pos`, `bronze.cms_hospital_general_info`, `bronze.cms_hospital_quality`
**Silver**: `silver.cms_facility_profile`
**Gold**: `gold.cms_facility_360`

| Column | Type | Source |
|--------|------|--------|
| `ccn` | TEXT PK | POS/Hospital Info |
| `facility_name` | TEXT | POS |
| `facility_type` | TEXT | POS |
| `address` | JSONB | POS |
| `state` | TEXT | POS |
| `county` | TEXT | POS |
| `bed_count` | INTEGER | POS |
| `ownership_type` | TEXT | POS |
| `star_rating` | INTEGER | Hospital Quality |
| `mortality_score` | NUMERIC | Hospital Quality |
| `readmission_score` | NUMERIC | Hospital Quality |
| `patient_experience_score` | NUMERIC | Hospital Quality |

### 6. Health System (Agent-Enriched)

**Source**: `bronze.cms_pecos` + `bronze.cms_chow`
**Silver**: `silver.cms_health_system_hierarchy`
**Agent**: IDNHierarchy

| Column | Type | Source |
|--------|------|--------|
| `system_id` | TEXT PK | Agent-generated |
| `system_name` | TEXT | Agent-inferred from PECOS |
| `parent_system_id` | TEXT FK (self) | Agent-inferred from CHOW |
| `member_ccns` | TEXT[] | Agent-inferred |
| `hierarchy_level` | INTEGER | Agent-inferred (0=top) |
| `confidence_score` | NUMERIC | Agent output |
| `agent_version` | TEXT | Agent metadata |

### 7. Drug Market

**Raw**: `raw.cms_ndc`, `raw.cms_part_d_spending`, `raw.cms_part_b_spending`, `raw.cms_formulary`
**Silver**: `silver.cms_drug_market`
**Gold**: `gold.cms_drug_market_profile`

| Column | Type | Source |
|--------|------|--------|
| `ndc` | TEXT PK | NDC Directory |
| `drug_name` | TEXT | NDC |
| `generic_name` | TEXT | NDC |
| `labeler_name` | TEXT | NDC |
| `route` | TEXT | NDC |
| `dosage_form` | TEXT | NDC |
| `part_d_total_spending` | NUMERIC | Part D Spending |
| `part_d_total_claims` | INTEGER | Part D Spending |
| `part_b_total_spending` | NUMERIC | Part B Spending |
| `formulary_coverage_pct` | NUMERIC | Formulary (% of plans covering) |
| `rbcs_category` | TEXT | RBCS |
| `usp_category` | TEXT | USP |

### 8. Geographic Analytics

**Raw**: `raw.cms_geographic_variation`, `raw.cms_chronic_conditions`, `raw.cms_post_acute`
**Silver**: `silver.cms_geographic`
**Gold**: `gold.cms_market_analytics`

| Column | Type | Source |
|--------|------|--------|
| `state` | TEXT | Geographic Variation |
| `county` | TEXT | Geographic Variation |
| `fips_code` | TEXT | Geographic Variation |
| `total_beneficiaries` | INTEGER | Geographic Variation |
| `per_capita_spending` | NUMERIC | Geographic Variation |
| `diabetes_prevalence` | NUMERIC | Chronic Conditions |
| `heart_failure_prevalence` | NUMERIC | Chronic Conditions |
| `copd_prevalence` | NUMERIC | Chronic Conditions |
| `snf_episodes` | INTEGER | Post-Acute |
| `hha_episodes` | INTEGER | Post-Acute |

### 9. Provider Network (Agent-Enriched)

**Source**: `bronze.cms_physician_puf` (shared patients)
**Silver**: `silver.cms_referral_edges`
**Gold**: `gold.cms_provider_network`
**Agent**: ReferralNetwork

| Column | Type | Source |
|--------|------|--------|
| `source_npi` | TEXT FK | Agent-inferred |
| `target_npi` | TEXT FK | Agent-inferred |
| `relationship_type` | TEXT | Agent-inferred (referral, shared_patient, co_practice) |
| `strength_score` | NUMERIC | Agent output (0.0–1.0) |
| `shared_patient_count` | INTEGER | Derived from PUF |
| `confidence_score` | NUMERIC | Agent output |

### 10. Agent Execution Log (Append-Only)

**Schema**: `meta.agent_execution_log`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` |
| `agent_name` | TEXT NOT NULL | |
| `agent_version` | TEXT NOT NULL | |
| `started_at` | TIMESTAMPTZ NOT NULL | |
| `completed_at` | TIMESTAMPTZ | |
| `status` | TEXT NOT NULL | RUNNING, COMPLETED, FAILED |
| `records_input` | INTEGER | |
| `records_enriched` | INTEGER | |
| `records_quarantined` | INTEGER | |
| `error_message` | TEXT | |
| `model_used` | TEXT NOT NULL | LiteLLM alias |
| `cost_usd` | NUMERIC(10,4) | |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT now() |

**Permissions**: INSERT + SELECT only for `api_user`. No UPDATE or DELETE (dk-canon audit integrity).

### 11. Agent Quarantine

**Schema**: `meta.agent_quarantine`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` |
| `agent_name` | TEXT NOT NULL | |
| `execution_id` | UUID FK | → `meta.agent_execution_log` |
| `record_data` | JSONB NOT NULL | The quarantined record |
| `reason` | TEXT NOT NULL | Why confidence was low |
| `confidence_score` | NUMERIC | |
| `status` | TEXT NOT NULL | PENDING, RESOLVED, REJECTED |
| `resolved_by` | TEXT | User who reviewed |
| `resolved_at` | TIMESTAMPTZ | |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT now() |

---

## Reference Tables

### `silver.ref_drg_service_line`

| Column | Type | Source |
|--------|------|--------|
| `drg_code` | TEXT PK | CMS DRG list |
| `drg_description` | TEXT | CMS |
| `service_line` | TEXT | Agent: ServiceLineInference |
| `confidence_score` | NUMERIC | Agent output |

### `silver.ref_hcpcs_equipment`

| Column | Type | Source |
|--------|------|--------|
| `hcpcs_code` | TEXT PK | CMS HCPCS |
| `hcpcs_description` | TEXT | CMS |
| `equipment_category` | TEXT | Agent: EquipmentInventoryInference |
| `confidence_score` | NUMERIC | Agent output |

### `silver.ref_nucc_taxonomy`

| Column | Type | Source |
|--------|------|--------|
| `taxonomy_code` | TEXT PK | NUCC |
| `classification` | TEXT | NUCC |
| `specialization` | TEXT | NUCC |
| `grouping` | TEXT | NUCC |

---

## Relationships

```
Provider (NPI) ─1:N─→ Prescribing Profile
Provider (NPI) ─1:N─→ Procedure Profile
Provider (NPI) ─1:N─→ Open Payments
Provider (NPI) ─N:N─→ Provider Network (via referral edges)
Facility (CCN) ─N:1─→ Health System (via hierarchy)
Drug (NDC) ──────────→ Drug Market (spending, formulary)
Geographic (FIPS) ───→ Market Analytics (chronic, post-acute)
```

---

## Partitioning Strategy

| Table | Partition key | Rows/year | Partitions |
|-------|-------------|-----------|-----------|
| `raw.cms_part_d_prescriber` | `year` | ~25M | 1 per year (2019–current) |
| `raw.cms_physician_puf` | `year` | ~10M | 1 per year (2019–current) |

All other tables are small enough for standard indexing.

---

## Validation Rules

| Entity | Rule |
|--------|------|
| Provider | NPI must be 10-digit numeric string |
| Facility | CCN must be 6-character alphanumeric |
| Drug | NDC must match `NNNNN-NNNN-NN` format (11-digit) |
| Agent output | `confidence_score` must be 0.0–1.0 |
| Agent log | No UPDATE/DELETE permitted |
