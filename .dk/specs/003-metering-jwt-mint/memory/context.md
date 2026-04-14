# Feature Context — 003-metering-jwt-mint

**Feature**: Metering proxy JWT minting so clients can reach silver/gold schemas
**Issue**: data-kinetic/dk-data-FE#283
**Branch**: `feature/003-metering-jwt-mint`
**Started**: 2026-04-14

## Active principle tags

- `[RBAC]` — this IS an auth feature; every change must be provably authenticated/authorized
- `[SECRT]` — JWT secret wiring lands in k8s manifest; no hardcoded values
- `[NOLOG]` — raw API key, minted JWT, and signing secret MUST NOT appear in any log
- `[TESTE]` — every new public function is tested
- `[AUDIT]` — the audit writer keeps emitting per consumer alias, not raw key
- `[GITOP]` — all cluster changes via ArgoCD, no manual kubectl

## Key decisions (from clarify + research)

1. One database role (`api_user`) for every current tier; multi-role deferred.
2. 60-second JWT TTL, per-request mint, no JWT cache.
3. `PGRST_DB_ANON_ROLE` points at a new `dk_data_no_anon` role with zero grants.
4. Startup self-test only — no periodic self-test.
5. Migration 218 pre-flight guard lives inside 218 itself as a DO block.
6. Live integration test is a manual-trigger GitHub Actions workflow.

## Files that will change

- `src/dk_data/metering_proxy/jwt_mint.py` (new)
- `src/dk_data/metering_proxy/proxy.py` (inject JWT)
- `src/dk_data/metering_proxy/app.py` (startup + self-test)
- `src/dk_data/metering_proxy/metrics.py` (new counters)
- `src/dk_data/sql/migrations/228_jwt_mint_schema_grants.sql` (new)
- `src/dk_data/sql/migrations/218_drop_web_anon.sql` (pre-flight DO block)
- `k8s/apps/postgrest/base/configmap.yaml` (anon role change)
- `k8s/apps/postgrest/base/deployment.yaml` (JWT_SECRET env)
- `grafana/dashboards/dk-data-adapter-telemetry.json` (new panel)
- `grafana/alerts/dk-data.yaml` (new alert)
- `tests/metering_proxy/test_jwt_mint.py` (populate)
- `tests/metering_proxy/test_nolog.py` (new)
- `packages/dk-data-client/python/tests/integration/test_live_client.py` (real cluster assertions)
- `.github/workflows/integration-live.yaml` (new)
- `docs/consumer-onboarding.md` (rewrite to match reality)
- `docs/runbooks/metering-proxy-401-debug.md` (rewrite)
- `docs/runbooks/rollback-web-anon-drop.md` (verify accuracy)

## Open questions

None. All ambiguities resolved in `spec.md` Clarifications section (2026-04-14 session, autonomous).
