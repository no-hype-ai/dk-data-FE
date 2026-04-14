# Runbook: Debugging "metering proxy returns 401"

**Feature**: 002-external-integration-foundation (US-3), 003-metering-jwt-mint
**Last verified**: 2026-04-14

After the US-2 lockdown AND feature 003 (JWT minting) landed, every dk-data request must present a valid raw API key in `Authorization: Bearer <key>` to the metering proxy at `https://data.behaviorlabs.ai`. A 401 response means one of: missing key, unknown raw key, the proxy's startup self-test failed, or the JWT signing secret differs between the proxy sidecar and the PostgREST container. This runbook walks through diagnosing each.

## Symptoms

- A consumer that was working yesterday now gets `401 Unauthorized` on every request
- A new consumer's first request fails with `401`
- The admin app shows "authentication failed" cards across all dk-data widgets
- A research agent in behavior-labs-ai logs `DkDataAuthError` from the dk-data-client

## Decision tree

```
401 from data.behaviorlabs.ai
  │
  ├─ Missing or malformed Authorization header?
  │   │
  │   ├─ YES → consumer is not setting DK_DATA_API_KEY env var
  │   │        → fix: set DK_DATA_API_KEY in the consumer's deployment
  │   │               and restart it to pick up the env var
  │   │
  │   └─ NO  → header is present and starts with "Bearer ", continue
  │
  ├─ Raw key not in consumers.yaml (proxy's consumer registry)?
  │   │
  │   ├─ YES → key is not provisioned
  │   │        → fix: add the key to the right consumer's api_keys[] list
  │   │              in k8s/apps/metering-proxy/base/configmap.yaml,
  │   │              commit + push, wait for ArgoCD sync,
  │   │              then POST /-/reload on the metering proxy
  │   │
  │   └─ NO  → key matched a consumer, continue
  │
  ├─ Metering proxy readiness probe is failing?
  │   │
  │   ├─ YES → startup self-test failed — JWT_SECRET mismatch between
  │   │        metering proxy and PostgREST. See "JWT secret mismatch".
  │   │
  │   └─ NO  → proxy is healthy, continue
  │
  ├─ Metering proxy returned 500 (not 401)?
  │   │
  │   ├─ YES → check metering_proxy_jwt_mint_errors_total metric.
  │   │        Common causes:
  │   │          - unknown_tier: the consumer's tier value isn't in
  │   │            TIER_TO_ROLE (src/dk_data/metering_proxy/jwt_mint.py)
  │   │          - not_loaded: the pod started without calling
  │   │            load_secret_at_startup() — broken deploy, restart it
  │   │          - secret_missing / secret_too_short: JWT_SECRET env
  │   │            var missing from the sidecar container
  │   │
  │   └─ NO  → proxy forwarded successfully, continue
  │
  └─ PostgREST returned 401 (after receiving the minted JWT)?
       │
       └─ YES → JWT signature verification failed. See the section below.
```

## Step 1 — Confirm the request is reaching the proxy

```bash
kubectl -n dk-data-prod logs -l app.kubernetes.io/component=metering-proxy --tail=50 | grep -i "401\|unauthorized"
```

If you see the request in the logs, the proxy got it. If not, the request may be failing at the ingress (Traefik) layer before reaching the proxy — check ingress logs:

```bash
kubectl -n traefik logs -l app=traefik --tail=50 | grep "data.behaviorlabs.ai"
```

## Step 2 — Check the consumer's API key

The consumer should be setting `DK_DATA_API_KEY` in its deployment env. Verify the value matches what's in `consumers.yaml`:

```bash
# What's in the consumer's deployment
kubectl -n behavior-labs-prod get deployment admin -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="DK_DATA_API_KEY")]}'

# What's in dk-data's metering-proxy configmap
kubectl -n dk-data-prod get configmap dk-data-consumers -o yaml | grep -A2 "behavior-labs-ai:"
```

If the key is missing from `consumers.yaml.api_keys[]` for the right consumer:

```bash
kubectl -n dk-data-prod edit configmap dk-data-consumers
# Add the key to the appropriate consumer's api_keys: [...] list
# Save and exit. The metering proxy watches the configmap and reloads
# (no pod restart needed); verify with a fresh request.
```

## Step 3 — JWT secret mismatch

If the API key validates and the JWT mints, but PostgREST/FastAPI rejects the JWT with "signature verification failed", the metering proxy and the receiver are using different `JWT_SECRET` values.

Check:

```bash
# Doppler value
doppler secrets get JWT_SECRET --config dk-data-prod --plain | head -c 16

# k8s secret value (should match)
kubectl -n dk-data-prod get secret dk-data-secrets -o jsonpath='{.data.JWT_SECRET}' | base64 -d | head -c 16
```

If they differ, run the JWT secret rotation runbook (`docs/runbooks/rotate-jwt-secret.md`) to bring all three layers into sync.

## Step 4 — Pre-existing JWT_SECRET_KEY bug (B002)

Before feature 002 fixed it, `JWTService` only read `JWT_SECRET_KEY` and the k8s deployment never set that env var, so FastAPI generated a random per-pod signing key. Symptom: the FIRST request to FastAPI works (uses the random key), every subsequent pod restart breaks all in-flight JWTs.

The fix in feature 002 makes `JWTService` fall back to `JWT_SECRET` (the shared k8s secret name). Verify the deployment is running the post-fix code:

```bash
kubectl -n dk-data-prod exec deployment/postgrest -c dk-data-api -- \
  python -c "from dk_data.services.auth.jwt_service import JWTService; \
             import os; \
             print('JWT_SECRET_KEY:', bool(os.getenv('JWT_SECRET_KEY'))); \
             print('JWT_SECRET:', bool(os.getenv('JWT_SECRET'))); \
             print('service secret prefix:', JWTService().secret_key[:8])"
```

The service should pick up the secret from `JWT_SECRET` if `JWT_SECRET_KEY` is unset. If it generates a random key (warning in the logs), the deployment is stale.

## Common false positives

- **A 401 right after deploying a new metering proxy version**: the proxy may not have loaded `consumers.yaml` yet. Wait 30s, retry.
- **A 401 from a new consumer**: their API key is provisioned but they haven't restarted their pods to pick up the env var. Restart their deployment.
- **A 401 only on POST routes**: not a metering-proxy issue — check if the consumer is sending a CSRF token or origin header that the receiver rejects.

## Related

- `docs/runbooks/rotate-jwt-secret.md`
- `docs/runbooks/rollback-web-anon-drop.md`
- `k8s/apps/metering-proxy/base/configmap.yaml`
- F-D014, B002 in `.dk/specs/002-external-integration-foundation/memory/`
