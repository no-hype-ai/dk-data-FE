# TAVR Data Infrastructure - Pipeline Status & TODOs

> Last Updated: 2026-01-15
> Feature: 001-data-layer-postgrest-gitops

## Overview

This document tracks the current status of the TAVR data pipeline, identifies gaps, and outlines remaining work items.

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DATA SOURCES                                   │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────────────┤
│ CMS Hospital│ CMS Medicare│ CMS Cost    │ HRSA        │ ACC TVC         │
│ Info        │ Inpatient   │ Reports     │ Shortage    │ Certifications  │
│ ✅ 5,421    │ ✅ 1,179    │ ✅ 6,086    │ ✅ 73,056   │ ⚠️ No source    │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┴────────┬────────┘
       │             │             │             │               │
       ▼             ▼             ▼             ▼               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           RAW LAYER                                      │
│  raw.cms_hospital_info, raw.cms_medicare_inpatient, raw.cms_cost_reports │
│  raw.hrsa_shortage_areas, raw.acc_tvc_certification                      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ SQLMesh
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         STAGING LAYER                                    │
│  staging.hospitals ✅        staging.tavr_volumes ✅                     │
│  staging.certifications ⚠️   staging.geographic_designations ✅          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           MART LAYER                                     │
│  mart.dim_hospital ✅        mart.fact_tavr_program ✅                   │
│  mart.fact_financial_metrics ✅                                          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         SCORING LAYER                                    │
│  scoring.target_scores ✅    scoring.score_factors ✅                    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        TARGETING LAYER                                   │
│  targeting.targeting_scores ✅  targeting.targeting_summary ✅           │
│  (Requires internal business data - see below)                           │
└─────────────────────────────────────────────────────────────────────────┘
```

## Current Status by Layer

### Raw Layer

| Table | Records | Source | Status | Notes |
|-------|---------|--------|--------|-------|
| `raw.cms_hospital_info` | 5,421 | CMS Provider Data | ✅ Complete | Hospital demographics, ratings |
| `raw.cms_medicare_inpatient` | 3,494 | CMS Data Portal | ✅ Complete | TAVR DRG 266/267, FY2021-2023 |
| `raw.cms_cost_reports` | 6,086 | CMS HCRIS | ✅ Complete | Financial metrics, FY2023 |
| `raw.hrsa_shortage_areas` | 73,056 | HRSA Data Warehouse | ✅ Complete | Primary Care HPSAs |
| `raw.acc_tvc_certification` | 0 | ACC Website | ⚠️ No Source | No public API/CSV available |

### Staging Layer

| Table | Records | Status | Notes |
|-------|---------|--------|-------|
| `staging.hospitals` | 5,421 | ✅ Complete | Cleaned hospital master data |
| `staging.tavr_volumes` | 3,494 | ✅ Complete | TAVR volumes by hospital/DRG/year (FY2021-2023) |
| `staging.certifications` | 0 | ⚠️ Blocked | Depends on ACC TVC data |
| `staging.geographic_designations` | 5,421 | ✅ Complete | 92% HPSA match rate |

### Mart Layer

| Table | Records | Status | Notes |
|-------|---------|--------|-------|
| `mart.dim_hospital` | 5,421 | ✅ Complete | Hospital dimension with bed_count |
| `mart.fact_tavr_program` | 2,069 | ✅ Complete | TAVR programs FY2021-2023 with YoY growth |
| `mart.fact_financial_metrics` | 4,981 | ✅ Complete | Operating margins, quartiles |

### Scoring Layer

| Table | Records | Status | Notes |
|-------|---------|--------|-------|
| `scoring.target_scores` | 5,421 | ✅ Complete | Hospital scoring factors |
| `scoring.score_factors` | 75,894 | ✅ Complete | Detailed score breakdown |

### Targeting Layer

| Table | Records | Status | Notes |
|-------|---------|--------|-------|
| `targeting.targeting_scores` | 704 | ✅ Functional | 84 Medium, 427 Low, 193 DNQ (need internal data for High) |
| `targeting.targeting_summary` | 2 | ✅ Functional | Summary aggregations |
| `targeting.volume_history` | 2,069 | ✅ Complete | TAVR volumes FY2021-2023 with YoY growth |

---

## Internal Business Data Tables (Targeting Schema)

These tables require data from internal systems (CRM, sales, contracts).

### targeting.biome_relationships
**Purpose:** Track Edwards Biome platform adoption status per hospital

| Column | Type | Description |
|--------|------|-------------|
| `hospital_id` | VARCHAR(10) | Primary key |
| `is_current_client` | BOOLEAN | Active customer flag |
| `echo_surveillance_active` | BOOLEAN | Echo module enabled |
| `workflow_active` | BOOLEAN | Workflow module enabled |
| `analytics_active` | BOOLEAN | Analytics module enabled |
| `pilot_phase` | VARCHAR(50) | 'Phase 1', 'Phase 2', etc. |
| `contract_type` | VARCHAR(50) | 'Full', 'Pilot', 'Trial' |
| `phase_2_tokens_needed` | INTEGER | Tokens for expansion |

**Data Source:** CRM / Contract Management System

### targeting.sales_coverage
**Purpose:** Sales team territory assignments

| Column | Type | Description |
|--------|------|-------------|
| `hospital_id` | VARCHAR(10) | Primary key |
| `regional_director` | VARCHAR(100) | Assigned RD |
| `area_vp` | VARCHAR(100) | Assigned AVP |
| `territory` | VARCHAR(100) | Territory name |
| `expressed_interest` | BOOLEAN | Interest in Biome |
| `last_contact_date` | DATE | Most recent contact |

**Data Source:** CRM / Sales Territory System

### targeting.emr_systems
**Purpose:** Hospital EMR information for integration planning

| Column | Type | Description |
|--------|------|-------------|
| `hospital_id` | VARCHAR(10) | Primary key |
| `primary_emr` | VARCHAR(100) | 'Epic', 'Cerner', etc. |
| `emr_version` | VARCHAR(50) | Version number |
| `integration_ready` | BOOLEAN | Ready for integration |

**Data Source:** Sales Intelligence / Manual Research

### targeting.champions
**Purpose:** Key clinical and administrative contacts

| Column | Type | Description |
|--------|------|-------------|
| `hospital_id` | VARCHAR(10) | Foreign key |
| `champion_type` | VARCHAR(50) | 'Clinical', 'Administrative' |
| `champion_name` | VARCHAR(200) | Contact name |
| `title` | VARCHAR(200) | Job title |
| `engagement_level` | VARCHAR(50) | 'Advocating', 'Interested', 'Passive' |

**Data Source:** CRM / Sales Activity Tracking

### targeting.volume_history
**Purpose:** Historical TAVR volumes for growth scoring

| Column | Type | Description |
|--------|------|-------------|
| `hospital_id` | VARCHAR(10) | Composite PK |
| `fiscal_year` | INTEGER | Composite PK |
| `total_tavr_volume` | INTEGER | Total procedures |
| `yoy_growth_pct` | DECIMAL | Year-over-year growth |

**Data Source:** Auto-populated from CMS data

**Current Status:** ✅ 2,069 records (FY2021: 675, FY2022: 690, FY2023: 704) with YoY growth calculated

---

## TODO Items

### High Priority

#### 1. Populate Internal Business Data
- [ ] **biome_relationships** - Export from CRM/contract system
- [ ] **sales_coverage** - Export from sales territory system
- [ ] **emr_systems** - Compile from sales intelligence
- [ ] **champions** - Export from CRM contacts

#### 2. Load Historical CMS Data ✅ COMPLETED
- [x] Fetch CMS Medicare Inpatient data for FY2021, FY2022
- [x] Calculate YoY growth percentages in `targeting.volume_history`
- [x] Update growth_score calculations in targeting model
- **Results:** 2,069 program-years across 704 hospitals (2021: 675, 2022: 690, 2023: 704)

### Medium Priority

#### 3. ACC TVC Certifications
- [ ] Investigate alternative data sources
- [ ] Consider manual data entry workflow
- [ ] Contact ACC for data access options

#### 4. Enhance dim_hospital
- [x] Add `bed_count` from CMS cost reports (93.5% coverage - 5,066 of 5,421)
- [ ] Add `teaching_status` from CMS data
- [ ] Add `urban_rural` classification

#### 5. Create API Views ✅ COMPLETED
- [x] Create `api.hospitals` view for PostgREST
- [x] Create `api.tavr_programs` view
- [x] Create `api.financial_metrics` view
- [x] Create `api.targeting` view
- [x] Create `api.scoring` view
- [x] Create `api.hpsa` view
- [x] Create `api.summary` view
- [ ] Set up row-level security if needed

### Low Priority

#### 6. Automation & Operations
- [ ] Set up cron job for daily CMS data refresh
- [ ] Configure SQLMesh scheduled runs
- [ ] Add data quality monitoring/alerts
- [ ] Document manual data entry procedures

#### 7. Data Quality Improvements
- [ ] Improve HPSA county matching (currently 92%)
- [ ] Add geocoding for hospital addresses
- [ ] Add health system grouping/hierarchy

---

## Data Refresh Procedures

### Automated (CMS Public Data)
```bash
# Fetch and load CMS data
docker exec tavr-job-trigger python -m ingestion.main cms_hospital_info --file <path>
docker exec tavr-job-trigger python -m ingestion.main cms_inpatient --file <path> --fiscal-year 2023
docker exec tavr-job-trigger python -m ingestion.main cms_cost_reports --file <path>

# Run SQLMesh transformations
uv run sqlmesh -p src/dk_data/sqlmesh plan --auto-apply
```

### Manual (Internal Business Data)
1. Export data from CRM system
2. Transform to match table schemas
3. Load via SQL INSERT or CSV import
4. Verify targeting scores update correctly

---

## Contacts & Resources

### Data Sources
- **CMS Data Portal:** https://data.cms.gov
- **CMS Provider Data:** https://data.cms.gov/provider-data
- **HRSA Data Warehouse:** https://data.hrsa.gov
- **ACC TVC Program:** https://www.acc.org/tvc (no public data API)

### Internal Systems
- CRM System: [TBD - add link]
- Contract Management: [TBD - add link]
- Sales Territory System: [TBD - add link]

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-01-15 | Initial pipeline implementation | Claude |
| 2026-01-15 | Fixed CMS column mappings | Claude |
| 2026-01-15 | Fixed HRSA column mappings | Claude |
| 2026-01-15 | Created targeting stub tables | Claude |
| 2026-01-15 | Pushed data to Neon cloud database | Claude |
| 2026-01-15 | Created PostgREST API views (6 views + summary) | Claude |
| 2026-01-15 | Added bed_count to dim_hospital from CMS cost reports | Claude |
| 2026-01-15 | Loaded historical CMS data (FY2021, FY2022) for YoY growth | Claude |
