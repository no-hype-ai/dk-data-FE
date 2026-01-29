# Feature Specification: Production Readiness for dk-data-fe

**Feature Branch**: `002-production-readiness`
**Created**: 2026-01-20
**Status**: Draft
**Input**: Based on comprehensive RECOMMENDATIONS.md analysis covering dk-alchemy integration, security hardening, codebase cleanup, and observability requirements.

## Executive Summary

Transform the dk-data-fe TAVR data platform from MVP status to production-ready by:
1. Integrating with dk-alchemy shared infrastructure (observability, secrets, database)
2. Resolving critical security issues (hardcoded credentials, weak JWT, permissive API access)
3. Cleaning up codebase technical debt (18 duplicate files, 74MB committed data, config sprawl)
4. Restructuring for GitOps deployment patterns

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Secure Secret Management (Priority: P1)

As a **platform operator**, I need all credentials removed from source control and managed through a centralized secrets system so that the platform meets security compliance requirements and credentials can be rotated without code changes.

**Why this priority**: Hardcoded credentials represent the highest security risk. This is a blocking requirement for any production deployment.

**Independent Test**: Can be tested by deploying the application and verifying no secrets exist in git history, all secrets are sourced from Doppler, and the application functions correctly with secrets injected at runtime.

**Acceptance Scenarios**:

1. **Given** the dk-data-fe repository, **When** scanning for secrets using gitleaks, **Then** zero secrets are detected in current code or git history
2. **Given** a fresh deployment environment, **When** the application starts without Doppler integration configured, **Then** it fails gracefully with a clear error message about missing secrets
3. **Given** properly configured Doppler secrets, **When** the application deploys to Kubernetes, **Then** all database passwords, JWT secrets, and API keys are injected from DopplerSecret CRDs
4. **Given** a deployed application, **When** a secret is rotated in Doppler, **Then** the application picks up the new secret within 5 minutes without restart

---

### User Story 2 - Codebase Deduplication (Priority: P1)

As a **developer**, I need a single canonical location for all scripts and configuration files so that I can confidently make changes without uncertainty about which version is authoritative.

**Why this priority**: 18 duplicate files create immediate maintenance risk and confusion. This blocks reliable development workflow.

**Independent Test**: Can be tested by verifying each script/config exists in exactly one location, all references point to the canonical location, and the application builds and runs successfully.

**Acceptance Scenarios**:

1. **Given** the `/scripts/` directory exists with duplicates, **When** cleanup is complete, **Then** the `/scripts/` directory no longer exists and all scripts are in `/src/dk_data/scripts/`
2. **Given** duplicate targeting_tables.sql files, **When** cleanup is complete, **Then** only `/src/dk_data/sql/targeting_tables.sql` exists with the complete schema
3. **Given** docker-compose volume mounts referencing both script locations, **When** cleanup is complete, **Then** only the canonical `/src/dk_data/scripts/` is mounted
4. **Given** a developer runs `make help`, **When** viewing available commands, **Then** all commands reference a single root Makefile without ambiguity

---

### User Story 3 - Repository Size Reduction (Priority: P1)

As a **developer**, I need committed data files and logs removed from git history so that repository clone times are reasonable and no sensitive data artifacts remain in version control.

**Why this priority**: 74+ MB of data files bloat the repository and may contain sensitive information. This affects every developer's workflow.

**Independent Test**: Can be tested by cloning the repository fresh and verifying total size is under 10MB, no CSV files exist in `/data/`, and no log files exist in `/logs/`.

**Acceptance Scenarios**:

1. **Given** 74+ MB of CSV data files committed to git, **When** history cleanup is complete, **Then** repository size is reduced by at least 70MB
2. **Given** SQLMesh log files in `/logs/`, **When** cleanup is complete, **Then** the `/logs/` directory is empty and properly gitignored
3. **Given** a fresh clone of the repository, **When** checking for data files, **Then** `/data/raw/` directory is empty or contains only a README explaining where to obtain data
4. **Given** the `.gitignore` file, **When** creating new files matching ignored patterns, **Then** they are not staged for commit

---

### User Story 4 - Observability Integration (Priority: P2)

As a **platform operator**, I need the dk-data-fe applications instrumented to send metrics, logs, and traces to the dk-alchemy observability stack so that I can monitor system health, troubleshoot issues, and track data freshness.

**Why this priority**: Observability is essential for production operations but requires security fixes first. The infrastructure already exists in dk-alchemy.

**Independent Test**: Can be tested by deploying the application and verifying metrics appear in Grafana, logs appear in Loki, and traces appear in Tempo.

**Acceptance Scenarios**:

1. **Given** a running PostgREST deployment, **When** API requests are made, **Then** request metrics (rate, latency, errors) are visible in Grafana within 1 minute
2. **Given** an ingestion job running, **When** the job completes or fails, **Then** structured log entries appear in Loki with job_name, status, duration, and row_count fields
3. **Given** a configured data freshness threshold of 48 hours, **When** a data source exceeds this age, **Then** an alert fires in Grafana and notification is sent
4. **Given** an API request spanning multiple services, **When** viewing in Tempo, **Then** the full trace shows the request path through PostgREST to PostgreSQL

---

### User Story 5 - ArgoCD GitOps Deployment (Priority: P2)

As a **platform operator**, I need dk-data-fe deployable through ArgoCD following dk-alchemy patterns so that infrastructure changes are version-controlled, auditable, and automatically synchronized.

**Why this priority**: GitOps deployment enables reliable, repeatable deployments but depends on cleaned-up codebase structure.

**Independent Test**: Can be tested by pushing changes to the repository and verifying ArgoCD automatically syncs the changes to the cluster.

**Acceptance Scenarios**:

1. **Given** the dk-data-fe bootstrap application in dk-alchemy, **When** ArgoCD syncs, **Then** all dk-data-fe applications appear in the ArgoCD dashboard as healthy
2. **Given** a change pushed to the dk-data-fe main branch, **When** ArgoCD detects the change, **Then** the production environment is automatically updated within 5 minutes
3. **Given** the staging branch, **When** ArgoCD syncs, **Then** staging environment reflects different resource limits (smaller replicas, less memory)
4. **Given** an invalid manifest is pushed, **When** ArgoCD attempts to sync, **Then** the sync fails with a clear error and the previous working state is preserved

---

### User Story 6 - API Access Control Hardening (Priority: P2)

As a **security administrator**, I need API access restricted based on user roles so that sensitive data (targeting scores, financial metrics) is only accessible to authorized users.

**Why this priority**: Currently `web_anon` role has overly permissive access. This is a security requirement but lower priority than credential management.

**Independent Test**: Can be tested by making API requests with different credentials and verifying access is granted or denied appropriately.

**Acceptance Scenarios**:

1. **Given** an unauthenticated request to `/api/targets`, **When** the request is made, **Then** a 401 Unauthorized response is returned
2. **Given** a valid JWT with `analyst` role, **When** requesting `/api/scoring`, **Then** the data is returned successfully
3. **Given** a valid JWT with `web_anon` role, **When** requesting `/api/health`, **Then** the health status is returned
4. **Given** requests exceeding 100/minute from a single source, **When** rate limit is triggered, **Then** a 429 Too Many Requests response is returned

---

### User Story 7 - Dependency Synchronization (Priority: P3)

As a **developer**, I need a single source of truth for Python dependencies so that installations via pip or package manager produce identical environments.

**Why this priority**: Dependency mismatch causes subtle bugs but is lower risk than security or duplicate files.

**Independent Test**: Can be tested by installing via `pip install .` and verifying all application features work including FastAPI job-trigger service.

**Acceptance Scenarios**:

1. **Given** the pyproject.toml file, **When** installing with `pip install .`, **Then** all dependencies including fastapi, uvicorn, and kubernetes are installed
2. **Given** a new developer environment, **When** running `uv sync`, **Then** the exact versions from uv.lock are installed
3. **Given** an outdated uv.lock file, **When** running CI checks, **Then** the build fails with a clear message about lock file drift

---

### User Story 8 - Documentation Consolidation (Priority: P3)

As a **developer**, I need clear documentation with a single authoritative source for each topic so that I can find information quickly without conflicting guidance.

**Why this priority**: Documentation redundancy causes confusion but doesn't block functionality.

**Independent Test**: Can be tested by searching for a topic (e.g., "API endpoints") and finding exactly one authoritative source.

**Acceptance Scenarios**:

1. **Given** a new developer reading README.md, **When** looking for detailed architecture, **Then** they find a clear link to ARCHITECTURE.md
2. **Given** the specs/001.../quickstart.md file, **When** checking for duplicates, **Then** it no longer exists (content merged into README)
3. **Given** README.md, **When** viewing the documentation map section, **Then** all documentation files are listed with their purpose

---

### Edge Cases

- What happens when Doppler is temporarily unavailable? The application should continue running with cached secrets but log warnings.
- How does the system handle partial cleanup (e.g., some duplicates removed but not all)? CI should fail if duplicate detection finds any remaining duplicates.
- What happens if git history rewrite fails partway through? Document rollback procedure and verify with backup branch.
- How are existing deployments affected during migration? Zero-downtime migration path must be documented.
- What happens if observability stack is down? Application continues functioning; metrics are buffered or dropped gracefully.

## Requirements *(mandatory)*

### Functional Requirements

#### Security (P0)

- **FR-001**: System MUST NOT contain any credentials, passwords, or secrets in source code or git history
- **FR-002**: System MUST source all secrets from Doppler via DopplerSecret CRDs in Kubernetes
- **FR-003**: System MUST use JWT tokens with 256-bit minimum secret strength for API authentication
- **FR-004**: System MUST restrict anonymous (`web_anon`) API access to only health and public catalog endpoints
- **FR-005**: System MUST implement rate limiting of 100 requests per minute per source IP
- **FR-006**: System MUST support secret rotation without application restart (within 5 minutes)

#### Codebase Cleanup (P1)

- **FR-007**: System MUST have exactly one canonical location for each script (`/src/dk_data/scripts/`)
- **FR-008**: System MUST have exactly one SQL schema definition file per table (in `/src/dk_data/sql/`)
- **FR-009**: Repository MUST NOT contain data files (CSV, JSON data) in git history
- **FR-010**: Repository MUST NOT contain log files in git history
- **FR-011**: System MUST have a single root Makefile for all build and operational commands
- **FR-012**: pyproject.toml MUST include all dependencies required for all application components

#### Observability (P2)

- **FR-013**: All Python services MUST emit structured JSON logs with correlation IDs
- **FR-014**: All Python services MUST expose Prometheus metrics for request rate, latency, and errors
- **FR-015**: System MUST export OpenTelemetry traces to the dk-alchemy Tempo endpoint
- **FR-016**: System MUST provide Grafana dashboard showing data freshness, job status, and API health
- **FR-017**: System MUST configure alerts for data staleness exceeding 48 hours and job failures

#### GitOps (P2)

- **FR-018**: System MUST be deployable via ArgoCD using the dk-alchemy external app pattern
- **FR-019**: System MUST have separate overlays for production and staging environments
- **FR-020**: System MUST include namespace, service account, and network policy definitions
- **FR-021**: System MUST use Kustomize for environment-specific configuration

#### Configuration (P3)

- **FR-022**: Docker Compose files MUST be located at the repository root
- **FR-023**: System MUST maintain a locked dependency file (uv.lock) committed to repository
- **FR-024**: Documentation MUST have clear ownership with no duplicate content across files

### Key Entities

- **DopplerSecret**: Kubernetes CRD that synchronizes secrets from Doppler to Kubernetes Secrets
- **ArgoCD Application**: GitOps resource defining how dk-data-fe is deployed and synchronized
- **IngressRoute**: Traefik CRD defining external access to PostgREST API with rate limiting
- **CNPG Cluster**: PostgreSQL cluster definition with backup configuration to MinIO

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero secrets detected in repository by gitleaks scan (current: multiple failures)
- **SC-002**: Repository size under 10 MB after cleanup (current: 80+ MB)
- **SC-003**: Zero duplicate files between `/scripts/` and `/src/dk_data/scripts/` (current: 18 duplicates)
- **SC-004**: All API requests visible in Grafana within 60 seconds of occurrence
- **SC-005**: ArgoCD sync completes within 5 minutes of git push
- **SC-006**: Application starts successfully in under 30 seconds with proper secret injection
- **SC-007**: Unauthenticated requests to protected endpoints return 401 within 100ms
- **SC-008**: CI pipeline passes all checks including duplicate detection, secret scanning, and dependency verification
- **SC-009**: Fresh repository clone completes in under 30 seconds (current: 60+ seconds due to size)
- **SC-010**: Developer can find authoritative documentation for any topic within 2 clicks from README

## Assumptions

- dk-alchemy cluster is operational with all infrastructure services (Doppler, CNPG, Mimir, Loki, Tempo, Grafana, ArgoCD)
- Doppler project `dk-infrastructure` exists and is accessible
- Team has permission to rewrite git history (force push to main)
- Existing 001-data-layer-postgrest-gitops feature spec remains as historical record
- MinIO is available for data file storage after removal from git

## Out of Scope

- Changes to core application logic (fetchers, ingestion, SQLMesh transformations)
- Database schema changes beyond table definition deduplication
- New feature development
- Performance optimization beyond observability instrumentation
- Multi-tenancy or generalization (Issue #8) - separate feature
- Full compliance implementation (audit trail, PII handling, retention) - separate feature
