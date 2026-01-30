# Feature Specification: Molecule Platform Integration

**Feature Branch**: `004-molecule-platform-integration`
**Created**: 2026-01-28
**Status**: Draft
**Input**: Integrate the DK Molecule Data Platform functionality from the `Philipp-working` branch into `staging`, aligned with the dk-alchemy GitOps workflow established in feature 003.

## Context

The existing dk-data-fe platform serves hospital targeting intelligence (TAVR/Edwards). A parallel development effort (the `Philipp-working` branch) built a comprehensive pharmaceutical molecule intelligence platform with 16+ external data source integrations, a medallion data architecture, and molecule lifecycle tracking. This feature integrates that molecule platform into the production-ready staging environment without disrupting existing functionality or the dk-alchemy deployment infrastructure.

### Assumptions

- The existing TAVR data pipeline and API endpoints remain unchanged and fully functional after integration
- All new database schemas use a `mol_` prefix to avoid collision with existing schemas (`raw`, `staging`, `mart`, `scoring`, `api`)
- The React frontend from the source branch is deferred to a separate follow-up feature and is out of scope
- All deployment infrastructure uses the dk-alchemy GitOps conventions (Kustomize base/overlays, ArgoCD app-of-apps, Doppler secrets, Traefik ingress)
- External data sources that require API keys (DrugBank, optional others) are treated as optional — the platform must function without them, using only freely available public sources
- A single container image serves all workloads (API server and batch CronJobs), differentiated by entrypoint
- Data sources beyond the initial 5 are integrated in the codebase but disabled in CronJob configuration; GitHub issues track their incremental enablement

### Constraints

- **Selective merge only** — the source branch contains GitOps, Docker, and infrastructure files that conflict with the dk-alchemy structure; only application code, migrations, SQLMesh models, and documentation carry over
- **Schema isolation** — molecule schemas must not touch or depend on existing TAVR schemas
- **Same image, different entrypoints** — no new container images beyond the existing job-trigger image
- **No hardcoded credentials** — all secrets via Doppler; all API keys as optional environment variables
- **Internal-only molecule API** — new FastAPI molecule routes (write operations, pipeline triggers, onboarding) remain behind the existing NetworkPolicy with no public ingress; read-only molecule data is exposed via PostgREST

## Clarifications

### Session 2026-01-28

- Q: Should the new FastAPI molecule routes (data source registration, onboarding, alerts, pipeline triggers) be exposed publicly or remain internal-only? → A: Internal-only — molecule write routes stay behind NetworkPolicy, accessible only within the cluster. Public exposure deferred to a follow-up feature.
- Q: What confidence threshold separates automatic entity linking from manual review? → A: 0.80 — matches scoring below 0.80 are flagged for manual review; matches at or above 0.80 are auto-merged.
- Q: Which external data sources should be enabled for initial staging deployment? → A: Core 5 — ClinicalTrials.gov, OpenFDA Labels, OpenFDA FAERS, ChEMBL, PubChem. Remaining sources (DrugBank, UniProt, OpenAlex, BindingDB, SIDER, Orange Book, USPTO, etc.) tracked as GitHub issues for incremental enablement.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Molecule Data Ingestion Pipeline (Priority: P1)

As a **data operations engineer**, I want the platform to automatically ingest data from pharmaceutical sources on a scheduled basis so that the molecule database stays current without manual intervention.

**Why this priority**: Without ingested data, no other molecule platform feature can function. The ingestion pipeline is the foundation of the entire platform.

**Independent Test**: Can be verified by triggering a scheduled fetch job and confirming that data appears in the raw and bronze database layers for at least one source (e.g., ClinicalTrials.gov).

**Acceptance Scenarios**:

1. **Given** the platform is deployed with molecule CronJobs configured, **When** the daily fetch schedule triggers, **Then** new records from daily-refresh sources (ClinicalTrials.gov, OpenFDA Labels) are stored in the raw layer and processed into the bronze layer.
2. **Given** the weekly fetch schedule triggers, **When** weekly-refresh sources are polled (FAERS, ChEMBL, OpenAlex), **Then** new records appear in the raw and bronze layers with source attribution.
3. **Given** an external source API is temporarily unavailable, **When** the fetch job runs, **Then** the job logs the failure, skips that source, continues processing other sources, and retries on the next scheduled run.
4. **Given** a fetch job has already ingested a record, **When** the same record is fetched again, **Then** the system deduplicates it (by response hash) and does not create a duplicate bronze entry.

---

### User Story 2 — Medallion Data Transformation (Priority: P1)

As a **data operations engineer**, I want raw source data to be automatically transformed through bronze, silver, and gold layers so that analysts can query normalized, entity-resolved, and aggregated molecule data.

**Why this priority**: Transformation is the second half of the data pipeline — without it, ingested data remains unqueryable blobs.

**Independent Test**: Can be verified by running the transform pipeline after ingestion and confirming that silver-layer molecules have cross-source identifiers linked and gold-layer aggregations are populated.

**Acceptance Scenarios**:

1. **Given** bronze-layer records exist for multiple sources, **When** the silver transformation runs, **Then** molecule entities are created with canonical identifiers and cross-source identifier mappings.
2. **Given** two sources reference the same molecule by different names, **When** entity resolution runs, **Then** they are linked to a single canonical molecule record via identifier matching.
3. **Given** a molecule match has a confidence score below 0.80, **When** the resolution runs, **Then** the record is flagged for manual review rather than auto-merged.
4. **Given** silver-layer data is current, **When** the gold aggregation runs, **Then** pre-computed molecule profiles, competitive landscapes, and safety signal summaries are updated.

---

### User Story 3 — Molecule Search and Profile API (Priority: P2)

As a **data analyst**, I want to search for molecules by name or identifier and retrieve comprehensive profiles so that I can quickly assess a molecule's development status, safety signals, and competitive landscape.

**Why this priority**: This is the primary consumer-facing value of the platform — making integrated molecule intelligence queryable.

**Independent Test**: Can be verified by calling the molecule search API endpoint with a known molecule name and receiving a structured profile response containing data sourced from multiple upstream providers.

**Acceptance Scenarios**:

1. **Given** molecules exist in the silver layer, **When** a user searches by molecule name, **Then** the API returns matching molecules ranked by relevance with key identifiers displayed.
2. **Given** a molecule has data from multiple sources, **When** a user retrieves its profile, **Then** the response includes aggregated properties, approval status, clinical trial counts, and safety event summaries.
3. **Given** a user searches with a partial or misspelled name, **When** fuzzy matching is enabled, **Then** the API returns approximate matches with similarity scores.

---

### User Story 4 — Database Schema Initialization (Priority: P1)

As a **platform administrator**, I want the molecule database schemas, tables, roles, and grants to be automatically created during deployment so that the platform is ready to ingest data immediately after first sync.

**Why this priority**: Without database initialization, no data can be stored. This blocks all other stories.

**Independent Test**: Can be verified by deploying to a fresh namespace and confirming that all molecule schemas exist, roles are granted, and the init job completes without error.

**Acceptance Scenarios**:

1. **Given** a fresh deployment to a new namespace, **When** the deployment syncs for the first time, **Then** all molecule schemas (`mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `mol_app`, `meta`) are created with appropriate tables and indexes.
2. **Given** the database init has already run, **When** the deployment syncs again, **Then** the init job runs idempotently without errors or data loss.
3. **Given** the existing TAVR schemas are in place, **When** molecule schemas are initialized, **Then** existing TAVR schemas and data are completely unaffected.

---

### User Story 5 — Kubernetes Deployment with dk-alchemy Conventions (Priority: P1)

As a **platform administrator**, I want the molecule platform components to be deployed via the existing dk-alchemy ArgoCD workflow so that all environments (staging, production) are managed consistently.

**Why this priority**: Deployment alignment is a prerequisite for all runtime stories. Without it, nothing runs in the cluster.

**Independent Test**: Can be verified by running `kustomize build` on both overlays and confirming the output includes molecule CronJobs, ConfigMaps, and updated PostgREST configuration.

**Acceptance Scenarios**:

1. **Given** the staging overlay, **When** `kustomize build` is run, **Then** the output includes molecule fetch CronJobs, transform CronJobs, pipeline ConfigMap, and extended database init Job.
2. **Given** the production overlay, **When** `kustomize build` is run, **Then** the output includes the same molecule resources with production-appropriate resource limits.
3. **Given** ArgoCD is syncing the staging Application, **When** a commit lands on the staging branch, **Then** ArgoCD deploys the updated molecule resources alongside existing TAVR resources.
4. **Given** the PostgREST deployment, **When** it starts, **Then** it exposes both existing TAVR API schemas and the new molecule API schema.

---

### User Story 6 — Pipeline Monitoring and Alerting (Priority: P2)

As a **data operations engineer**, I want to monitor the health of the molecule ingestion pipeline and receive alerts when data becomes stale or jobs fail so that I can respond before downstream consumers are affected.

**Why this priority**: Monitoring is essential for operational reliability but not a blocker for initial deployment.

**Independent Test**: Can be verified by checking that Prometheus metrics are scraped from molecule CronJobs and that alert rules fire when a mock staleness condition is simulated.

**Acceptance Scenarios**:

1. **Given** molecule CronJobs are running, **When** Prometheus scrapes metrics, **Then** job completion status, duration, and record counts are visible in Grafana.
2. **Given** a molecule fetch job fails, **When** the alert evaluation runs, **Then** a `MoleculeFetchFailed` alert fires with the source name and error details.
3. **Given** a data source has not been refreshed within its expected interval, **When** the freshness monitor evaluates, **Then** a staleness alert fires identifying the overdue source.

---

### User Story 7 — Secrets and Credential Security (Priority: P1)

As a **platform administrator**, I want all credentials (database passwords, API keys, JWT secrets) to be managed via Doppler and injected at runtime so that no secrets are hardcoded in source code or container images.

**Why this priority**: Security is non-negotiable for a platform handling pharmaceutical data from regulated sources.

**Independent Test**: Can be verified by scanning all source files for hardcoded credentials and confirming zero matches, and by verifying all runtime secrets reference the Doppler-managed Kubernetes secret.

**Acceptance Scenarios**:

1. **Given** the full source code of the molecule platform, **When** a credentials scan runs (gitleaks or equivalent), **Then** zero hardcoded secrets are found.
2. **Given** a molecule CronJob pod starts, **When** it reads database credentials, **Then** they come from the `dk-data-secrets` Kubernetes secret (managed by Doppler).
3. **Given** an optional external API key (e.g., DrugBank), **When** the key is not configured in Doppler, **Then** the platform skips that source gracefully without failing the entire pipeline.

---

### User Story 8 — Existing TAVR Functionality Preservation (Priority: P1)

As a **data analyst using the existing TAVR system**, I want the hospital targeting API and batch jobs to continue working identically after the molecule platform is integrated so that my existing workflows are not disrupted.

**Why this priority**: Regression prevention is critical — the integration must not break production workloads.

**Independent Test**: Can be verified by calling existing TAVR API endpoints (`/health`, `/jobs/*`) and running existing CronJobs, confirming identical behavior.

**Acceptance Scenarios**:

1. **Given** the integrated platform is deployed, **When** the `/health` endpoint is called, **Then** it returns a 200 response.
2. **Given** the integrated platform is deployed, **When** the existing CMS fetch CronJob runs, **Then** it completes successfully with the same behavior as before integration.
3. **Given** the integrated platform is deployed, **When** a user queries the existing PostgREST API for TAVR data, **Then** results are identical to pre-integration responses.

---

### Edge Cases

- What happens when a molecule exists in 10+ external sources with slightly different names? The entity resolution system must handle high-cardinality aliases without creating duplicate canonical records.
- How does the system handle an external API that changes its response schema? The raw layer preserves the original response; the bronze transformation should log a schema mismatch warning and skip unparseable records rather than failing the entire batch.
- What happens when the database init Job runs concurrently with an active data ingestion? All schema creation uses `IF NOT EXISTS` and `CREATE OR REPLACE` to ensure idempotency even under concurrent access.
- What happens if the transform CronJob starts before the fetch CronJob completes? Transform jobs should operate on whatever data is available at execution time — they process only records marked as untransformed, so partial data is handled gracefully.
- What happens when the single container image grows large due to all molecule dependencies? The multi-stage Docker build ensures only runtime dependencies are in the final image; build-time dependencies (compilers, headers) are discarded.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST selectively integrate all molecule platform application code (API routes, services, models, data loaders, migrations, SQLMesh models) from the source branch without carrying over infrastructure files that conflict with the dk-alchemy GitOps structure.
- **FR-002**: System MUST create molecule database schemas (`mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `mol_app`, `meta`) via an idempotent database initialization process that runs automatically during deployment.
- **FR-003**: System MUST schedule automated data ingestion from pharmaceutical sources at three tiers: daily (high-change sources), weekly (moderate-change sources), and monthly (stable reference sources). Initial staging deployment enables 5 core sources: ClinicalTrials.gov (daily), OpenFDA Labels (daily), OpenFDA FAERS (weekly), ChEMBL (weekly), and PubChem (monthly). Remaining sources are tracked as GitHub issues for incremental enablement.
- **FR-004**: System MUST transform ingested data through a medallion pipeline: raw (unmodified API responses) → bronze (typed source-native columns) → silver (entity-resolved, cross-source normalized) → gold (pre-aggregated analytics).
- **FR-005**: System MUST resolve molecule entities across sources using canonical identifiers, linking records from different providers that refer to the same molecule.
- **FR-006**: System MUST flag entity matches with a confidence score below 0.80 for manual review rather than auto-merging them into the canonical record. Matches scoring 0.80 or above are auto-linked.
- **FR-007**: System MUST expose molecule search and profile endpoints via the existing API, allowing queries by name, identifier, or fuzzy match.
- **FR-008**: System MUST update the PostgREST configuration to expose the molecule API schema alongside the existing TAVR API schema.
- **FR-009**: System MUST create Kubernetes CronJob manifests for molecule fetch and transform pipelines following the existing Kustomize base/overlay pattern.
- **FR-010**: System MUST update the container image build to include all new Python dependencies without breaking existing functionality.
- **FR-011**: System MUST register new molecule API routes in the existing FastAPI application additively, without modifying or removing existing TAVR endpoints. These routes remain internal-only (no public ingress); read-only molecule data is served via PostgREST.
- **FR-012**: System MUST ensure zero hardcoded credentials in all integrated source code; all secrets MUST be read from environment variables backed by Doppler-managed Kubernetes secrets.
- **FR-013**: System MUST handle optional external API keys gracefully — sources requiring unavailable keys are skipped without failing the overall pipeline.
- **FR-014**: System MUST deduplicate ingested records using content hashing to prevent duplicate entries in the bronze layer.
- **FR-015**: System MUST extend observability (metrics scraping and alert rules) to cover molecule pipeline health, job completion, and data freshness.
- **FR-016**: System MUST pass lint checks (`ruff check`) and render valid Kustomize output for both staging and production overlays after integration.
- **FR-017**: System MUST preserve all existing TAVR API endpoints, batch jobs, and database schemas without modification.
- **FR-018**: System MUST update the local development environment file (`.env.example`) to document all new environment variables introduced by the molecule platform.

### Key Entities

- **Molecule**: The central entity — a pharmaceutical compound identified by a canonical identifier (structural hash). Attributes include canonical name, structural representation, molecular formula, weight, type (small molecule, protein, antibody), development status, and maximum clinical phase.
- **Identifier Mapping**: Links a molecule to its identifiers across external sources (source name, identifier type, identifier value, confidence score). Enables cross-source entity resolution.
- **Data Source**: A registered external pharmaceutical data provider with attributes including name, base URL, API type, refresh frequency tier, and optional credential reference.
- **Raw Record**: An unmodified API response archive entry with request metadata, response body, content hash, and processing status flag.
- **Bronze Record**: A typed, source-native row extracted from a raw record. Schema varies per data source. Carries a hash and processing status flag for downstream transformation.
- **Silver Record**: A normalized, entity-resolved record linked to a canonical molecule. Includes clinical trials, drug labels, adverse events, patents, publications, and bioactivity data.
- **Gold Aggregate**: A pre-computed analytics record — molecule profiles, competitive landscapes, safety signal summaries, lifecycle stage evidence roll-ups.
- **Pipeline Configuration**: Runtime parameters for batch jobs — batch size, fetch mode, enabled layers, log level. Managed as a Kubernetes ConfigMap.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All molecule platform application code is integrated and passes automated lint checks with zero errors.
- **SC-002**: Both staging and production deployment configurations render valid manifests including all molecule resources (CronJobs, ConfigMap, extended database init, updated API config).
- **SC-003**: The container image builds successfully with all new dependencies included.
- **SC-004**: Existing TAVR API endpoints return identical responses before and after integration — zero regressions.
- **SC-005**: The molecule ingestion pipeline successfully fetches and stores data from all 5 core sources (ClinicalTrials.gov, OpenFDA Labels, OpenFDA FAERS, ChEMBL, PubChem) in the staging environment.
- **SC-006**: The medallion transformation pipeline processes data through all four layers (raw → bronze → silver → gold) end-to-end for at least one source.
- **SC-007**: Entity resolution correctly links records from 2+ different sources to the same canonical molecule for at least one known test molecule.
- **SC-008**: The database initialization job creates all molecule schemas idempotently — running twice produces no errors.
- **SC-009**: Zero hardcoded credentials are found across all integrated source files when scanned with a secrets detection tool.
- **SC-010**: Molecule pipeline alert rules are active in the monitoring stack and fire correctly when simulated failure conditions occur.
