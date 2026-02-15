# Open Issues Reconciliation

**Date**: 2026-02-15 (updated)
**Branch**: main (post-merge of PR #89 — 012-platform-hardening, PR #90 — promote workflow fix)
**Open Issues**: 8

---

## Executive Summary

Since the initial reconciliation (2026-02-14), **all Sprint 1 and Sprint 2 items are complete**. PR #89 (012-platform-hardening) resolved 7 issues in a single feature branch covering Dockerfile fixes, API views, data sources, dependency management, and secret documentation. PR #90 fixed a race condition in the production promotion workflow.

Of the 8 remaining open issues, 2 are from the original reconciliation (#52, #84) and 6 are older platform issues (#8, #9, #16, #17, #18, #19) that predate the reconciliation scope.

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

---

## Remaining Open Issues (8)

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

These predate the reconciliation scope and represent longer-term architectural debt:

| Issue | Title | Priority | Notes |
|-------|-------|----------|-------|
| #8 | Tight coupling to Edwards/TAVR use case | P3 | Ongoing — new fetcher pattern (BaseFetcher) is generic, but legacy code still TAVR-specific |
| #9 | No database migration strategy | P2 | Partially addressed — migrations 025-066 exist but no automated runner (manual SQL execution) |
| #16 | Documentation drift risk | P3 | CLAUDE.md auto-updated per feature; DOPPLER_SECRETS.md added in PR #89 |
| #17 | No audit trail for data changes | P3 | Not yet addressed |
| #18 | Unclear PII/PHI data handling | P2 | Not yet addressed — ORCID data may contain researcher PII |
| #19 | No defined data retention policy | P3 | Not yet addressed |

---

## Recommended Next Steps

### Immediate (next session)
- Review #84 (LiteLLM) — close if not needed, or spike evaluation
- Review #8, #9, #16, #17, #18, #19 — triage and close any that are no longer relevant

### Next Feature (Sprint 3)
- **#52** — Frontend integration against the 6 available API views
- **mol_gold compute architecture** — decide on pre-computation vs FastAPI sidecar for molecule property endpoints

---

## Issue Cross-Reference Matrix

| Issue | Status | Theme | Blocked By |
|-------|--------|-------|------------|
| #8 | Open | Architecture debt | — |
| #9 | Open | Platform engineering | — |
| #16 | Open | Documentation | — |
| #17 | Open | Observability | — |
| #18 | Open | Security/compliance | — |
| #19 | Open | Data governance | — |
| #52 | Open | Frontend | mol_gold compute decision |
| #84 | Open | Optional | Decision needed |

---

## Post-Reconciliation Summary

| Action | Count | Issues |
|--------|-------|--------|
| Closed (pre-reconciliation) | 4 | #78, #80, #82, #83 |
| Closed (PR #89) | 7 | #88, #81, #42, #50, #51, #20, #57 |
| Remaining open | 8 | #8, #9, #16, #17, #18, #19, #52, #84 |
| **Total resolved this cycle** | **11** | |
