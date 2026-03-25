# Platform Alignment Audit — dk-data-fe

**Date:** 2026-03-24
**Epic:** data-kinetic/dk-planning#15
**Plan:** plans/dk-data-fe/01-platform-alignment-audit.md
**Issue:** data-kinetic/dk-data-fe#133

## ArgoCD Bootstrap Verification

| Item | Status | Evidence |
|------|--------|----------|
| dk-alchemy external bootstrap | **Done** | `.gitops/external/dk-data-fe.yaml` in dk-alchemy |
| Production Application | **Done** | `dk-data-bootstrap-prod` targets `main` branch, path `.gitops/prod/apps` |
| Staging Application | **Done** | `dk-data-bootstrap-staging` targets `staging` branch, path `.gitops/staging/apps` |
| AppProject | **Done** | `dk-data-bootstrap` project defined in dk-alchemy |
| In-repo gitops | **Done** | `.gitops/prod/` and `.gitops/staging/` directories exist in dk-data-fe |

## dk-managed Topic

| Item | Status |
|------|--------|
| `dk-managed` GitHub topic | **Done** — already set on repository |

## Onboarding Checklist Status

| # | Section | Status | Evidence |
|---|---------|--------|----------|
| 1 | Repository Scaffold | **Partial** | `.gitops/` + `k8s/` exist but use flat structure (`k8s/base/`) not `k8s/apps/<service>/` |
| 2 | dk-alchemy Integration | **Done** | AppProject + external bootstrap in dk-alchemy |
| 3 | CI/CD Pipeline | **Strong** | 4 workflows: `ci.yaml`, `build-push.yaml`, `post-deploy-verify.yaml`, `promote-to-prod.yaml` |
| 4 | Secrets | **Done** | DopplerSecret (`dk-data-secrets`), `ghcr-credentials`, `minio-backup-credentials` |
| 5 | Observability | **Strong** | `service-monitor.yaml`, alert-rules, OTel tracing, structlog |
| 6 | Health Checks | **Done** | PostgREST `/health` with startup/liveness/readiness probes |
| 7 | Product Analytics | **N/A** | Not user-facing; PostHog not applicable |
| 8 | Issue Governance | **Missing** | No governance label taxonomy (`status/*`, `priority/*`) |
| 9 | Kustomize Components | **Missing** | Not using dk-alchemy shared components (HPA, PDB, etc.) |
| 10 | Standards Compliance | **Missing** | No `.dk-standards.yaml`, no `standards.yaml` workflow |
| 11 | PR Review Service | **Done** | Org-level service |
| 12 | Production Hardening | **Gaps** | No rolling update strategy, PDBs, anti-affinity, or securityContext |
| 13 | Documentation | **Partial** | CLAUDE.md exists; ARCHITECTURE.md exists; not in dk-planning product portfolio |

## Gap Inventory

| ID | Gap | Severity | Current State | Remediation Plan | Downstream Issue |
|----|-----|----------|---------------|------------------|-----------------|
| G1 | No `dk-managed` GitHub topic | P0 | **Resolved** — topic already set | Plan 01 (this audit) | n/a |
| G2 | No `.dk-standards.yaml` | P1 | **Open** — file does not exist at repo root | Plan 02 | #135 |
| G3 | No `standards.yaml` CI workflow | P1 | **Open** — `.github/workflows/` has 4 workflows, none for standards | Plan 02 | #135 |
| G4 | No issue governance labels | P1 | **Open** — labels are default GitHub + ad-hoc (`litellm-migration`, `infrastructure`, `observability`, `assessment-integration`); missing `status/*`, `priority/*`, `team/*` taxonomy | Plan 02 | #135 |
| G5 | No rolling update strategy on Deployments | P0 | **Open** — `k8s/base/postgrest/deployment.yaml` and `k8s/base/ingestion/job-trigger-deployment.yaml` have no `strategy:` field | Plan 03 | #134 |
| G6 | No PodDisruptionBudgets | P0 | **Open** — no PDB manifests anywhere in `k8s/` | Plan 03 | #134 |
| G7 | No pod anti-affinity | P0 | **Open** — no `podAntiAffinity` in any deployment spec | Plan 03 | #134 |
| G8 | No securityContext on pods/containers | P0 | **Open** — no `securityContext` in any manifest | Plan 03 | #134 |
| G9 | No resource limits on CronJob containers | P1 | **Resolved** — all 23 CronJobs in `k8s/base/ingestion/` have `resources.requests` and `resources.limits` set | n/a | n/a |
| G10 | No `monitoring/` directory | P1 | **Open** — no `k8s/base/monitoring/` or top-level `monitoring/` directory (dk-template pattern has `monitoring/` at root) | Plan 04 | #136 |
| G11 | No Grafana dashboards as code | P1 | **Open** — no dashboard JSON files in repo | Plan 04 | #136 |
| G12 | Alert rules missing `product`/`service` labels | P1 | **Open** — `k8s/base/alert-rules.yaml` has `severity` + `team` labels only; no `product` or `service` labels on any of the 12 alert rules | Plan 04 | #136 |
| G13 | Backup CronJobs reference MinIO (migrating to SeaweedFS) | P2 | **Open** — `k8s/base/backup/` has 5 files with extensive MinIO references (endpoint `minio.infra.svc.cluster.local:9000`, `MINIO_*` env vars, `minio-backup-credentials` secret) | Plan 03 | #134 |
| G14 | `runs-on: ubuntu-latest` (not self-hosted ARC v2) | P2 | **Open** — all 4 workflows (8 job definitions) use `runs-on: ubuntu-latest` | Plan 02 | #135 |

## Summary

- **Total gaps identified:** 14
- **Already resolved:** 2 (G1 dk-managed topic, G9 CronJob resource limits)
- **Open P0 gaps:** 4 (G5, G6, G7, G8) — all production hardening, tracked in #134
- **Open P1 gaps:** 6 (G2, G3, G4, G10, G11, G12) — standards/governance (#135) and monitoring (#136)
- **Open P2 gaps:** 2 (G13, G14) — SeaweedFS migration (#134) and self-hosted runners (#135)

## Downstream Issues

All downstream issues verified as existing and OPEN:

| Issue | Title | Plan |
|-------|-------|------|
| [#134](https://github.com/data-kinetic/dk-data-fe/issues/134) | Production hardening — rolling updates, PDBs, security contexts, Kyverno compliance | Plan 03 |
| [#135](https://github.com/data-kinetic/dk-data-fe/issues/135) | Standards & governance — .dk-standards.yaml, CI workflow, issue labels | Plan 02 |
| [#136](https://github.com/data-kinetic/dk-data-fe/issues/136) | Monitoring consolidation — dashboards, alert labels, metering observability | Plan 04 |
| [#137](https://github.com/data-kinetic/dk-data-fe/issues/137) | API integration & metering — proxy sidecar, consumer keys, rate limiting | Plan 05 |
