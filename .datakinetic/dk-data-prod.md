# dk-data Production Readiness Plan

**Created:** 2026-03-25
**Updated:** 2026-03-25 (v2 — full dk CLI alignment choices applied)
**Source:** xenon-dk-data-fe-status.update-23032026.md + repo audit + dk-template + dk CLI + dk-alchemy audit
**Goal:** Resolve all dk-data pipeline issues blocking reliable xenon assessments, and fully align the repo as a dk-managed application.

---

## Part 1: dk-data Issues Requiring Resolution

Issues extracted from the xenon status report, verified against current codebase state.

### P0 — Must fix before assessments are reliable

#### 1. DrugBank XML parser produces 92% garbage rows

**File:** `src/dk_data/ingestion/fetchers/drugbank.py:172-186`
**Problem:** `iterparse` matches ALL `<drug>` elements at any nesting depth. Drug targets, metabolites, and interaction references each embed nested `<drug>` stubs with only `drugbank_id` + `name` — no pharmacological fields. Of 50,000 parsed records, only 3,759 are unique top-level entries; ~46,000 are empty nested duplicates.
**Impact:** DrugBank contributes nothing to `mechanism_of_action` or `molecule_profile` sections. Key assessed molecules (Durvalumab DB14392, Atezolizumab, Dupilumab) absent entirely.
**Fix:**
  - Track nesting depth in `_parse_drugbank_xml()` — only process `<drug>` elements whose parent is `<drugbank>` (depth 1), skip nested `<drug>` stubs inside `<targets>`, `<metabolites>`, `<interactions>`.
  - Verify bundled XML version (`data/drugbank/drugbank_all_full_database.xml.zip`, 205MB LFS) includes DB14392. If not, update the XML.
  - After fix: expect ~14,000 clean unique entries with populated pharmacological fields.
**Verification:** `SELECT COUNT(*), COUNT(DISTINCT drugbank_id), COUNT(*) FILTER (WHERE mechanism_of_action IS NOT NULL) FROM mol_raw.drugbank;`

#### 2. INCREMENTAL_BY_UNIQUE_KEY models use `gen_random_uuid()` — idempotency broken

**Files:**
  - `src/dk_data/sqlmesh/models/molecules/silver/adverse_events.sql:60` — `gen_random_uuid() AS id`
  - `src/dk_data/sqlmesh/models/molecules/silver/drug_labels.sql` — `gen_random_uuid()` for id
**Problem:** Both models declare `INCREMENTAL_BY_UNIQUE_KEY` but generate a random UUID for `id` on every run. More critically, `clinical_trials.sql` uses `INCREMENTAL_BY_TIME_RANGE` with `gen_random_uuid() AS trial_id` — re-ingesting the same time range produces duplicate rows.
**Fix:**
  - `adverse_events.sql`: Replace `gen_random_uuid()` with `md5(molecule_id::TEXT || meddra_pt)::uuid`
  - `drug_labels.sql`: Replace with `md5(set_id)::uuid`
  - `clinical_trials.sql`: Convert to `INCREMENTAL_BY_UNIQUE_KEY (unique_key nct_id)` and use `md5(nct_id)::uuid AS trial_id`
**Verification:** Run SQLMesh plan twice, confirm row counts are stable.

#### 3. `mol_silver.adverse_events` linkage rate ~17% — synonym matching missing

**File:** `src/dk_data/sqlmesh/models/molecules/silver/adverse_events.sql:30-35`
**Current state:** The model joins FAERS -> molecules on `LOWER(drug_name) = LOWER(canonical_name)` plus `similarity() > 0.8`. It does NOT use `molecule_aliases` at all.
**Fix:** Add a CTE that unions `mol_silver.molecule_aliases` synonyms into the matching logic so FAERS drug names like "HUMIRA" match aliases, not just canonical names.
**Verification:** `SELECT COUNT(*) FILTER (WHERE molecule_id IS NOT NULL)::FLOAT / COUNT(*) FROM mol_silver.adverse_events;` — target >70%.

#### 4. `mol_silver.side_effects` model does not exist

**Expected location:** `src/dk_data/sqlmesh/models/molecules/silver/side_effects.sql`
**Current state:** No such file. SIDER data loads into `bronze.sider_side_effects` but no silver transformation exists.
**Fix:** Create `silver.side_effects` model joining `bronze.sider_side_effects` -> `mol_silver.pubchem` (on `cid`) -> `mol_silver.molecules`.
**Verification:** `SELECT COUNT(*), COUNT(*) FILTER (WHERE molecule_id IS NOT NULL) FROM mol_silver.side_effects;`

#### 5. Rebuild container image after SQL model fixes

After all P0 fixes: `git push` -> CI build -> deploy staging -> run SQLMesh plan -> verify linkage rates -> promote to prod.

---

### P1 — Verify post-fix

#### 6. Re-measure DATA_INSUFFICIENT failure rate
Trigger a fresh Durvalumab/IMFINZI assessment. Pre-fix rate was ~69%.

#### 7. Measure per-section confidence baselines

| Section | Pre-fix | Target |
|---------|---------|--------|
| safety_interpretation | 0.52 | >0.75 |
| mechanism_of_action | 0.48 | >0.65 |
| molecule_profile | 0.34 | >0.50 |
| patient_journey | 0.31 | >0.45 |
| pivotal_trial_analysis | 0.17 | >0.40 |

#### 8. Confirm `mol_silver.molecule_targets` builds with rows

---

### P2 — Lower priority / structural limitations

#### 9. SEC EDGAR per-indication revenue — not solvable via filing parsing
#### 10. Competitor HTA/patent data — requires extending competitor enrichment
#### 11. IMGT/NPI/TTD sources — assess reachability before investing

---

## Part 2: Full dk CLI Alignment

### Decisions Made

| # | Decision | Choice |
|---|----------|--------|
| 1 | `.dk-standards.yaml` | **Update to full schema now** (services, promotion config) |
| 2 | `.dk-os/config.yaml` | **Run `dk adopt` to generate** |
| 3 | `.gitops/` directory | **Create full structure matching template** (already partially exists) |
| 4 | `k8s/` structure | **Restructure to per-service layout** |
| 5 | CI/CD workflows | **Keep local workflows, add shared standards check alongside** |
| 6 | Doppler project naming | **Rename to `dk-data-applications`** |
| 7 | Security contexts | **Add to K8s manifests now** |
| 8 | Missing platform files | **Create all now** |
| 9 | Code structure cleanup | **Archive to `docs/archive/`** |

---

### Existing dk-alchemy Infrastructure (already provisioned)

Before starting, note what dk-alchemy already has for dk-data:

| Component | Path in dk-alchemy | Status |
|-----------|-------------------|--------|
| AppProject | `.gitops/repositories/dk-data-bootstrap-project.yaml` | `dk-data-bootstrap` project, allows dk-data-prod + dk-data-staging namespaces |
| Applications | `.gitops/external/dk-data-fe.yaml` | `dk-data-bootstrap-prod` (main -> .gitops/prod/apps), `dk-data-bootstrap-staging` (staging -> .gitops/staging/apps) |
| Namespaces | `k8s/infrastructure/namespaces/base/namespaces.yaml` | `dk-data-prod`, `dk-data-staging` with PSS baseline + restricted audit |
| Doppler tokens | `k8s/infrastructure/doppler-secrets/base/dk-data-token.yaml` | Syncs `DK_DATA_FE_PRD_TOKEN` + `DK_DATA_FE_STG_TOKEN` from `dk-infrastructure` |
| Grafana alerts | `grafana/alerts/dk-data.yaml` | 10+ alert rules (sync failed, backend down, quarantine high, latency, etc.) |
| Contact points | `grafana/provisioning/alerting/contact-points.yaml` | `dk-data-slack` -> `#dk-data-fe` channel |
| Notification routing | `grafana/provisioning/alerting/notification-policies.yaml` | Routes `team=data-platform` to dk-data-slack |

**Kustomize components available in dk-alchemy:**
- `doppler-secret`, `otlp-collector`, `hpa-production`, `hpa-standard`, `pdb-standard`, `service-loadbalancer`

---

### Phase 3: `.dk-standards.yaml` — Full Schema (Choice 1A)

**Current:**
```yaml
version: "1.0"
tier: 2
product: dk-data
team: data-platform
grace_period_until: "2026-06-30"
checks:
  claude_md: true
  architecture_md: true
  ...
```

**Target:**
```yaml
version: "1.0"
product: dk-data
team: data-platform
tiers: [1, 2, 3]

services:
  - name: job-trigger
    port: 8000
    health_endpoint: /health
    ready_endpoint: /ready
  - name: postgrest
    port: 3000
    health_endpoint: /
    ready_endpoint: /
  - name: metering-proxy
    port: 8080
    health_endpoint: /health
    ready_endpoint: /health

promotion:
  staging:
    approvers: []
    auto_assign: true
  production:
    approvers: []
    require_cross_approval: true
    min_staging_soak_hours: 4
```

---

### Phase 4: `.dk-os/config.yaml` via `dk adopt` (Choice 2B)

Run `dk adopt` from repo root. Expected output:
```yaml
language: python
framework: fastapi
org: data-kinetic
repo: dk-data-FE
```

Also generates any other missing platform files.

---

### Phase 5: `.gitops/` — Full Template Structure (Choice 3A)

**Current state:** `.gitops/` already exists with prod/staging apps. Needs alignment to template pattern with per-service Applications.

**Current structure:**
```
.gitops/
  prod/apps/
    application.yaml     # Single monolithic app -> k8s/overlays/prod
    namespace.yaml
    project.yaml
    kustomization.yaml
  staging/apps/
    application.yaml     # Single monolithic app -> k8s/overlays/staging
    namespace.yaml
    project.yaml
    kustomization.yaml
```

**Target structure:**
```
.gitops/
  dk-data-root-app-prod.yaml         # Root app syncing prod/apps/
  dk-data-root-app-staging.yaml      # Root app syncing staging/apps/
  prod/apps/
    00-project.yaml                   # AppProject for dk-data
    job-trigger.yaml                  # Application -> k8s/apps/job-trigger/overlays/prod
    postgrest.yaml                    # Application -> k8s/apps/postgrest/overlays/prod
    doppler-secrets.yaml              # Application -> k8s/apps/doppler-secrets/overlays/prod
    cronjobs.yaml                     # Application -> k8s/apps/cronjobs/overlays/prod
    kustomization.yaml
  staging/apps/
    00-project.yaml
    job-trigger.yaml
    postgrest.yaml
    doppler-secrets.yaml
    cronjobs.yaml
    kustomization.yaml
  local/apps/
    docker-compose.yaml               # Symlink or copy of root docker-compose.yml
    .env.example                       # Symlink or copy of root .env.example
```

**dk-alchemy coordination required:** Update `.gitops/external/dk-data-fe.yaml` to match new root app naming if changed. Current external apps already point to `.gitops/prod/apps` and `.gitops/staging/apps` — paths stay the same, only contents change.

---

### Phase 6: `k8s/` Per-Service Restructure (Choice 4A)

**Current flat structure:**
```
k8s/
  base/           # Everything: postgrest, job-trigger, cronjobs, backups, secrets, PDBs, ingress, metering-proxy
  overlays/
    staging/      # Single kustomization.yaml
    prod/         # Single kustomization.yaml
```

**Target per-service structure:**
```
k8s/
  apps/
    job-trigger/
      base/
        deployment.yaml
        service.yaml
        kustomization.yaml
      overlays/
        prod/kustomization.yaml    # References dk-alchemy components
        staging/kustomization.yaml
    postgrest/
      base/
        deployment.yaml
        service.yaml
        configmap.yaml
        kustomization.yaml
      overlays/
        prod/kustomization.yaml
        staging/kustomization.yaml
    metering-proxy/
      base/
        configmap.yaml
        service.yaml
        servicemonitor.yaml
        deployment-patch.yaml      # Sidecar patch for postgrest
        kustomization.yaml
      overlays/
        prod/kustomization.yaml
        staging/kustomization.yaml
    cronjobs/
      base/
        cronjob-*.yaml             # All 22 CronJob files
        kustomization.yaml
      overlays/
        prod/kustomization.yaml
        staging/kustomization.yaml
    doppler-secrets/
      base/
        doppler-secret.yaml
        kustomization.yaml
      overlays/
        prod/kustomization.yaml
        staging/kustomization.yaml
    infrastructure/
      base/
        ingress.yaml
        networkpolicy.yaml
        middleware-rate-limit.yaml
        db-init-job.yaml
        service-monitor.yaml
        alert-rules.yaml
        backup/                    # pg-backup-*.yaml files
        kustomization.yaml
      overlays/
        prod/kustomization.yaml
        staging/kustomization.yaml
```

**Migration steps:**
1. Create new directory structure
2. Move files from `k8s/base/` to per-service `base/` dirs
3. Split monolithic `kustomization.yaml` into per-service kustomizations
4. Add dk-alchemy component references in overlays:
   - `doppler-secret` — all services
   - `otlp-collector` — job-trigger, postgrest
   - `hpa-production` — postgrest (prod)
   - `pdb-standard` — postgrest, job-trigger
5. Update `.gitops/` Applications to point to new paths
6. Test with `kubectl kustomize` for each overlay
7. Coordinate dk-alchemy sync (external apps already point to `.gitops/*/apps/`)

**Risk:** This is a breaking change for ArgoCD. Must be deployed atomically — update `.gitops/` and `k8s/` in the same commit, or ArgoCD will lose track of resources.

---

### Phase 7: CI/CD — Add Shared Standards Check (Choice 5B)

Keep existing 5 local workflows. Add shared standards check:

**New file:** `.github/workflows/dk-standards.yaml`
```yaml
name: DK Standards Check
on:
  push:
    branches: [main, staging]
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  standards:
    uses: data-kinetic/.github/.github/workflows/standards-check.yaml@main
    with:
      product: dk-data
      team: data-platform
    secrets: inherit
```

**Note:** Shared workflows may not exist yet in `data-kinetic/.github`. Verify before adding. If missing, the local `standards.yaml` already validates `.dk-standards.yaml`, CLAUDE.md, ARCHITECTURE.md, and kustomize overlays — sufficient for now.

---

### Phase 8: Doppler Project Rename (Choice 6A)

**Current:** Project `dk-data-fe` with configs `dev`, `stg`, `prd`
**Target:** Project `dk-data-applications` with configs `dev`, `stg`, `prd`

**Migration steps:**
1. Create new Doppler project `dk-data-applications`
2. Copy all secrets from `dk-data-fe` to `dk-data-applications` (all 3 configs)
3. Update `doppler.yaml` in repo root: `project: dk-data-applications`
4. Update `Makefile` references (auto-detected from `doppler.yaml`)
5. Update dk-alchemy DopplerSecret: `dk-data-token.yaml` project reference
6. Update dk-alchemy `DK_DATA_FE_PRD_TOKEN` / `DK_DATA_FE_STG_TOKEN` naming
7. Update CI workflows if they reference the Doppler project directly
8. Verify staging + prod secrets sync after rename
9. Delete old `dk-data-fe` Doppler project

**Risk:** Secrets sync interruption in prod. Do this during a maintenance window. Test staging first.

---

### Phase 9: Security Contexts on K8s Manifests (Choice 7A)

**Current state:** Dockerfile already runs as `appuser` (non-root). K8s manifests lack explicit security contexts. PDBs already exist (`pdb-postgrest.yaml`, `pdb-job-trigger.yaml`).

**Add to all Deployment specs:**
```yaml
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        fsGroup: 1001
      containers:
        - securityContext:
            runAsUser: 1001
            runAsGroup: 1001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
```

**Files to update:**
- `k8s/apps/job-trigger/base/deployment.yaml`
- `k8s/apps/postgrest/base/deployment.yaml`
- All CronJob specs in `k8s/apps/cronjobs/base/`

**Note:** `readOnlyRootFilesystem: true` may break job-trigger if it writes to `/app/data` or `/app/logs`. Add `emptyDir` volume mounts for writable paths:
```yaml
volumeMounts:
  - name: tmp
    mountPath: /tmp
  - name: data
    mountPath: /app/data
  - name: logs
    mountPath: /app/logs
volumes:
  - name: tmp
    emptyDir: {}
  - name: data
    emptyDir: {}
  - name: logs
    emptyDir: {}
```

Remove `security_context: deferred` from `.dk-standards.yaml`.

---

### Phase 10: Create All Missing Platform Files (Choice 8B)

#### 10a. `CODEOWNERS`

**File:** `.github/CODEOWNERS`
```
* @data-kinetic/data-platform
.gitops/ @data-kinetic/data-platform @data-kinetic/platform
k8s/ @data-kinetic/data-platform @data-kinetic/platform
.github/workflows/ @data-kinetic/data-platform @data-kinetic/platform
```

#### 10b. `renovate.json`

**File:** `renovate.json`
```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["local>data-kinetic/.github:renovate-config"]
}
```

#### 10c. `/ready` endpoint

**File:** `src/dk_data/ingestion/batch/api.py` — add alongside existing `/health`:
```python
@app.get("/ready")
async def readiness_check():
    """Readiness probe — checks database connectivity."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return {"status": "ready"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
```

Update K8s deployments to use `/ready` for readiness probe and `/health` for liveness probe.

#### 10d. Monitoring dashboards in Grafana JSON format

**Files:**
- `monitoring/dashboards/job-trigger-overview.json` — request rate, error rate, p95 latency, memory, CPU, restarts
- `monitoring/dashboards/postgrest-overview.json` — same panels scoped to postgrest

Use dk-template's `{{service}}-overview.json` as base, replace placeholders with dk-data values.

#### 10e. Monitoring alerts in Grafana provisioning format

**File:** `monitoring/alerts/job-trigger.yaml`, `monitoring/alerts/postgrest.yaml`

Note: dk-alchemy already has `grafana/alerts/dk-data.yaml` with 10+ rules. These local files can reference or extend those.

#### 10f. `_dk-alchemy-pr/` bootstrap content

**Already provisioned in dk-alchemy** — AppProject, Applications, namespaces, Doppler tokens, contact points, notification policies all exist. Create `_dk-alchemy-pr/README.md` noting this is already complete:
```markdown
# dk-alchemy Bootstrap — Already Provisioned

dk-data was provisioned in dk-alchemy before the template pattern existed.
All bootstrap resources are already in place:
- AppProject: .gitops/repositories/dk-data-bootstrap-project.yaml
- Applications: .gitops/external/dk-data-fe.yaml
- Namespaces: dk-data-prod, dk-data-staging
- Doppler: dk-data-token with PRD/STG tokens
- Grafana: contact points, notification policies, alert rules
```

---

### Phase 11: Archive Specs and Status Docs (Choice 9C)

Move to `docs/archive/`:
- `specs/` -> `docs/archive/specs/` (15 feature specification directories)
- `xenon-dk-data-fe-status.update-23032026.md` -> `docs/archive/`
- `plans/` -> `docs/archive/plans/` (if these belong in dk-planning)

Keep in repo root:
- `ARCHITECTURE.md`, `CLAUDE.md`, `README.md` (required by standards)
- `dk-data-prod.md` (this plan)

---

## Execution Order

```
Phase 1 — P0 data pipeline fixes (blocking xenon)
  1.1  Fix DrugBank XML parser nesting depth
  1.2  Fix INCREMENTAL_BY_UNIQUE_KEY idempotency
  1.3  Add molecule_aliases to adverse_events matching
  1.4  Create mol_silver.side_effects model
  1.5  Rebuild + deploy staging + run SQLMesh + verify

Phase 2 — P1 verification (requires Phase 1 in prod)
  2.1  Trigger Durvalumab assessment, measure failure rate
  2.2  Record per-section confidence baselines
  2.3  Confirm molecule_targets builds

Phase 3 — Platform files (low risk, no downtime)
  3.1  Update .dk-standards.yaml to full schema
  3.2  Run dk adopt to generate .dk-os/config.yaml
  3.3  Create CODEOWNERS, renovate.json
  3.4  Add /ready endpoint to FastAPI
  3.5  Create monitoring dashboards + alerts in template format
  3.6  Create _dk-alchemy-pr/README.md
  3.7  Add shared standards workflow (if available)
  3.8  Archive specs/ and status docs to docs/archive/

Phase 4 — K8s restructure (high risk, requires coordination)
  4.1  Create per-service k8s/apps/ directory structure
  4.2  Move and split manifests from k8s/base/
  4.3  Add security contexts to all deployments
  4.4  Add dk-alchemy component references in overlays
  4.5  Update .gitops/ Applications to per-service pattern
  4.6  Test all overlays with kubectl kustomize
  4.7  Deploy atomically: single commit with k8s/ + .gitops/ changes
  4.8  Verify ArgoCD sync for staging
  4.9  Verify ArgoCD sync for prod

Phase 5 — Doppler rename (requires maintenance window)
  5.1  Create dk-data-applications project in Doppler
  5.2  Copy all secrets (dev, stg, prd configs)
  5.3  Update doppler.yaml, Makefile references
  5.4  Update dk-alchemy DopplerSecret and token names
  5.5  Verify staging secrets sync
  5.6  Verify prod secrets sync
  5.7  Delete old dk-data-fe project
```

### Dependencies

```
Phase 1 ──> Phase 2 (need fixes deployed to verify)
Phase 3 ──> (independent, can run in parallel with Phase 1)
Phase 4 ──> Phase 5 (Doppler rename should happen after k8s restructure stabilizes)
Phase 3.1 ──> Phase 3.2 (dk adopt reads .dk-standards.yaml)
Phase 4.2 ──> Phase 4.3 (add security contexts during restructure)
```
