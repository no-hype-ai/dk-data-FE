# Blockers & Workarounds

## B001 — US-15 scope collapses: `require_auth` already exists (2026-04-13)

**Context**: The spec and plan for US-15 call for creating `src/dk_data/api/dependencies/auth.py` with a new `verify_jwt` function. Before writing it, I discovered dk-data-FE already has a complete JWT+RBAC system:

- `src/dk_data/services/auth/jwt_service.py` — `JWTService`, `UserRole` (VIEWER/ANALYST/DATA_OPS/ADMIN), `AuthenticatedUser`, `verify_token()`
- `src/dk_data/api/middleware/rbac.py` — `require_auth` (raises 401 on missing/invalid JWT), `RoleChecker`, `PermissionChecker`, pre-configured deps (`require_viewer`, `require_analyst`, `require_data_ops`, `require_admin`), pre-configured permission deps (`can_read_gold`, `can_read_silver`, `can_manage_queue`, etc.)

US-15's real work shrinks to: apply `dependencies=[Depends(require_auth)]` at the `/data-platform` router level. No new dep module, no new `verify_jwt`.

**Workaround**: Use existing `require_auth` from `middleware.rbac` instead of creating `verify_jwt`. Update T026/T027 task descriptions to reflect the revised scope.

**Status**: Resolved (pivoted to using existing infrastructure)

**Affects**: T026, T027, T028, T029

---

## B002 — `JWT_SECRET_KEY` is not set in k8s (2026-04-13)

**Context**: `JWTService.__init__` reads `os.getenv("JWT_SECRET_KEY")`. If unset, it generates a random key via `secrets.token_hex(32)` with a warning. Grep of `k8s/` and `src/` shows JWT_SECRET_KEY is NOT set anywhere in the deployment manifests. Meanwhile, PostgREST uses `PGRST_JWT_SECRET` sourced from a secret named `JWT_SECRET` in `dk-data-secrets`.

**Consequence**: FastAPI is currently generating a random JWT signing key per pod restart. Any JWT minted by the metering proxy (using the shared `JWT_SECRET`) would be rejected by FastAPI because FastAPI uses a different secret. This is a pre-existing bug that US-15 exposes but does not introduce.

**Workaround**: Update `JWTService.__init__` to read `JWT_SECRET_KEY` first, then fall back to `JWT_SECRET` (the shared k8s secret name). This restores parity with PostgREST + metering-proxy without requiring a separate k8s manifest change to rename the env var.

Follow-up: a separate PR in a future session should add `JWT_SECRET_KEY` to the k8s deployment.yaml env block (sourced from the existing `JWT_SECRET` secret) for clarity. This session's fix keeps the runtime working without modifying k8s manifests.

**Status**: Workaround applied in this session; k8s env var rename tracked as follow-up.

**Affects**: T026 (JWTService instantiation), T027 (router-level dep), T028 (tests must work with either env var name)

---

## B003 — Stub `get_current_user()` conflict in `dependencies.py` (2026-04-13)

**Context**: There are TWO `get_current_user` functions:

1. `src/dk_data/api/dependencies.py:149` — STUB that returns a fake `{"roles": ["admin", "api_user"], "authenticated": True}` without any auth check. Imported by `src/dk_data/api/routes/alerts.py`.
2. `src/dk_data/api/middleware/rbac.py:41` — REAL version that decodes JWT via `JWTService.verify_token()`.

The stub is in use by `alerts.py`. Replacing it now would change alerts.py's auth behavior, which is out of scope for US-15 (US-15 only covers `/data-platform/*`).

**Workaround**: Leave the stub in place for this session. Document the conflict, apply `require_auth` only to the data_platform router. A follow-up should audit every `get_current_user` import and migrate `alerts.py` to the real `rbac.get_current_user`.

**Status**: Documented; not fixed in this session (out of scope for US-15).

**Affects**: Follow-up task — audit and migrate every `from ..dependencies import get_current_user` call site.

## B004 — T017 was already complete before the spec was written (2026-04-13)

**Context**: The spec and US-12 Fix 12.4 claimed `POST /api/v1/monitoring/job-complete` was "partially broken" because it only emitted `BATCH_JOB_LAST_SUCCESS_TIMESTAMP` and did not call helpers for the other three batch-job metrics. Verified against current code: the handler at `src/dk_data/api/routes/monitoring.py` `report_job_completion` calls:

- `mark_job_success(job_name)` on success → `BATCH_JOB_LAST_SUCCESS_TIMESTAMP.set(time.time())`
- `record_job_records(job_name, records)` on success → `BATCH_JOB_RECORDS_PROCESSED.inc(count)`
- `increment_job_failure(job_name)` on failure → `BATCH_JOB_FAILURES_TOTAL.inc()`
- `record_job_duration(job_name, duration)` unconditionally → `BATCH_JOB_DURATION_SECONDS.observe(duration)`

All four metric objects and all four helper functions exist in `src/dk_data/observability/metrics.py` lines 84–103 (defs) and 584–601 (helpers). The audit that produced the brief must have been based on a stale snapshot or a different code version.

**Workaround**: Mark T017 `[x]` with a note. No code change required.

**Status**: Resolved — already in a correct state.

**Affects**: T017 only. Raises the question of whether the broader "38 dead metrics" claim in US-12 is also stale. T158 (re-audit at Phase 6 start) already handles this by regenerating the dead-metric list at execution time instead of trusting the brief's snapshot — that task is more important than ever now that we have concrete evidence the brief's metric audit is stale.

<!-- Append blockers encountered during implementation -->
