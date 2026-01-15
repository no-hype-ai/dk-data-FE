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
| `raw.cms_medicare_inpatient` | 1,179 | CMS Data Portal | ✅ Complete | TAVR DRG 266/267 only, FY2023 |
| `raw.cms_cost_reports` | 6,086 | CMS HCRIS | ✅ Complete | Financial metrics, FY2023 |
| `raw.hrsa_shortage_areas` | 73,056 | HRSA Data Warehouse | ✅ Complete | Primary Care HPSAs |
| `raw.acc_tvc_certification` | 0 | ACC Website | ⚠️ No Source | No public API/CSV available |

### Staging Layer

| Table | Records | Status | Notes |
|-------|---------|--------|-------|
| `staging.hospitals` | 5,421 | ✅ Complete | Cleaned hospital master data |
| `staging.tavr_volumes` | 1,179 | ✅ Complete | TAVR volumes by hospital/DRG |
| `staging.certifications` | 0 | ⚠️ Blocked | Depends on ACC TVC data |
| `staging.geographic_designations` | 5,421 | ✅ Complete | 92% HPSA match rate |

### Mart Layer

| Table | Records | Status | Notes |
|-------|---------|--------|-------|
| `mart.dim_hospital` | 5,421 | ✅ Complete | Hospital dimension |
| `mart.fact_tavr_program` | 704 | ✅ Complete | Hospitals with TAVR programs |
| `mart.fact_financial_metrics` | 4,981 | ✅ Complete | Operating margins, quartiles |

### Scoring Layer

| Table | Records | Status | Notes |
|-------|---------|--------|-------|
| `scoring.target_scores` | 5,421 | ✅ Complete | Hospital scoring factors |
| `scoring.score_factors` | 75,894 | ✅ Complete | Detailed score breakdown |

### Targeting Layer

| Table | Records | Status | Notes |
|-------|---------|--------|-------|
| `targeting.targeting_scores` | 704 | ✅ Functional | All Low/DNQ without internal data |
| `targeting.targeting_summary` | 2 | ✅ Functional | Summary aggregations |

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

**Current Status:** 708 records (FY2023 only)

---

## TODO Items

### High Priority

#### 1. Populate Internal Business Data
- [ ] **biome_relationships** - Export from CRM/contract system
- [ ] **sales_coverage** - Export from sales territory system
- [ ] **emr_systems** - Compile from sales intelligence
- [ ] **champions** - Export from CRM contacts

#### 2. Load Historical CMS Data
- [ ] Fetch CMS Medicare Inpatient data for FY2021, FY2022
- [ ] Calculate YoY growth percentages in `targeting.volume_history`
- [ ] Update growth_score calculations in targeting model

### Medium Priority

#### 3. ACC TVC Certifications
- [ ] Investigate alternative data sources
- [ ] Consider manual data entry workflow
- [ ] Contact ACC for data access options

#### 4. Enhance dim_hospital
- [ ] Add `bed_count` from CMS cost reports
- [ ] Add `teaching_status` from CMS data
- [ ] Add `urban_rural` classification

#### 5. Create API Views
- [ ] Create `api.hospitals` view for PostgREST
- [ ] Create `api.targeting_scores` view
- [ ] Create `api.summary` view
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
