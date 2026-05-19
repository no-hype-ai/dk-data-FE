---
pr: 149
title: "feat(019): CMS PUF platform reconciliation — 22 new data sources, agent schema separation, full medallion HCS domain"
branch: "019-cms-puf-platform-reconciliation"
base: "main"
created: "2026-03-30"
---

# PR #149 Validation Plan

## Phase 1: CI & Baseline Verification

Confirm all CI checks pass and the PR branch is up-to-date with base.

### Steps
1. Verify all CI checks pass (Lint, Test, Standards, SQLMesh Validate, K8s Manifests)
2. Check branch is up-to-date with main (no merge conflicts)
3. Verify local infra is running (PostgreSQL, PostgREST, job-trigger)

### Checkpoint
Gate: CI green, no conflicts, local infra healthy.

---

## Phase 2: SQL Migration Review

Review the 52 migration files (036–123) for correctness, ordering, and safety.

### Steps
1. **[agent:pr-code-reviewer] Review migration files** — Check for: idempotency (IF NOT EXISTS), correct ordering, no destructive DROP without safety, proper schema separation (hcs_raw, hcs_bronze, hcs_silver, hcs_gold, hcs_agents, mol_agents, agents)
2. Verify migration file naming follows sequential numbering with no gaps or collisions
3. Check that key migrations create expected schemas and tables (086 as the anchor migration)
4. Verify unique indexes on mol_raw.clinicaltrials(request_id) and mol_raw.openfda_labels(request_id) in migration 123

### Checkpoint
Gate: Migrations are safe, ordered, and create the expected schema topology.

---

## Phase 3: Fetcher & Loader Code Review

Review the 135 fetcher/loader files for correctness, security, and pattern compliance.

### Steps
1. **[agent:pr-code-reviewer] Review fetcher/loader code** — Check: BaseFetcher pattern compliance, proper error handling, no hardcoded secrets, max_records propagation, pagination correctness (ClinicalTrials token-based, OpenFDA skip/limit, Orange Book ZIP handling)
2. Verify main.py registers all 90 sources correctly
3. Check new ClinicalTrials.gov v2 fetcher for correct API v2 usage and date scoping
4. Check OpenFDA Labels fetcher for FDA 25k per-query limit handling
5. Check Orange Book fetcher for ZIP/PK magic bytes detection and delimiter handling

### Checkpoint
Gate: All fetchers follow BaseFetcher pattern, no security issues, pagination is correct.

---

## Phase 4: SQLMesh Model Review

Review the 225 SQLMesh model files across the medallion architecture.

### Steps
1. **[agent:pr-code-reviewer] Review SQLMesh models** — Check: correct layer placement (bronze reads raw, silver reads bronze, gold reads silver), INCREMENTAL_BY_UNIQUE_KEY usage for agent promotion, proper grain definitions, no cross-domain contamination
2. Verify HCS models are in correct directories (hcs/bronze, hcs/silver, hcs/gold) — not in molecules/
3. Verify gold models satisfy >=2 source rule (advocacy_groups fix)
4. Check agent schema separation: mol_agents/hcs_agents tables are isolated from deterministic pipeline

### Checkpoint
Gate: Medallion architecture is correctly layered, no model placement errors.

---

## Phase 5: Kubernetes Manifests & CronJob Review

Review the 85+ K8s CronJob YAMLs and infrastructure manifests.

### Steps
1. **[agent:pr-code-reviewer] Review K8s manifests** — Check: valid cron schedule syntax, image tag uses kustomize patching (not hardcoded), env vars reference Doppler/secrets correctly, resource limits set, schedule spread avoids thundering herd
2. Verify all 90 sources have corresponding CronJob YAMLs
3. Check agent CronJobs have LiteLLM proxy env injection
4. **[agent:infra-health-checker] Verify local infra** — Confirm dk-data-FE services healthy

### Checkpoint
Gate: All CronJobs are valid, no hardcoded secrets, schedules are spread.

---

## Phase 6: Test & Documentation Review

Review tests, docs, and configuration changes.

### Steps
1. **[agent:pr-code-reviewer] Review tests** — Check: test coverage for new fetchers (clinicaltrials, openfda_labels, orange_book, hrsa), bronze model contract tests, agent router tests
2. Review documentation updates (COLUMN_LINEAGE.md, DATA_CLASSIFICATION.md, ENTITY_LINKING_STRATEGY.md, MEDALLION_ARCHITECTURE.md)
3. Check docker-compose.yml changes are safe and backward-compatible
4. Verify .gitignore and Dockerfile changes are appropriate

### Verification
```bash
cd src && pytest --tb=short -q 2>&1 | tail -20
ruff check . 2>&1 | tail -10
```

### Checkpoint
Gate: Tests pass, docs are accurate, config changes are safe.
