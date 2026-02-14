# Research: Platform Stabilization

**Feature Branch**: `010-platform-stabilization`
**Date**: 2026-02-14

## R1: Container Registry Authentication & k3d DNS

**Decision**: Fix DNS via CoreDNS forward config + create `ghcr-credentials` secret via Doppler-sourced init job

**Rationale**: The k3d DNS issue is a known macOS/Docker Desktop problem where CoreDNS cannot resolve external hostnames. Patching CoreDNS to forward to `8.8.8.8` is the simplest reliable fix. For registry auth, extending the existing Doppler setup to include `GHCR_USERNAME` and `GHCR_PASSWORD` secrets keeps credential management centralized and survives namespace recreations.

**Alternatives considered**:
- `k3d image import` (bypass registry entirely): Works for dev but doesn't solve production or CI; deferred as supplementary convenience
- k3d `--resolv-conf` flag: Requires cluster recreation; CoreDNS patch is non-destructive
- Sealed Secrets for GHCR credentials: Adds dependency; Doppler is already in place
- External Secrets Operator: Over-engineered for this use case

## R2: Image Promotion Strategy

**Decision**: Use Kustomize `images` transformer per overlay + `crane tag` for registry-level re-tagging + auto-promote workflow

**Rationale**: The current `sed` approach on shared base manifests causes staging/prod tag pollution. Moving to Kustomize `images` transformers is the standard best practice — each overlay independently pins its tag. `crane tag` re-tags images at the registry level without rebuilding (fast, lightweight). Auto-promotion runs after staging validation succeeds.

**Alternatives considered**:
- `docker buildx imagetools create`: Heavier, designed for multi-arch manifests; overkill for simple re-tagging
- Manual `workflow_dispatch` only: Adds human friction; the team chose auto-promote in clarification
- Git tag-based promotion: Requires tagging discipline; adds process overhead for small team

**Implementation sketch**:
1. Base manifests use placeholder tag (`latest`)
2. `build-push.yaml` updates staging overlay only: `kustomize edit set image ...`
3. New `promote-to-prod.yaml` workflow: validates staging health → `crane tag` to add prod tag → updates prod overlay
4. Trigger: `workflow_run` after staging validation succeeds

## R3: Database Backup to MinIO

**Decision**: Alpine-based custom image with `pg_dump` (custom format, compression level 6) + MinIO client (`mc`), deployed as K8s CronJobs with script-based retention cleanup

**Rationale**: Custom format (`-Fc`) enables `pg_restore --list` for integrity verification without full restore. Alpine base keeps the image < 80MB. MinIO lifecycle policies can't distinguish daily vs weekly backups on the same day, so a script-based cleanup using `mc find --older-than` is more reliable for the 7-daily + 4-weekly retention policy.

**Alternatives considered**:
- `bitnami/postgresql` base: 200-300MB, unnecessarily large for a backup-only container
- Pre-built solutions (postgres-backup-s3): Not verified for PostgreSQL 16 compatibility; less control over verification logic
- MinIO lifecycle policies only: Limited expressiveness for multi-tier retention; can't distinguish backup types in same prefix
- WAL-G continuous archiving: More complex, requires CloudNativePG operator; deferred to future work

**Key design details**:
- Daily CronJob at 02:00 UTC, weekly at 03:00 UTC Sunday
- Backup verification: `pg_restore --list` (object count) + SHA256 checksum stored as MinIO object tags
- Weekly verification job: Monday 04:00 UTC, runs `pg_restore --list` on latest daily backup
- Storage path: `postgres-backups/{namespace}/{daily|weekly}/dk_data_{timestamp}_{type}.dump`
- NetworkPolicy: Add MinIO (port 9000) to egress rules
- Resources: 512Mi request / 2Gi limit (pg_dump can be memory-intensive)

## R4: Test Coverage Strategy

**Decision**: pytest-cov with `--cov-fail-under=15`, phased approach starting with import tests → Pydantic model tests → FastAPI TestClient → mocked fetchers using `responses` library

**Rationale**: Import tests give 5-8% coverage in 30 minutes (highest ROI). Pydantic model instantiation tests add another 8-12% with minimal effort. These two alone cross the 15% threshold. The `responses` library is the natural fit for the existing `requests.Session()`-based `BaseFetcher` pattern.

**Alternatives considered**:
- `pytest-httpx`: Better for httpx-based code, but fetchers use `requests.Session()`
- VCR.py: Records real API responses; good for regression but requires initial API access
- RESPX: Modern, cleaner API, but for httpx only; future migration path

**Configuration**:
- `pyproject.toml`: Add `pytest-cov>=6.0.0`, `responses>=0.25.0` to dev deps
- `[tool.pytest.ini_options]`: `addopts = ["--cov=src/dk_data", "--cov-report=term-missing", "--cov-report=xml", "--cov-fail-under=15"]`
- `[tool.coverage.run]`: `source = ["src/dk_data"]`, `branch = true`, omit tests/migrations
- CI: Add coverage XML upload + PR comment action (`MishaKav/pytest-coverage-comment`)

**Phased rollout**:
1. Day 1: Import tests (5-8%) — 30 minutes
2. Day 2: Pydantic model tests (cumulative 15-20%) — 2 hours
3. Day 3: FastAPI TestClient basics (cumulative 20-30%) — 3 hours
4. Week 2: Mocked fetcher tests — 4 hours
5. Raise threshold: 15% → 20% after 2 weeks → 30% after 1 month

## R5: Observability Stack Enablement

**Decision**: Install Prometheus Operator CRDs (Helm chart, CRDs only), deploy Grafana Alloy for OTLP reception + metrics scraping, uncomment ServiceMonitor/PrometheusRule in kustomization

**Rationale**: CRDs are cluster-scoped and lightweight — they enable ServiceMonitor resources without requiring the full Prometheus Operator deployment. Grafana Alloy serves as a unified telemetry collector (OTLP receiver for traces, ServiceMonitor scraper for metrics). The application already has OpenTelemetry instrumentation; only the cluster-side collection is missing.

**Alternatives considered**:
- Full kube-prometheus-stack: Includes Prometheus, Grafana, AlertManager — heavy for a single-node k3d cluster; may conflict with existing infra services
- Victoria Metrics: Good alternative but adds a new tool; Prometheus is more standard
- Direct Prometheus scraping (no Alloy): Works but misses trace collection; Alloy unifies both
- Grafana Cloud: External dependency, cost; self-hosted is preferred for this stage

**Components to deploy**:
1. `prometheus-operator-crds` Helm chart (kube-system namespace)
2. Grafana Alloy deployment (infra namespace) — receives OTLP on 4317, scrapes ServiceMonitors
3. Uncomment `service-monitor.yaml` and `alert-rules.yaml` in base kustomization
4. Grafana dashboard JSON with 7 panels: API request rate, API latency, success rate, CronJob success rate, batch job stats, PostgreSQL connection pool, DB query latency

## R6: Security Hardening

**Decision**: Parameterize `init_database.sql` credentials using psql variables, standardize database name to `dk_data`, add pre-flight validation rejecting default values

**Rationale**: The hardcoded `'postgrest_secret_change_me'` password in init SQL is a high-severity finding. psql variable substitution (`:'VAR_NAME'`) is the standard PostgreSQL approach for parameterized scripts without introducing external tooling. Standardizing on `dk_data` aligns with what Kubernetes (Doppler) already uses.

**Alternatives considered**:
- Jinja2 templating: Adds Python dependency to SQL execution; psql variables are simpler
- Envsubst: Works but loses SQL syntax highlighting; psql variables are native
- Separate migration for role creation: More moving parts; keeping it in init is cleaner

**Changes required**:
1. `init_database.sql`: Replace `PASSWORD 'postgrest_secret_change_me'` with `PASSWORD :'AUTHENTICATOR_PASSWORD'`
2. `docker-compose.yml`: Change default from `edwards_tavr` to `dk_data`
3. `init_database.sql`: Remove `\connect edwards_tavr` (caller specifies database)
4. Add validation: `DO $$ BEGIN IF :'AUTHENTICATOR_PASSWORD' = 'postgrest_secret_change_me' THEN RAISE EXCEPTION 'Default password detected'; END IF; END $$;`
5. `db-init-job.yaml`: Pass `-v AUTHENTICATOR_PASSWORD="$POSTGREST_PASSWORD"` to psql command

## R7: Repository Hygiene

**Decision**: `git rm --cached` to untrack raw CSV files, add `.gitignore` entry, document data retrieval in README

**Rationale**: 182MB of CSV files in git bloats clone times and CI. Untracking via `git rm --cached` preserves local copies while removing from git. Git history rewriting (`git filter-repo`) is explicitly out of scope per the spec — it requires team coordination and is a separate concern.

**Alternatives considered**:
- Git LFS: Adds complexity and still stores data in the repo; better for binary assets, not CSV
- Git filter-repo: Cleans history but destructive; deferred per spec
- Move to MinIO immediately: Good long-term but adds deployment dependency for local dev
