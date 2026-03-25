# Feature Specification: Data Layer Enhancement with PostgREST and GitOps Deployment

**Feature Branch**: `001-data-layer-postgrest-gitops`
**Created**: 2026-01-14
**Status**: Draft
**Input**: User description: "Review dk_data and expand ARCHITECTURE.md to enhance the data layer, taking advantage of PostgREST, and update docker-compose to also support a .gitops deployment based on target architecture from dk-alchemy"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - API Consumer Queries Data via REST (Priority: P1)

An application developer or frontend client needs to query the TAVR targeting data through a REST API without writing custom backend code. They access hospital scores, targeting summaries, and related data through PostgREST endpoints with filtering, pagination, and sorting capabilities.

**Why this priority**: The REST API is the primary data access pattern for downstream consumers. Without a well-designed API layer, the entire data platform's value cannot be realized by consuming applications.

**Independent Test**: Can be fully tested by querying the PostgREST endpoints with various filter combinations and verifying correct data is returned with proper pagination.

**Acceptance Scenarios**:

1. **Given** the API is running and data has been ingested, **When** a client sends a GET request to `/targets` with filters for state and score threshold, **Then** the system returns a paginated list of matching hospital targets with all required fields.
2. **Given** the API is running, **When** a client requests data with sorting by score descending and limit of 50, **Then** the system returns the top 50 highest-scoring targets in descending order.
3. **Given** a client makes a request, **When** the total result count exceeds the page size, **Then** the response includes proper pagination metadata (total count, page info) in headers.

---

### User Story 2 - DevOps Engineer Deploys to Kubernetes via GitOps (Priority: P2)

A DevOps engineer needs to deploy the TAVR data platform to a Kubernetes cluster using GitOps principles. They commit Kubernetes manifests to a git repository, and ArgoCD automatically synchronizes the desired state to the cluster, providing declarative, version-controlled infrastructure.

**Why this priority**: GitOps deployment enables production-grade deployments with audit trails, rollbacks, and automated synchronization, which is essential for operating the platform reliably at scale.

**Independent Test**: Can be tested by applying the Kubernetes manifests to a k3s cluster and verifying all components start correctly and can serve API requests.

**Acceptance Scenarios**:

1. **Given** manifests are committed to the gitops directory, **When** ArgoCD detects the change, **Then** it automatically applies the manifests to the target cluster and reports sync status.
2. **Given** a deployment is in progress, **When** the new pods are ready, **Then** the system performs zero-downtime rolling updates with health checks.
3. **Given** a bad configuration is deployed, **When** the operator requests a rollback, **Then** the previous version can be restored by reverting the git commit.

---

### User Story 3 - Developer Runs Full Stack Locally (Priority: P3)

A developer needs to run the complete data platform locally for development and testing. They use docker-compose to spin up PostgreSQL, PostgREST, SQLMesh, and supporting services with a single command, with data persisted between restarts.

**Why this priority**: Local development experience directly impacts developer productivity. A working local stack allows rapid iteration without deploying to shared environments.

**Independent Test**: Can be tested by running `docker compose up` and verifying all services start, data can be ingested, and API endpoints respond correctly.

**Acceptance Scenarios**:

1. **Given** docker-compose files exist, **When** the developer runs `docker compose up`, **Then** all services start successfully within 2 minutes with health checks passing.
2. **Given** services are running, **When** the developer ingests sample data, **Then** the data is visible through the PostgREST API.
3. **Given** the developer stops and restarts the stack, **When** they query the API, **Then** previously ingested data is still available (persistence works).

---

### User Story 4 - Platform Team Configures Role-Based API Access (Priority: P4)

A platform administrator needs to configure different access levels for the REST API. Anonymous users can read public targeting data, while authenticated users with appropriate roles can access detailed financial and certification data.

**Why this priority**: Security and access control are essential for production use, but the platform can initially operate with read-only anonymous access for MVP.

**Independent Test**: Can be tested by making API requests with and without valid JWT tokens and verifying the correct data is accessible based on role.

**Acceptance Scenarios**:

1. **Given** the API is configured with role-based access, **When** an anonymous request is made, **Then** only public views (targeting summaries, scores) are accessible.
2. **Given** a user has an authenticated JWT with "analyst" role, **When** they request detailed financial data, **Then** the system returns the restricted data.
3. **Given** an invalid or expired token is provided, **When** a request is made to a protected endpoint, **Then** the system returns a 401 Unauthorized response.

---

### Edge Cases

- What happens when the database connection is unavailable? PostgREST returns 503 Service Unavailable with appropriate retry headers.
- How does the system handle requests exceeding max_rows limit? Returns the configured maximum with pagination headers indicating more data exists.
- What happens when Kubernetes resources are insufficient for scheduled pods? Pods remain in Pending state with clear events explaining the constraint.
- How does GitOps handle conflicting manual changes to the cluster? ArgoCD detects drift and can auto-heal or alert depending on configuration.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose PostgreSQL views through PostgREST as RESTful API endpoints with OpenAPI documentation auto-generated.
- **FR-002**: System MUST support filtering, sorting, and pagination on all API endpoints via query parameters (e.g., `?state=eq.CA&score=gte.80&order=score.desc&limit=50`).
- **FR-003**: System MUST provide docker-compose configurations for local development that start all required services (PostgreSQL, PostgREST, Metabase).
- **FR-004**: System MUST provide Kubernetes manifests compatible with k3s and ArgoCD for GitOps deployment.
- **FR-005**: System MUST define an `api` schema in PostgreSQL containing views that expose curated data for API consumption.
- **FR-006**: System MUST support health check endpoints for all services to enable container orchestration readiness/liveness probes.
- **FR-007**: System MUST include database roles (`api_user`, `web_anon`, `authenticator`) with appropriate permissions for PostgREST operation.
- **FR-008**: System MUST persist configuration as code (database roles, API views, Kubernetes manifests) in the repository.
- **FR-009**: System MUST support environment-based configuration (development, staging, production) through environment variables and config files.
- **FR-010**: System MUST include Kustomize overlays for different deployment environments (base, dev, staging, prod).
- **FR-011**: System MUST support batch scheduling for data ingestion jobs (e.g., "fetch all CMS datasets") with configurable schedules.
- **FR-012**: System MUST maintain a data catalog table containing: table name, row count, last updated timestamp, health status, size in bytes, and schema information.
- **FR-013**: System MUST store semantic metadata (description, topic tags, column descriptions) in the catalog to support AI-powered data discovery and retrieval.
- **FR-014**: System MUST expose the data catalog via PostgREST API endpoint (`/catalog`) with filtering by topic, table name, and freshness status.
- **FR-015**: System MUST calculate table health status based on data freshness (configurable staleness thresholds per source) and data quality metrics (null rates, validation error counts).
- **FR-016**: System MUST support Kubernetes CronJobs for scheduled batch ingestion with cron expressions defined in GitOps manifests.
- **FR-017**: System MUST provide an API endpoint to trigger batch ingestion jobs on-demand (manual runs outside scheduled times).

### Key Entities

- **API Schema**: PostgreSQL schema containing views that expose data for REST API consumption. Maps SQLMesh mart/scoring tables to API-friendly representations.
- **PostgREST Configuration**: Settings controlling API behavior including schemas exposed, anonymous role, connection pooling, and max rows.
- **Kubernetes Deployment**: Container orchestration resources (Deployments, Services, ConfigMaps, Secrets) defining how services run in a cluster.
- **Docker Compose Stack**: Local development environment definition specifying services, networks, volumes, and their relationships.
- **Kustomize Base/Overlays**: Kubernetes manifest organization pattern separating common configuration from environment-specific customizations.
- **Data Catalog**: Metadata registry tracking all tables with operational metrics (row count, size, health, freshness) and semantic metadata (descriptions, topic tags, column info) for observability and AI retrieval.
- **Batch Job**: Scheduled ingestion task that fetches data from one or more sources (e.g., "all CMS datasets") on a configurable schedule.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: API consumers can retrieve targeting data with filtering and pagination in under 500ms for typical queries (fewer than 1000 results).
- **SC-002**: Local development stack starts and is ready to serve requests within 2 minutes of running `docker compose up`.
- **SC-003**: GitOps deployment to a fresh k3s cluster completes successfully within 5 minutes with all pods healthy.
- **SC-004**: Zero manual steps required after git commit for changes to be reflected in deployed environments (full GitOps automation).
- **SC-005**: All API endpoints return valid JSON responses with appropriate HTTP status codes for both success and error cases.
- **SC-006**: Documentation (ARCHITECTURE.md) accurately describes the enhanced data layer patterns and deployment options.
- **SC-007**: System supports at least 50 concurrent API connections without degradation in response times.

## Clarifications

### Session 2026-01-14

- Q: Should batch scheduling for data sources (CMS datasets, etc.) be in-scope? → A: Yes, include batch scheduling for data sources as in-scope.
- Q: What metadata should the data catalog table contain? → A: Full catalog with table name, row count, last updated, health status, size, schema info, description, topic tags, and column descriptions for AI retrieval.
- Q: How should AI agents discover and query the data catalog? → A: PostgREST API endpoint - catalog queryable at `/catalog` with filtering.
- Q: How should table health status be determined? → A: Freshness-based plus data quality checks (null rates, validation error counts).
- Q: How should batch jobs be scheduled and triggered? → A: Kubernetes CronJobs for scheduled runs plus API endpoint for manual/on-demand triggering.

## Assumptions

- PostgREST v12.x or later is used, supporting the latest configuration options and OpenAPI generation.
- Target Kubernetes environment is k3s with standard ingress controller (Traefik).
- ArgoCD is available in the target cluster for GitOps synchronization.
- Doppler or similar secrets management is available for production credential injection.
- The existing SQLMesh transformation pipeline continues to produce mart/scoring tables that the API views will expose.
- CloudNativePG operator is available for production PostgreSQL if database is deployed to Kubernetes.

## Out of Scope

- Custom authentication/authorization service implementation (JWT issuance) - assumes external identity provider.
- Metabase provisioning automation for Kubernetes - remains docker-compose only for now.
- Database migration automation (SQLMesh handles transformations, initial schema is manual).
- Multi-region or multi-cluster deployments.
