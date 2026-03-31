# Tasks: Post-Deployment Fixes & Credential Audit

**Branch**: `021-post-deploy-fixes` | **Status**: Completed (retrospec)

---

## Phase 1: Cluster Diagnosis

- [x] T001 Connect to prod cluster via Proxmox API → QEMU guest agent exec on k3s-master-1 (VMID 200, node `penguin`)
- [x] T002 [P] Identify pods running old image `prod-61e05d7` vs new `prod-85e01aa`
- [x] T003 [P] Confirm datetime offset bug is fixed in new image (PR #159)
- [x] T004 [P] Identify EPO 401 as the only actionable cluster error (not a self-healing artifact)
- [x] T005 Check pg-backup configmap state — confirmed self-healing after ArgoCD sync

---

## Phase 2: Credential Audit

- [x] T006 Run `doppler secrets --project dk-data-applications --config prd` — full key inventory
- [x] T007 [P] Cross-reference Doppler keys against all CronJob `secretKeyRef` entries
- [x] T008 [P] Cross-reference fetcher `os.environ.get()` calls against CronJob manifests
- [x] T009 Identify EPO keys as CHANGEME placeholders in correct project, real values in `dk-data-fe/prd`
- [x] T010 Update EPO keys via `doppler secrets set --project dk-data-applications --config prd`
- [x] T011 Identify USPTO keys as CHANGEME — registration blocked by ID.me (non-US)
- [x] T012 Create GitHub issue #170 — USPTO API key registration blocker
- [x] T013 [P] Verify DrugBank graceful-skip: `source_unavailable` exit 0 in `main.py` line 1342
- [x] T014 [P] Verify USPTO Patents graceful-skip: `source_unavailable` when key absent
- [x] T015 [P] Verify USPTO Trademarks graceful-skip: empty batch on 401, proceeds without crash

---

## Phase 3: DDInter Retirement (branch `020`, merged to main)

- [x] T016 Confirm ddinter.scbdd.com and ddinter2.scbdd.com are TCP-unreachable
- [x] T017 Confirm zero downstream silver/gold consumers of DDInter data
- [x] T018 Remove `src/dk_data/ingestion/fetchers/cms_ddinter.py`
- [x] T019 Remove `src/dk_data/ingestion/sources/cms_ddinter.py`
- [x] T020 Remove `cms_ddinter` from `sources/__init__.py`
- [x] T021 Remove DDInter `SOURCES` entry and imports from `main.py`
- [x] T022 Remove `cronjob-fetch-cms-ddinter.yaml` from `k8s/apps/cronjobs/base/kustomization.yaml`
- [x] T023 Add retirement comment to `hcs_bronze/cms_ddinter.sql` (model retained for historical data)
- [x] T024 Merge to main via PR — ArgoCD prunes live CronJob on next sync

---

## Phase 4: Source Catalogue Hardening

- [x] T025 [P] Audit EUIPO IBM Gateway token URL — fix to `https://euipo.europa.eu/cas-server-webapp/oidc/accessToken`
- [x] T026 [P] Confirm USPTO ODP migration already applied in #159 (`api.uspto.gov`)
- [x] T027 [P] Fix NICE API header name
- [x] T028 [P] Rewrite IMGT fetcher to use official bulk FASTA endpoint
- [x] T029 API rate limits and backfill caps — systematic review of all ~90 sources (`034d9fc`)
- [x] T030 Complete audit of all ~90 sources: auth tokens, rate limits, skip sources (`af9f1de`)
- [x] T031 CMS PUF dynamic multi-year backfill via catalog UUID discovery (`139e334`)

---

## Phase 5: Documentation & Tracking

- [x] T032 Create GitHub issue #169 — EPO Doppler project mis-placement (closed: fixed via CLI)
- [x] T033 Revert unnecessary `doppler-secret-epo.yaml` (correct fix is Doppler UI, not new manifest)
- [x] T034 Create specs/021-post-deploy-fixes/ retrospec folder (this document)
- [x] T035 Document HCS bronze/silver pipeline gap — `job-initial-backfill` never run post-PR #149
