# Implementation Plan: Post-Deployment Fixes & Credential Audit

**Branch**: `021-post-deploy-fixes` | **Date**: 2026-03-31 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/021-post-deploy-fixes/spec.md`

---

## Summary

Post-deployment audit and remediation after prod image promotion `prod-85e01aa`. Fixes span three categories: (1) credential mis-placement in Doppler, (2) dead-source retirement (DDInter), and (3) systematic rate-limit and pagination hardening across all ~90 ingestion sources. No new schemas, no migrations, no new CronJobs — this is pure configuration and fetcher correctness work.

---

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: psycopg2-binary, requests + urllib3 (retry in BaseFetcher), Doppler CLI (credential management), kubectl/ArgoCD (cluster state)
**Storage**: PostgreSQL 16 (CloudNativePG). No schema changes — all existing `hcs_raw`, `hcs_bronze`, `mol_raw`, `mol_bronze` tables used as-is
**Secrets**: Doppler project `dk-data-applications/prd` — all CronJob env vars sourced from this project via DopplerSecret `dk-data-secrets`
**Target Platform**: K3s cluster (penguin/krang), namespaces `dk-data-staging` / `dk-data-prod`. ArgoCD GitOps — manifest changes auto-sync within ~2 minutes of push
**Constraints**: No cluster-direct changes — all fixes via git push + ArgoCD sync. EPO credential update via Doppler CLI only.
**Scale/Scope**: ~90 sources audited; 1 source retired (DDInter); 1 credential corrected (EPO); 2 credential gaps tracked (USPTO); rate-limit config reviewed across all fetchers

---

## Constitution Check

| Gate | Status | Notes |
|---|---|---|
| No cluster-direct changes | PASS | All fixes via git + Doppler CLI only |
| Dead source retired via manifest removal (ArgoCD prunes) | PASS | `cronjob-fetch-cms-ddinter.yaml` removed from kustomization |
| Retired fetcher code fully removed | PASS | No orphaned imports in `main.py` or `sources/__init__.py` |
| Bronze model retained with retirement comment | PASS | Historical data in `hcs_raw.cms_ddinter` remains queryable |
| All fetchers with absent keys exit 0 | PASS | `source_unavailable` path verified in `main.py` line 1342 |
| Credential gap tracked in GitHub issue | PASS | Issue #170 — USPTO registration blocked |
| EPO keys in correct Doppler project | PASS | Updated via `doppler secrets set` to `dk-data-applications/prd` |

---

## Project Structure

### Documentation (this feature)

```text
specs/021-post-deploy-fixes/
├── spec.md              # Feature specification (this branch)
├── plan.md              # This file
├── research.md          # Doppler project audit findings + cluster investigation
├── data-model.md        # N/A — no schema changes
├── quickstart.md        # How to verify fixes are live in cluster
├── tasks.md             # Completed task list
├── checklists/
│   └── requirements.md  # Spec quality validation
└── contracts/
    └── doppler-secrets.md  # Required keys in dk-data-applications/prd
```

### Source Code (repository root)

```text
src/dk_data/ingestion/
├── fetchers/
│   ├── euipo_trademarks.py     # Fixed: IBM Gateway token URL, default backend
│   ├── uspto_patents.py        # Already migrated to api.uspto.gov in #159
│   └── [~90 others audited]    # Rate limits, pagination caps reviewed
├── sources/
│   └── __init__.py             # Removed: 'cms_ddinter'
└── main.py                     # Removed: DDInter SOURCES entry + imports

k8s/apps/
├── cronjobs/base/
│   └── cronjob-fetch-cms-ddinter.yaml  # Removed from kustomization (ArgoCD prunes)
└── infrastructure/base/
    └── doppler-secret.yaml     # Unchanged — syncs all of dk-data-applications/prd
```

---

## Implementation Phases

### Phase 1: Cluster Diagnosis (Completed)

Investigated prod cluster state via Proxmox API → QEMU guest agent exec on k3s-master-1 (VMID 200, node `penguin`). Findings:

- Pods running old image `prod-61e05d7` (fetch-news, fetch-pubmed, fetch-openalex-ci, fetch-sec-edgar) — self-healing on next scheduled run
- `pg-backup` pods running old configmap — self-healing after ArgoCD sync
- EPO CronJob — 401 Unauthorized every run (credential mis-placement)
- CMS PUF sources — scheduled first week April 2026, not yet failing

### Phase 2: Credential Audit (Completed)

`doppler secrets --project dk-data-applications --config prd` revealed:

| Key | State Before | Action |
|-----|-------------|--------|
| `EPO_CONSUMER_KEY` | `CHANGEME_obtain_from_developers_epo_org` | Updated via `doppler secrets set` |
| `EPO_CONSUMER_SECRET` | `CHANGEME_obtain_from_developers_epo_org` | Updated via `doppler secrets set` |
| `USPTO_API_KEY` | `CHANGEME_obtain_from_developer_uspto_gov` | Issue #170 — blocked by ID.me |
| `USPTO_TSDR_API_KEY` | `CHANGEME_obtain_from_developer_uspto_gov` | Issue #170 — blocked by ID.me |
| `DRUGBANK_API_KEY` | *(empty)* | Intentional — XML seed covers bulk data |

### Phase 3: DDInter Retirement (Completed — branch `020`, merged via PR)

Source `ddinter.scbdd.com` (Alibaba Cloud) TCP-unreachable since March 2026. No downstream silver/gold consumers. DrugBank covers DDI data via `mol_bronze.drugbank_data.drug_interactions`.

### Phase 4: Source Catalogue Hardening (Completed — branch `021`)

Commits on `021-post-deploy-fixes`:
- `034d9fc` — API rate limits, pagination, and backfill caps across all fetchers
- `af9f1de` — Complete audit of all ~90 sources: auth tokens, rate limits, skip sources
- `71930ed` — NICE API header fix; IMGT rewritten to official bulk FASTA
- `139e334` — Dynamic CMS PUF multi-year backfill via catalog UUID discovery
