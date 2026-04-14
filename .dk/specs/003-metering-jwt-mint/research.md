# Research — Metering Proxy JWT Minting

Decisions resolved before implementation starts. Each entry follows: **Decision**, **Rationale**, **Alternatives considered**.

## R-001: JWT library

**Decision:** Use `PyJWT` (already imported in `src/dk_data/services/auth/jwt_service.py`).

**Rationale:** PyJWT is already a transitive dependency. Adding a second JWT library (`python-jose`, `authlib`) would double the attack surface and force a reviewer to maintain two sets of version pins. PyJWT's HS256 path is well-audited and widely used by PostgREST consumers.

**Alternatives considered:**
- `python-jose` — actively maintained, supports more algorithms, but unnecessary for HS256.
- `authlib` — much broader OAuth/OIDC surface than we need; not worth the footprint.
- Hand-rolled HMAC — rejected outright; crypto you write yourself is crypto you break yourself.

---

## R-002: JWT algorithm

**Decision:** HS256 with the shared `JWT_SECRET`.

**Rationale:** The metering proxy sidecar and PostgREST run in the same pod (the proxy is a sidecar on the PostgREST deployment). They share the same secret store. An asymmetric algorithm (RS256/ES256) would require key-pair management for no security benefit — the private signing key and the public verification key would both live in the same k8s secret. PostgREST is already configured to accept HS256 via `PGRST_JWT_SECRET`.

**Alternatives considered:**
- RS256 — forces RSA key-pair rotation, adds key-management runbooks, no benefit because trust boundary is shared.
- ES256 — same trade-offs as RS256, plus ECC key handling.

---

## R-003: JWT TTL

**Decision:** 60 seconds, per-request mint.

**Rationale:** 60s is long enough to survive a slow upstream response without expiring, and short enough that a rotated secret propagates to every in-flight token within one minute. Per-request minting avoids a JWT cache (which would need a TTL, an eviction policy, and memory accounting) and PyJWT HS256 encode is ~50 μs — well within the 1 ms latency budget from SC-003.

**Alternatives considered:**
- 5-minute TTL with a per-consumer JWT cache — saves ~50 μs per cached hit but adds cache-invalidation complexity, memory accounting, and a second bug surface for secret rotation. Rejected as premature optimization.
- 10-second TTL — unnecessarily tight; a slow network hop plus PostgREST query could plausibly take 5+ seconds, and a 10s buffer leaves no headroom.
- Long-lived JWTs (hours) — defeats the purpose of "secret rotation propagates immediately" and enlarges the blast radius of a leaked token.

---

## R-004: PostgREST anonymous-role strategy

**Decision:** Create a new database role `dk_data_no_anon` with zero grants on any schema, and set `PGRST_DB_ANON_ROLE=dk_data_no_anon`. Every unauthenticated request falls through to this role, which can reach nothing, so the query returns "permission denied" immediately.

**Rationale:** PostgREST 12.2.3 requires `PGRST_DB_ANON_ROLE` to be set at startup — unsetting it causes the container to fail. A permission-less role is the closest we can get to "reject unauthenticated requests at the gateway" without a PostgREST upgrade. The role is created in migration 228 (this feature), and the rename aligns the role's name with its actual purpose ("no anon access allowed"), so no reader will mistake it for a grant target.

**Alternatives considered:**
- Keep `web_anon` with stripped grants — rejected because migration 218 drops the role entirely.
- Unset `PGRST_DB_ANON_ROLE` — rejected because PostgREST 12.2.3 crashes on startup.
- Upgrade PostgREST to a version that allows unset — out of scope for this feature and has its own compatibility audit.

---

## R-005: Tier → role mapping

**Decision:** Every current tier (`unlimited`, `high`, `standard`) maps to the single database role `api_user`. The mapping lives in `src/dk_data/metering_proxy/jwt_mint.py:TIER_TO_ROLE` as a dict.

**Rationale:** `api_user` already exists in the database (verified via `SELECT rolname FROM pg_roles`). It is the SELECT-only role the documentation describes. A second role (`analyst`) could be added later for tiers that need write paths or fuzzy-search functions — the mapping dict makes this a one-line change with no caller impact. Keeping the first cut to one role removes an entire category of "what does this tier grant" design questions and lets us ship.

**Alternatives considered:**
- Introduce `analyst` in v0.1 for the `high` tier — rejected because no consumer currently needs write access via the proxy, and splitting tiers creates a second grant-management migration we would have to maintain.
- Use the consumer alias as the role name (one role per consumer) — rejected because it pushes policy into the database layer instead of keeping it in the proxy's allowlist, and PostgREST would need every consumer's role pre-created.

---

## R-006: Secret loading — startup vs lazy

**Decision:** Load once at container startup inside `app.lifespan()`. Cache in a module-level variable. Never re-read.

**Rationale:** The secret is static for the lifetime of a pod — it comes from a k8s secret mount that is only re-read on pod restart. Re-reading on every request would waste a syscall and provide no fresh value. Loading at startup surfaces misconfiguration (missing secret, too-short secret) before any traffic arrives, which makes the readiness probe the single source of truth.

**Alternatives considered:**
- Lazy load on first request — hides startup failures until traffic arrives. Rejected.
- Watch the k8s secret for changes — unnecessary because k8s restarts the pod when the secret mount changes and we want the restart anyway so startup checks run.

---

## R-007: Startup self-test

**Decision:** At container startup, the metering proxy mints a test JWT and issues a single `GET /health` to PostgREST (`http://localhost:3000/health`) with the test JWT in the Authorization header. If PostgREST responds with anything other than a 2xx, the proxy fails its readiness probe and logs a structured error. The self-test runs once and is idempotent.

**Rationale:** This is the cheapest possible end-to-end sanity check for the shared-secret configuration. If the proxy and PostgREST have different values of `JWT_SECRET`, PostgREST will reject the JWT with a signature failure. Running the check at startup means a misconfigured deploy never takes traffic, which is much safer than discovering the mismatch on the first real request. A periodic self-test was considered and rejected because the secret cannot change under a running process — the startup check is sufficient.

**Alternatives considered:**
- Periodic self-test (every 30s) — rejected as unnecessary; the secret is static.
- No self-test at all — rejected because the failure mode (all requests 401) is user-visible and worth catching at deploy time instead of in a pager.

---

## R-008: Schema grant scope

**Decision:** Grant `USAGE` on 13 schemas (mol_silver, mol_gold, mol_api, hcs_silver, hcs_gold, ind_silver, ind_gold, hcp_silver, hcp_gold, ip_silver, ip_gold, mart, scoring) and `SELECT` on every existing table. Use `ALTER DEFAULT PRIVILEGES` so future tables inherit the grant.

**Rationale:** The metering proxy enforces the per-consumer schema allowlist BEFORE any database query runs (via `check_schema_access` in `schemas.py`). The database grants are a second, coarser layer whose only job is "is this schema reachable at all from `api_user`". Granting `api_user` access to every schema the product exposes is safe because a consumer can only route to a schema that is both in their `allowed_schemas` AND granted to `api_user`. The intersection is the effective access.

Schemas intentionally NOT granted to `api_user`: `staging`, `application`, `public`, `agents`, `hcs_agents`, `mol_agents`, `xenon`, `meta`. These are either internal state, administrative, or legacy/empty (the `mol_agents` and `hcs_agents` stubs are being consolidated into `agents` per the CLAUDE.md note).

**Alternatives considered:**
- Grant only what the P1 consumers actually use today — rejected because the allowlist layer is already doing that job, and a minimal grant set means every new client call would need a migration.
- RLS policies with per-consumer row filters — rejected as out of scope and a much larger security design.

---

## R-009: Migration ordering for drop-web-anon

**Decision:** Rename the drop-web-anon migration from `218_drop_web_anon.sql` to `229_drop_web_anon.sql` (and its rollback companion from `218_drop_web_anon_rollback.sql` to `229_drop_web_anon_rollback.sql`) on this feature branch. The new schema-grant migration keeps the number 228. This way the migration runner executes them in natural numeric order: 228 (create `dk_data_no_anon`, grant `api_user`) runs first, then 229 (drop `web_anon`) runs second, after the prerequisite role already exists.

**Rationale:** The earlier design (pre-flight DO guard inside 218) is broken: the migration runner stops on the first failure, so if 218 runs before 228 and its guard raises, the runner never advances to 228. The deploy is stuck. A DO guard only works if the migration that creates its prerequisite has already been applied — which is the opposite of the situation here.

Renaming is safe because `218_drop_web_anon.sql` merged in PR #280 but has NOT been applied to any environment yet (the `db-migrate` job last ran before the merge). Renaming the file on this branch is effectively "the migration was always numbered 229". The rename is recorded in the PR description and in `memory/changelog.md` so no reviewer is surprised.

**Alternatives considered:**
- Keep 218 as-is and add the DO-guard hack — rejected because the runner's "stop on first failure" behavior means 218 never gets to run.
- Fractional numbering (218a, 218.5, 219) — rejected because the runner sorts purely by numeric prefix and does not understand fractions.
- Merge 228 into 218 (one big migration) — rejected because it conflates two unrelated concerns (schema grants vs. role drop) and makes rollback harder.
- Revert 218 entirely in this PR and add it back as 229 — same outcome as rename, but with more churn in the diff. Rename is the minimal move.

---

## R-010: Live integration test runner

**Decision:** A manual-trigger GitHub Actions workflow at `.github/workflows/integration-live.yaml` that uses `workflow_dispatch`, pulls a dedicated test consumer API key from GitHub Actions secrets, and runs `packages/dk-data-client/python/tests/integration/test_live_client.py` against `https://data.behaviorlabs.ai`.

**Rationale:** Per-PR CI would need a disposable cluster (expensive and slow) or a stub PostgREST (doesn't validate the cluster path, which is the whole point). A manual-trigger workflow runs only when an operator wants the verification — after every production deploy, after a major configuration change, after a suspected regression. The unit test suite covers the per-PR regression bar; this workflow covers "does it actually work end-to-end in production".

**Alternatives considered:**
- Nightly scheduled run — rejected as noise; unit tests catch regressions and nightly would only find production issues.
- Per-PR against a disposable test cluster — rejected as too expensive and slow.
- Per-PR against a stub — defeats the purpose of the integration test.

---

## R-011: Observability — metric emission site

**Decision:** Increment `metering_proxy_jwt_minted_total{tier}` at the injection site inside `proxy.py`, immediately after `Authorization: Bearer <token>` is added to the forwarded headers. Increment `metering_proxy_jwt_mint_errors_total{error_type}` inside the `except JWTMintError` block.

**Rationale:** Emission at the injection site means the counter reflects actual forwarded requests, not just successful mint operations. A JWT minted but never forwarded (because of a downstream failure between mint and send) is still counted — which matches how operators think about the signal ("how many requests reached PostgREST with a valid JWT").

**Alternatives considered:**
- Emit inside `jwt_mint.mint()` — would count mints that then get dropped, which is misleading.
- Emit after receiving the PostgREST response — delays the metric and adds handling complexity with no benefit.
