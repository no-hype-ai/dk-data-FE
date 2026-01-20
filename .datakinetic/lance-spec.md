# Feature Specification: DK Data v3 Source Automation

**Feature Branch**: `001-dk-data-v3`
**Created**: 2026-01-19
**Status**: Draft
**Input**: User description: "The DataKinetic system dk-data needs to be updated to version 3. The primary purpose for this version is to simplify the addition of new data sources to the service. The current architecture has an ETL system for each data source, a database schema for each datasource, and a REST API that should give access to the database schema for each data source. In version 3 the REST API will be replaced with PostgREST which will automatically publish the various schemas (including any schemas that aggegate or process the raw data in the datasource schemas); and for the datasource schema and ETL an application will be created that will use LLMs to analyze the datasource and create the ETL and schema from that."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rapid onboarding of a new data source (Priority: P1)

As a data platform administrator, I can register a new data source and receive a proposed schema and ingestion plan so that the source can be onboarded with minimal manual setup.

**Why this priority**: The primary goal of v3 is to make adding new data sources fast and repeatable.

**Independent Test**: Provide a representative sample or connection details for a new source and verify that a proposed schema and ingestion plan are produced and can be approved to create an initial dataset.

**Acceptance Scenarios**:

1. **Given** a registered data source with sample data, **When** analysis is run, **Then** a proposed schema and ingestion plan are produced for review.
2. **Given** a proposed schema and ingestion plan, **When** an admin approves it, **Then** the initial dataset is created and available for access.

---

### User Story 2 - Access to published datasets without custom APIs (Priority: P2)

As a data consumer, I can discover and access published datasets for both raw and derived schemas so that I can use the data without source-specific integrations.

**Why this priority**: Removing source-specific APIs is required to scale access to many schemas.

**Independent Test**: After a source is onboarded, verify that datasets for raw and derived schemas are discoverable and accessible through the standard data access interface.

**Acceptance Scenarios**:

1. **Given** a source with raw and derived schemas, **When** the datasets are published, **Then** they are discoverable and accessible via the standard interface.

---

### User Story 3 - Manage changes to sources over time (Priority: P3)

As a platform operator, I can detect and manage schema changes so that updates do not break existing data access.

**Why this priority**: Sources evolve, and safe change handling protects downstream users.

**Independent Test**: Modify a source to introduce a schema change and confirm that the system proposes an updated schema version and preserves access to existing versions.

**Acceptance Scenarios**:

1. **Given** a source with a changed structure, **When** analysis is rerun, **Then** a new schema version is proposed with clear differences from the previous version.

---

### Edge Cases

- What happens when the provided sample data is insufficient to infer a stable schema?
- How does the system handle conflicting field types across sample records?
- What happens when an ingestion run fails after partial data load?
- How does the system handle derived schema definitions that depend on missing raw fields?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow authorized administrators to register a new data source with descriptive metadata and access details.
- **FR-002**: System MUST analyze the registered source to propose a schema and ingestion plan.
- **FR-003**: System MUST allow administrators to review, edit, approve, or reject proposed schemas and ingestion plans.
- **FR-004**: System MUST create a distinct schema for each data source and support derived schemas built from source data.
- **FR-005**: System MUST publish data access interfaces for each schema automatically once approved.
- **FR-006**: System MUST execute ingestion runs and provide status, including success, failure, and partial completion.
- **FR-007**: System MUST track lineage from source inputs to raw and derived datasets.
- **FR-008**: System MUST support schema versioning and preserve access to previous versions when changes occur.
- **FR-009**: System MUST enforce access controls at the schema level.
- **FR-010**: System MUST provide actionable error feedback when analysis or ingestion fails.
- **FR-011**: System MUST allow manual overrides to automated schema and ingestion proposals.
- **FR-012**: System MUST support deprecating a data source while retaining defined retention obligations.

### Key Entities *(include if feature involves data)*

- **Data Source**: A registered origin of data, with metadata, ownership, and access details.
- **Source Profile**: The analyzed characteristics of the source, including detected fields and types.
- **Proposed Schema**: A draft schema generated from analysis, prior to approval.
- **Ingestion Plan**: The defined steps and rules for loading source data into datasets.
- **Schema Version**: A labeled version of a schema with change history.
- **Derived Schema**: A dataset definition that aggregates or transforms source data.
- **Publication**: The published access surface for a schema.
- **Ingestion Run**: A record of a single execution of data loading with status and outcomes.
- **Lineage Record**: The mapping of source inputs to dataset outputs.
- **Access Policy**: The permissions and roles applied to schemas and datasets.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 80% of new data sources reach first successful data availability within one business day of registration.
- **SC-002**: 95% of new sources require no more than one manual edit cycle before approval.
- **SC-003**: 90% of data consumers can discover and access a newly published dataset in under 5 minutes.
- **SC-004**: 100% of failed analysis or ingestion attempts produce an actionable error report within 10 minutes.

## Constitution Alignment Checklist *(mandatory)*

- **Regulated Data Integrity**: Source ownership, schema versions, and lineage are recorded for every dataset; sensitive data handling follows existing organizational policy.
- **Contract-First Interfaces**: Published dataset contracts are documented and versioned; breaking changes require a defined migration window.
- **Test-First Automation**: Acceptance scenarios for onboarding, publishing, and versioning are defined prior to rollout; test data is anonymized.
- **Predictive Observability**: Operators receive visibility into onboarding progress, ingestion health, and schema change impacts through standard monitoring.
- **Security & Access Governance**: Access policies are enforced per schema with least-privilege defaults and auditable approvals.
- **Independent Delivery**: Each prioritized user story can be delivered and validated independently, providing a usable slice of the overall capability.

## Assumptions

- Initial scope focuses on batch or scheduled ingestion rather than real-time streaming.
- Only internal platform administrators can approve schema and ingestion proposals.
- Data retention follows existing organizational policy unless overridden for a source.

## Out of Scope

- Building custom, source-specific APIs for data access.
- Manual, hand-built ETL pipelines outside the onboarding workflow.
