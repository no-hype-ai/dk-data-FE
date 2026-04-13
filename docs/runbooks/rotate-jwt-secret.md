# Runbook: Rotate the dk-data JWT signing secret

**Target rotation time: ≤ 5 minutes** (SC-019)
**Cadence: every 90 days, OR immediately on any suspected leak**
**Feature**: 002-external-integration-foundation, US-3
**Last verified**: 2026-04-13

## What this rotates

The shared HS256 signing secret used by:

- **PostgREST** — env var `PGRST_JWT_SECRET` (k8s deployment.yaml)
- **FastAPI** `/data-platform/*` — env var `JWT_SECRET_KEY` (with fallback to `JWT_SECRET`, see B002)
- **Metering proxy** — mints JWTs from validated API keys using the same secret

All three layers must use the same secret or JWTs minted by one will fail signature verification on another.

The secret lives in the Doppler config `dk-data-prod` as `JWT_SECRET`, surfaced into k8s via the `dk-data-secrets` Secret object via DopplerSecret.

## When to rotate

- **Scheduled**: every 90 days (calendar reminder)
- **Suspected leak**: immediately, no questions asked
- **Personnel changes**: any time someone with secret access leaves the org

## Procedure

### Step 1 — Generate a new secret

```bash
NEW_SECRET=$(openssl rand -base64 48 | tr -d '=+/' | cut -c1-64)
echo "$NEW_SECRET" | wc -c   # should print >= 32
```

The dk-data JWT uses HS256 which requires ≥ 256 bits of entropy. 64 base64 characters give you ~48 bytes = 384 bits, comfortably above the minimum.

### Step 2 — Update Doppler

```bash
doppler secrets set JWT_SECRET="$NEW_SECRET" --config dk-data-prod
doppler secrets set PGRST_JWT_SECRET="$NEW_SECRET" --config dk-data-prod
```

(Set both names — the k8s deployment uses `JWT_SECRET` and the standalone postgrest config uses `PGRST_JWT_SECRET`. Keeping them in sync is the easiest path.)

### Step 3 — Roll the metering proxy first

The metering proxy mints new JWTs. Roll it before the consumers of those JWTs (PostgREST, FastAPI) so that any JWT minted during the cutover is signed with the new secret, not the old one.

```bash
kubectl -n dk-data-prod rollout restart deployment/postgrest
# (the metering proxy is a sidecar in the postgrest deployment per the
# strategic merge patch — rolling postgrest also rolls the proxy)
kubectl -n dk-data-prod rollout status deployment/postgrest
```

Wait for `rollout status` to return success.

### Step 4 — Verify

```bash
# Mint a fresh JWT from the new secret (via metering proxy)
curl -X POST -H "Authorization: Bearer $TEST_API_KEY" \
  https://data.behaviorlabs.ai/health
# Expected: 200 OK from PostgREST (which validated the JWT with the new secret)

# Existing JWTs minted with the old secret should fail
curl -H "Authorization: Bearer $OLD_JWT_FROM_BEFORE_ROTATION" \
  https://data.behaviorlabs.ai/molecules
# Expected: 401 (signature verification failed)
```

### Step 5 — Notify consumers

Consumers don't usually need to do anything — they hold an API key, not a JWT. The metering proxy mints a fresh JWT for each request, signed with the new secret. Consumers see at most one transient 401 retry if they had an in-flight JWT during the cutover.

If a consumer has the old `JWT_SECRET` cached anywhere (shouldn't happen — only the metering proxy and dk-data services should hold the signing secret), they need to refresh their config.

## Rollback

If something goes wrong:

```bash
# Restore the old secret in Doppler
doppler secrets set JWT_SECRET="$OLD_SECRET" --config dk-data-prod
doppler secrets set PGRST_JWT_SECRET="$OLD_SECRET" --config dk-data-prod

# Roll postgrest again to pick up the rolled-back secret
kubectl -n dk-data-prod rollout restart deployment/postgrest
kubectl -n dk-data-prod rollout status deployment/postgrest
```

Total rollback time: ≤ 3 minutes. Don't keep the old secret accessible for longer than the rollback window — once the new secret is verified working, scrub the old value from any local notes.

## Related

- F-D018 (memory commit discipline)
- B002 (JWT_SECRET_KEY env var fallback)
- `src/dk_data/services/auth/jwt_service.py` — JWTService with `secret_key` resolution
- `k8s/apps/postgrest/base/deployment.yaml` — PGRST_JWT_SECRET env wiring
- SC-019 — rotation completes within 5 minutes
