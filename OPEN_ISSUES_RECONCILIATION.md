# Open Issues Reconciliation

**Date**: 2026-02-15 (updated)
**Branch**: main (post-merge of PR #92 — 013-observability-governance)
**Open Issues**: 3

---

## Executive Summary

Since the initial reconciliation (2026-02-14), **all Sprint 1, Sprint 2, and Sprint 3 items are complete**. PR #89 (012-platform-hardening) resolved 7 issues. PR #90 fixed a production promotion race condition. PR #92 (013-observability-governance) resolved 5 issues covering metrics scraping, audit trail, migration runner, and data classification/retention.

Of the 3 remaining open issues, 2 are from the original reconciliation (#52, #84) and 1 is an older architecture debt item (#8). Issues #9, #16, #17, #18, #19 were all closed by PR #92.

---

## Completed Work (since 2026-02-14)

### Closed — Previously Resolved (2026-02-14)

| Issue | Title | Closed By |
|-------|-------|-----------|
| #78 | dk-data platform: remaining issues and integration roadmap | Superseded by this document |
| #80 | Add missing gold/bronze tables required by behavior-labs-ai specs | Duplicate of #81 |
| #82 | Import SIDER side effect database | PR #87 (011-datasource-integration) |
| #83 | Unblock PatentsView API key | PR #87 (implementation complete) |

### Closed — PR #89 (012-platform-hardening, 2026-02-15)

| Issue | Title | What Was Done |
|-------|-------|---------------|
| #88 | CronJob pods fail: ModuleNotFoundError | Fixed Dockerfile multi-stage build — removed redundant COPY and PYTHONPATH override, fixed absolute imports |
| #81 | Create missing PostgREST API views | Added 6 API views (company_pipeline, molecule_targets, trial_publication_features, sider_side_effects, bioactivity, patents) with migration 065 and GRANTs |
| #42 | Enable UniProt data source | UniProt fetcher, loader, validator, CronJob, seed SQL, catalog entry |
| #50 | Enable PDB data source | PDB fetcher, loader, validator, CronJob, seed SQL, catalog entry |
| #51 | Enable ORCID data source | ORCID fetcher, loader, validator, migration 066, CronJob, seed SQL, catalog entry |
| #20 | Python dependency version management | All 38 deps pinned with upper bounds, uv.lock generated, CI lock freshness check |
| #57 | Document Doppler secret configuration | docs/DOPPLER_SECRETS.md (14 secrets), startup validation module with 7 tests |

### Additional Fix — PR #90 (2026-02-15)

Fixed race condition in `.github/workflows/promote-to-prod.yaml` — production promotion now reads the staging image tag from the overlay kustomization.yaml instead of computing from HEAD SHA (which pointed to the manifest commit, not the build commit).

### Closed — PR #92 (013-observability-governance, 2026-02-15)

| Issue | Title | What Was Done |
|-------|-------|---------------|
| #91 | Enable full observability: deploy ServiceMonitors, verify metrics endpoint, add PostgREST exporter | Fixed ServiceMonitor/PodMonitor labels (`release: mimir`), added `batch-job` labels to 15 CronJob pod templates, replaced PostgREST ServiceMonitor with Probe CRD (blackbox-exporter), updated `APIUnavailable` alert to `probe_success` metric |
| #17 | No audit trail for data changes and API access | Two-layer audit trail: `AuditLoggingMiddleware` (FastAPI, async thread pool) + PostgreSQL trigger via `current_setting('request.jwt.claims')`; `api.audit_log` view restricted to `api_user`; migration 067 |
| #9 | No database migration strategy | Lightweight migration runner (`run_migrations.py`) with SHA-256 checksums, `--baseline`/`--dry-run` flags, `meta.schema_migrations` tracking table, `api.migration_status` view; migration 068 |
| #18 | Unclear PII/PHI data handling | 4-tier data classification (public/internal/pii/confidential) for 43 tables; `raw.orcid` identified as PII with 6 fields; `api.data_classification` view; migration 069 |
| #19 | No defined data retention policy | Retention-based `purge_by_classification()` with `--all-tables` flag; retention_days column on `meta.data_sources`; `docs/DATA_CLASSIFICATION.md`; migration 070 |

198 new tests added (all passing). Also addressed #16 (documentation drift) via comprehensive spec artifacts and `DATA_CLASSIFICATION.md`.

---

## Remaining Open Issues (3)

### Near-Term — Actionable

#### #52 — Frontend integration — React onboarding wizard + dashboard
**Priority**: P2
**Effort**: Large (1-2 weeks)
**Dependencies**: API views now exist (resolved by #81/PR #89)
**Current state**: The frontend directory does not exist on main. The 6 API views from PR #89 now provide data endpoints. The mol_gold compute-on-demand views (molecule_properties, SHAP explanations, synthesizability scores) are still not implemented — these would require a FastAPI sidecar or pre-computation.
**Recommendation**: Can begin basic frontend work against the 6 available API views. Defer mol_gold-dependent features until compute architecture is decided.

#### #84 — Evaluate LiteLLM proxy integration for AI calls
**Priority**: P3
**Effort**: Small (evaluation) or Medium (migration)
**Dependencies**: Decision on centralized LLM budgeting/observability
**Current state**: dk-data-FE uses direct Anthropic SDK calls. The dk-litellm proxy exists but integration hasn't been implemented.
**Recommendation**: Close as "won't fix" if centralized budgeting isn't a priority, or defer to post-MVP.

### Older Platform Issues

| Issue | Title | Priority | Notes |
|-------|-------|----------|-------|
| #8 | Tight coupling to Edwards/TAVR use case | P3 | Ongoing — new fetcher pattern (BaseFetcher) is generic, but legacy code still TAVR-specific |

---

## Recommended Next Steps

### Immediate (next session)
- Review #84 (LiteLLM) — close if not needed, or spike evaluation
- Review #8 — triage whether TAVR decoupling is worth a dedicated effort

### Next Feature (Sprint 4)
- **#52** — Frontend integration against the 6 available API views
- **mol_gold compute architecture** — decide on pre-computation vs FastAPI sidecar for molecule property endpoints

---

## Issue Cross-Reference Matrix

| Issue | Status | Theme | Blocked By |
|-------|--------|-------|------------|
| #8 | Open | Architecture debt | — |
| #9 | **Closed** (PR #92) | Platform engineering | — |
| #16 | **Closed** (PR #92) | Documentation | — |
| #17 | **Closed** (PR #92) | Observability | — |
| #18 | **Closed** (PR #92) | Security/compliance | — |
| #19 | **Closed** (PR #92) | Data governance | — |
| #52 | Open | Frontend | mol_gold compute decision |
| #84 | Open | Optional | Decision needed |

---

## Post-Reconciliation Summary

| Action | Count | Issues |
|--------|-------|--------|
| Closed (pre-reconciliation) | 4 | #78, #80, #82, #83 |
| Closed (PR #89) | 7 | #88, #81, #42, #50, #51, #20, #57 |
| Closed (PR #92) | 5 | #91, #17, #9, #18, #19 |
| Also addressed (PR #92) | 1 | #16 (documentation drift — comprehensive specs + DATA_CLASSIFICATION.md) |
| Remaining open | 3 | #8, #52, #84 |
| **Total resolved this cycle** | **17** | |
