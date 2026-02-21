# Open Issues Reconciliation

**Date**: 2026-02-21 (updated)
**Branch**: staging + main (synced, post-merge of PR #115 + fetch-news fix)
**Open Issues**: 7 GitHub issues (#93, #94, #95, #108, #116, #117, #118)

---

## Executive Summary

Since the 2026-02-17 reconciliation:
- **PR #115** merged to staging and promoted to main (22 files, observability remediation — metric deduplication, scrape annotations, alert rule fixes, batch metrics reporting, distributed tracing, structured logging)
- **Issue #114** closed (auto-closed by PR #115 merge)
- **Issue #107** closed (superseded by more specific #116 and #117)
- **fetch-news date parsing bug found and fixed** — `_parse_pub_date()` truncated `'Feb 20, 2026'` to `'Feb 20, 20'` (#118, fix pushed to staging + main)
- **Prod deployment confirmed** — job-trigger restarted with new image, 2/2 pods running
- **New issues filed**: #116 (USPTO API key), #117 (EUIPO API keys), #118 (fetch-news date parsing)
- **Stale branches cleaned up**: `011-datasource-integration`, `012-platform-hardening` deleted

---

## Completed Work (2026-02-21)

### Closed — PR #115 (observability remediation, merged 2026-02-21)

| Issue | Title | What Was Done |
|-------|-------|---------------|
| #114 | DK Data Platform Observability Remediation | 7 phases: metric deduplication, scrape annotations, alert rule fixes, batch metrics, tracing, logging |

### Closed — #107 (superseded 2026-02-21)

Replaced by #116 (USPTO TSDR API key) and #117 (EUIPO API keys) with detailed provisioning instructions.

### Fixed — #118 (fetch-news date parsing, committed 2026-02-21)

`_parse_pub_date()` used `str(val)[:10]` which truncated `'Feb 20, 2026'` to `'Feb 20, 20'`, causing 100% Pydantic validation failures. Fixed to parse common date formats (`%b %d, %Y`, etc.) before ISO-only fallback. Commit `1fb10ad` on staging, `6668f3e` merge on main.

### Previously Completed (2026-02-16 to 2026-02-17)

| PR/Issue | Title | What Was Done |
|----------|-------|---------------|
| PR #106 | Unified ingestion + trademarks | 22-source unified CLI, resolves #109-#112 |
| PR #103 | Backup image fix | `postgres:16-alpine` with `mc` client |

---

## Prod Cluster Status (2026-02-21)

| Component | Status | Details |
|-----------|--------|---------|
| PostgREST | **3/3 Running** | Healthy |
| job-trigger | **2/2 Running** | New image deployed (observability + fetch-news fix) |
| PostgreSQL (infra) | **3/3 Healthy** | |
| pg-backup | **Working** | Daily backups completing |
| fetch-pubmed | **Completing** | Daily runs succeeding |
| fetch-journal-rss | **Completing** | Daily runs succeeding |
| fetch-sec-edgar | **Completing** | Daily runs succeeding |
| fetch-openalex-ci | **Completing** | 1Gi memory fix resolved OOMKilled |
| fetch-news | **Erroring** | Date parsing fix deployed, awaiting next scheduled run |
| mol-fetch-daily | **Completing** | Every 6h runs succeeding |
| mol-transform | **Completing** | Daily runs succeeding |
| catalog-refresh | **Completing** | Daily runs succeeding |

---

## Remaining Open Issues (7)

### Actionable

| Issue | Title | Priority | Action Required |
|-------|-------|----------|-----------------|
| #116 | Provision USPTO TSDR API key in Doppler | P2 | Register at USPTO developer portal, add key to Doppler stg + prd |
| #117 | Provision EUIPO API keys in Doppler | P2 | Register at EUIPO TMview, add key(s) to Doppler stg + prd |
| #118 | fetch-news date parsing truncates non-ISO dates | P1 | **Fix deployed** — awaiting next CronJob run to verify |

### Deferred

| Issue | Title | Priority | Status |
|-------|-------|----------|--------|
| #93 | Decouple TAVR-specific hardcoding for multi-domain reuse | P3 | Architecture debt — defer to Sprint 4+ |
| #94 | Frontend: dashboard + molecule onboarding against PostgREST API views | P2 | Blocked on mol_gold compute decision |
| #95 | Evaluate LiteLLM proxy vs direct Anthropic SDK | P3 | Decision needed |
| #108 | Implement dynamic data source auto-registration from fetcher metadata | P3 | Enhancement / tech-debt — future sprint |

---

## Issue Cross-Reference Matrix

| Issue | Status | Theme | Closed By |
|-------|--------|-------|-----------|
| #118 | Open (fix deployed) | fetch-news date parsing | Commit `1fb10ad` |
| #117 | Open | EUIPO API keys (infra) | — |
| #116 | Open | USPTO API key (infra) | — |
| #114 | **Closed** | Observability remediation | PR #115 |
| #109 | **Closed** | Unified ingestion | PR #106 |
| #110 | **Closed** | Trademark sources | PR #106 |
| #111 | **Closed** | CronJob deployment | PR #106 |
| #112 | **Closed** | Validation script | PR #106 |
| #107 | **Closed** | Doppler secrets (superseded) | #116, #117 |
| #108 | Open | Auto-registration (enhancement) | — |
| #93 | Open | Architecture debt | — |
| #94 | Open | Frontend | — |
| #95 | Open | LiteLLM evaluation | — |

---

## Recommended Next Steps

### Immediate
1. **Monitor fetch-news next run** — verify date parsing fix resolves the Error state
2. **Close #118** after next successful fetch-news CronJob run
3. **Provision Doppler secrets (#116, #117)** — register at USPTO/EUIPO developer portals

### Short-term
4. **Run prod database init** — meta tables + seeds + migrations (if not already done)
5. **Verify observability** — confirm metrics appear in Grafana/Mimir within ~2 min of deployment
6. **Verify batch metrics** — trigger a CronJob, check `batch_job_duration_seconds` in Mimir

### Next Feature (Sprint 4)
- **#94** — Frontend integration against available API views
- **mol_gold compute architecture** — pre-computation vs FastAPI sidecar
- **#108** — Auto-registration to reduce maintenance burden

---

## Post-Reconciliation Summary

| Action | Count |
|--------|-------|
| Closed (previous cycles) | 20 issues |
| Closed this cycle | 2 issues (#114, #107) |
| Bugs found and fixed | 1 (#118 fetch-news date parsing) |
| New issues filed | 3 (#116, #117, #118) |
| Staging → main promotions | 2 (PR #115 + fetch-news fix) |
| Stale branches cleaned | 2 (011, 012) |
| Remaining GitHub issues | 7 (#93, #94, #95, #108, #116, #117, #118) |
| **Total resolved all time** | **29** |
