# Feature Specification: Prioritized Issue Resolution

**Feature Branch**: `005-prioritized-issue-resolution`
**Created**: 2026-01-30
**Status**: Draft
**Input**: User description: "Prioritized issue resolution for dk-data-fe production readiness based on ISSUES_PRIORITY.md analysis"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Secure API Access (Priority: P1)

As an operations team member, I need the data platform to enforce secure authentication so that sensitive hospital scoring data, financial indicators, and competitive intelligence cannot be accessed by unauthorized users.

**Why this priority**: Security vulnerabilities (GitHub Issues #3 and #4) are classified as P0-Critical. The platform currently allows authentication bypass through empty/weak JWT secrets and grants anonymous users read access to all sensitive tables. This must be resolved before any production deployment.

**Independent Test**: Can be fully tested by attempting API access with forged JWT tokens and as anonymous users, verifying that sensitive endpoints return 401/403 errors appropriately.

**Acceptance Scenarios**:

1. **Given** a user without valid credentials, **When** they attempt to access the `/targets` endpoint, **Then** they receive a 401 Unauthorized response
2. **Given** a user with a forged JWT token using an empty secret, **When** they attempt to access protected endpoints, **Then** authentication fails and access is denied
3. **Given** the anonymous role, **When** they access the API, **Then** they can only see explicitly public endpoints (health check, API documentation)
4. **Given** a user with valid analyst credentials, **When** they access the `/targets` endpoint, **Then** they receive the hospital scoring data appropriate to their role

---

### User Story 2 - Functional Database Initialization (Priority: P1)

As a platform administrator, I need the database initialization job to complete successfully so that the platform has the required database roles, schemas, and permissions for PostgREST to function.

**Why this priority**: GitHub Issue #56 is classified as P0-Critical and blocks all database functionality. Without successful db-init, PostgREST reports "0 Relations" and the platform cannot serve any data.

**Independent Test**: Can be fully tested by running the db-init job and verifying all roles are created, permissions are applied, and PostgREST can connect and see available relations.

**Acceptance Scenarios**:

1. **Given** a fresh database, **When** the db-init job runs, **Then** all required roles (authenticator, web_anon, analyst, api_user, readonly) are created
2. **Given** the db-init job has completed, **When** PostgREST starts, **Then** it reports the expected number of relations, relationships, and functions
3. **Given** the db-init job has already run, **When** it runs again (idempotent), **Then** it completes without errors and maintains correct state

---

### User Story 3 - API Schema with Data Access (Priority: P1)

As an API consumer, I need the platform to expose data through PostgREST so that I can query hospital targeting information via RESTful endpoints.

**Why this priority**: GitHub Issue #60 blocks API functionality. Even with authentication fixed, there's no data to access if no tables/views exist in the API schema.

**Independent Test**: Can be fully tested by querying the PostgREST endpoints and receiving structured data responses.

**Acceptance Scenarios**:

1. **Given** an authenticated analyst user, **When** they query `/targets`, **Then** they receive a JSON array of hospital targeting records
2. **Given** an authenticated user, **When** they query an endpoint with filters, **Then** results are filtered according to PostgREST query parameters
3. **Given** the database has data, **When** a user queries `/data_catalog`, **Then** they see metadata about available data sources and freshness

---

### User Story 4 - CI/CD Pipeline for Automated Deployment (Priority: P2)

As a developer, I need an automated CI/CD pipeline so that code changes are tested and deployed consistently without manual intervention.

**Why this priority**: GitHub Issue #59 is classified as P1-High. Without CI/CD, deployments are manual, error-prone, and inconsistent across environments.

**Independent Test**: Can be fully tested by pushing a commit and verifying the pipeline runs tests, builds containers, and deploys to staging.

**Acceptance Scenarios**:

1. **Given** a developer pushes code to a feature branch, **When** the CI pipeline runs, **Then** all tests execute and results are reported
2. **Given** code is merged to the main branch, **When** the CD pipeline runs, **Then** container images are built and pushed to the registry
3. **Given** a new container image is published, **When** the deployment triggers, **Then** the staging environment is updated within minutes

---

### User Story 5 - Container Images for Kubernetes (Priority: P2)

As an operations team member, I need container images for all platform services so that they can be deployed to Kubernetes.

**Why this priority**: GitHub Issues #54 and #55 are classified as P1-High. The job-trigger service and ingestion CronJobs cannot run in Kubernetes without published container images.

**Independent Test**: Can be fully tested by pulling the container images and running them locally or in a test cluster.

**Acceptance Scenarios**:

1. **Given** the job-trigger Dockerfile, **When** the image is built, **Then** it runs successfully and responds to HTTP requests
2. **Given** the ingestion CronJob Dockerfile, **When** the image is built, **Then** it can execute data fetching jobs
3. **Given** container images are published, **When** Kubernetes references them, **Then** pods start successfully

---

### User Story 6 - Health Check Endpoints (Priority: P2)

As a Kubernetes operator, I need health check endpoints so that the orchestrator can detect and recover from service failures.

**Why this priority**: GitHub Issue #58 is P1-High. Without health endpoints, Kubernetes cannot perform liveness/readiness probes, leading to undetected failures.

**Independent Test**: Can be fully tested by hitting the health endpoint and verifying correct status responses.

**Acceptance Scenarios**:

1. **Given** PostgREST is healthy, **When** the health endpoint is called, **Then** it returns a 200 status
2. **Given** the database connection fails, **When** the health endpoint is called, **Then** it returns a non-200 status indicating the issue
3. **Given** Kubernetes probes are configured, **When** a service becomes unhealthy, **Then** the pod is restarted automatically

---

### User Story 7 - Observability Integration (Priority: P3)

As an operations team member, I need metrics, logs, and traces so that I can monitor platform health and troubleshoot issues.

**Why this priority**: GitHub Issues #11 and #61 are P1-High but ranked lower than blocking functionality. Observability is essential for production operations but not for initial deployment.

**Independent Test**: Can be fully tested by generating load and verifying metrics appear in Grafana and logs are searchable.

**Acceptance Scenarios**:

1. **Given** PostgREST is handling requests, **When** I view the Grafana dashboard, **Then** I see request latency and error rate metrics
2. **Given** a CronJob runs, **When** I search logs, **Then** I find structured log entries for the job execution
3. **Given** an alert condition is triggered, **When** the threshold is breached, **Then** I receive a notification

---

### User Story 8 - CronJob Failure Detection (Priority: P3)

As an operations team member, I need to be alerted when data ingestion jobs fail so that I can investigate and resolve data freshness issues.

**Why this priority**: GitHub Issue #6 is P1-High. Silent CronJob failures lead to stale data without awareness, degrading data quality over time.

**Independent Test**: Can be fully tested by intentionally failing a CronJob and verifying an alert is generated.

**Acceptance Scenarios**:

1. **Given** a CronJob fails, **When** the failure is detected, **Then** an alert is sent to the operations team
2. **Given** a CronJob succeeds but produces no data, **When** the data freshness check runs, **Then** a warning is generated
3. **Given** data has not been updated within the expected interval, **When** the staleness check runs, **Then** an alert indicates which data source is stale

---

### Edge Cases

- What happens when database connection is lost during db-init job execution?
- How does the system handle JWT secret rotation without service interruption?
- What happens when a CronJob runs longer than its scheduled interval?
- How does the system behave when external data sources are unavailable?
- What happens when container images fail to pull in Kubernetes?

## Requirements *(mandatory)*

### Functional Requirements

**Security (P0)**

- **FR-001**: System MUST require cryptographically strong JWT secrets (minimum 256 bits) for authentication
- **FR-002**: System MUST deny all API access when JWT secret is empty or missing
- **FR-003**: System MUST restrict anonymous role access to only explicitly public endpoints (health, API docs)
- **FR-004**: System MUST enforce role-based access control for all sensitive data endpoints
- **FR-005**: System MUST validate JWT tokens against the configured secret before granting access

**Database Initialization (P0)**

- **FR-006**: System MUST create all required database roles in correct dependency order (authenticator, web_anon, analyst, api_user, readonly)
- **FR-007**: System MUST configure role hierarchy with proper inheritance
- **FR-008**: System MUST apply schema-level permissions correctly
- **FR-009**: System MUST handle idempotent re-execution without errors
- **FR-010**: System MUST properly escape PL/pgSQL blocks in shell heredocs

**API Schema (P1)**

- **FR-011**: System MUST expose data views in the `api` schema for PostgREST
- **FR-012**: System MUST provide a health check view accessible to Kubernetes probes
- **FR-013**: System MUST include a data catalog view showing available data sources and freshness
- **FR-014**: System MUST implement row-level security where appropriate for multi-tenant access

**CI/CD (P1)**

- **FR-015**: System MUST run automated tests on every pull request
- **FR-016**: System MUST build and publish container images on merge to main using branch+SHA tags (e.g., `main-abc1234`)
- **FR-017**: System MUST deploy to staging environment automatically after image publication by updating image tags in k8s manifests via CI
- **FR-018**: System MUST fail the pipeline if tests do not pass
- **FR-018a**: GitOps MUST use a single consolidated ArgoCD AppProject (`dk-data`) with both `dk-data-staging` and `dk-data-prod` namespaces in destinations list

**Container Images (P1)**

- **FR-019**: System MUST provide a container image for the job-trigger FastAPI service
- **FR-020**: System MUST provide container images for ingestion CronJobs
- **FR-021**: System MUST publish images to a container registry accessible by Kubernetes
- **FR-021a**: Job-trigger deployment MUST be enabled after image is published (staging: 1 replica, prod: 2 replicas)

**Observability (P2)**

- **FR-022**: System MUST expose Prometheus metrics for PostgREST requests
- **FR-023**: System MUST generate structured logs in JSON format
- **FR-024**: System MUST configure ServiceMonitor resources for Prometheus scraping
- **FR-025**: System MUST define PrometheusRule resources for critical alerts
- **FR-026**: System MUST detect and alert on CronJob failures

### Key Entities

- **Database Role**: Represents a permission level in PostgreSQL (authenticator, web_anon, analyst, api_user, readonly) with specific grants to schemas and tables
- **API View**: A database view exposed through PostgREST that provides read access to underlying data with appropriate filtering
- **Container Image**: A packaged service (job-trigger, ingestion CronJob) ready for Kubernetes deployment
- **Alert Rule**: A condition definition that triggers notifications when metrics exceed thresholds
- **CronJob**: A scheduled task that fetches data from external sources and loads it into the database

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Unauthenticated requests to protected endpoints return 401 within 100ms
- **SC-002**: Forged JWT tokens using empty/weak secrets are rejected 100% of the time
- **SC-003**: Database initialization job completes successfully on fresh and existing databases
- **SC-004**: PostgREST reports expected relations count (non-zero) after db-init
- **SC-005**: API endpoints return data within 500ms for standard queries
- **SC-006**: CI/CD pipeline completes (tests + build + deploy) within 10 minutes
- **SC-007**: Container images are published and pullable from Kubernetes
- **SC-008**: Health endpoint responds correctly in under 100ms
- **SC-009**: Metrics appear in Grafana within 60 seconds of request generation
- **SC-010**: CronJob failure alerts are delivered within 5 minutes of failure detection
- **SC-011**: All security issues (GitHub #3, #4) are resolved with zero regression
- **SC-012**: All blocking issues (GitHub #56, #60) are resolved enabling basic API functionality

## Assumptions

- Prometheus Operator CRDs are available in the target Kubernetes cluster for ServiceMonitor and PrometheusRule resources
- Doppler is configured for secret management and accessible from the cluster
- The existing dk-alchemy infrastructure provides Grafana, Prometheus, and logging stack
- GitHub Actions is the CI/CD platform
- Container images will be stored in a registry accessible by the Kubernetes cluster (GitHub Container Registry or similar)
- The base Kubernetes namespace and network policies are already configured

## Dependencies

- dk-alchemy cluster must be operational with all infrastructure services
- Doppler project access for secret synchronization
- GitHub Actions workflow permissions for the repository
- Container registry credentials for image publishing

## Clarifications

### Session 2026-01-30

- Q: Should staging and prod use separate AppProjects or a consolidated single AppProject? → A: Consolidate into single AppProject with both namespaces in destinations list
- Q: How should PR testing be implemented given only build-push.yaml exists? → A: Create separate `ci.yaml` workflow for PR testing (pytest + ruff)
- Q: Should job-trigger remain disabled (replicas: 0) or be enabled after image builds? → A: Enable both environments once image builds (staging: 1 replica, prod: 2 replicas)
- Q: How should image updates trigger deployments given ArgoCD won't detect `latest` tag changes? → A: Use branch+SHA tags (e.g., `main-abc1234`); update manifest in CI after build

## Out of Scope

- New data source integrations (P3 issues in ISSUES_PRIORITY.md)
- Frontend dashboard implementation (GitHub #52)
- Multi-tenancy architecture changes (GitHub #8)
- Full compliance implementation for PII/PHI (requires separate compliance review)
- Database backup and recovery automation (GitHub #13 - separate initiative)
