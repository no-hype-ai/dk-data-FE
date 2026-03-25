# Feature Specification: Admin App Integration Fix

**Feature Branch**: `006-admin-integration-fix`
**Created**: 2026-02-01
**Status**: Draft
**Input**: DK_DATA_ADMIN_INTEGRATION_RECOMMENDATIONS.md - Fix db-init heredoc escaping for production deployment, add missing Compass API views, implement graceful degradation patterns

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Production Database Initialization (Priority: P1)

As a platform operator, I need the db-init job to successfully create all required PostgreSQL roles and API views in production so that PostgREST can serve requests to the Admin App.

**Why this priority**: Production is currently broken with 0 Relations loaded and CrashLoopBackOff pods. This blocks all Compass functionality for Admin App users.

**Independent Test**: Can be tested by deploying to production and verifying PostgREST logs show "Schema cache loaded X Relations" where X > 0, and `/health` endpoint returns 200 OK.

**Acceptance Scenarios**:

1. **Given** a fresh production deployment, **When** the db-init job runs, **Then** all 5 roles (authenticator, web_anon, analyst, api_user, readonly) are created without errors
2. **Given** the db-init job has completed, **When** PostgREST starts, **Then** it loads at least 5 Relations into its schema cache
3. **Given** PostgREST is running, **When** an HTTP request is made to `/health`, **Then** it returns 200 OK with valid JSON

---

### User Story 2 - Compass API Views (Priority: P2)

As an Admin App user accessing Compass features, I need the dk-data API to expose molecule search, data sources, and resolution queue endpoints so that I can use the Compass search and management functionality.

**Why this priority**: Admin App Compass features return 503 errors because expected views don't exist. This is the primary user-facing issue.

**Independent Test**: Can be tested by calling `GET /molecules`, `GET /data_sources`, and `GET /resolution_queue` endpoints with valid JWT and receiving 200 OK responses.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they access `/molecules` endpoint, **Then** they receive a list of molecules with id, smiles, inchi_key, name, molecular_weight fields
2. **Given** an authenticated user, **When** they access `/resolution_queue` endpoint, **Then** they receive pending resolution items with id, source_id, target_smiles, status, priority fields
3. **Given** an authenticated user with analyst role, **When** they access `/data_sources` endpoint, **Then** they receive a list of data sources with name, source_type, last_fetch_at, status, record_count

---

### User Story 3 - Graceful Service Degradation (Priority: P3)

As an Admin App user, I need the Compass UI to show a clear service status indicator and graceful error messages when dk-data is unavailable, rather than showing generic 503 errors.

**Why this priority**: Improves user experience during outages but is not blocking core functionality.

**Independent Test**: Can be tested by stopping dk-data service and verifying Admin App shows "dk-data: offline" badge and user-friendly error messages instead of raw 503 errors.

**Acceptance Scenarios**:

1. **Given** dk-data is unavailable, **When** a user visits Compass pages, **Then** they see a "dk-data: offline" status badge and friendly unavailable message
2. **Given** dk-data becomes available, **When** the next health check runs (within 30 seconds), **Then** the status badge updates to "dk-data: online"
3. **Given** dk-data is unavailable, **When** a user triggers a search, **Then** they see "Molecule database is currently unavailable" instead of a raw 503 error

---

### User Story 4 - Production Pod Recovery (Priority: P1)

As a platform operator, I need the CrashLoopBackOff pod in production to be recovered so that all PostgREST replicas are healthy and serving traffic.

**Why this priority**: One pod in production is in CrashLoopBackOff with 472+ restarts, consuming cluster resources and potentially affecting reliability.

**Independent Test**: Can be tested by running `kubectl get pods -n dk-data-prod` and verifying all postgrest pods show 1/1 Running with 0 recent restarts.

**Acceptance Scenarios**:

1. **Given** db-init has successfully created all views including `/health`, **When** PostgREST pods restart, **Then** HTTP health probes succeed
2. **Given** the CrashLoopBackOff pod exists, **When** db-init completes successfully, **Then** the pod recovers to Running state or can be deleted to let ReplicaSet recreate it

---

### Edge Cases

- What happens when db-init runs against a database that already has some but not all roles?
  - Should use `IF NOT EXISTS` pattern to be idempotent
- What happens when PostgREST loads before db-init completes?
  - Startup probe should delay liveness/readiness checks until PostgREST is actually ready
- What happens when authentication JWT secret is incorrect?
  - API should return 401 Unauthorized with clear error message
- How does system handle concurrent db-init job runs?
  - Job should be idempotent; concurrent runs should not cause data corruption

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: db-init job MUST use proper shell escaping for PL/pgSQL `DO $$...$$` blocks to work in Kubernetes Job containers
- **FR-002**: db-init job MUST create all 5 roles: authenticator, web_anon, analyst, api_user, readonly
- **FR-003**: db-init job MUST be idempotent - running multiple times produces same result
- **FR-004**: PostgREST MUST expose `api.molecules` view with molecule discovery data
- **FR-005**: PostgREST MUST expose `api.resolution_queue` view for pending molecule resolutions
- **FR-006**: PostgREST MUST expose `api.data_sources` view with real data (not placeholder)
- **FR-007**: API views MUST have appropriate GRANT permissions for each role
- **FR-008**: web_anon role MUST have SELECT on api.health, api.molecules, api.data_sources (public views)
- **FR-009**: analyst and api_user roles MUST have SELECT on all API views including resolution_queue
- **FR-010**: Admin App health check endpoint MUST cache status for 30 seconds to prevent excessive API calls

### Key Entities

- **Role**: PostgreSQL role with specific permissions (authenticator, web_anon, analyst, api_user, readonly)
- **API View**: PostgreSQL view in `api` schema exposed through PostgREST
- **Molecule**: Chemical compound with SMILES, InChI key, name, molecular weight
- **Resolution Queue Item**: Pending molecule resolution with source, target SMILES, status, priority
- **Data Source**: External data provider with name, type, fetch status, record count

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Production PostgREST logs show "Schema cache loaded N Relations" where N >= 8 (5 existing + 3 new)
- **SC-002**: All PostgREST pods in production show Running status with 0 restarts after deployment
- **SC-003**: Admin App Compass search page loads without 503 errors when dk-data is available
- **SC-004**: Admin App shows service status badge within 5 seconds of page load
- **SC-005**: `/health` endpoint responds within 100ms with 200 OK status
- **SC-006**: db-init job completes successfully with exit code 0 in both staging and production
