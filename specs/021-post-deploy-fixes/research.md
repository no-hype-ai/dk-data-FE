# Research: Post-Deployment Fixes & Credential Audit

**Branch**: `021-post-deploy-fixes` | **Date**: 2026-03-31

---

## Finding 1: Doppler Project Topology

**Decision**: `dk-data-applications/prd` is the single source of truth for all CronJob env vars.

**Rationale**: The `DopplerSecret` manifest (`k8s/apps/infrastructure/base/doppler-secret.yaml`) reads from `dk-data-applications/prd` with no `secrets` filter — it syncs all keys. The staging overlay patches `config: stg`. Any key placed in a different Doppler project (e.g., `dk-data-fe`) is invisible to the cluster.

**Alternatives considered**: Adding a second `DopplerSecret` pointing to `dk-data-fe/prd` — rejected because it requires a second service token secret in the cluster and adds operational complexity. Simpler to place all CronJob keys in the correct project.

**Root cause of EPO failure**: Keys were set in `dk-data-fe/prd` (wrong project) with `CHANGEME` placeholders in `dk-data-applications/prd`. Fixed by running:
```bash
doppler secrets set EPO_CONSUMER_KEY="..." EPO_CONSUMER_SECRET="..." \
  --project dk-data-applications --config prd
```

---

## Finding 2: Image Promotion and Self-Healing Pods

**Decision**: Failing pods running old image `prod-61e05d7` require no action — they self-heal.

**Rationale**: ArgoCD synced `prod-85e01aa` but CronJob pods only pull new images when they next trigger. Pods that ran between the old and new promotion window completed with the datetime offset bug (fixed in PR #159). The next scheduled run picks up the new image automatically.

**Pods affected**:
- `fetch-news` — weekly
- `fetch-pubmed` — daily
- `fetch-openalex-ci` — daily
- `fetch-sec-edgar` — daily

All self-heal within 24 hours of the prod promotion without intervention.

---

## Finding 3: DDInter Unreachability

**Decision**: Retire DDInter permanently. No recovery path.

**Rationale**: `ddinter.scbdd.com` is hosted on Alibaba Cloud. TCP connection attempts timeout consistently since early March 2026. DDInter v2 (`ddinter2.scbdd.com`) is equally unreachable. The service shows no status page, no social media activity, and no announcement of downtime. This is a permanent outage.

**Drug-drug interaction data coverage post-retirement**:
- `mol_bronze.drugbank_data.drug_interactions` column — full DDI dataset from DrugBank XML (~17k drugs)
- `mol_bronze.bindingdb` — binding affinity data complementary to DDI

**Alternatives considered**: Polling for recovery on a schedule — rejected; maintaining dead-code fetchers pollutes `meta.refresh_log` and triggers false Grafana alerts.

---

## Finding 4: USPTO API Registration Blocker

**Decision**: Track in GitHub issue #170, leave fetchers in `source_unavailable` skip mode.

**Rationale**: USPTO account.uspto.gov requires ID.me verification with a US government-issued ID + SSN. Registration is being done from outside the US with a non-US passport — ID.me cannot verify the identity. The USPTO legacy developer hub decommissions April 20, 2026.

**Resolution path**: Either (a) a US-based team member registers and shares keys, or (b) email APIhelp@uspto.gov directly for assistance with non-US registration.

**Impact assessment**: USPTO patent and trademark fetchers already handle missing keys with `source_unavailable` exit 0. No data loss — these sources have never successfully ingested data.

---

## Finding 5: SQLMesh HCS Pipeline Gap

**Decision**: Document gap; track separately. Out of scope for `021`.

**Rationale**: The `cms-gold-refresh` CronJob runs `sqlmesh run hcs_gold.* mol_gold.*` daily but there are no HCS bronze or silver transform CronJobs. Gold depends on bronze and silver being populated. `job-initial-backfill` (one-time job) was never manually triggered on the cluster after PR #149 merged.

**Impact**: HCS gold models run daily but produce empty results because upstream silver is unpopulated. This will become visible when CMS PUF fetchers start running in the first week of April 2026.

**Resolution**: Either (a) manually apply `job-initial-backfill` to the cluster, or (b) create `cronjob-hcs-transform-bronze` and `cronjob-hcs-transform-silver` mirroring the mol pipeline pattern.

---

## Doppler Keys Audit Summary

Full audit of `dk-data-applications/prd` against CronJob manifest requirements:

| Key | Value State | Action Taken |
|-----|-------------|--------------|
| `EPO_CONSUMER_KEY` | CHANGEME → real key | Updated via Doppler CLI |
| `EPO_CONSUMER_SECRET` | CHANGEME → real key | Updated via Doppler CLI |
| `USPTO_API_KEY` | CHANGEME (blocked) | Issue #170 |
| `USPTO_TSDR_API_KEY` | CHANGEME (blocked) | Issue #170 |
| `DRUGBANK_API_KEY` | Empty (intentional) | No action — XML seed covers it |
| `EUIPO_API_KEY` | Set ✅ | — |
| `EUIPO_SECRET_KEY` | Set ✅ | — |
| `NCBI_API_KEY` | Set ✅ | — |
| `OPENALEX_API_KEY` | Set ✅ | — |
| `WHO_ICD_CLIENT_ID` | Set ✅ | — |
| `WHO_ICD_CLIENT_SECRET` | Set ✅ | — |
| `LITELLM_API_KEY` | Set ✅ | — |
| `LITELLM_BASE_URL` | Set ✅ | — |
| `DATABASE_URL` | Set ✅ | — |
