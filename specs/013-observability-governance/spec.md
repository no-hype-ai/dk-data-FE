# Feature Specification: Observability & Platform Governance

**Feature Branch**: `013-observability-governance`
**Created**: 2026-02-15
**Status**: Draft
**Input**: GitHub Issue #91 (observability), #17 (audit trail), #9 (migration strategy), #18 (PII/PHI handling), #19 (data retention policy)

## Clarifications

### Session 2026-02-15

- Q: Which roles should have read access to audit log data? → A: Only `api_user` role can query audit logs (admin-level access)

## User Scenarios & Testing

### User Story 1 - Deploy ServiceMonitors and Verify Metrics Scraping (Priority: P1)

The platform operator needs to verify that the existing Prometheus instrumentation in the job-trigger service is actually being scraped and populating Grafana dashboards. The ServiceMonitor and PrometheusRule manifests already exist in the codebase (`k8s/base/service-monitor.yaml`, `k8s/base/alert-rules.yaml`) but have never been deployed because Prometheus Operator CRDs were not installed until recently (dk-alchemy PR #183). The operator needs to validate labels match the cluster's Prometheus scrape configuration, deploy the resources, and confirm that all 10 defined metrics appear in Grafana.

**Why this priority**: Without working metrics scraping, three Grafana dashboards (`dk-data-platform-status`, `dk-data-pipeline`, `dk-data-api`) show empty panels. This is the highest-impact observability gap.

**Independent Test**: Port-forward to the job-trigger pod on port 8000, curl `/metrics`, and confirm all 10 metric families are emitted. After ServiceMonitor deployment, query Prometheus for `http_requests_total{namespace="dk-data"}` and confirm data points exist.

**Acceptance Scenarios**:

1. **Given** the job-trigger service is running, **When** an operator curls `localhost:8000/metrics` via port-forward, **Then** all 10 defined metric families are present in the response
2. **Given** ServiceMonitors are deployed to the cluster, **When** Prometheus scrapes the job-trigger service, **Then** metrics appear in Prometheus within 60 seconds of the scrape interval
3. **Given** metrics are being scraped, **When** the operator opens each of the 3 Grafana dashboards, **Then** panels that depend on `http_requests_total`, `batch_job_*`, and `dk_data_source_*` metrics show data instead of "No data"
4. **Given** PrometheusRules are deployed, **When** a data source becomes stale (no refresh for >48 hours), **Then** a `DataSourceStale` alert fires in Prometheus

**Resolves**: GitHub Issue #91 (tasks 1-3, 5)

---

### User Story 2 - Add PostgREST Observability (Priority: P2)

PostgREST does not expose a native `/metrics` endpoint. The platform operator needs to monitor PostgREST availability, request latency, and error rates. A lightweight approach using blackbox-style probing of the PostgREST health endpoint will provide basic availability monitoring without requiring a sidecar container.

**Why this priority**: PostgREST is the primary API gateway serving all downstream consumers (behavior-labs-ai, dashboards). Without monitoring, outages go undetected until users report them.

**Independent Test**: Deploy the PostgREST probe configuration. Query Prometheus for `probe_success{job="dk-data-postgrest"}` and confirm it returns 1 when PostgREST is healthy.

**Acceptance Scenarios**:

1. **Given** PostgREST is running and healthy, **When** the probe checks the health endpoint, **Then** `probe_success` returns 1 and `probe_http_duration_seconds` is recorded
2. **Given** PostgREST goes down, **When** the probe fails, **Then** `probe_success` returns 0 and an `APIUnavailable` alert fires within 5 minutes
3. **Given** PostgREST probes are active, **When** the operator opens the `dk-data-api` dashboard, **Then** the availability panel shows uptime percentage based on probe data

**Resolves**: GitHub Issue #91 (task 4)

---

### User Story 3 - Implement Audit Trail for Data Changes and API Access (Priority: P3)

The compliance team needs a record of who accessed what data, when data was modified, and what system actions occurred. Audit log models already exist in the codebase (`src/dk_data/models/application/audit_log.py` with 16 action types and 8 categories) but are not wired into any middleware or data pipelines. The system needs to capture API access events and data ingestion events automatically, and expose an audit log query endpoint for compliance review.

**Why this priority**: Regulatory readiness requires demonstrating data lineage and access control. The models already exist, reducing implementation effort.

**Independent Test**: Make an authenticated API request to any PostgREST endpoint, then query the audit log and confirm the access event was recorded with timestamp, user role, endpoint, and response status.

**Acceptance Scenarios**:

1. **Given** a user makes an authenticated API request, **When** the request completes, **Then** an audit log entry is created with timestamp, user identity (from JWT), endpoint path, HTTP method, and response status
2. **Given** a data ingestion CronJob runs, **When** the job completes, **Then** an audit log entry records the data source, record count, duration, and success/failure status
3. **Given** audit logs are accumulating, **When** an admin-level user (`api_user` role) queries the audit log with date range and category filters, **Then** paginated results are returned matching the query criteria
4. **Given** an audit log entry exists, **When** anyone attempts to modify or delete it, **Then** the operation is denied (audit logs are append-only)

**Resolves**: GitHub Issue #17

---

### User Story 4 - Automated Database Migration Runner (Priority: P4)

Platform engineers currently run database migrations manually by executing SQL files against the database. With 26 migrations and growing, this is error-prone and creates environment drift between dev, staging, and production. The system needs an automated migration runner that tracks which migrations have been applied, runs pending migrations in order, and prevents duplicate application.

**Why this priority**: Manual migration execution is the most common source of deployment errors. Every new data source or API view adds another migration that must be manually applied across 3 environments.

**Independent Test**: Add a new empty migration file, run the migration runner, and confirm it applies only the new migration. Run it again and confirm it reports "no pending migrations."

**Acceptance Scenarios**:

1. **Given** a clean database with no migration history, **When** the migration runner executes, **Then** all 26+ existing migrations are applied in numeric order and recorded in a migration tracking table
2. **Given** a database with some migrations already applied, **When** the migration runner executes, **Then** only unapplied migrations are run, and previously applied migrations are skipped
3. **Given** a migration fails mid-execution, **When** the runner encounters the error, **Then** it stops, reports the failing migration with the error message, and does not mark it as applied
4. **Given** the migration runner is integrated into the deployment pipeline, **When** the container starts, **Then** pending migrations are automatically applied before the application accepts traffic

**Resolves**: GitHub Issue #9

---

### User Story 5 - PII/PHI Data Classification and Retention Policy (Priority: P5)

The platform ingests data from sources that may contain personally identifiable information (ORCID researcher profiles with names, affiliations, biographies) and operates in a healthcare-adjacent domain. The organization needs a data classification scheme that identifies which tables contain PII, a retention policy that defines how long each data category is kept, and enforcement mechanisms that automatically purge expired data.

**Why this priority**: Combining PII/PHI handling (#18) and data retention (#19) into a single story because they are tightly coupled -- retention rules depend on data classification, and PII has stricter retention requirements than anonymized data.

**Independent Test**: Run the data classification tool against the database, confirm ORCID tables are classified as "contains PII," and verify the retention policy document lists all data categories with retention periods.

**Acceptance Scenarios**:

1. **Given** the platform has tables containing PII (ORCID researcher names, affiliations), **When** the data classification audit runs, **Then** each table is tagged with its classification level (public, internal, PII, sensitive)
2. **Given** a data retention policy is defined, **When** data exceeds its retention period, **Then** the existing purge mechanism (`purge_history.py`) applies the policy and removes expired records
3. **Given** a retention schedule exists, **When** a new data source is added, **Then** the retention period for its raw and processed data is defined as part of the data source registration
4. **Given** PII-containing tables are identified, **When** data is exported or accessed via API, **Then** PII fields are clearly documented in the API schema so downstream consumers can handle them appropriately

**Resolves**: GitHub Issues #18 and #19

---

### Edge Cases

- What happens when Prometheus Operator CRDs are removed or upgraded? ServiceMonitor resources should fail gracefully without affecting application pods
- What happens when the migration runner encounters a migration that has been manually applied but not tracked? The runner should detect the current schema state and allow marking migrations as already applied (baseline command)
- What happens when audit log storage grows unbounded? The audit log itself should have a retention period (default: 1 year for access logs, 7 years for data change logs)
- What happens when a CronJob runs but the job-trigger pod is not running? Batch job metrics from CronJobs should be persisted independently of the job-trigger pod lifecycle
- What happens when PostgREST is healthy but the database connection is broken? The health probe should detect this as an unhealthy state

## Requirements

### Functional Requirements

- **FR-001**: System MUST verify that all 10 defined Prometheus metric families are emitted by the job-trigger `/metrics` endpoint
- **FR-002**: System MUST deploy ServiceMonitor resources with labels matching the cluster's Prometheus scrape configuration
- **FR-003**: System MUST deploy PrometheusRule resources for data freshness, API health, batch job, and resource alerts
- **FR-004**: System MUST monitor PostgREST availability via health endpoint probing with success/failure and latency recording
- **FR-005**: System MUST record an audit log entry for every authenticated API access event with timestamp, user identity, endpoint, method, and status
- **FR-006**: System MUST record an audit log entry for every data ingestion job execution with source, record count, duration, and outcome
- **FR-007**: System MUST provide a queryable audit log endpoint accessible only to the `api_user` role, with filtering by date range, category, user, and action type
- **FR-008**: System MUST enforce append-only semantics on audit log entries (no updates or deletes)
- **FR-009**: System MUST track applied database migrations in a version table with migration number, filename, applied timestamp, and checksum
- **FR-010**: System MUST execute pending migrations in numeric order and skip already-applied migrations
- **FR-011**: System MUST halt migration execution on failure and report the error without marking the failed migration as applied
- **FR-012**: System MUST run pending migrations automatically as part of the deployment pipeline before the application accepts requests
- **FR-013**: System MUST classify all database tables by data sensitivity level (public, internal, PII, sensitive)
- **FR-014**: System MUST define retention periods for each data classification level
- **FR-015**: System MUST automatically purge data that exceeds its defined retention period using the existing purge infrastructure
- **FR-016**: System MUST include unit tests for all new code paths (migration runner, audit logging, data classification)

### Key Entities

- **ServiceMonitor**: Prometheus scrape configuration targeting a specific service, port, and metrics path
- **PrometheusRule**: Alerting rule definitions with conditions, severity levels, and notification labels
- **AuditLogEntry**: Immutable record of a system event including timestamp, actor, action, target, and metadata
- **MigrationRecord**: Tracking entry for an applied database migration including version number, filename, checksum, and applied timestamp
- **DataClassification**: Table-level metadata tagging data sensitivity as public, internal, PII, or sensitive
- **RetentionPolicy**: Per-classification rule defining maximum data age before automatic purging

## Success Criteria

### Measurable Outcomes

- **SC-001**: All 3 Grafana dashboards (`dk-data-platform-status`, `dk-data-pipeline`, `dk-data-api`) show live data in previously empty panels within 24 hours of deployment
- **SC-002**: PostgREST availability is monitored with uptime percentage visible in dashboards, with alerts firing within 5 minutes of an outage
- **SC-003**: 100% of authenticated API requests and data ingestion jobs produce audit log entries within 1 second of completion
- **SC-004**: Database migrations execute automatically during deployment with zero manual SQL execution required across all environments
- **SC-005**: Migration runner correctly identifies and skips already-applied migrations, achieving idempotent deployment behavior
- **SC-006**: All database tables have documented data classification levels, and PII-containing tables are explicitly identified
- **SC-007**: Data older than the defined retention period is automatically purged within 24 hours of expiration

## Assumptions

- Prometheus Operator CRDs are installed in the cluster (confirmed via dk-alchemy PR #183)
- Grafana is configured with the Prometheus data source and dashboards are already deployed via dk-alchemy
- The existing `purge_history.py` script provides a working foundation for automated data purging
- The existing `AuditLog` models in `src/dk_data/models/application/audit_log.py` define the correct schema for audit entries
- PostgREST health endpoint (`/health` or `/`) returns a meaningful status that can be probed
- The 26 existing migrations have been manually applied to staging and production databases and represent the current schema state
- PII in this context is limited to researcher identity data (names, affiliations from ORCID) -- the platform does not handle patient health records (PHI)

## Scope Boundaries

### In Scope
- ServiceMonitor and PrometheusRule deployment and verification
- PostgREST health probing (blackbox approach)
- Audit logging middleware for API access and ingestion events
- Automated migration runner with tracking table
- Data classification documentation and retention policy definition
- Integration of purge mechanism with retention policy

### Out of Scope
- Custom PostgREST metrics exporter sidecar (deferred -- blackbox probing is sufficient for MVP)
- Real-time alerting notification channels (Slack, PagerDuty) -- alerts fire in Prometheus; routing is managed by dk-alchemy
- AI decision audit trail (model inputs/outputs) -- deferred to future ML observability feature
- GDPR/CCPA subject access request automation -- deferred until the platform handles end-user personal data
- Frontend integration (#52) -- remains a separate initiative
- Edwards/TAVR decoupling (#8) -- long-term architecture debt, not addressed here
