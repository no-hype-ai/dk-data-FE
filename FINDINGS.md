# PR Validation Findings

> Persistent tracker for issues discovered during PR #149 validation.
> Managed by `/pr-findings`. Do not edit severity/status fields manually.

---

## Active Findings

| # | Severity | Category | Description | File | PR | Status |
|---|----------|----------|-------------|------|----|--------|
| 10 | info | style | 93 sources registered in main.py (exceeds expected 90 — not a problem, just noted) | `main.py` | 149 | closed |
| 16 | info | style | 7 agent CronJobs found (PR says 6) — all properly configured with LiteLLM proxy env | `k8s/apps/cronjobs/base/` | 149 | closed |
| 20 | info | style | Several models retain intentional `WHERE FALSE` stubs (targeting_scores, stg_certifications, indication_revenue, hcpcs_molecule_bridge) — schema placeholders, not broken | various | 149 | closed |
| 21 | info | style | `mol_gold.market_summary` depends on `mol_gold.trial_outcomes` — gold-to-gold dependency increases plan complexity | `molecules/gold/market_summary.sql:101` | 149 | closed |

## Resolved

| # | Severity | Category | Description | Resolution | Resolved |
|---|----------|----------|-------------|------------|----------|
| 11 | critical | bug | No `startingDeadlineSeconds` on 104 CronJobs | Added `startingDeadlineSeconds: 3600` to all 104 CronJob YAMLs | 2026-03-30 |
| 17 | critical | bug | `mol_silver.healthcare_facilities` references non-existent `facility_id` | Replaced with `(facility_name \|\| '_' \|\| state)` matching hcs_silver pattern | 2026-03-30 |
| 1 | warning | bug | Migrations 092-094: DROP TABLE + RECREATE on 17 raw tables | Added deployment warning comments documenting the batch-apply constraint | 2026-03-30 |
| 2 | warning | bug | Migration 086 rollback references non-existent schemas | Removed `hcs_agents`/`mol_agents`/`agents` refs from rollback | 2026-03-30 |
| 3 | warning | style | Migration numbering gap; header/filename mismatches | Fixed headers in 086, 113, 086_rollback to match filenames | 2026-03-30 |
| 4 | warning | bug | Migration 090 missing idempotency guard on constraint | Wrapped in DO $$ IF NOT EXISTS block | 2026-03-30 |
| 5 | warning | bug | Migration 092 TEXT->BOOLEAN type change via DROP/RECREATE | Covered by deployment warning comment (same batch as #1) | 2026-03-30 |
| 6 | info | style | Duplicated ALTER TABLE blocks in migration 088 | Added explanatory comments documenting intentional duplication | 2026-03-30 |
| 7 | warning | bug | HRSAFetcher failure path missing return keys | Added `records`, `record_count`, `hash` to both failure paths | 2026-03-30 |
| 8 | warning | bug | PubMedFetcher uses `max_results` instead of `max_records` | Now accepts `max_records` (with `max_results` fallback) | 2026-03-30 |
| 9 | warning | bug | PubMedFetcher/CMSCareCompareFetcher missing `record_count` | Added `record_count` to all return paths | 2026-03-30 |
| 12 | warning | bug | 31 CronJobs hardcode stale image tag `main-5f46ed1` | Replaced with `main` in all 31 files | 2026-03-30 |
| 13 | warning | bug | `cms-gold-refresh` missing `/tmp` emptyDir volume | Added volumeMounts and volumes for /tmp | 2026-03-30 |
| 14 | warning | performance | Hour 3 UTC thundering herd (26 CronJobs) | Spread 10 CMS jobs to hours 4-6, reducing hour-3 to 16 | 2026-03-30 |
| 15 | warning | style | `cms-gold-refresh` non-standard labels | Updated to `app.kubernetes.io/*` pattern, added seccompProfile | 2026-03-30 |
| 18 | warning | bug | Single-source gold models (cms_provider_360, cms_market_analytics) | Added exception comments documenting multi-source silver hub | 2026-03-30 |
| 19 | warning | bug | Cross-domain silver-to-silver read in physician_profiles | Added CROSS-DOMAIN NOTE comment documenting intentional exception | 2026-03-30 |
| 22 | warning | improvement | No fetcher tests for ClinicalTrials.gov v2 or OpenFDA Labels | Added 9 + 11 = 20 tests covering pagination, caps, errors, date scoping | 2026-03-30 |
| 23 | warning | improvement | Agent schemas undocumented | Added to MEDALLION_ARCHITECTURE.md and PLATFORM_GUIDE.md | 2026-03-30 |
| 24 | warning | style | `data-samples/requestfromnick` personal notes committed | Deleted via git rm | 2026-03-30 |
| 25 | info | style | PostgREST healthcheck degraded to TCP-only | Restored HTTP wget healthcheck in docker-compose.yml | 2026-03-30 |
| 26 | info | style | COLUMN_LINEAGE.md references "feature 020" | Changed to "feature 019" | 2026-03-30 |

## Summary

- **Critical**: 0 | **Warning**: 0 | **Info**: 0
- **Open**: 0 (4 closed-informational) | **Resolved**: 22
