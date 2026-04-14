# Quickstart — Feature 003 Metering JWT Minting

## Prerequisites

- `uv` for Python dependency management
- `docker` + `docker-compose` for local metering-proxy + PostgREST + Postgres
- `kubectl` + a working kubeconfig for a staging cluster
- A `JWT_SECRET` value (at least 32 chars) — any random string works for local dev
- A test consumer API key registered in a local `consumers.yaml`

## Local development loop

### 1. Install dev dependencies

```bash
uv sync --all-extras
```

### 2. Run the metering proxy + PostgREST + Postgres locally

```bash
docker compose up -d postgres postgrest metering-proxy
```

Verify readiness:

```bash
curl http://localhost:3001/health        # metering proxy
curl http://localhost:3000/health        # postgrest
docker compose exec postgres psql -U postgres -d dk_data -c '\du'
```

You should see `api_user`, `authenticator`, `dk_data_no_anon` in the role list (after migrations run).

### 3. Apply local migrations

```bash
uv run python -m dk_data.scripts.run_migrations --target 228
```

This applies every migration up through 228, including the new schema-grant migration. Verify:

```sql
SELECT rolname FROM pg_roles WHERE rolname IN ('api_user', 'dk_data_no_anon');
SELECT has_schema_privilege('api_user', 'mol_silver', 'USAGE');  -- expect: t
```

### 4. Set the JWT secret locally

```bash
export JWT_SECRET="$(openssl rand -hex 32)"
```

Both PostgREST and the metering proxy must see the same value. In `docker-compose.yml`, both containers read it from the shared `.env` file — update both blocks if you set them separately.

### 5. Run the unit tests

```bash
uv run pytest tests/metering_proxy/test_jwt_mint.py -v
```

Expected: all tests green. The JWT mint + decode roundtrip, unknown-tier handling, missing-secret handling, and short-secret handling are all covered.

### 6. Smoke-test locally

```bash
API_KEY="dk_data_blai_test_key"   # must match consumers.yaml in the local docker-compose
curl -H "Authorization: Bearer $API_KEY" \
     http://localhost:3001/mol_silver/molecules?limit=5
```

Expected: HTTP 200 with JSON body. If you get a 401 from PostgREST, your `JWT_SECRET` differs between the proxy and PostgREST containers — fix the `.env` and restart.

## Staging deployment

1. Merge the PR to `main`.
2. CI builds the image and promotes it to `prod-<sha>`; the staging overlay picks up `main-<sha>`.
3. ArgoCD syncs `dk-data-staging` — the readiness probe runs the startup self-test. If the secret is wrong on the staging side, the pod stays non-ready.
4. Migration 228 runs in the staging `db-migrate` job (creates `dk_data_no_anon`, grants `api_user`).
5. Migration 218 runs next — its pre-flight guard checks for `dk_data_no_anon` and passes (because 228 just ran).
6. Manually trigger the live integration workflow against staging:
   ```bash
   gh workflow run integration-live.yaml \
     -f base_url=https://data.staging.behaviorlabs.ai \
     -f api_key_secret=DK_DATA_STAGING_KEY
   ```
7. Verify Grafana: `metering_proxy_jwt_minted_total` > 0; `requests_executed_as_anon_total` = 0.

## Production deployment

Same as staging, against `data.behaviorlabs.ai`. Coordinate with the platform operator and schedule during a low-traffic window because:

- The PostgREST pod restart will briefly pause forwarded requests (10–30s depending on the rolling strategy).
- Migration 218 is a hard break of the old anonymous path — any client that was somehow still using `web_anon` will fail. A pre-flight audit of the running cluster should confirm no such callers exist.

## Rolling back

See `plan.md:Rollback plan`. Short version:

1. Revert the `PGRST_DB_ANON_ROLE` ConfigMap change.
2. Revert the metering-proxy image tag.
3. If migrations already ran and the role created issues: `DROP ROLE dk_data_no_anon`.

None of these are destructive. The grant migration is additive and can remain in place.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Metering proxy pod stuck in `CrashLoopBackOff` with "JWT_SECRET env var is not set" | Deployment missing the new env block | Apply the deployment.yaml change |
| Metering proxy readiness never becomes ready, logs show "jwt secret mismatch" | `JWT_SECRET` differs between proxy env and PostgREST env | Both sources point at the same k8s secret key; check `dk-data-secrets.JWT_SECRET` in both containers |
| `GET /mol_silver/molecules` returns 401 from PostgREST | JWT signed with a different secret than PostgREST expects | Same as above |
| `GET /mol_silver/molecules` returns 403 from PostgREST | `api_user` lacks grants on `mol_silver` | Run migration 228; verify with `has_schema_privilege('api_user','mol_silver','USAGE')` |
| `GET /mol_silver/molecules` returns 500 from the proxy | Consumer tier not in `TIER_TO_ROLE` | Add the tier to `jwt_mint.TIER_TO_ROLE` or fix the consumers.yaml |
| Migration 218 fails with "requires feature 003" | Migration 228 has not run yet | Run 228 first (it's in the same deploy) |

## Reference

- Spec: `.dk/specs/003-metering-jwt-mint/spec.md`
- Plan: `.dk/specs/003-metering-jwt-mint/plan.md`
- Research decisions: `.dk/specs/003-metering-jwt-mint/research.md`
- Data model: `.dk/specs/003-metering-jwt-mint/data-model.md`
- Contracts: `.dk/specs/003-metering-jwt-mint/contracts/jwt-mint-api.md`
- Issue: data-kinetic/dk-data-FE#283
