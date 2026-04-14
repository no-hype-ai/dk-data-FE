# Tasks — 003 Metering JWT Minting

**Feature branch**: `feature/003-metering-jwt-mint`
**Spec**: `.dk/specs/003-metering-jwt-mint/spec.md`
**Plan**: `.dk/specs/003-metering-jwt-mint/plan.md`
**Issue**: data-kinetic/dk-data-FE#283

---

## Legend

- `[P]` — task can run in parallel with other `[P]` tasks in the same phase (no file overlap)
- `[US1]`, `[US2]`, ... — task is scoped to that user story's acceptance criteria
- Tasks are listed in dependency order; complete earlier tasks before later ones in the same phase

---

## Phase 1 — Setup

- [x] **T001** Verify working tree is clean on branch `feature/003-metering-jwt-mint` and pull latest `main` into the branch (`git fetch origin && git rebase origin/main`). No file changes.
- [x] **T002** [P] Confirm `pyjwt` is already in `pyproject.toml` dependencies (no change needed); record version in `plan.md` if different from `jwt_service.py`'s expectation. File: `pyproject.toml`. — verified `pyjwt>=2.8.0,<3.0` present.
- [x] **T003** [P] Confirm `uv sync --all-extras` succeeds on the branch; capture output in `memory/changelog.md`. No file changes.

---

## Phase 2 — Foundational

Blocking prerequisites for every user story. Complete the whole phase before starting US1.

- [x] **T010** Create `src/dk_data/metering_proxy/jwt_mint.py` with the `TIER_TO_ROLE` constant, `JWTMintError`, `load_secret_at_startup()`, `mint()`, and `self_test()` functions. File: `src/dk_data/metering_proxy/jwt_mint.py`.
- [x] **T011** Add counters to `src/dk_data/metering_proxy/metrics.py`: `JWT_MINTED_TOTAL` (labels: `tier`), `JWT_MINT_ERRORS_TOTAL` (labels: `error_type`), and `REQUESTS_FORWARDED_WITHOUT_JWT_TOTAL` (unlabeled, FR-010 bug-detector). File: `src/dk_data/metering_proxy/metrics.py`.
- [x] **T012** Add `JWT_SECRET` env var to the metering-proxy sidecar container in `k8s/apps/metering-proxy/base/deployment-patch.yaml` (the sidecar is defined in the metering-proxy base patch, not in postgrest/base/deployment.yaml as the original task text said), sourced from `dk-data-secrets.JWT_SECRET`. File: `k8s/apps/metering-proxy/base/deployment-patch.yaml`.
- [x] **T013** Write migration `src/dk_data/sql/migrations/228_jwt_mint_schema_grants.sql`: `GRANT USAGE` + `GRANT SELECT ON ALL TABLES` + `ALTER DEFAULT PRIVILEGES` on the 13 target schemas for `api_user`, plus `GRANT EXECUTE` on the 10 resolve functions. Idempotent. No role creation — `api_user` already exists, and feature 002's unset `PGRST_DB_ANON_ROLE` handles the "no anonymous access" side without a new role. File: `src/dk_data/sql/migrations/228_jwt_mint_schema_grants.sql`.
- [x] **T014** (NO-OP, kept for task-ID stability) — no migration rename is needed. Migration 218 (drop `web_anon`) and migration 228 (grant `api_user`) are independent. The earlier plan to rename 218 → 229 was based on a false ordering constraint and has been reverted.

---

## Phase 3 — US1: Client application reads silver data through a valid API key (P1)

- [x] **T020** [US1] Modify `src/dk_data/metering_proxy/proxy.py:proxy_request()` to accept `consumer_alias: str | None` and `tier: str | None` parameters. When both are set, call `jwt_mint.mint(...)`, set `Authorization: Bearer <token>` on `proxy_headers`, and increment `JWT_MINTED_TOTAL.labels(tier=tier).inc()`. Wrap in `try/except JWTMintError` that increments `JWT_MINT_ERRORS_TOTAL.labels(error_type=...).inc()` and re-raises as a 500 response. File: `src/dk_data/metering_proxy/proxy.py`.
- [x] **T021** [US1] Modify `src/dk_data/metering_proxy/app.py:proxy_handler()` to pass `consumer.alias` and `consumer.tier` into `proxy_request(...)` after `validate_key()` succeeds and allowlist passes. File: `src/dk_data/metering_proxy/app.py`.
- [x] **T022** [P] [US1] Write unit test `tests/metering_proxy/test_jwt_mint.py::test_mint_roundtrip` — mint a JWT with alias=`"blai"`, tier=`"high"`, a dummy 32-char secret, decode with PyJWT, assert all claims match and `exp - iat == 60`. File: `tests/metering_proxy/test_jwt_mint.py`.
- [x] **T023** [P] [US1] Add `tests/metering_proxy/test_jwt_mint.py::test_unknown_tier_raises` and `::test_mint_before_startup_raises`. File: `tests/metering_proxy/test_jwt_mint.py`.
- [x] **T024** [P] [US1] Add `tests/metering_proxy/test_jwt_mint.py::test_every_configured_tier_is_mapped` — parse `k8s/apps/metering-proxy/base/configmap.yaml` (or the equivalent test fixture), assert every `tier:` value is a key in `TIER_TO_ROLE`. File: `tests/metering_proxy/test_jwt_mint.py`.
- [x] **T025** [P] [US1] Add `tests/metering_proxy/test_auth.py::test_forwarded_headers_strip_raw_api_key` — spy on `proxy_request` arguments, assert no forwarded header matches the raw API key. File: `tests/metering_proxy/test_auth.py`.
- [x] **T025a** [P] [US1] Add `tests/metering_proxy/test_schema_allowlist.py::test_allowlist_rejection_does_not_mint_jwt` — when a consumer tries a schema not in its `allowed_schemas`, assert the response is 403 AND `JWT_MINTED_TOTAL` counter delta is zero for the window. Satisfies FR-015. File: `tests/metering_proxy/test_schema_allowlist.py`.
- [x] **T026** [P] [US1] Update `packages/dk-data-client/python/tests/integration/test_live_client.py` to assert that a real `molecules.resolve("aspirin")` call returns a response with `fallthrough=False` (proving silver hub responded, not upstream). File: `packages/dk-data-client/python/tests/integration/test_live_client.py`.

**US1 checkpoint**: Unit tests green, proxy forwards Bearer JWT, `jwt_minted_total` counter emits on every request that reaches PostgREST.

---

## Phase 4 — US2: Every authenticated request reaches the database as a real role, never as `web_anon` (P1)

- [ ] **T030** [US2] Modify `src/dk_data/metering_proxy/app.py:lifespan()` to call `jwt_mint.load_secret_at_startup()` before any traffic is accepted; let `JWTMintError` propagate so the container fails readiness. File: `src/dk_data/metering_proxy/app.py`.
- [ ] **T031** [US2] Extend `app.lifespan()` to call `jwt_mint.self_test(POSTGREST_URL)` after secret load; on failure, structured-log and raise so readiness stays failed. File: `src/dk_data/metering_proxy/app.py`.
- [ ] **T032** [P] [US2] Add `tests/metering_proxy/test_jwt_mint.py::test_missing_secret_fails_startup` and `::test_short_secret_fails_startup`. File: `tests/metering_proxy/test_jwt_mint.py`.
- [ ] **T033** [P] [US2] Add `tests/metering_proxy/test_jwt_mint.py::test_self_test_detects_secret_mismatch` — monkeypatch PostgREST response to 401, assert self_test raises `JWTMintError`. File: `tests/metering_proxy/test_jwt_mint.py`.
- [ ] **T034** (NO-OP, kept for task-ID stability) — feature 002 already commented out `PGRST_DB_ANON_ROLE` in `k8s/apps/postgrest/base/configmap.yaml`, which is the right behavior for this feature too. No configmap change needed here.

**US2 checkpoint**: Startup self-test runs, readiness probe correctly reflects JWT_SECRET validity, PostgREST anon fallback points at a permission-less role.

---

## Phase 5 — US3: `web_anon` can be safely dropped without breaking the API (P1)

- [ ] **T040** [US3] Extend `tests/test_218_drop_web_anon.py` with a new test that verifies migration 218 and migration 228 can be applied in either order on a fresh database (no dependency between them). This catches any regression where someone reintroduces a false ordering coupling. File: `tests/test_218_drop_web_anon.py`.
- [ ] **T041** [US3] Write pytest `tests/test_228_schema_grants.py` — apply migration 228 against a temp database with the 13 target schemas, assert `has_schema_privilege('api_user', schema, 'USAGE')` and `has_table_privilege('api_user', table, 'SELECT')` for each schema and at least one representative table. File: `tests/test_228_schema_grants.py`.
- [ ] **T042** [US3] Verify `docs/runbooks/rollback-web-anon-drop.md` is still accurate under the new design (no dk_data_no_anon role, migration number 218 unchanged). Update only the "restore PGRST_DB_ANON_ROLE" section to note that feature 003 does not change how the anon-role fallback works. File: `docs/runbooks/rollback-web-anon-drop.md`.

**US3 checkpoint**: Migrations 218 + 228 both apply cleanly on a fresh database; rollback runbook reflects the new layout.

---

## Phase 6 — US4: The target database role has exactly the schema access the product promises (P2)

- [ ] **T050** [P] [US4] Extend `tests/test_228_schema_grants.py::test_api_user_cannot_write` — assert `api_user` attempting `INSERT INTO mol_silver.molecules` fails with `permission denied`. File: `tests/test_228_schema_grants.py`.
- [ ] **T051** [P] [US4] Extend `tests/test_228_schema_grants.py::test_api_user_can_execute_resolve_functions` — call each resolve function from a session using `SET ROLE api_user`, assert no permission error. File: `tests/test_228_schema_grants.py`.
- [ ] **T052** [P] [US4] Extend `tests/test_228_schema_grants.py::test_new_table_inherits_select_grant` — create a test table in `mol_silver`, assert `api_user` can SELECT without an explicit GRANT (tests `ALTER DEFAULT PRIVILEGES`). File: `tests/test_228_schema_grants.py`.

**US4 checkpoint**: All grant tests green; no unexpected grant (write/DDL/administrative).

---

## Phase 7 — US5: Observability and operator confidence (P2)

- [ ] **T060** [US5] Update `grafana/dashboards/dk-data-adapter-telemetry.json`: add a panel that plots `rate(metering_proxy_jwt_minted_total[1m])` broken down by `tier`, a second panel for `metering_proxy_jwt_mint_errors_total`, and a third panel for `metering_proxy_requests_forwarded_without_jwt_total` (expected to be zero at steady state — this satisfies FR-010's consumption binding). File: `grafana/dashboards/dk-data-adapter-telemetry.json`.
- [ ] **T061** [US5] Add alerts to `grafana/alerts/dk-data.yaml`: `MeteringProxyJWTMintSuccessRateLow` (fires when minted success rate < 99.9% over 5m) AND `MeteringProxyRequestsAsAnonRoleDetected` (fires when `rate(metering_proxy_requests_forwarded_without_jwt_total[5m]) > 0` — this satisfies FR-010's alert requirement). File: `grafana/alerts/dk-data.yaml`.
- [ ] **T062** [P] [US5] Update `tests/observability/test_metric_coverage.py` to include `metering_proxy_jwt_minted_total`, `metering_proxy_jwt_mint_errors_total`, AND `metering_proxy_requests_forwarded_without_jwt_total` in the expected-metrics list. File: `tests/observability/test_metric_coverage.py`.
- [ ] **T063** [P] [US5] Write `tests/metering_proxy/test_nolog.py` — spy on the `structlog` processor chain, run one request through the proxy, assert no log record contains the raw API key string, the minted JWT, or the `JWT_SECRET` value. This test is the enforcement for the `[NOLOG]` tag on this feature. File: `tests/metering_proxy/test_nolog.py`.

**US5 checkpoint**: Metric is bound three ways (definition in metrics.py, emission in proxy.py, consumption in dashboard + alert); the no-log regression test passes.

---

## Phase 8 — Polish & cross-cutting

- [ ] **T070** Rewrite `docs/consumer-onboarding.md` to match the actual running behavior: raw keys in `consumers.yaml`, metering-proxy mints JWTs, no bcrypt hashing. Keep the "future work" section that points at the issue for bcrypt hashing. File: `docs/consumer-onboarding.md`.
- [ ] **T071** Rewrite `docs/runbooks/metering-proxy-401-debug.md` to describe the actual JWT flow (proxy mint, not consumer-sent JWT) and remove the fictional "JWT secret mismatch" dual-source path. File: `docs/runbooks/metering-proxy-401-debug.md`.
- [ ] **T072** [P] Create `.github/workflows/integration-live.yaml` — manual-trigger workflow that runs `packages/dk-data-client/python/tests/integration/test_live_client.py` against `$DK_DATA_BASE_URL` with `$DK_DATA_API_KEY` from a GitHub Actions secret. File: `.github/workflows/integration-live.yaml`.
- [ ] **T073** [P] Add a brief JWT-mint section to `.dk/memory/lessons.md` capturing the "documentation described a design that was never implemented" pattern, so future readers find it when they hit the same confusion. File: `.dk/memory/lessons.md`.
- [ ] **T074** Run the full local test suite (`uv run pytest tests/metering_proxy/ tests/sql/test_228_schema_grants.py tests/sql/test_218_preflight_guard.py tests/observability/test_metric_coverage.py`) and capture output in `memory/changelog.md`. File: `memory/changelog.md`.
- [ ] **T075** Run `uv run ruff check src/ tests/` and `uv run mypy src/dk_data/metering_proxy/` and fix any findings. No new file changes expected.
- [ ] **T076** Run `kubectl kustomize k8s/overlays/prod/ | kubectl apply --dry-run=client -f -` locally to verify the manifest changes are valid. No new file changes.
- [ ] **T077** Open the PR against `main`, link to issue #283 in the description, paste the full plan checklist from `checklists/requirements.md`, and request review.

---

## Dependencies & Execution Order

```
Phase 1 (T001-T003) — Setup
  ↓
Phase 2 (T010-T014) — Foundational (ALL blocking for Phase 3+)
  ↓
  ├─ Phase 3 (US1: T020-T026)      ──┐
  ↓                                   │
Phase 4 (US2: T030-T034)              │  These three can be started together
  ↓                                   │  after Phase 2 if the workers avoid
Phase 5 (US3: T040-T042)              │  the same files (see "Parallel" below).
  ↓                                   │
  ├─ Phase 6 (US4: T050-T052) ──────┤
  └─ Phase 7 (US5: T060-T063) ──────┘
  ↓
Phase 8 (T070-T077) — Polish & cross-cutting
```

### Parallel execution opportunities

**Within Phase 3 (US1):**
- T022, T023, T024 all edit `tests/metering_proxy/test_jwt_mint.py` — sequential, one worker.
- T025 edits `tests/metering_proxy/test_auth.py` — parallel with the above.
- T026 edits `packages/dk-data-client/.../test_live_client.py` — parallel with the above.
- T020 and T021 edit `proxy.py` and `app.py` — sequential, same worker because they're tightly coupled (T021 uses T020's new signature).

**Across Phase 3 and Phase 4:**
- Phase 3 touches `proxy.py`, `app.py`, `tests/metering_proxy/`, integration test.
- Phase 4 T030-T031 touch `app.py` — CONFLICT with Phase 3 T021. These must be sequential (same worker) OR Phase 4 T030-T031 start after Phase 3 T021 merges.
- Phase 4 T032, T033 edit `tests/metering_proxy/test_jwt_mint.py` — CONFLICT with Phase 3 T022-T024. Sequential.
- Phase 4 T034 edits `configmap.yaml` — CAN run in parallel with Phase 3 non-yaml tasks.

**Phase 5, 6, 7:**
- Phase 5 T040, T041 create new SQL test files; T042 edits a runbook — all three can run in parallel with each other AND with Phase 6, 7.
- Phase 6 T050-T052 all edit the same file (`tests/sql/test_228_schema_grants.py`) — sequential.
- Phase 7 T060 edits dashboard JSON; T061 edits alerts YAML; T062 edits a metric-coverage test; T063 creates a new test file — all four parallel.

**Suggested wave layout for `/dk.swarm`:**

| Wave | Type | Workers | Tasks | Notes |
|---|---|---|---|---|
| 1 | Direct | — | T001-T014 | Setup + foundational; creates the new module, migration, and manifest changes |
| 2 | Parallel | us1-core / us1-tests | US1: T020+T021 // T022-T026 | Core proxy edits + parallel test writing |
| 3 | Parallel | us2 / us4-tests | US2: T030-T034 // US4: T050-T052 | No file overlap — US2 touches app.py/test_jwt_mint.py; US4 touches test_228_schema_grants.py |
| 4 | Parallel | us3-sql / us5-obs | US3: T040-T042 // US5: T060-T063 | No overlap — US3 is SQL tests + runbook; US5 is dashboard/alerts/metrics |
| 5 | Direct | — | T070-T077 | Polish — docs, workflow, lint, kustomize dry-run, PR |

---

## Implementation strategy

1. **Phase 1 + 2 as a single direct session** — the foundational files (`jwt_mint.py`, `metrics.py`, migration, deployment.yaml) must be in place before any US can test against them. One commit per task; the migration and `jwt_mint.py` are the two largest commits.

2. **Phase 3 (US1) first** — this is the critical path: once US1 is green (JWT mint + inject + unit tests + integration test), everything else is additive safety net.

3. **Phase 4 (US2) next** — startup self-test + anon-role change. US2 provides the "defense in depth" proof; US1 provides the functional proof. US2 must complete before a production deploy because without the self-test a secret mismatch lands silently.

4. **Phase 5 + 6 in parallel** — both are database-only work with no runtime code changes. Wave 4 in `/dk.swarm` launches them together.

5. **Phase 7 in parallel with Phase 5/6** — observability is decoupled from database. Same wave.

6. **Phase 8 direct** — docs, workflow, lint, kustomize dry-run, PR open. All sequential, but quick.

---

## Testing strategy per task

- Unit tests run on every commit locally and in CI.
- Integration test (T026) runs only when the manual-trigger workflow (T072) is fired — not on every PR.
- SQL tests (T040, T041, T050-T052) require a temp Postgres — use the existing `tests/conftest.py` fixture.
- Manifest dry-run (T076) is a local check, not CI — add to the checklist if the team wants it in CI later.

---

## Definition of done for this feature

All boxes in `checklists/requirements.md` are ticked.
All tasks in this file are checked off.
Integration test workflow runs green against staging.
Observability panel and alert are live in Grafana.
Issue #283 is closed with a reference to the merged PR.
