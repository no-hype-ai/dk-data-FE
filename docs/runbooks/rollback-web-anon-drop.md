# Runbook: Rollback migration 218 (drop web_anon)

**Target rollback time: ≤ 5 minutes** (SC-020)
**Feature**: 002-external-integration-foundation, US-2
**Last verified**: 2026-04-13

## When to use this runbook

Use this runbook when migration `218_drop_web_anon.sql` has landed in
production and something has broken that cannot be forward-fixed within
a ~15 minute window. Symptoms:

- Multiple consuming apps returning 401 on every dk-data request AND
  API key provisioning for the affected consumers is not yet complete
- k8s liveness/readiness probes failing on PostgREST (unexpected —
  probes are TCP-only per deployment.yaml, shouldn't be affected, but
  check first)
- A cluster-internal service that was silently reading `hcs_silver` or
  `hcs_gold` via `web_anon` (which is exactly what the T001d consumer
  audit was supposed to catch, but a surprise is still possible)

## When NOT to use this runbook

- **A single consumer failing** — forward-fix instead: provision that
  consumer's API key in `k8s/apps/metering-proxy/base/configmap.yaml`
  and re-deploy. Don't roll the whole platform back for one consumer.
- **A non-urgent migration/consumer mismatch** — forward-fix in the
  next business hour.
- **A bug in the adapter package or the metering proxy** — those have
  their own rollback paths.

## Rollback policy (F-D014)

**The rollback restores ONLY the minimum grants**, not the full legacy
grant set. Specifically:

- Recreates the `web_anon` role (NOLOGIN)
- Grants `web_anon` to `authenticator` so PostgREST can impersonate it
- `GRANT USAGE ON SCHEMA api TO web_anon`
- `GRANT SELECT ON api.health TO web_anon`
- `GRANT SELECT ON api.data_catalog TO web_anon`
- **Nothing else.**

If the minimum rollback does not unblock whatever is failing, the
correct next step is still **forward-fix** (provision the missing
consumer credential). Do NOT broaden the grants here — doing so
re-opens every hole migration 218 closed.

## Procedure

### Prerequisites (should already be in place)

- psql access to the production database
- kubectl context set to the production cluster
- Ability to edit `k8s/apps/postgrest/base/configmap.yaml` (or the
  corresponding deployed configmap)

### Step 1 — Run the SQL rollback (≤ 1 min)

```bash
psql -h $PROD_POSTGRES_HOST \
     -p $PROD_POSTGRES_PORT \
     -U postgres \
     -d dk_data \
     -f src/dk_data/sql/migrations/218_drop_web_anon_rollback.sql
```

Expected output:

```
NOTICE:  recreated web_anon role (NOLOGIN)
NOTICE:  granted web_anon to authenticator
NOTICE:  granted SELECT on api.health to web_anon
NOTICE:  granted SELECT on api.data_catalog to web_anon
NOTICE:  218_drop_web_anon_rollback complete: MINIMUM grants restored
```

If any NOTICE says "could not" — investigate but don't block; the
essential restoration is the `CREATE ROLE` + `GRANT web_anon TO
authenticator` pair.

### Step 2 — Restore PGRST_DB_ANON_ROLE in the configmap (≤ 1 min)

Edit the PostgREST configmap to re-enable the anonymous role:

```bash
kubectl -n dk-data-prod edit configmap postgrest-config
```

Restore this line (it was removed by the migration 218 cutover):

```yaml
data:
  PGRST_DB_ANON_ROLE: "web_anon"
```

Save and exit.

### Step 3 — Roll PostgREST to pick up the config (≤ 2 min)

```bash
kubectl -n dk-data-prod rollout restart deployment/postgrest
kubectl -n dk-data-prod rollout status deployment/postgrest
```

The `rollout status` command returns when the new pods are ready.

### Step 4 — Verify (≤ 1 min)

```bash
# Health endpoint should respond without auth
curl https://data.behaviorlabs.ai/health
# Expected: 200 OK with JSON body

# Data catalog should respond without auth
curl https://data.behaviorlabs.ai/data_catalog
# Expected: 200 OK

# Actual data endpoint should STILL require auth (minimum rollback)
curl https://data.behaviorlabs.ai/molecules
# Expected: 401 Unauthorized (the broader grants were NOT restored)
```

If all four checks pass, the rollback is complete.

### Step 5 — Open a forward-fix incident

A rollback is not the fix — it's a time-buying measure. Open an
incident to identify which consumer broke, provision its API key in
the metering proxy, and re-apply migration 218 once the consumer is
on the adapter path.

## Last-resort broader restoration

**Do not do this without incident commander approval.** The grants
below re-open the holes migration 218 was supposed to close. Use only
if:

- An internal cluster service was reading `hcs_silver` via `web_anon`
- Forward-fixing (provisioning an API key for that service) would
  take longer than the outage window allows
- Incident commander has explicitly approved broader restoration

```sql
-- DANGEROUS: re-opens the silver/gold exposure
GRANT USAGE ON SCHEMA hcs_silver TO web_anon;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_silver TO web_anon;
```

Document the decision in the incident notes and schedule the narrower
forward-fix for follow-up within 24 hours. Do NOT leave these grants
in place longer than the incident window.

## Related

- `src/dk_data/sql/migrations/218_drop_web_anon.sql` — the migration being rolled back
- `src/dk_data/sql/migrations/218_drop_web_anon_rollback.sql` — the rollback SQL
- Feature 002 spec `.dk/specs/002-external-integration-foundation/spec.md` US-2
- Feature 002 decisions `memory/decisions.md` F-D014 (minimum-only policy)
- Success criterion SC-020 (rollback ≤ 5 min)
