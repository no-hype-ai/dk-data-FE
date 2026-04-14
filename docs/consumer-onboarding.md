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

The metering proxy reads its consumer registry from the `dk-data-consumers` ConfigMap, defined in `k8s/apps/metering-proxy/base/configmap.yaml` (the `consumers.yaml` key holds the YAML). It enforces a per-consumer `allowed_schemas` list — a request to any other schema returns 403 before it ever reaches PostgREST.

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

The client library has its own READMEs. Follow whichever matches your language — they are the canonical source of truth for constructor arguments, method signatures, and error types. This guide does not duplicate code examples because they drift; the READMEs are tested against the published client.

- **Python**: [`packages/dk-data-client/python/README.md`](../packages/dk-data-client/python/README.md)
  - Install: `pip install dk-data-client`
  - Import: `from dk_data_client import DkDataClient`
  - Constructor: `DkDataClient(metering_proxy_url=..., api_key=...)` (async). Sync facade at `dk_data_client.sync.DkDataClient`.

- **TypeScript**: [`packages/dk-data-client/typescript/README.md`](../packages/dk-data-client/typescript/README.md)
  - Install: `pnpm add @datakinetic/dk-data-client`
  - Import: `import { DkDataClient } from "@datakinetic/dk-data-client";`
  - Constructor: `new DkDataClient({ meteringProxyUrl: ..., apiKey: ... })`

### Env vars to set in the consumer deployment

The client constructors both take `metering_proxy_url`/`meteringProxyUrl` and `api_key`/`apiKey` directly. Conventionally consumers pass them from env vars:

```bash
DK_DATA_API_KEY=<raw key from step 3>
DK_DATA_BASE_URL=https://data.behaviorlabs.ai
```

For in-cluster consumers, skip the ingress and use the ClusterIP directly:

```bash
DK_DATA_BASE_URL=http://dk-data-metering-proxy.dk-data-prod.svc.cluster.local:3001
```

Load `DK_DATA_API_KEY` from a k8s secret (`valueFrom.secretKeyRef`), never from the image or a ConfigMap. The raw key lives in git via the `dk-data-consumers` ConfigMap (see step 3's note on key hygiene), which is a separate exposure — the consumer's own secret store still matters because that's where the key gets passed to the app at runtime.

## Step 5 — Verify end-to-end

Once the consumer pod is running and the env vars are set, run these three checks from inside the consumer's own pod (so DNS, network policy, and mounted secrets all get exercised the same way they will at runtime):

```bash
# 1. /health bypasses auth — this proves connectivity only
kubectl -n <consumer-ns> exec deployment/<consumer> -- \
  curl -s -o /dev/null -w "%{http_code}\n" \
  https://data.behaviorlabs.ai/health
# Expected: 200

# 2. An authenticated call against a schema in the consumer's allowlist.
#    PostgREST exposes each schema under its own URL prefix. mol_api is a
#    safe default because it holds the curated client-facing views; pick
#    whichever schema the consumer actually reads.
kubectl -n <consumer-ns> exec deployment/<consumer> -- \
  curl -sS -o /tmp/resp.json -w "%{http_code}\n" \
  -H "Authorization: Bearer $DK_DATA_API_KEY" \
  "https://data.behaviorlabs.ai/mol_api/molecules?limit=1"
# Expected: 200, one JSON row

# 3. Confirm the metering proxy saw the request tagged with the consumer's alias.
#    The alias comes from consumers.yaml (e.g. "blai" for behavior-labs-ai).
kubectl -n dk-data-prod logs -l app.kubernetes.io/component=metering-proxy \
  -c metering-proxy --tail=30 \
  | grep '"consumer": "<alias>"'
```

Failure triage:

- **401** — the key is missing, unknown, or the metering proxy's startup self-test failed. Run the decision tree in [`docs/runbooks/metering-proxy-401-debug.md`](runbooks/metering-proxy-401-debug.md).
- **403** — the key is valid but the requested schema is not in the consumer's `allowed_schemas` list. Extend the list in the ConfigMap and redeploy.
- **429** — rate-limited. Bump `rpm_limit` in the ConfigMap or have the consumer back off.
- **503** — per-consumer concurrency guard hit its ceiling. Bump `max_in_flight` or reduce in-flight requests from the consumer.

## Step 6 — Watch the telemetry

Consumers emit structured telemetry from the client — every call produces an event with `outcome`, `method`, `latency_ms`, and `args_hash`. These land in Loki under `app=adapter-telemetry` and power the Adapter Hydration Heat Map in Grafana.

Things to watch in the first 48 hours after a new consumer goes live:

- **Error rate** — baseline should be ≤ 1%. A sustained > 5% error rate means the allowlist is wrong, the key is bad, or the consumer is retrying on non-retryable errors.
- **Fallthrough rate** — baseline should be ≤ 5%. A sustained > 20% rate means the consumer wants data dk-data doesn't have (see `docs/runbooks/adapter-fallthrough-spike.md`).
- **Rate limiting** — any sustained `429` response means the `rpm_limit` field on the consumer entry is too low for the actual usage. Bump it in `k8s/apps/metering-proxy/base/configmap.yaml` or ask the consumer to batch requests.
- **Concurrency shedding** — any `503` response means the consumer hit its `max_in_flight` budget. If this happens under real steady load (not a traffic spike), the consumer is running too much work concurrently for its slot count; raise `max_in_flight` on its ConfigMap entry, or check whether the consumer is failing to release connections.

## Rotating a consumer's key

Keys rotate every 90 days or immediately on a suspected leak. Because `api_keys` is a list (not a single value), both the old and new keys can be live simultaneously for the duration of the cutover — that's how you avoid a 401 window.

1. Generate a new raw key (same procedure as Step 3).
2. Add the new key as a **second entry** under the consumer's `api_keys:` list in `k8s/apps/metering-proxy/base/configmap.yaml` — do NOT remove the old one yet. The list now has both.
3. Commit, push, let ArgoCD sync, then `POST /-/reload` on the metering proxy (or let a rolling restart pick up the new ConfigMap). The proxy now accepts either key.
4. Update the consumer's secret store (Doppler, k8s secret) with the new key and roll the consumer's deployment. The consumer starts sending the new key on the next request.
5. Verify the metering proxy logs show requests arriving with the new key's alias still matching the same `consumer` — since both keys map to the same consumer entry, the alias is unchanged, but you can grep for the first 20 chars of the new key prefix in the audit log to confirm the new one is being used.
6. Once you're confident the consumer is on the new key (wait at least one full request cycle), remove the OLD key from the `api_keys:` list in a follow-up commit, sync, reload.

There are no hashes — the keys are raw strings in the ConfigMap. The running code at `src/dk_data/metering_proxy/auth.py:validate_key()` does a plain dict lookup. A hashed-at-rest design is on the roadmap (see issue #283 follow-ons), but today rotation is a two-commit dance against the ConfigMap.

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

1. Remove the consumer entry from the `consumers.yaml` block inside `k8s/apps/metering-proxy/base/configmap.yaml`.
2. Commit, push, let ArgoCD sync, and `POST /-/reload` on the metering proxy (or let the rolling restart do it).
3. Verify the consumer's key returns 401 on the next request.
4. Delete the raw key from the consumer's secret store (Doppler, k8s secret) and delete any env var references in the consumer's deployment manifest.

Keep the ConfigMap's git history — `git log k8s/apps/metering-proxy/base/configmap.yaml` is the audit trail for who had access when.

## Related

- `docs/runbooks/metering-proxy-401-debug.md` — debugging auth failures
- `docs/runbooks/rotate-jwt-secret.md` — rotating the shared JWT signing secret (separate from consumer API keys)
- `docs/runbooks/adapter-fallthrough-spike.md` — responding to fallthrough spikes
- `k8s/apps/metering-proxy/base/configmap.yaml` — canonical consumer registry (contains `consumers.yaml` as a ConfigMap data key)
- `packages/dk-data-client/README.md` — monorepo root: package layout, invariants, integration-test setup
- `packages/dk-data-client/python/README.md` — Python client API reference (source of truth for Python consumers)
- `packages/dk-data-client/typescript/README.md` — TypeScript client API reference (source of truth for TS consumers)
- `.dk/specs/003-metering-jwt-mint/spec.md` — the feature spec for how auth actually works after feature 003
