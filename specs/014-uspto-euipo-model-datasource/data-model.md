# Data Model: USPTO & EUIPO Model Datasource Integration

**Feature**: 014-uspto-euipo-model-datasource
**Date**: 2026-02-16
**Source**: [spec.md](spec.md), [research.md](research.md)

## Entity Relationship Overview

```
                         PATENTS
                         -------
raw.uspto_patents ──> bronze.uspto_patents ──┐
raw.uspto_ci ──────> bronze.uspto_ci ────────┤
raw.epo_patents ───> bronze.epo_patents ─────┼──> silver.patents ──┐
                     bronze.drugbank ────────┘                     │
                                                                   ├──> gold.molecule_profile
                         TRADEMARKS                                │
                         ----------                                │
raw.uspto_trademarks ─> bronze.uspto_trademarks ─┐                 │
raw.euipo_trademarks ─> bronze.euipo_trademarks ─┼─> silver.trademarks ─┘
                                                 │
raw.trademark_status_history <───────────────────┘ (populated during ingestion)
```

## Entities

### 1. Raw USPTO Patents (`raw.uspto_patents`) — EXISTS

Already created by migration `064_uspto_patents_raw_table.sql`. No changes needed.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| patent_number | VARCHAR(50) | NOT NULL, UNIQUE (PK) | e.g., "US-11234567-B2" |
| title | TEXT | | Patent title |
| abstract | TEXT | | Patent abstract |
| inventors | JSONB | | Array of {first_name, last_name, city, country} |
| assignees | JSONB | | Array of {organization, type} |
| filing_date | DATE | | Application filing date |
| grant_date | DATE | | Patent grant/issue date |
| cpc_codes | TEXT[] | | CPC classification codes |
| claims_count | INTEGER | | Number of claims |
| _loaded_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Ingestion timestamp |
| _source_file | VARCHAR(500) | | Source file reference |
| _source_hash | VARCHAR(64) | | Content hash for dedup |

**Indexes**: `idx_uspto_patents_grant` (grant_date DESC), `idx_uspto_patents_cpc` (GIN on cpc_codes)

### 2. Raw USPTO CI (`raw.uspto_ci`) — EXISTS

Already created by migration `060_ci_source_tables.sql`. No changes needed.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| patent_id | VARCHAR(50) | NOT NULL, UNIQUE (PK) | e.g., "US-11234567-B2" |
| title | TEXT | | Patent title |
| abstract | TEXT | | Patent abstract |
| inventors | JSONB | | Array of {first, last} |
| assignees | JSONB | | Array of {org} |
| filing_date | DATE | | Application filing date |
| grant_date | DATE | | Patent grant/issue date |
| cpc_codes | TEXT[] | | CPC codes |
| claims_count | INTEGER | | Number of claims |
| _loaded_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

### 3. Raw EPO Patents (`raw.epo_patents`) — EXISTS

Already created by a previous migration. No changes needed.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| publication_id | VARCHAR(50) | NOT NULL, UNIQUE (PK) | e.g., "EP3456789A1" |
| title | TEXT | | Patent title |
| abstract | TEXT | | Patent abstract |
| applicants | JSONB | | Array of applicant names |
| inventors | JSONB | | Array of inventor names |
| filing_date | DATE | | Application filing date |
| publication_date | DATE | | Publication date |
| ipc_codes | TEXT[] | | IPC classification codes |
| family_id | VARCHAR(50) | | Patent family ID |
| _loaded_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

### 4. Raw USPTO Trademarks (`raw.uspto_trademarks`) — NEW

Created by migration `071_uspto_trademarks_raw.sql`.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| serial_number | VARCHAR(20) | NOT NULL, UNIQUE (PK) | 8-digit serial number |
| mark_element | TEXT | | The mark text (word mark) |
| mark_type | VARCHAR(50) | | TRADEMARK, SERVICEMARK, etc. |
| status | VARCHAR(100) | | Status string from TSDR |
| status_code | INTEGER | | Numeric status code |
| status_date | DATE | | Date of last status change |
| filing_date | DATE | | Application filing date |
| registration_number | VARCHAR(20) | | Registration number if registered |
| registration_date | DATE | | Registration date |
| nice_classes | INTEGER[] | | International Nice classes |
| us_classes | TEXT[] | | US classification codes |
| owner_name | TEXT | | Current owner name |
| owner_entity_type | VARCHAR(50) | | CORPORATION, INDIVIDUAL, etc. |
| goods_and_services | TEXT | | Description of goods/services |
| description_of_mark | TEXT | | Mark description |
| _loaded_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

**Indexes**: `idx_uspto_tm_filing` (filing_date DESC), `idx_uspto_tm_nice` (GIN on nice_classes), `idx_uspto_tm_status` (status), `idx_uspto_tm_mark` (GIN on mark_element gin_trgm_ops)

### 5. Raw EUIPO Trademarks (`raw.euipo_trademarks`) — NEW

Created by migration `072_euipo_trademarks_raw.sql`.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| application_number | VARCHAR(30) | NOT NULL, UNIQUE (PK) | EUIPO application number |
| mark_name | TEXT | | The mark text |
| mark_kind | VARCHAR(50) | | Word, Figurative, 3D, Sound, etc. |
| mark_feature | VARCHAR(50) | | Standard, non-standard |
| mark_basis | VARCHAR(50) | | National, EU, International |
| applicant_name | TEXT | | Applicant/owner name |
| applicant_country | VARCHAR(10) | | ISO country code |
| representative_name | TEXT | | Legal representative |
| status | VARCHAR(100) | | Filed, Registered, Refused, etc. |
| filing_date | DATE | | Application filing date |
| registration_date | DATE | | Registration date |
| expiry_date | DATE | | Registration expiry date |
| nice_classes | INTEGER[] | | Nice classification numbers |
| goods_and_services | TEXT | | Goods/services description |
| image_url | TEXT | | URL for figurative marks |
| _loaded_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

**Indexes**: `idx_euipo_tm_filing` (filing_date DESC), `idx_euipo_tm_nice` (GIN on nice_classes), `idx_euipo_tm_status` (status), `idx_euipo_tm_mark` (GIN on mark_name gin_trgm_ops)

### 6. Trademark Status History (`raw.trademark_status_history`) — NEW

Created by migration `073_trademark_status_history.sql`.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | NOT NULL, DEFAULT gen_random_uuid(), PK | Auto-generated |
| trademark_identifier | VARCHAR(30) | NOT NULL | serial_number (USPTO) or application_number (EUIPO) |
| source | VARCHAR(20) | NOT NULL | 'uspto_trademarks' or 'euipo_trademarks' |
| old_status | VARCHAR(100) | | Previous status value |
| new_status | VARCHAR(100) | NOT NULL | New status value |
| change_detected_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | When change was detected |

**Indexes**: `idx_tm_history_identifier` (trademark_identifier, source), `idx_tm_history_detected` (change_detected_at DESC)

**Constraint**: CHECK (source IN ('uspto_trademarks', 'euipo_trademarks'))

### 7. Bronze USPTO Patents (`bronze.uspto_patents`) — MODIFY

SQLMesh model. Currently broken (reads JSONB `response_body`). Must be refactored to read flat columns from `raw.uspto_patents`.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| id | UUID | generated | uuid_generate_v4() |
| patent_number | VARCHAR(50) | raw.patent_number | PK, grain |
| patent_title | TEXT | raw.title | Renamed from title |
| patent_abstract | TEXT | raw.abstract | |
| patent_date | DATE | raw.grant_date | Grant date |
| patent_type | TEXT | NULL | Not in raw table |
| patent_kind | TEXT | NULL | Not in raw table |
| cpc_codes | JSONB | raw.cpc_codes::jsonb | Cast TEXT[] to JSONB |
| assignee_organization | TEXT | raw.assignees->0->>'organization' | First assignee |
| assignee_type | TEXT | raw.assignees->0->>'type' | First assignee type |
| inventors | JSONB | raw.inventors | Already JSONB |
| num_claims | INTEGER | raw.claims_count | |
| is_pharma_related | BOOLEAN | computed | CPC code prefix check |
| processed_to_silver | BOOLEAN | FALSE | Processing flag |
| ingested_at | TIMESTAMP | NOW() | Time column for incremental |

### 8. Bronze USPTO CI (`bronze.uspto_ci`) — NEW

SQLMesh model. New model reading from `raw.uspto_ci`.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| id | UUID | generated | |
| patent_number | VARCHAR(50) | raw.patent_id | Renamed to match bronze schema |
| patent_title | TEXT | raw.title | |
| patent_abstract | TEXT | raw.abstract | |
| patent_date | DATE | raw.grant_date | |
| cpc_codes | JSONB | raw.cpc_codes::jsonb | |
| assignee_organization | TEXT | raw.assignees->0->>'org' | |
| inventors | JSONB | raw.inventors | |
| num_claims | INTEGER | raw.claims_count | |
| is_pharma_related | BOOLEAN | computed | |
| processed_to_silver | BOOLEAN | FALSE | |
| ingested_at | TIMESTAMP | NOW() | |

### 9. Bronze EPO Patents (`bronze.epo_patents`) — NEW

SQLMesh model. New model reading from `raw.epo_patents`.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| id | UUID | generated | |
| patent_number | VARCHAR(50) | raw.publication_id | Renamed to patent_number |
| patent_title | TEXT | raw.title | |
| patent_abstract | TEXT | raw.abstract | |
| patent_date | DATE | raw.publication_date | |
| ipc_codes | JSONB | raw.ipc_codes::jsonb | IPC instead of CPC |
| assignee_organization | TEXT | raw.applicants->0 | First applicant |
| inventors | JSONB | raw.inventors | |
| family_id | VARCHAR(50) | raw.family_id | EPO-specific |
| is_pharma_related | BOOLEAN | computed | IPC A61K/A61P check |
| processed_to_silver | BOOLEAN | FALSE | |
| ingested_at | TIMESTAMP | NOW() | |

### 10. Bronze USPTO Trademarks (`bronze.uspto_trademarks`) — NEW

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| id | UUID | generated | |
| serial_number | VARCHAR(20) | raw.serial_number | PK, grain |
| mark_element | TEXT | raw.mark_element | |
| mark_type | VARCHAR(50) | raw.mark_type | |
| status | VARCHAR(100) | raw.status | |
| status_date | DATE | raw.status_date | |
| filing_date | DATE | raw.filing_date | |
| registration_number | VARCHAR(20) | raw.registration_number | |
| registration_date | DATE | raw.registration_date | |
| nice_classes | JSONB | raw.nice_classes::jsonb | |
| owner_name | TEXT | raw.owner_name | |
| owner_entity_type | VARCHAR(50) | raw.owner_entity_type | |
| goods_and_services | TEXT | raw.goods_and_services | |
| is_pharma_related | BOOLEAN | computed | Nice class 5 check |
| processed_to_silver | BOOLEAN | FALSE | |
| ingested_at | TIMESTAMP | NOW() | |

### 11. Bronze EUIPO Trademarks (`bronze.euipo_trademarks`) — NEW

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| id | UUID | generated | |
| application_number | VARCHAR(30) | raw.application_number | PK, grain |
| mark_name | TEXT | raw.mark_name | |
| mark_kind | VARCHAR(50) | raw.mark_kind | |
| mark_feature | VARCHAR(50) | raw.mark_feature | |
| applicant_name | TEXT | raw.applicant_name | |
| applicant_country | VARCHAR(10) | raw.applicant_country | |
| representative_name | TEXT | raw.representative_name | |
| status | VARCHAR(100) | raw.status | |
| filing_date | DATE | raw.filing_date | |
| registration_date | DATE | raw.registration_date | |
| expiry_date | DATE | raw.expiry_date | |
| nice_classes | JSONB | raw.nice_classes::jsonb | |
| goods_and_services | TEXT | raw.goods_and_services | |
| is_pharma_related | BOOLEAN | computed | Nice class 5 check |
| processed_to_silver | BOOLEAN | FALSE | |
| ingested_at | TIMESTAMP | NOW() | |

### 12. Silver Patents (`silver.patents`) — MODIFY

Currently only reads from `bronze.drugbank`. Must be extended to UNION ALL from 4 bronze sources with `DISTINCT ON (patent_number)` deduplication.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| id | UUID | generated | |
| patent_number | VARCHAR(50) | bronze.* | PK, grain, unique key |
| application_number | TEXT | bronze (if available) | |
| title | TEXT | bronze.patent_title | |
| abstract | TEXT | bronze.patent_abstract | |
| filing_date | DATE | bronze.* | |
| grant_date | DATE | bronze.patent_date | |
| expiry_date | DATE | bronze.drugbank only | |
| assignee | TEXT | bronze.assignee_organization | |
| assignee_normalized | TEXT | computed | |
| inventors | JSONB | bronze.inventors | |
| patent_type | TEXT | bronze.patent_type | |
| country | TEXT | computed | US, EP based on source |
| cpc_codes | JSONB | bronze.cpc_codes | |
| ipc_codes | JSONB | bronze.ipc_codes | EPO only |
| status | TEXT | computed | active/expired/pending |
| pediatric_extension | BOOLEAN | DrugBank only | |
| extension_days | INTEGER | DrugBank only | |
| related_patents | JSONB | NULL | Future use |
| molecule_id | UUID | NULL | Entity resolution link |
| source | TEXT | computed | 'drugbank', 'uspto_patents', 'uspto_ci', 'epo_ops' |
| source_updated_at | TIMESTAMP | bronze.* | |
| created_at | TIMESTAMP | NOW() | |
| updated_at | TIMESTAMP | NOW() | |

**Source priority** (for DISTINCT ON deduplication): drugbank > uspto_patents > uspto_ci > epo_ops

### 13. Silver Trademarks (`silver.trademarks`) — NEW

UNION ALL from `bronze.uspto_trademarks` and `bronze.euipo_trademarks`. No cross-registry dedup.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| id | UUID | generated | |
| trademark_identifier | VARCHAR(30) | serial_number / application_number | PK for within-source dedup |
| mark_name | TEXT | mark_element / mark_name | Unified column |
| mark_type | VARCHAR(50) | mark_type / mark_kind | |
| status | VARCHAR(100) | status | |
| filing_date | DATE | filing_date | |
| registration_date | DATE | registration_date | |
| expiry_date | DATE | EUIPO only, NULL for USPTO | |
| owner_name | TEXT | owner_name / applicant_name | |
| nice_classes | JSONB | nice_classes | |
| goods_and_services | TEXT | goods_and_services | |
| is_pharma_related | BOOLEAN | computed | Nice class 5 |
| source | TEXT | 'uspto_trademarks' / 'euipo_trademarks' | Registry identifier |
| source_updated_at | TIMESTAMP | _loaded_at | |
| created_at | TIMESTAMP | NOW() | |
| updated_at | TIMESTAMP | NOW() | |

**Deduplication**: `DISTINCT ON (trademark_identifier, source)` — within-registry only.

### 14. Gold Molecule Profile (IP Trademark Section) — MODIFY

Add new CTE `trademark_info` to `gold.molecule_profile`:

| New Column | Type | Source | Notes |
|------------|------|--------|-------|
| trademark_count | INTEGER | COUNT from silver.trademarks | Total trademarks (US + EU) |
| active_trademark_count | INTEGER | COUNT FILTER (status = 'Registered') | Active/registered only |
| us_trademark_count | INTEGER | COUNT FILTER (source = 'uspto_trademarks') | US-only count |
| eu_trademark_count | INTEGER | COUNT FILTER (source = 'euipo_trademarks') | EU-only count |
| latest_us_trademark_status | TEXT | silver.trademarks | Most recent USPTO status |
| latest_eu_trademark_status | TEXT | silver.trademarks | Most recent EUIPO status |

**Link strategy**: Join `silver.trademarks` to `silver.molecules` on `mark_name ILIKE '%' || canonical_name || '%'` with alias matching.

## Validation Rules (Pydantic)

### USPTOTrademarkRecord

| Field | Type | Validation |
|-------|------|------------|
| serial_number | str | min_length=1, strip whitespace |
| mark_element | Optional[str] | |
| mark_type | Optional[str] | |
| status | Optional[str] | |
| status_code | Optional[int] | |
| status_date | Optional[date] | |
| filing_date | Optional[date] | |
| registration_number | Optional[str] | |
| registration_date | Optional[date] | |
| nice_classes | Optional[list[int]] | |
| us_classes | Optional[list[str]] | |
| owner_name | Optional[str] | |
| owner_entity_type | Optional[str] | |
| goods_and_services | Optional[str] | |

### EUIPOTrademarkRecord

| Field | Type | Validation |
|-------|------|------------|
| application_number | str | min_length=1, strip whitespace |
| mark_name | Optional[str] | |
| mark_kind | Optional[str] | |
| mark_feature | Optional[str] | |
| mark_basis | Optional[str] | |
| applicant_name | Optional[str] | |
| applicant_country | Optional[str] | max_length=10 |
| representative_name | Optional[str] | |
| status | Optional[str] | |
| filing_date | Optional[date] | |
| registration_date | Optional[date] | |
| expiry_date | Optional[date] | |
| nice_classes | Optional[list[int]] | |
| goods_and_services | Optional[str] | |

## State Transitions

### Trademark Status Values

**USPTO** (from TSDR API):
- NEW APPLICATION
- PUBLISHED FOR OPPOSITION
- REGISTERED
- CANCELLED
- ABANDONED
- EXPIRED

**EUIPO** (from TMview):
- Filed
- Registered
- Refused
- Withdrawn
- Expired
- Cancelled
- Appealed
- Opposition pending
- (18 total values)

### Status History Tracking

```
Ingestion Run N:
  fetch trademark → compare status vs last raw.trademark_status_history row
  if different → INSERT INTO raw.trademark_status_history (
    trademark_identifier, source, old_status, new_status, change_detected_at
  )
```
