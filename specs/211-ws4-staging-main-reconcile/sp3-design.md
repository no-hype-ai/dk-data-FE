# SP3 — Data created once (design + implementation)

**Date:** 2026-05-19 · **Status:** implemented (PR to `main`) · Feature 211 / US3 / FR-011/FR-012/SC-005

## Discovered topology (decisive)

`docs/PLATFORM_GUIDE.md:490` — environments use **separate Postgres
instances**: staging `postgresql.infra-staging.svc.cluster.local`, prod
`postgresql.infra.svc.cluster.local`, each with its own `dk_data`. They do
**not** share the warehouse. So today every external source is fetched twice
(once per env) → cost + cross-env drift (the FR-011 problem).

## Strategy

The repo already has the "create once, share" mechanism: **feature-005
prestaged hydration** (`deploy/jobs/prestaged-hydrate.yaml`, `prestaged.py`;
CLAUDE.md "two ways data lands → Pre-staged dumps"). Prod fetches/produces
`pg_dump` artifacts once; staging restores them. SP3 therefore makes staging
stop external re-fetching and rely on prestaged hydration:

**Suspend ONLY the external fetchers in the staging overlay** (CronJob name
`^fetch-.*`). Prod overlay untouched → prod still fetches exactly once.

## FR-012 enumeration (verified against `kubectl kustomize` render)

- Staging render: 139 CronJobs. **109 suspended — every one `fetch-*`**; zero
  non-fetch suspended; zero `fetch-*` left running. Prod render: **0 suspended.**
- Kept running in staging (operate on prestaged raw data, not external
  fetchers): all `*-transform-*`/`*-gold-*` SQLMesh transforms, `agent-*`,
  `backfill-orchestrator`, `build-model-lineage`, `catalog-refresh`,
  `refresh-api-views`, `*-snapshot`, `cms-gold-refresh`, `platform-init`,
  `tray-*`, and the prestaged-hydrate Job/Cron.

## Implementation

Single kustomize patch appended to `k8s/overlays/staging/kustomization.yaml`
(strategic merge `spec.suspend: true`, `target: {kind: CronJob, name:
"^fetch-.*"}`). Staging-overlay only; prod and base unaffected. `kubectl
kustomize` base/staging/prod all valid.

## Operational precondition (MUST surface to operator)

Staging's prestaged-hydration pipeline must be provisioned (`PRESTAGED_ROOT` +
access to the prod-produced artifact store) **before/with** this change, or
staging's `dk_data` raw layer goes stale (degraded *staging only* — prod
unaffected; fully reversible). This is the FR-012 "environment-specific data
need" explicitly enumerated. If prestaged hydration is not yet wired for
staging, hold the rollout (revert the patch) until it is.

## Rollback

Delete the SP3 patch block from the staging kustomization (or set
`suspend: false`). Instant, staging-only, no prod impact, no data loss
(suspending a CronJob does not delete data; un-suspending resumes fetching).

## SC-005

Each external source fetched **at most once per cycle across environments**
(prod once; staging zero) → 100 % elimination of duplicate external fetches.
