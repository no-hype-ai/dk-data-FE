# Feature Specification: Platform Hardening

**Feature Branch**: `012-platform-hardening`
**Created**: 2026-02-14
**Status**: Draft
**Input**: OPEN_ISSUES_RECONCILIATION.md + GitHub Issue #88 (CronJob ModuleNotFoundError)

## User Scenarios & Testing

### User Story 1 - Fix Broken CronJob Container Image (Priority: P1)

A data operations engineer deploys the dk-data platform to staging and expects all CronJob pods (molecule fetch, catalog refresh, CI source fetch) to run on schedule. Currently, every CronJob pod fails immediately with `ModuleNotFoundError: No module named 'dk_data'` because the container image does not have the `dk_data` package installed or on the Python path.

**Why this priority**: All ingestion pipelines are completely non-functional. No data flows into the platform until this is fixed. This is a deployment-blocking defect.

**Independent Test**: Trigger any CronJob manually (e.g., `mol-fetch-daily`), verify the pod starts, executes the Python module, and exits successfully (or fails gracefully on an expected external dependency like a missing API key — not a missing module).

**Acceptance Scenarios**:

1. **Given** a freshly deployed staging environment, **When** the `mol-fetch-daily` CronJob triggers, **Then** the pod runs `python -m dk_data.ingestion.fetch_molecules` without `ModuleNotFoundError` and either fetches data or reports a clear external error (e.g., API timeout, missing credential).
2. **Given** a rebuilt container image, **When** a developer runs `python -c "import dk_data"` inside the container, **Then** the import succeeds.
3. **Given** the fixed image is deployed, **When** all 15+ CronJobs trigger on their schedules, **Then** zero pods fail due to missing Python modules.

---

### User Story 2 - Create Downstream API Views for behavior-labs-ai (Priority: P2)

A behavior-labs-ai backend service queries dk-data's read-only API for competitive landscape data, molecule profiles, patent information, and trial-publication features. These views do not yet exist, blocking specs 029-034 in behavior-labs-ai from functioning against real data.

**Why this priority**: Six behavior-labs-ai feature specs depend on these views. Without them, the AI decision engine, discovery optimization, commercial analytics, and patent intelligence features have no data to operate on.

**Independent Test**: Query each new API view endpoint and verify it returns data (or an empty set with correct schema). Verify that authenticated requests with the `api_user` role can access the views and unauthenticated requests are rejected.

**Acceptance Scenarios**:

1. **Given** raw data exists in ingestion tables from ingestion pipelines, **When** a downstream service queries `competitive_landscape` through the read-only API, **Then** it receives structured competitive landscape records with company names, pipeline counts, and market positions.
2. **Given** patent data has been ingested, **When** a downstream service queries the patents view, **Then** it receives patent records with patent number, title, assignee, filing date, expiry date, and CPC codes.
3. **Given** molecule data exists in the molecule schemas, **When** a service queries molecule properties, **Then** it receives pre-computed property records (not on-demand computation) for known compounds.
4. **Given** no authentication token is provided, **When** a client queries any new API view, **Then** the request is rejected with a 401 or 403 response.

---

### User Story 3 - Enable Remaining Molecule Data Sources (Priority: P3)

A pharmaceutical analyst needs UniProt protein target data, PDB structural data, and ORCID researcher profiles to complete the molecule platform's coverage of drug-target interactions and key opinion leader identification.

**Why this priority**: These three sources complete the molecule data platform's coverage. Existing API clients already exist for all three; only the ingestion pipeline integration (fetcher, loader, CronJob, registration) is missing.

**Independent Test**: Trigger each source's CronJob manually, verify records land in the appropriate raw tables, and confirm the source appears in the data catalog.

**Acceptance Scenarios**:

1. **Given** the UniProt ingestion pipeline is configured, **When** the UniProt CronJob triggers, **Then** protein records are stored in the raw layer with accession numbers, gene names, organism, and function annotations.
2. **Given** the PDB ingestion pipeline is configured, **When** the PDB CronJob triggers, **Then** structure records are stored with PDB IDs, resolution, method, and ligand information.
3. **Given** the ORCID ingestion pipeline is configured using the public API, **When** the ORCID CronJob triggers, **Then** researcher records are stored with ORCID iDs, names, affiliations, and publication counts.
4. **Given** all three sources are running, **When** a user views the data catalog, **Then** UniProt, PDB, and ORCID appear with accurate freshness timestamps and record counts.

---

### User Story 4 - Dependency Version Management (Priority: P4)

A developer onboarding to the project installs dependencies and gets different package versions than production, causing subtle bugs. The project needs pinned dependency versions with upper bounds and a lock file so that every environment — local development, CI, staging, production — uses identical dependency versions.

**Why this priority**: Reduces risk of dependency drift causing hard-to-diagnose failures. Important for reliability but not blocking any features.

**Independent Test**: Delete the local virtual environment, reinstall from the lock file, and verify the installed versions exactly match the lock file. Run the test suite and confirm all tests pass.

**Acceptance Scenarios**:

1. **Given** the project has a lock file, **When** two developers install dependencies independently, **Then** both get identical package versions.
2. **Given** a dependency has a new major version release, **When** a developer runs a standard install, **Then** the lock file prevents the major version upgrade until explicitly updated.
3. **Given** the CI pipeline runs, **When** it checks dependency freshness, **Then** it warns if the lock file is out of date with the source constraints.

---

### User Story 5 - Document Doppler Secret Configuration (Priority: P5)

A DevOps engineer setting up a new environment needs to know exactly which secrets are required, what values they expect, and how to configure them. Currently this is tribal knowledge scattered across CronJob manifests and code.

**Why this priority**: Low effort, high documentation value. Prevents deployment failures from missing secrets.

**Independent Test**: Follow the documentation to set up a fresh Doppler configuration from scratch. Verify that all CronJobs and services start without "missing secret" errors.

**Acceptance Scenarios**:

1. **Given** a new environment with no secrets configured, **When** an engineer follows the Doppler setup documentation, **Then** they can configure all required secrets without consulting anyone else.
2. **Given** the documentation lists all required secrets, **When** compared against actual CronJob manifests and application code, **Then** every referenced environment variable is documented with its purpose, format, and where to obtain it.
3. **Given** a startup validation check runs, **When** a required secret is missing, **Then** the system logs a clear error message identifying the missing secret by name.

---

### Edge Cases

- What happens when a CronJob pod's container image is updated mid-schedule? Existing pods complete with the old image; new pods use the new image.
- What happens when a downstream API view references a table that has no data yet? The view returns an empty result set, not an error.
- What happens when a data source API is down during a scheduled fetch? The fetcher logs the error, exits with a non-zero code, and the CronJob retries on its next schedule.
- What happens when the lock file and source constraints diverge? CI fails with a clear message indicating the lock file needs regeneration.
- What happens when a secret is present but empty? The startup check treats empty values as missing and logs a warning.

## Requirements

### Functional Requirements

- **FR-001**: The container image used by all CronJob pods MUST have the application package available for import at runtime.
- **FR-002**: A developer MUST be able to verify the container image's environment includes the application package by running a simple import check.
- **FR-003**: The system MUST expose at minimum 8 new read-only API views for downstream services: `competitive_landscape`, `company_pipeline`, `patents`, `trial_publication_features`, `molecule_properties`, `sider`, `bioactivity`, and `targets`.
- **FR-004**: All new API views MUST be accessible only to authenticated users with appropriate roles.
- **FR-005**: API views MUST return empty result sets (not errors) when underlying tables contain no data.
- **FR-006**: The system MUST support pre-computed molecule properties for all known compounds in the database; on-demand computation for arbitrary inputs is out of scope for this feature.
- **FR-007**: UniProt, PDB, and ORCID data sources MUST be integrated into the ingestion pipeline with scheduled fetch, validation, storage, and catalog registration.
- **FR-008**: ORCID integration MUST use the public API (no registration required); Member API upgrade is deferred.
- **FR-009**: All dependencies MUST have upper version bounds preventing unexpected major version upgrades.
- **FR-010**: A lock file MUST pin exact dependency versions including transitive dependencies.
- **FR-011**: CI MUST validate that the lock file is consistent with the declared constraints.
- **FR-012**: All required environment variables and secrets MUST be documented with name, purpose, expected format, and source.
- **FR-013**: A startup validation check MUST verify the presence of critical secrets and log clear errors for any that are missing.
- **FR-014**: Each new data source and API view MUST have unit tests covering the primary success path and at least one error path.

### Key Entities

- **API View**: A read-only database view exposed through the API layer, representing a specific data domain (competitive landscape, patents, molecule properties, etc.)
- **Data Source**: An external data provider (UniProt, PDB, ORCID) with a fetcher, loader, validator, scheduled job, and catalog entry
- **Container Image**: The build artifact used by CronJob pods, containing the application code and all dependencies
- **Secret**: A named environment variable stored in the secrets manager, required by one or more services at runtime
- **Lock File**: A generated file pinning exact dependency versions for reproducible installations

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of CronJob pods start successfully without module import errors after image rebuild
- **SC-002**: At least 8 new API views are queryable by authenticated downstream services, each returning valid schema-conformant responses
- **SC-003**: 3 additional data sources (UniProt, PDB, ORCID) appear in the data catalog with successful initial fetch recorded
- **SC-004**: Dependency installations across different machines produce identical package versions 100% of the time when using the lock file
- **SC-005**: A new engineer can configure all secrets for a fresh environment in under 30 minutes using only the documentation
- **SC-006**: All new code has unit test coverage; overall test suite maintains at least 20% coverage
- **SC-007**: Zero CronJob failures attributed to missing modules or missing secrets within 7 days of deployment

## Scope

### In Scope

- Container image fix for application module availability (GitHub Issue #88)
- Pre-computed API views for downstream service integration (GitHub Issue #81)
- UniProt, PDB, and ORCID data source ingestion pipelines (GitHub Issues #42, #50, #51)
- Dependency version pinning with lock file (GitHub Issue #20)
- Secret configuration documentation and startup validation (GitHub Issue #57)

### Out of Scope

- On-demand molecular property computation (compute-on-demand for arbitrary SMILES strings)
- Frontend integration (GitHub Issue #52 — deferred until API views exist)
- LiteLLM proxy migration (GitHub Issue #84 — separate evaluation)
- ORCID Member API integration (requires registration; public API first)
- Transformation models beyond what is needed for the API views
- Legacy code cleanup (technical debt, non-blocking)

## Assumptions

- The container image build process is accessible and modifiable in this repository
- The existing fetcher/loader pattern (used by 14 sources in PR #87) is the correct integration pattern for UniProt, PDB, and ORCID
- Pre-computing molecule properties for ~965K existing compounds is feasible within storage and processing constraints
- The secrets manager is the sole secrets management solution; no migration to another system is planned
- behavior-labs-ai specs 029-034 are the definitive list of required downstream views
- The ORCID public API provides sufficient data for initial KOL identification without Member API access

## Dependencies

- **GitHub Issue #88**: CronJob container image fix (P1, blocking all ingestion)
- **GitHub Issue #81**: Missing API views (P2, blocking behavior-labs-ai)
- **GitHub Issues #42, #50, #51**: Remaining molecule data sources (P3)
- **GitHub Issue #20**: Dependency management (P4)
- **GitHub Issue #57**: Secret documentation (P5)
- **External**: PatentsView API key must be obtained and configured for the patents view to return data
- **External**: EPO consumer credentials must be obtained for EPO OPS data
