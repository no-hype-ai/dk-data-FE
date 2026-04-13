# Rebase Log — feature/002-external-integration-foundation

**Feature**: 002-external-integration-foundation (T159, D9)
**Policy**: Rebase onto `main` at least once per week while the
feature branch is active. Conflict hotspots identified up front so
owners can coordinate.

## Conflict hotspots

Files that feature 002 and other active work both touch:

| File | Owner we coordinate with | Why |
|---|---|---|
| `src/dk_data/api/routes/data_platform.py` | anyone adding a /data-platform/* route | router-level `require_auth` + new resolve wrappers |
| `k8s/apps/metering-proxy/base/configmap.yaml` | anyone provisioning a new consumer | consumers.yaml edits |
| `k8s/apps/postgrest/base/deployment.yaml` | observability / probes / image bumps | stale-comment fix + JWT_SECRET wiring |
| `src/dk_data/observability/metrics.py` | any feature adding new metrics | 37-entry dead-metric ratchet |
| `grafana/dashboards/*.json` | anyone editing dashboards | 5 dashboards + 1 new (adapter-telemetry) |
| `src/dk_data/sql/migrations/` | any feature adding a migration | number collision — see T155 |

## Rebase rhythm

- **Mondays 10 am PT**: run `git fetch origin main && git rebase origin/main`
- Log the rebase below with timestamp + conflict count

## Rebase history

| Date | Base SHA | Conflicts | Resolved by | Notes |
|---|---|---|---|---|
| 2026-04-13 | (feature branch created) | 0 | pschloz | initial branch |

Append a new row every time a rebase happens.

## Resolution playbook

### `data_platform.py` conflict

- Usually a new route added on main that clashes with our new resolve
  wrappers. Keep BOTH changes — preserve the router-level
  `dependencies=[Depends(require_auth)]` from our side and the new
  route definition from main.

### `configmap.yaml` conflict

- New consumer provisioning on main + our T020/T021 edits to the
  `internal` and `behavior-labs-ai` entries. Merge by hand — each
  consumer block is independent, so the conflict is usually just a
  reordering.

### `metrics.py` conflict

- A new metric landed on main while we were touching the file for T108
  / T109 / T110. Keep the new metric AND make sure it goes into the
  EMISSION_ALLOWLIST ratchet if it's not wired up yet.

### Dashboard JSON conflict

- Dashboards are serialized per T162 — one dev touches at a time.
  If both sides touched the same dashboard, the most-recent wins
  because Grafana re-serializes panel order on every save anyway.

### Migration number collision

- See `docs/reviews/migration-renumber-check.md`. This is the
  highest-risk conflict because it requires renaming files + updating
  every reference + re-running the test suite.

## Related

- `docs/reviews/migration-renumber-check.md` — T155
- `docs/reviews/migrations-215-220.md` — T067a
