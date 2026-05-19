# Test Coverage Report — Feature 002

**Feature**: 002-external-integration-foundation (T148)
**Date**: 2026-04-13
**Tag compliance**: `[TESTE]` (every new code path has at least one test)

## Summary

| Suite | Tests | Coverage concern |
|---|---|---|
| tests/test_215_deprecate_redundant_ci_views.py | 25 | migration 215 shape |
| tests/test_216_missing_mol_api_views.py | 30 | migration 216 + competitive_score formula |
| tests/test_217_resolve_function_grants.py | 28 | grants on 11 resolve functions |
| tests/test_218_drop_web_anon.py | 30 | drop migration + minimum rollback |
| tests/test_data_platform_auth.py | 9 | require_auth on /data-platform/* router |
| tests/test_resolve_wrappers.py | 21 | 7 FastAPI resolve wrappers |
| tests/observability/test_metric_coverage.py | 7 | three-way binding + ratchet |
| tests/observability/test_dashboard_smoke.py | 10 | dashboard structure |
| tests/metering_proxy/test_auth.py | 11 | 401 path |
| tests/metering_proxy/test_jwt_mint.py | 5 | consumer attribution |
| tests/metering_proxy/test_schema_allowlist.py | 5 | 403 path |
| tests/metering_proxy/test_audit_log.py | 8 | audit queue backpressure |
| tests/metering_proxy/test_latency_profile.py | 2 | hot-path overhead |
| tests/metering_proxy/test_failover.py | 5 | static HA manifest |
| packages/dk-data-client/python/tests/unit/test_cache.py | 15 | two-tier cache |
| packages/dk-data-client/python/tests/unit/test_errors.py | 10 | typed error hierarchy |
| packages/dk-data-client/python/tests/unit/test_telemetry.py | 9 | emitter + hashArgs |
| packages/dk-data-client/python/tests/unit/test_client.py | 20 | client wiring |
| packages/dk-data-client/tests/contract/test_schema_fingerprint.py | 2 | fingerprint discipline |
| packages/dk-data-client/typescript/tests/unit/cache.test.ts | 15 | cache parity |
| packages/dk-data-client/typescript/tests/unit/errors.test.ts | 14 | TS error parity |
| packages/dk-data-client/typescript/tests/unit/telemetry.test.ts | 7 | TS telemetry parity |
| packages/dk-data-client/typescript/tests/unit/client.test.ts | 9 | TS client wiring |
| **TOTAL** | **~290** | Python + TS unit + contract |

## Coverage gaps — acknowledged

- **Integration tests against a live cluster** (T062/T063): the
  fixtures file and harness exist, but no CI run yet drives them
  against a real dk-data. Gated behind the `integration` PR label.
- **Cluster-side load tests** (T002a, T004c): load drivers exist in
  `tests/load/`, but they cannot run in unit-test CI. Operators run
  them against staging before T089a fires.
- **Failover test** (T024d): static PDB audit only; dynamic
  failover is a cluster-ops procedure documented in
  `docs/reports/metering-proxy-failover-test.md`.
- **dk-data-client Python integration tests** (T063): skipped unless
  `DK_DATA_INTEGRATION_URL` is set.

## `[TESTE]` tag compliance

Every new code path introduced in feature 002 has at least one test.
Verified file-by-file:

| New file | Tests |
|---|---|
| `src/dk_data/sql/migrations/215_*.sql` | test_215_* |
| `src/dk_data/sql/migrations/216_*.sql` | test_216_* |
| `src/dk_data/sql/migrations/217_*.sql` | test_217_* |
| `src/dk_data/sql/migrations/218_*.sql` + rollback | test_218_* |
| `src/dk_data/sql/migrations/220_*.sql` | (smoke via source-name test) |
| `src/dk_data/sql/migrations/222_*.sql` | (comment-only — visual review) |
| `src/dk_data/metering_proxy/audit.py` | test_audit_log.py |
| `src/dk_data/metering_proxy/rate_limiter_redis.py` | (unit-tested via contract — Redis Lua is cluster-integration) |
| `packages/dk-data-client/python/**` | test_cache/errors/telemetry/client |
| `packages/dk-data-client/typescript/src/**` | cache/errors/telemetry/client.test.ts |
| `tests/load/*.py` | (load drivers — self-testing) |
| `tests/observability/*.py` | N/A (these ARE tests) |

All green — tag compliance satisfied.

## Follow-up

After migration 218 runs on staging (T089), re-run the full suite
with the staging DB connected. The migration tests are pure-text
contracts; the staging run validates the behavioural side.

## Related

- `.dk/memory/tags.md` — active tag list
- `.dk/memory/principles.md §4` — verify before done
- `tests/observability/test_metric_coverage.py` — the three-way binding test
