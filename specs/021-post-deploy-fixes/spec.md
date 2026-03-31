# Feature Specification: Post-Deployment Fixes & Credential Audit

**Feature Branch**: `021-post-deploy-fixes`
**Created**: 2026-03-31
**Status**: Completed (retrospec)
**Issues**: [#169](https://github.com/data-kinetic/dk-data-FE/issues/169), [#170](https://github.com/data-kinetic/dk-data-FE/issues/170)

## Overview

Following the prod promotion of image `prod-85e01aa` (PRs #149, #159), a post-deployment audit was conducted across the live cluster and the full ingestion source catalogue (~90 sources). This feature captures all fixes applied:

1. **Credential gaps** — EPO OAuth2 keys were in the wrong Doppler project; corrected via CLI. USPTO registration blocked by ID.me requiring US identification; sources skip gracefully in the interim.
2. **DDInter retirement** — The DDInter drug-drug interaction source (ddinter.scbdd.com, Alibaba Cloud) has been permanently unreachable since March 2026. Fetcher, CronJob, and source registry entry removed; DrugBank and BindingDB are the canonical DDI data path.
3. **API endpoint and auth fixes** — EUIPO IBM Gateway token URL corrected; USPTO ODP migration from PatentsView to api.uspto.gov already applied in #159; NICE API header fixed; IMGT rewritten to use official bulk FASTA.
4. **Rate limits, pagination, and backfill caps** — Systematic audit added per-source rate limiting, consistent pagination boundaries, and CMS PUF multi-year backfill via catalog UUID discovery.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Credentials Correctly Wired to Cluster (Priority: P1)

Operations needs confidence that all API-gated sources have their credentials in the right Doppler project (`dk-data-applications/prd`) so the Doppler operator syncs them to `dk-data-secrets` and CronJobs pick them up without manual intervention.

**Why this priority**: Silent credential failures (401s, empty runs) are invisible without proactive auditing. EPO was producing 401s every Sunday despite keys existing in Doppler — they were in the wrong project.

**Independent Test**: Run `doppler secrets --project dk-data-applications --config prd` and confirm all required API keys are present and non-placeholder. Trigger the EPO CronJob manually and confirm it completes with data rather than a 401 error.

**Acceptance Scenarios**:

1. **Given** EPO credentials exist in Doppler, **When** the EPO CronJob runs, **Then** it authenticates successfully and inserts patent records rather than returning 401
2. **Given** a key is absent or set to a CHANGEME placeholder, **When** the affected fetcher runs, **Then** it exits with status `source_unavailable` (exit code 0) and logs a warning — it does not crash the pod or produce a failed CronJob
3. **Given** USPTO registration is blocked (non-US identity), **When** USPTO CronJobs run, **Then** they skip gracefully and the issue is tracked for follow-up (#170)

---

### User Story 2 — Dead Sources Retired Cleanly (Priority: P2)

The DDInter source has been unreachable for weeks. Keeping it active creates noise in the failure logs and wastes CronJob execution slots.

**Why this priority**: Each failing source in `meta.refresh_log` pollutes the freshness dashboard and can trigger false Grafana alerts. Clean retirement keeps the operational picture accurate.

**Independent Test**: Confirm `cms_ddinter` no longer appears in the SOURCES registry, no CronJob for it exists in the cluster (ArgoCD prunes it), and the SQLMesh bronze model carries a retirement comment documenting why it is retained for historical data.

**Acceptance Scenarios**:

1. **Given** DDInter has been retired, **When** ArgoCD syncs, **Then** the `fetch-cms-ddinter` CronJob is pruned from the cluster with no manual deletion
2. **Given** historical `hcs_raw.cms_ddinter` data exists, **When** the bronze model runs, **Then** it still materialises that data (model retained, fetcher removed)
3. **Given** drug-drug interaction data is needed, **When** the platform is queried, **Then** DrugBank (`mol_bronze.drugbank_data`) is the authoritative source

---

### User Story 3 — All ~90 Sources Audited for Rate Limits and Pagination (Priority: P3)

A full source catalogue audit ensures every fetcher respects upstream rate limits, uses consistent pagination, and has appropriate backfill caps so scheduled runs do not overload external APIs or produce unbounded data volumes.

**Why this priority**: Uncontrolled backfills caused 429 errors and pod OOMKills in earlier runs. The audit prevents recurrence as CMS PUF sources come online in April 2026.

**Independent Test**: Run any single CMS PUF fetcher in isolation with a multi-year window and confirm it paginates within configured caps without triggering rate-limit errors from the upstream CMS data catalog.

**Acceptance Scenarios**:

1. **Given** a CMS PUF source with 3 years of available data, **When** the fetcher runs with `days_back=1095`, **Then** it discovers available dataset UUIDs dynamically from the CMS catalog rather than relying on hardcoded year references
2. **Given** an API source with a rate limit, **When** the fetcher exceeds the configured request-per-second cap, **Then** it backs off and retries rather than returning a 429 error to the caller
3. **Given** a fetcher with a backfill cap, **When** the full historical window exceeds that cap, **Then** it fetches up to the cap and logs that pagination was bounded — it does not silently drop data

---

## Functional Requirements

### FR-001 — EPO Credential Placement
EPO OAuth2 keys must exist in `dk-data-applications/prd` Doppler config (not `dk-data-fe/prd`). The `DopplerSecret` in `k8s/apps/infrastructure/base/doppler-secret.yaml` syncs all keys from `dk-data-applications/prd` to `dk-data-secrets`; keys in any other project are invisible to the cluster.

### FR-002 — Graceful Credential Absence
Any fetcher whose API key is absent or empty must return `status: "source_unavailable"` with a warning log and exit 0. It must not raise an exception or cause a pod failure.

### FR-003 — DDInter Retirement
Remove: `src/dk_data/ingestion/fetchers/cms_ddinter.py`, `sources/cms_ddinter.py`, `sources/__init__.py` entry, `k8s/apps/cronjobs/base/cronjob-fetch-cms-ddinter.yaml`, SOURCES dict entry in `main.py`. Retain: `hcs_bronze/cms_ddinter.sql` with retirement notice.

### FR-004 — CMS PUF Multi-Year Backfill
CMS PUF fetchers must discover available dataset UUIDs from the CMS data catalog API dynamically, covering all available years, rather than using hardcoded year-keyed UUIDs.

### FR-005 — EUIPO Token URL
EUIPO IBM Gateway token endpoint must be `https://euipo.europa.eu/cas-server-webapp/oidc/accessToken`.

### FR-006 — USPTO Key Tracking
Create issue #170 documenting that USPTO API key registration is blocked by ID.me US-identity requirement. Fetchers continue in `source_unavailable` graceful-skip mode.

---

## Success Criteria

- **SC-001**: EPO CronJob produces data inserts rather than 401 errors on next Sunday run
- **SC-002**: Zero `fetch-cms-ddinter` CronJob entries in cluster after next ArgoCD sync
- **SC-003**: All ~90 sources in SOURCES registry have reviewed rate-limit and pagination config
- **SC-004**: `doppler secrets --project dk-data-applications --config prd` shows no CHANGEME values for EPO keys
- **SC-005**: Any fetcher with a missing key exits 0 (`source_unavailable`) — not exit 1

---

## Dependencies & Assumptions

- Doppler operator resync interval is 300 seconds — EPO keys propagate to cluster within 5 minutes of Doppler update
- `job-initial-backfill` has not been run on the cluster; HCS bronze/silver transform pipeline requires a manual trigger (tracked separately)
- USPTO registration requires a US-based team member or email to APIhelp@uspto.gov; April 20, 2026 legacy hub shutdown is the hard deadline
- DrugBank API key is intentionally empty; the local XML seed (`mol_bronze.drugbank_data` via `job-drugbank-seed`) covers all bulk drug data needs
