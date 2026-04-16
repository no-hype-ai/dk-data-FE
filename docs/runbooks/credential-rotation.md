# Runbook: Per-Source Credential Rotation

**Horizon**: 3 (§D.5)
**Goal**: rotate a single data-source's credential without touching any other
source, without a full redeploy, and without blast radius beyond one consumer.
**Last verified**: 2026-04-16

## Why per-source

The legacy `dk-data-secrets` DopplerSecret contains every data-source key
(DRUGBANK_API_KEY, NCBI_API_KEY, OPENFDA_API_KEY, …). Rotating one key meant
touching a secret consumed by every fetcher — blast radius equals everything.

Per-source DopplerSecret CRs under
[`k8s/apps/secrets/per-source/`](../../k8s/apps/secrets/per-source/) split this
into one K8s Secret per source, each backed by a dedicated Doppler config in
project `dk-data`. Rotation touches exactly one consumer.

**The monolithic `dk-data-secrets` is DEPRECATED for per-source keys.** New
sources MUST use the per-source pattern; existing sources migrate as they are
touched. Shared infrastructure (POSTGRES_*, JWT_SECRET) stays in the monolith —
that surface is the same for every consumer and isn't what the split is for.

## Canonical CR shape

```yaml
apiVersion: secrets.doppler.com/v1alpha1
kind: DopplerSecret
metadata:
  name: dk-data-secrets-<source>
  labels:
    app.kubernetes.io/name: dk-data
    app.kubernetes.io/component: source-credentials
    app.kubernetes.io/part-of: dk-data
    app.kubernetes.io/managed-by: doppler-operator
    dk-data.source: <source>
spec:
  tokenSecret:
    name: doppler-token-secret
    key: serviceToken
  project: dk-data
  config: <source>        # staging overlay flips to <source>-stg
  managedSecret:
    name: dk-data-secrets-<source>
    type: Opaque
  secrets:
    - <SOURCE>_API_KEY    # exactly one key per CR
  resyncSeconds: 300
```

Hard rules:
- **One Secret, one key.** Never pack two source keys into one CR. That is
  the whole point.
- **Project `dk-data`**, config named after the source. Staging uses the
  `<source>-stg` config; the `overlays/staging/kustomization.yaml` patch
  substitutes automatically.
- **No hardcoded credentials** anywhere in this repo. Ever.

## Adding a new per-source secret

### 1. Create the Doppler config

Coordinate with dk-alchemy (they own the Doppler project). Open or comment on
the dk-alchemy coordination issue for D.5 requesting:

- New Doppler config `dk-data/<source>` (prod) and `dk-data/<source>-stg`
  (staging).
- One secret in each config: `<SOURCE>_API_KEY = <value>`.
- Service token for `<source>` config written into cluster secret
  `doppler-token-secret` (namespace `dk-data-prod` / `dk-data-staging`).

Do not create Doppler configs from this repo — that's a dk-alchemy-side
operation governed by the drift-protection stack.

### 2. Add the per-source DopplerSecret CR

Create
`k8s/apps/secrets/per-source/dk-data-secrets-<source>.yaml` using the template
above. Register it in
`k8s/apps/secrets/per-source/kustomization.yaml`:

```yaml
resources:
  - dk-data-secrets-drugbank.yaml
  - dk-data-secrets-<source>.yaml   # ← new
```

Add a staging-overlay patch in
`k8s/overlays/staging/kustomization.yaml` so the CR resolves to
`<source>-stg` in staging (follow the pattern used for `dk-data-secrets-drugbank`).

### 3. Reference from the consumer

In the CronJob / Job / Deployment that needs the key, use `valueFrom`
targeting **only** the per-source Secret — never `envFrom` the monolithic
`dk-data-secrets`:

```yaml
env:
  - name: <SOURCE>_API_KEY
    valueFrom:
      secretKeyRef:
        name: dk-data-secrets-<source>
        key: <SOURCE>_API_KEY
        optional: true       # if the fetcher degrades gracefully without it
```

### 4. Validate

```bash
# Kustomize build must pass for both overlays.
kubectl kustomize k8s/overlays/prod > /tmp/prod.yaml
kubectl kustomize k8s/overlays/staging > /tmp/staging.yaml

# Confirm the managed Secret appears after ArgoCD sync.
kubectl -n dk-data-prod get secret dk-data-secrets-<source>
kubectl -n dk-data-prod get secret dk-data-secrets-<source> -o jsonpath='{.data}' | jq 'keys'
# → should list exactly ["<SOURCE>_API_KEY"]
```

## Rotating a single key (≤ 5 minutes)

This is the whole point of D.5: one source rotates without touching any other.

### Step 1 — Generate a new credential

Obtain a new API key from the vendor's portal (DrugBank, openFDA, NCBI, …).

### Step 2 — Update Doppler

```bash
doppler secrets set <SOURCE>_API_KEY="<new-value>" \
  --project dk-data --config <source>

# Staging (if the key is distinct):
doppler secrets set <SOURCE>_API_KEY="<new-staging-value>" \
  --project dk-data --config <source>-stg
```

### Step 3 — Let the Doppler operator pick up the change

The DopplerSecret CR has `resyncSeconds: 300`. Within 5 minutes the managed
`dk-data-secrets-<source>` Secret is rewritten. To force immediate pickup:

```bash
# Prod:
kubectl -n dk-data-prod annotate dopplersecret dk-data-secrets-<source> \
  secrets.doppler.com/resync-trigger="$(date +%s)" --overwrite
```

### Step 4 — Restart the consumers

K8s does NOT automatically restart Pods when a mounted Secret changes. The new
value is only picked up on Pod restart for `secretKeyRef` env vars, or via
projected volume for mounted secrets.

```bash
# Only the consumers of THIS source need restarting — the whole point.
# CronJobs pick up the new Secret on their next scheduled run; force an
# immediate rollout on Deployments that use the key.

# Example for the DrugBank fetcher CronJob (no rollout needed — next run
# uses the new Secret). If you want to force a test run immediately:
kubectl -n dk-data-prod create job --from=cronjob/fetch-drugbank \
  fetch-drugbank-rotation-verify-$(date +%s)

# For long-running Deployments that consume the key:
kubectl -n dk-data-prod rollout restart deployment/<deployment-name>
```

No other source's Pods are touched. No PostgREST restart. No job-trigger
restart. No fetch-openfda restart.

### Step 5 — Verify

```bash
# Inspect the new Secret value (base64-decoded) to confirm it matches
# what you set in Doppler:
kubectl -n dk-data-prod get secret dk-data-secrets-<source> \
  -o jsonpath='{.data.<SOURCE>_API_KEY}' | base64 -d | head -c 10; echo

# Tail the consumer's logs on its next run; look for successful auth.
kubectl -n dk-data-prod logs -l app=fetch-<source> --tail=50 -f
```

## What stays in the monolithic `dk-data-secrets`

These keys are legitimately shared by every consumer and should NOT be split:

- `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD` /
  `POSTGRES_DB` — same DB for everything.
- `JWT_SECRET` / `PGRST_JWT_SECRET` — same signing secret for PostgREST,
  FastAPI, metering proxy (see `docs/runbooks/rotate-jwt-secret.md`).

These follow the JWT rotation runbook. D.5 only splits **source-specific**
credentials (per-source API keys) out of the monolith.

## Migration status

Tracked against the "D.5 follow-up: sweep all fetcher manifests to per-source
refs" issue — see the PR body for the link. Until the sweep lands, CronJobs
still `envFrom` the monolithic `dk-data-secrets` for their source key; that is
a known gap and is not a regression.

The base `deploy/jobs/prestaged-hydrate.yaml` Job is the proof-of-pattern:
it uses `valueFrom` against `dk-data-secrets-drugbank` specifically. New
fetcher manifests MUST follow that pattern; legacy ones migrate as they are
touched.

## Related runbooks

- [`rotate-jwt-secret.md`](./rotate-jwt-secret.md) — shared JWT signing secret.
- dk-alchemy `docs/runbooks/doppler-token-rotation.md` — rotating the service
  token that lets the operator talk to Doppler itself (cross-cutting; touches
  every DopplerSecret in the cluster).
