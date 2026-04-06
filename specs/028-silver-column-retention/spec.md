# Feature Specification: Silver Column Retention

**Feature Branch**: `028-silver-column-retention`  
**Created**: 2026-04-06  
**Status**: Draft  
**Input**: Silver models must carry forward all bronze columns. 95 silver SQLMesh models are dropping columns from upstream bronze sources. External apps only read silver/gold, so dropped columns are invisible to consumers.  
**Related**: GitHub issue #253

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Data Analyst Queries Silver for Drug Details (Priority: P1)

A data analyst building a dashboard queries `mol_silver.drugbank` to display drug interaction data, pathway information, and calculated molecular properties. Currently these columns exist in bronze but are dropped in silver, forcing the analyst to query bronze directly — breaking the medallion architecture contract.

**Why this priority**: Core data accessibility. If silver doesn't have the data, the entire silver/gold API layer is incomplete and consumers lose trust in it as the single source of truth.

**Independent Test**: Query any silver table and verify that every non-system column from its upstream bronze source(s) is present and populated.

**Acceptance Scenarios**:

1. **Given** a bronze table with columns A, B, C, D, **When** the silver transform runs, **Then** the silver table contains columns A, B, C, D plus any entity-resolution columns (molecule_id, facility_id, etc.)
2. **Given** a silver model that reads from multiple bronze sources, **When** columns share the same name across sources, **Then** they are prefixed with the source name to avoid collisions (e.g., `chembl_max_phase`, `drugbank_max_phase`)
3. **Given** a bronze column of type JSONB (arrays, nested objects), **When** carried to silver, **Then** the JSONB column is preserved as-is (not flattened or dropped)

---

### User Story 2 - Healthcare App Reads Facility Detail Data (Priority: P1)

A healthcare application queries `hcs_silver.cms_facility_profile` to display hospital-level DRG breakdown, APC-level outpatient data, and individual provider affiliations. Currently these detail-level fields are aggregated away — the silver model only exposes 33 summary columns from 9 upstream bronze tables.

**Why this priority**: Without detail-level data in silver, the healthcare app cannot drill down into facility performance metrics. Multi-source aggregation models must retain detail alongside summaries.

**Independent Test**: Query `hcs_silver.cms_facility_profile` and verify that DRG codes, APC descriptions, individual provider names, and line-item financials are accessible — not just aggregated totals.

**Acceptance Scenarios**:

1. **Given** an aggregation silver model that summarizes multiple bronze tables, **When** detail-level data is needed by consumers, **Then** companion detail-level silver tables exist alongside the aggregation (e.g., `hcs_silver.cms_inpatient_detail` alongside `hcs_silver.cms_facility_profile`)
2. **Given** a bronze table with 20 columns, **When** the silver model aggregates it into 5 summary metrics, **Then** the remaining 15 columns are available in a detail-level silver table

---

### User Story 3 - Safety Analyst Accesses Individual FAERS Reports (Priority: P2)

A safety analyst needs individual adverse event report data (patient demographics, reporter qualification, all concomitant drugs) from `mol_silver.adverse_events`. Currently the silver model aggregates FAERS data into counts and rates, losing the individual report details.

**Why this priority**: Individual-level safety data is critical for signal detection and case review. Aggregated counts alone are insufficient for pharmacovigilance workflows.

**Independent Test**: Query silver for a specific safety report ID and retrieve patient age, sex, reporter type, all drugs involved, and the full reaction list.

**Acceptance Scenarios**:

1. **Given** FAERS bronze has individual reports with patient demographics and drug lists, **When** silver transform runs, **Then** individual report data is available in a detail-level silver table
2. **Given** SIDER bronze has individual side effect records, **When** silver transform runs, **Then** individual records with frequency data are available in silver

---

### Edge Cases

- What happens when a bronze column is NULL for all rows? Silver should still include the column (schema consistency).
- What happens when two bronze sources have the same column name in a multi-source silver model? Prefix with source name.
- What happens when a bronze model adds a new column in a future migration? Silver model should be updated to include it (documented maintenance procedure).
- What happens when a bronze column contains very large JSONB values? Silver carries it as-is — no truncation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every silver model MUST carry forward all domain columns from its upstream bronze source(s). Only system/ETL metadata columns may be excluded: `raw_json`, `raw_source_id`, `processed_to_bronze`, `processed_to_silver`, `_bronze_loaded_at`.
- **FR-002**: Silver models that read from a single bronze source MUST include all bronze SELECT columns in their own SELECT (plus any entity-resolution joins like molecule_id).
- **FR-003**: Silver models that aggregate multiple bronze sources into summary metrics MUST be accompanied by detail-level silver tables that preserve the full bronze columns with entity linkage.
- **FR-004**: When multiple bronze sources have columns with the same name, the silver model MUST disambiguate by prefixing with the source name (e.g., `chembl_max_phase`, `drugbank_max_phase`).
- **FR-005**: JSONB array columns (targets, pathways, interactions, synonyms, etc.) MUST be carried through to silver as JSONB — not dropped or flattened.
- **FR-006**: Each modified silver model MUST compile successfully with `sqlmesh plan --dry-run`.
- **FR-007**: Source tracking columns (`source`, `_source_year`, `_source_hash`) MUST be carried to silver for lineage.

### Key Entities

- **Silver Model**: A SQLMesh SQL model in the silver layer that reads from one or more bronze tables and produces entity-resolved, typed output.
- **Bronze Model**: A SQLMesh SQL model in the bronze layer that unpacks raw API responses into typed columns.
- **Domain Column**: Any column that contains business data (not ETL metadata). Must be preserved from bronze to silver.
- **Detail Table**: A companion silver table that preserves row-level bronze data alongside an aggregation model.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of silver models carry forward all domain columns from their upstream bronze source(s), verified by automated column-diff audit.
- **SC-002**: External application queries against silver return all fields previously requiring direct bronze queries — zero bronze bypass needed.
- **SC-003**: All 95 silver models compile and run without errors after modification.
- **SC-004**: Multi-source aggregation models (cms_facility_profile, adverse_events) have companion detail tables exposing full bronze column sets.
- **SC-005**: No net increase in query latency for existing silver consumers (new columns are additive, not replacing existing ones).

## Assumptions

- Bronze models are the source of truth for available columns. If a column doesn't exist in bronze, it's not expected in silver.
- The `raw_json` column (full API response body) is intentionally excluded from silver — it's a storage optimization, not a data gap. Consumers needing raw responses query bronze.
- The `processed_to_silver` and `_bronze_loaded_at` flags are ETL-internal and not consumer-facing.
- Existing silver model consumers will not break from additive column changes (new columns added, no existing columns removed or renamed).
- Silver storage increase from carrying additional columns is acceptable (~5-15 GB estimated across all models).
