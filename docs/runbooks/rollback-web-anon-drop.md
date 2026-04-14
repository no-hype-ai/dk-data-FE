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

## How feature 003 affects this runbook

Feature 003 (metering-jwt-mint, issue #283) is **independent of this rollback**.
Migration 228 (`228_jwt_mint_schema_grants.sql`) grants `api_user` USAGE + SELECT
on 13 schemas and EXECUTE on 10 resolve functions. It does not touch `web_anon`,
`authenticator`, or the `api` schema. The two migrations are independent by
design — verified by the CI test
`tests/test_218_drop_web_anon.py::TestIndependentOrdering`.

**Scenario A — Roll back migration 218 only (keep feature 003 image)**

Consumers routed through the metering proxy will continue to work because the
proxy mints a JWT with `role=api_user` and `api_user` has the grants from
migration 228. `web_anon` is recreated with minimum grants (health + data catalog
only), but authenticated traffic never touches `web_anon`. This is the normal
rollback path — use the procedure above.

**Scenario B — Roll back BOTH migration 218 AND the feature 003 image**

If you also roll back the metering proxy image to a pre-003 tag (before JWT
minting was added), the proxy will no longer mint JWTs. Requests will reach
PostgREST as `web_anon`. Consumers will fall back to the minimum grants restored
by this rollback — `api.health` and `api.data_catalog` only. Broader silver/gold
access will not be available. Follow up with a forward-fix to provision API keys
and re-deploy feature 003.

**About migration 228 during rollback**

Do NOT undo migration 228 as part of this rollback. Migration 228's `api_user`
grants are additive and harmless in every rollback scenario. Removing them would
break any service or tool that accesses `api_user`-scoped resources, without any
benefit to the `web_anon` rollback objective.

---

## Related

- `src/dk_data/sql/migrations/218_drop_web_anon.sql` — the migration being rolled back
- `src/dk_data/sql/migrations/218_drop_web_anon_rollback.sql` — the rollback SQL
- `src/dk_data/sql/migrations/228_jwt_mint_schema_grants.sql` — feature 003 grant migration (independent; do not roll back)
- Feature 002 spec `.dk/specs/002-external-integration-foundation/spec.md` US-2
- Feature 002 decisions `memory/decisions.md` F-D014 (minimum-only policy)
- Feature 003 spec `.dk/specs/003-metering-jwt-mint/spec.md`
- Success criterion SC-020 (rollback ≤ 5 min)
