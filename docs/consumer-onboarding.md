# Consumer Onboarding — dk-data

**Feature**: 002-external-integration-foundation
**Last verified**: 2026-04-13

This guide is for anyone onboarding a new consumer application to dk-data (`data.behaviorlabs.ai`). It covers provisioning an API key, choosing the right tier, integrating the client package, and verifying end-to-end.

If you just want to debug an existing consumer's auth error, read `docs/runbooks/metering-proxy-401-debug.md` instead.

## Prerequisites

Before you start, the consumer must have:

- A stable identifier (e.g., `behavior-labs-ai`, `ground-truth-charlie`, `trials-predictor`)
- A human owner (squad or engineer) who is on-call for auth/rate-limit failures
- A clear understanding of which schemas they need. "Everything" is not an answer — use the minimum set that satisfies the read surface they're building.

## Step 1 — Pick a tier

Every consumer gets mapped to one of two tiers. The tier determines the JWT role the metering proxy mints.

| Tier | Role in JWT | Use case |
|---|---|---|
| `analyst` | `analyst` | Human-driven research tooling: admin app, notebooks, internal dashboards. Broad schema access, lower rate limits. |
| `api_user` | `api_user` | Machine-to-machine: cron jobs, scoring pipelines, agent backends. Narrower schema allowlist per consumer, higher rate limits. |

**Default**: `api_user`. Only pick `analyst` if the consumer is a human-facing tool — machine consumers get finer-grained schema allowlists and their 429s don't hurt a user waiting on a page.

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

Edit `k8s/apps/metering-proxy/base/consumers.yaml` to add the consumer. There's a reference entry at the top of the file — copy its shape.

```yaml
consumers:
  - id: my-new-consumer
    tier: api_user
    owner: my-squad
    allowed_schemas:
      - mol_silver
      - mol_gold
    rate_limit:
      requests_per_minute: 600
      burst: 50
    api_keys:
      - name: primary
        hash: <bcrypt hash of the raw key>
```

**Generating the key**:

```bash
# Generate a raw key (copy this — you'll only see it once)
RAW_KEY=$(openssl rand -base64 48 | tr -d '=+/' | cut -c1-64)
echo "$RAW_KEY"

# Hash it for consumers.yaml
python3 -c "import bcrypt; print(bcrypt.hashpw(b'$RAW_KEY', bcrypt.gensalt()).decode())"
```

Store the raw key in the consumer's own secret store (Doppler, k8s secret, etc.). **The raw key never goes into git.**

Commit `consumers.yaml`, push, and let ArgoCD sync. The metering proxy reloads the configmap without a pod restart (verified via the `/reload` endpoint in logs).

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
