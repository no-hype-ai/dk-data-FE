# Feature Specification: Platform Stabilization

**Feature Branch**: `010-platform-stabilization`
**Created**: 2026-02-14
**Status**: Draft
**Input**: Comprehensive platform review of dk-data-fe identifying critical deployment failures, security vulnerabilities, missing data protection, near-zero test coverage, and observability gaps

## Clarifications

### Session 2026-02-14

- Q: How should image promotion from staging to production work? → A: Auto-promote — image automatically gets a production tag after staging jobs succeed.
- Q: What backup retention policy should be used? → A: 7 daily + 4 weekly — daily backups retained for 7 days, weekly backups retained for 30 days.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Restore Data Ingestion Pipelines (Priority: P1)

As a platform operator, I need all data ingestion pipelines to run successfully so that the platform continuously receives fresh data from external sources (CMS, HRSA, molecule APIs) without manual intervention.

Currently, all 5 scheduled data jobs and the job-trigger service are broken in both staging and production because the cluster cannot pull container images from the registry. No new data has been ingested since the pipelines broke.

**Why this priority**: Without functioning ingestion, the platform serves stale data. This is the single most impactful fix -- it unblocks the entire data pipeline that downstream consumers (API, dashboards, analytics) depend on.

**Independent Test**: Can be fully tested by verifying each scheduled job completes successfully and new data appears in the database after a job run.

**Acceptance Scenarios**:

1. **Given** the container registry credentials are configured, **When** the job-trigger service starts, **Then** the pod reaches Running state and the health endpoint responds successfully within 60 seconds.
2. **Given** the cluster can resolve external hostnames, **When** a scheduled data job runs, **Then** the job pod pulls its image, executes the data fetch, and completes without error.
3. **Given** all 5 scheduled jobs are enabled, **When** 24 hours elapse, **Then** at least the daily-scheduled jobs (catalog-refresh, mol-fetch-daily, mol-transform) have completed successfully.
4. **Given** the production environment, **When** a staging-tagged image passes all staging scheduled jobs successfully, **Then** the system automatically tags that image for production use without manual intervention.

---

### User Story 2 - Protect Data from Loss (Priority: P1)

As a platform owner, I need automated database backups with verified recovery so that hardware failure, human error, or data corruption does not result in permanent data loss.

Currently, no automated backups exist. The shared PostgreSQL instance holds all TAVR targeting data, molecule pipeline data, and platform metadata. A single failure could destroy months of accumulated and transformed data.

**Why this priority**: Data is the platform's core asset. Without backups, every other investment (pipeline development, transformation models, API views) is at risk of total loss. This is a prerequisite for any production deployment.

**Independent Test**: Can be fully tested by triggering a backup, then restoring to a temporary database and verifying data integrity.

**Acceptance Scenarios**:

1. **Given** the backup system is configured, **When** the daily backup schedule triggers, **Then** a complete database snapshot is stored in object storage with a timestamped identifier.
2. **Given** a backup exists in storage, **When** an operator initiates a restore to a test database, **Then** all schemas, tables, and row counts match the source database at backup time.
3. **Given** backups are running daily, **When** 7 days elapse, **Then** at least 7 daily backup snapshots exist; and after 30 days, at least 4 weekly snapshots are retained alongside the 7 most recent daily snapshots.
4. **Given** the backup storage is accessible, **When** an operator checks backup health, **Then** they can see the timestamp, size, and success/failure status of each recent backup.

---

### User Story 3 - Eliminate Security Vulnerabilities (Priority: P1)

As a security-conscious operator, I need hardcoded credentials removed from source control and database names standardized so that no default or well-known passwords exist in any deployed environment.

Currently, the database initialization script contains a hardcoded password for the PostgREST authenticator role. The database name differs across local development, CI, and Kubernetes environments, creating confusion and potential misapplied migrations.

**Why this priority**: Hardcoded credentials in source control are a high-severity security finding. Combined with database name drift, this creates risk of both unauthorized access and operational errors.

**Independent Test**: Can be fully tested by scanning the codebase for hardcoded credentials and verifying environment consistency.

**Acceptance Scenarios**:

1. **Given** the database initialization script, **When** it runs in any environment, **Then** no hardcoded passwords are used; all credentials are injected from external secret management.
2. **Given** the codebase is scanned for credential patterns, **When** searching for known default values, **Then** zero matches are found for hardcoded passwords, API keys, or tokens.
3. **Given** the database name configuration, **When** comparing local dev, CI, staging, and production, **Then** all environments use the same standardized database name.
4. **Given** an operator runs the init script with a default/placeholder password, **Then** the script rejects the value and fails with a clear error message.

---

### User Story 4 - Establish Test Safety Net (Priority: P2)

As a developer, I need a baseline test suite so that code changes can be validated before deployment and regressions are caught automatically in CI.

Currently, the platform has ~88,000 lines of Python code with only 3 test files covering PostgREST access control. No tests exist for data fetchers, transformation logic, API endpoints, Pydantic validators, or any service-layer business logic.

**Why this priority**: Without tests, every deployment is a gamble. Establishing even minimal coverage creates a foundation that prevents the most obvious breakages and enables confident iteration.

**Independent Test**: Can be fully tested by running the test suite in CI and verifying it passes with reported coverage above the threshold.

**Acceptance Scenarios**:

1. **Given** the CI pipeline runs on a pull request, **When** tests execute, **Then** the test suite passes and reports code coverage percentage.
2. **Given** a minimum coverage threshold is configured, **When** coverage falls below the threshold, **Then** the CI pipeline fails with a clear message indicating the gap.
3. **Given** the data validation models exist, **When** unit tests run, **Then** at least the core Pydantic models and data validators are covered.
4. **Given** the data fetchers exist, **When** integration tests run with mocked external services, **Then** each fetcher's happy path and common error paths are verified.

---

### User Story 5 - Reduce Repository Bloat (Priority: P2)

As a developer, I need raw data files removed from version control so that repository clone times are reasonable and data management follows best practices.

Currently, 182MB of raw CSV files are committed to the repository, slowing clones and CI runs. This data should be fetched by the ingestion pipeline, not stored in git.

**Why this priority**: Repository bloat affects every developer and every CI run. Removing it is a one-time fix with permanent improvement to developer experience and CI performance.

**Independent Test**: Can be fully tested by cloning the repository and verifying raw data files are absent and listed in .gitignore.

**Acceptance Scenarios**:

1. **Given** the raw data directory is in .gitignore, **When** a developer clones the repository, **Then** no CSV data files are downloaded as part of the clone.
2. **Given** the ingestion pipeline runs, **When** data is fetched from external sources, **Then** it is stored in the appropriate external location (object storage or local data directory outside version control).
3. **Given** the raw data directory exists locally, **When** a developer runs `git status`, **Then** files in the raw data directory do not appear as untracked or modified.

---

### User Story 6 - Enable Platform Observability (Priority: P3)

As a platform operator, I need metrics collection, alerting, and dashboard visibility so that I can monitor platform health, detect issues proactively, and troubleshoot problems efficiently.

Currently, observability infrastructure exists in the codebase (OpenTelemetry, ServiceMonitor, PrometheusRule) but is disabled. Logs go to stdout without aggregation. No dashboards exist.

**Why this priority**: Observability transforms operations from reactive firefighting to proactive monitoring. While not blocking current functionality, it is essential for sustainable production operations.

**Independent Test**: Can be fully tested by verifying metrics are scraped, alerts fire on test conditions, and dashboards render data.

**Acceptance Scenarios**:

1. **Given** the monitoring stack is enabled, **When** the platform is running, **Then** key metrics (request latency, error rate, job success/failure) are collected and queryable.
2. **Given** alerting rules are configured, **When** a critical condition occurs (e.g., all CronJobs fail), **Then** an alert fires within the configured evaluation window.
3. **Given** dashboards are available, **When** an operator opens the dashboard, **Then** they see current platform health including API performance, job status, and database connection usage.

---

### User Story 7 - Clean Up Issue Tracker (Priority: P3)

As a project manager, I need the GitHub issue tracker to accurately reflect the current state of work so that the team can prioritize effectively without noise from resolved or duplicate issues.

Currently, 50 issues are open, approximately 15 of which are already resolved in code. Several others overlap or duplicate each other.

**Why this priority**: An accurate backlog is essential for planning. Closing resolved issues and consolidating duplicates reduces cognitive load and makes the remaining work clearer.

**Independent Test**: Can be fully tested by reviewing each closed issue against the codebase to verify the resolution claim, and confirming no duplicate issues remain.

**Acceptance Scenarios**:

1. **Given** issues identified as resolved in the platform review, **When** an operator verifies each against the codebase, **Then** confirmed-resolved issues are closed with a comment citing the evidence.
2. **Given** overlapping issues exist, **When** duplicates are identified, **Then** the lower-priority duplicate is closed with a cross-reference to the surviving issue.
3. **Given** the cleanup is complete, **When** viewing open issues, **Then** every open issue represents genuinely unresolved work with a clear priority label.

---

### Edge Cases

- What happens if the backup storage (MinIO) is full or unreachable when a backup runs? The backup job should fail with a clear error and alert, not silently skip.
- What happens if the container registry credential expires or is rotated? The platform should surface clear errors, and the credential rotation procedure should be documented.
- What happens if a database migration is applied to the wrong database due to name mismatch? The standardized naming and pre-flight validation should prevent this scenario entirely.
- What happens if test coverage drops below the threshold due to new untested code? CI should block the merge with a clear message indicating which files need coverage.
- What happens if DNS resolution fails intermittently rather than permanently? Scheduled jobs should have retry logic so transient failures do not cause permanent job failure.

## Requirements *(mandatory)*

### Functional Requirements

**Ingestion Pipeline Restoration**

- **FR-001**: System MUST authenticate to the container registry to pull deployment images in all environments (staging and production).
- **FR-002**: System MUST resolve external hostnames from within the cluster for both image pulls and data source API calls.
- **FR-003**: Each scheduled data job MUST complete within its configured deadline or retry automatically on transient failures.
- **FR-004**: Production deployments MUST use production-tagged images that are distinct from staging-tagged images. Images MUST be automatically promoted to production after staging validation succeeds (no manual approval gate required).

**Data Protection**

- **FR-005**: System MUST perform automated daily database backups to object storage.
- **FR-006**: Each backup MUST be verifiable -- an operator must be able to confirm backup integrity without performing a full restore.
- **FR-007**: Backup retention MUST follow this schedule: daily backups retained for 7 days, weekly backups retained for 30 days. Expired backups MUST be automatically deleted.
- **FR-008**: Backup and restore procedures MUST be documented with step-by-step runbooks.

**Security Hardening**

- **FR-009**: System MUST NOT contain any hardcoded credentials, passwords, API keys, or tokens in source-controlled files.
- **FR-010**: Database initialization MUST accept credentials exclusively from external secret management (environment variables or secret store).
- **FR-011**: The database name MUST be consistent across all environments (local, CI, staging, production) with a single configurable default.
- **FR-012**: System MUST reject known-default or placeholder values for security-critical configuration (JWT secrets, database passwords).

**Test Coverage**

- **FR-013**: CI pipeline MUST run the test suite on every pull request and report coverage.
- **FR-014**: CI pipeline MUST enforce a minimum code coverage threshold, blocking merges that fall below it.
- **FR-015**: Test suite MUST include unit tests for core data validation models.
- **FR-016**: Test suite MUST include integration tests for data fetchers using mocked external services.

**Repository Hygiene**

- **FR-017**: Raw data files MUST be excluded from version control via .gitignore.
- **FR-018**: System MUST document the procedure for obtaining raw data files outside of git.

**Observability**

- **FR-019**: System MUST expose metrics that are scrapeable by the monitoring stack.
- **FR-020**: System MUST define alerting rules for critical failure conditions (all jobs failing, API unreachable, database connection errors).
- **FR-021**: System MUST provide at least one operator dashboard showing platform health at a glance.

**Issue Tracker Maintenance**

- **FR-022**: Issues confirmed as resolved by code review MUST be closed with evidence citations.
- **FR-023**: Duplicate or overlapping issues MUST be consolidated with cross-references.

### Key Entities

- **Scheduled Job**: A recurring data ingestion task with a schedule, target data source, execution history, and success/failure status.
- **Backup Snapshot**: A point-in-time database backup with timestamp, storage location, size, integrity checksum, and retention policy.
- **Platform Secret**: A credential or key managed externally (via Doppler or Kubernetes secrets), with an associated environment scope and rotation schedule.
- **Coverage Report**: A test execution artifact showing per-file and aggregate code coverage percentages, generated on each CI run.
- **Platform Metric**: A time-series measurement of platform behavior (latency, throughput, error rate, job duration) collected continuously.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 5 scheduled data ingestion jobs complete successfully within 24 hours of pipeline restoration, with zero image-pull errors.
- **SC-002**: Database backups run daily and at least 7 consecutive successful backups exist within the first week of enablement.
- **SC-003**: A backup can be restored to a temporary database within 30 minutes, with full data integrity verified.
- **SC-004**: Zero hardcoded credentials exist in source-controlled files, confirmed by automated scanning.
- **SC-005**: All environment configurations reference the same database name, with no drift across local, CI, staging, and production.
- **SC-006**: CI test suite achieves at least 15% code coverage (baseline) within the first sprint, with a path to 30% within 30 days.
- **SC-007**: Repository clone time decreases by at least 50% after raw data removal (measured on a clean clone).
- **SC-008**: Platform operator can view real-time health status (API latency, job success rate, database connectivity) from a single dashboard.
- **SC-009**: Open issue count decreases by at least 15 after closing resolved and duplicate issues, with remaining issues accurately reflecting pending work.
- **SC-010**: No scheduled job remains in a failed state for more than 2 consecutive runs without an alert being raised.

## Assumptions

- The existing MinIO instance in the `infra` namespace has sufficient storage capacity for daily database backups and can be used without additional procurement.
- The Prometheus Operator CRDs can be installed on the k3d cluster without conflicting with existing infrastructure services.
- The Doppler secret management integration (DopplerSecret CRD) is functional and can be used as the sole credential source for all environments.
- The GitHub Container Registry (ghcr.io) will remain the image registry, and a GitHub PAT with `read:packages` scope can be provisioned for the Kubernetes cluster.
- Database name standardization to `dk_data` will not break any existing external integrations or downstream consumers.
- The k3d cluster DNS issue is a configuration problem (not a fundamental networking limitation) and can be resolved without cluster recreation.

## Dependencies

- **MinIO (infra namespace)**: Required for backup storage. Already running but capacity and access permissions need verification.
- **Doppler**: Required for secret injection. The DopplerSecret CRD must be functional in both staging and production namespaces.
- **GitHub PAT**: Required for container registry authentication. Must be provisioned with appropriate scope.
- **Prometheus Operator CRDs**: Required for observability enablement. Must be installed on the cluster before ServiceMonitor/PrometheusRule can be activated.

## Out of Scope

- New data source integrations (Issues #41-#51 molecule enablement, Issues #26-#35 CI fetchers) -- these are new capabilities, not stabilization.
- Frontend development (Issue #52) -- depends on stable API surface which this feature helps establish.
- Audit trail / compliance logging (Issue #17) -- important but a separate, larger effort requiring its own specification.
- Database replication or CloudNativePG migration -- scaling concern deferred until the platform is stable.
- Git history rewriting to remove previously committed large files -- optional optimization that requires team coordination.
