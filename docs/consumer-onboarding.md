# Consumer Onboarding — dk-data

**Feature**: 002-external-integration-foundation, 003-metering-jwt-mint
**Last verified**: 2026-04-14

This guide is for anyone onboarding a new consumer application to dk-data (`data.behaviorlabs.ai`). It covers provisioning an API key, choosing the right tier, integrating the client package, and verifying end-to-end.

If you just want to debug an existing consumer's auth error, read `docs/runbooks/metering-proxy-401-debug.md` instead.

## Prerequisites

Before you start, the consumer must have:

- A stable identifier (e.g., `behavior-labs-ai`, `ground-truth-charlie`, `trials-predictor`)
- A human owner (squad or engineer) who is on-call for auth/rate-limit failures
- A clear understanding of which schemas they need. "Everything" is not an answer — use the minimum set that satisfies the read surface they're building.

## Step 1 — Pick a tier

Every consumer gets mapped to one of three tiers. The tier determines the rate-limit bucket and (in the current v0.1 implementation) maps to the same database role in the minted JWT.

| Tier | Role in JWT | Use case |
|---|---|---|
| `unlimited` | `api_user` | Internal platform services with no rate-limit budget |
| `high` | `api_user` | BehaviorLabs, Carbon-5 — heavy machine-to-machine consumers |
| `standard` | `api_user` | DK-OS and similar lighter consumers |

In feature 003 (metering-jwt-mint) every tier maps to the **same** database role, `api_user`, which has SELECT on all client-readable silver/gold schemas and EXECUTE on every silver-hub resolve function. A second role (`analyst` with write paths) may be added later for specific tiers — it's a one-line change in `src/dk_data/metering_proxy/jwt_mint.py:TIER_TO_ROLE`.

**Default**: `standard`. Only request `high` if the consumer has a measured rpm need above 200, and `unlimited` is reserved for internal platform callers.

## Step 2 — Pick the schema allowlist

The metering proxy reads `k8s/apps/metering-proxy/base/consumers.yaml` and enforces a per-consumer `allowed_schemas` list. A request to any other schema returns 403 before it ever reaches PostgREST.

Minimum viable allowlists by read surface:

| Read surface | Schemas |
|---|---|
| Molecule profile (BehaviorLabs admin) | `mol_silver`, `mol_gold`, `mol_api` |
| Competitive landscape | `mol_gold`, `mol_api` |
| Clinical trials (trials-predictor) | `mol_silver`, `mol_gold`, `ind_silver` |
| Ground truth (ground-truth-charlie) | `mol_silver`, `mol_gold`, `ip_silver` |
| Internal research | `mol_silver`, `hcs_silver`, `ind_silver`, `hcp_silver`, `ip_silver` |

Start narrow. Adding a schema later is a configmap edit + proxy restart. Removing one once consumers depend on it is a migration with a breaking-change window.

## Step 3 — Provision the API key

Edit `k8s/apps/metering-proxy/base/configmap.yaml` (the ConfigMap that holds `consumers.yaml`) to add the consumer. The shape in the real file:

```yaml
consumers:
  my-new-consumer:
    alias: myc
    allowed_schemas:
      - mol_silver
      - mol_gold
    rpm_limit: 500
    tier: high
    api_keys:
      - dk_data_myc_<random-suffix>
```

**Generating the key**:

```bash
# Generate a raw key. The format is dk_data_<alias>_<random>.
# The alias here is the short one from the consumer block above.
ALIAS=myc
SUFFIX=$(openssl rand -hex 16)
RAW_KEY="dk_data_${ALIAS}_${SUFFIX}"
echo "$RAW_KEY"
```

**IMPORTANT — current state of key hygiene (tracked in #283 follow-on):**

The implementation stores the raw key directly in the ConfigMap's `api_keys` list. A bcrypt-hashed design is documented in this project's history but is NOT what the running code does — `ConsumerKeyStore.validate_key()` in `src/dk_data/metering_proxy/auth.py` does a plain dict lookup against raw strings. Until hashing ships (follow-on issue), the operational reality is:

- The raw key lands in git via the ConfigMap
- The same value MUST be deployed to the consumer's own secret store so it can be passed as the bearer token
- Key rotation is a configmap edit + ArgoCD sync + `POST /-/reload` on the metering proxy (no pod restart needed)

Store the raw key in the consumer's own secret store (Doppler, k8s secret) as `DK_DATA_API_KEY`. Commit the configmap, push, and let ArgoCD sync. The metering proxy reloads the configmap without a pod restart when you call its `/-/reload` endpoint.

### What the metering proxy does with the key

After the consumer sends `Authorization: Bearer <raw_key>`, the metering proxy:

1. Does a plain dict lookup against the `api_keys` list in `consumers.yaml` to find the matching consumer
2. Checks the requested path's schema against `allowed_schemas` (403 if not allowed)
3. Checks the rate limiter (429 if over budget)
4. Checks the concurrency guard (503 if over `max_in_flight`)
5. **Strips the raw key from the forwarded headers**
6. **Mints a short-lived (60s TTL) HS256 JWT** with `sub=<consumer.alias>`, `role=api_user`, `iss=metering-proxy`, and injects it as `Authorization: Bearer <jwt>` before forwarding to PostgREST on localhost
7. PostgREST validates the JWT with its shared `PGRST_JWT_SECRET` and switches to the `api_user` database role for the query

The raw API key never reaches PostgREST. The minted JWT never gets logged or persisted. Every request you see in PostgREST logs has a freshly-minted, already-expired JWT.

## Step 4 — Wire up the consumer

### TypeScript

```bash
cd my-consumer-app
pnpm add @datakinetic/dk-data-client
```

```ts
import { DkDataClient } from '@datakinetic/dk-data-client';

const client = new DkDataClient({
  baseUrl: process.env.DK_DATA_BASE_URL ?? 'https://data.behaviorlabs.ai',
  apiKey: process.env.DK_DATA_API_KEY!,
  // Optional — defaults to 'best-effort'
  fallbackMode: 'best-effort',
});

const profile = await client.molecules.getProfile({ id: 'CHEMBL25' });
```

### Python

```bash
pip install dk-data-client
```

```python
import os
from dk_data_client import DkDataClient

client = DkDataClient(
    base_url=os.environ.get("DK_DATA_BASE_URL", "https://data.behaviorlabs.ai"),
    api_key=os.environ["DK_DATA_API_KEY"],
)

profile = client.molecules.get_profile(id="CHEMBL25")
```

### Env vars to set in the consumer deployment

```bash
DK_DATA_API_KEY=<raw key from step 3>
DK_DATA_BASE_URL=https://data.behaviorlabs.ai
```

For k8s-deployed consumers, add the API key as a k8s secret and reference it in the deployment spec's `env:` with `valueFrom.secretKeyRef`. Do not bake the raw key into the image or a configmap.

## Step 5 — Verify end-to-end

Once the consumer pod is running with the env vars set:

```bash
# 1. The client should get a 200 on a healthcheck-style call
kubectl -n <consumer-ns> exec deployment/<consumer> -- \
  curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $DK_DATA_API_KEY" \
  https://data.behaviorlabs.ai/health
# Expected: 200

# 2. The metering proxy should log the request with the consumer id
kubectl -n dk-data-prod logs -l app.kubernetes.io/component=metering-proxy --tail=20 | grep "<consumer-id>"

# 3. A real data call should return a 200 with JSON
kubectl -n <consumer-ns> exec deployment/<consumer> -- \
  curl -s -H "Authorization: Bearer $DK_DATA_API_KEY" \
  "https://data.behaviorlabs.ai/molecules?limit=1"
```

If any of these return 401 or 403, read `docs/runbooks/metering-proxy-401-debug.md`.

## Step 6 — Watch the telemetry

Consumers emit structured telemetry from the client — every call produces an event with `outcome`, `method`, `latency_ms`, and `args_hash`. These land in Loki under `app=adapter-telemetry` and power the Adapter Hydration Heat Map in Grafana.

Things to watch in the first 48 hours after a new consumer goes live:

- **Error rate** — baseline should be ≤ 1%. A sustained > 5% error rate means the allowlist is wrong, the key is bad, or the consumer is retrying on non-retryable errors.
- **Fallthrough rate** — baseline should be ≤ 5%. A sustained > 20% rate means the consumer wants data dk-data doesn't have (see `docs/runbooks/adapter-fallthrough-spike.md`).
- **Rate limiting** — any sustained `429` response means the `rate_limit` in `consumers.yaml` is too low for the actual usage. Bump it or ask the consumer to batch requests.

## Rotating a consumer's key

Keys rotate every 90 days or immediately on a suspected leak.

1. Generate a new raw key (same procedure as Step 3)
2. Add the new key's hash as a second entry under `api_keys:` — do NOT remove the old one yet
3. Commit + let ArgoCD sync — the proxy now accepts both keys
4. Push the new key to the consumer's secret store and roll their deployment
5. Verify the consumer is hitting dk-data with the new key (logs should show the new key's `name`)
6. Remove the old key's hash from `consumers.yaml` in a follow-up commit

This two-step process gives the consumer a graceful cutover without a 401 window.

## dk-data-client v0.1 → v0.2 transition window

When migration 216 lands and `mol_api.competitive_scores` goes live, the PostgREST OpenAPI changes shape. The `@datakinetic/dk-data-client` package regenerates its typed module fingerprints against the updated OpenAPI and ships as v0.2.0 (tracked in T149).

**Expected consumer behavior during the transition window**:

- Consumers still running `v0.1.x` will continue to function against the post-migration dk-data. The client's `serverInfo()` schema fingerprint check emits a **warning** (`serverInfo.schemaMismatch`) but does not throw (T150). This means the `dk_data_client_schema_mismatch_total` Prometheus counter will tick up for every `v0.1.x` consumer until they upgrade.
- Consumers upgrade to `v0.2.0` via their own PR cycle. They need no other change — the new types compile against both the pre-migration and post-migration schema.
- **Target transition window: ≤ 7 days** between migration 216 landing in production and every consumer running `v0.2.0`. Past 7 days, page the consumer's owner.

**Why warn instead of throw**: a strict throw would turn migration 216 into a coordinated hard cutover — every consumer would need to ship `v0.2.0` at the exact moment the migration lands, or their pods would crash on startup. Warning-only gives each consumer squad a window to schedule the upgrade without blocking the migration.

**Monitoring the window**: watch the `dk_data_client_schema_mismatch_total{consumer="..."}` counter in Grafana. When it goes flat (no new warnings for 1 hour), every consumer has upgraded and you can mark T151 complete.

If a consumer is still on `v0.1.x` after 7 days, the decision is:

| Situation | Action |
|---|---|
| Consumer is actively maintained | Page the owner, ask them to ship v0.2.0 |
| Consumer is abandoned | Retire it — see "Decommissioning a consumer" below |
| v0.2.0 broke something for the consumer | File a bug, keep them on v0.1.x, roll a v0.2.1 |

## Decommissioning a consumer

When a consumer is retired:

1. Remove the consumer entry from `consumers.yaml` entirely
2. Commit + let ArgoCD sync
3. Verify the consumer's key returns 401 on the next request
4. Delete the raw key from the consumer's secret store

Keep the `consumers.yaml` history — git blame is the audit trail for who had access when.

## Related

- `docs/runbooks/metering-proxy-401-debug.md` — debugging auth failures
- `docs/runbooks/rotate-jwt-secret.md` — rotating the shared JWT signing secret (separate from consumer keys)
- `docs/runbooks/adapter-fallthrough-spike.md` — responding to fallthrough spikes
- `k8s/apps/metering-proxy/base/consumers.yaml` — canonical consumer registry
- `packages/dk-data-client/` — client package source
