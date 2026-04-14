# Feature: Metering Proxy JWT Minting

## Summary

Make the dk-data metering proxy mint short-lived JWTs for every authenticated request so that PostgREST can switch to a real database role with the right schema permissions. Today the proxy validates the raw API key but strips the `Authorization` header without replacing it, so PostgREST treats every call as anonymous and the client cannot read anything from the silver or gold hubs. This feature closes that gap, grants the target role the schema access it needs, and unblocks the dk-data-client package that was shipped in PR #280.

## User Scenarios & Testing

### US-1: Client application reads silver data through a valid API key (P1)

**As a** consumer application (BehaviorLabs, Carbon-5, DK-OS) holding a valid API key,
**I want to** call `molecules.resolve(...)` and other silver-hub reads through the dk-data-client,
**so that** I can actually retrieve data from dk-data without falling through to upstream APIs on every call.

**Acceptance Scenarios:**

```gherkin
Given a consumer with a valid API key provisioned in the metering proxy's consumer registry
And silver-hub data exists in mol_silver
When the consumer sends "GET /mol_silver/molecules?name_or_id=aspirin" with "Authorization: Bearer <api_key>"
Then the response status is 200
And the response body contains at least one molecule record
And the dk-data telemetry event for this call reports outcome="miss" (or "hit" on repeat) with cache_tier="none" or "l1"/"l2"
And the consumer's own audit log shows the call completed successfully
```

```gherkin
Given a consumer with a valid API key
When the consumer calls a silver-hub read endpoint multiple times within a short window
Then every call succeeds
And the proxy's per-consumer concurrency guard enforces the configured max_in_flight
And no request ever reaches PostgREST as the anonymous database role
```

```gherkin
Given a consumer with a valid API key but whose tier is not granted access to the requested schema
When the consumer attempts to read from that schema
Then the proxy rejects the request at the allowlist layer with a 403
And no JWT is minted for a schema the consumer is not allowed to reach
```

**Edge Cases:**

- The consumer rotates to a new API key between requests — both keys work while both are listed, and requests flow through with the correct tier mapping.
- The consumer sends a pre-minted JWT in `Authorization: Bearer` expecting it to pass through — the proxy rejects it with 401 because the metering proxy is the only authority that mints JWTs.
- The target database role exists but has no grants on the requested schema — the request fails with a clear 403 from the database layer and the proxy emits a structured error event, not a generic 500.

---

### US-2: Every authenticated request reaches the database as a real role, never as `web_anon` (P1)

**As a** platform operator,
**I want to** guarantee that every request that reaches PostgREST carries a valid JWT whose role claim maps to a real, granted database role,
**so that** the anonymous-role fallback (`PGRST_DB_ANON_ROLE`) is unreachable in practice and a misconfigured consumer cannot accidentally exercise unauthenticated access to any schema.

**Acceptance Scenarios:**

```gherkin
Given the metering proxy is running and the consumer registry is loaded
When any request arrives at PostgREST via the metering proxy
Then the forwarded request carries a bearer JWT signed with the shared signing secret
And the JWT's role claim is a non-anonymous database role present in pg_roles
And the JWT's subject identifies the consumer alias that passed the API key check
And the JWT's expiration is no further than sixty seconds in the future
```

```gherkin
Given the anonymous-role fallback in PostgREST has been disabled
When an unauthenticated request somehow reaches PostgREST (misconfiguration, bypass, accident)
Then the request is rejected with a 401 at the database layer
And no query is executed against any schema
```

**Edge Cases:**

- The signing secret is rotated — both old and new tokens are accepted for a brief grace window, or the proxy re-mints on the next request; the operator runbook describes the procedure.
- PostgREST and the proxy see different values of the signing secret — the proxy detects the mismatch on startup via a self-test call and fails the readiness probe instead of silently issuing tokens PostgREST will reject.
- A JWT minted sixty seconds ago arrives at PostgREST after a long network pause — PostgREST rejects it as expired and the client retries; the proxy mints a fresh one.

---

### US-3: `web_anon` can be safely dropped without breaking the API (P1)

**As a** platform operator,
**I want to** apply the pending migration that drops the `web_anon` database role,
**so that** there is no anonymous database identity a future misconfiguration could expose, and the project's defense-in-depth posture matches the documentation.

**Acceptance Scenarios:**

```gherkin
Given the JWT minting feature is deployed to the cluster
And the PostgREST configuration no longer treats an unauthenticated request as "web_anon"
When the pending "drop web_anon" database migration is applied
Then every existing client request continues to succeed
And no PostgREST replica logs "role web_anon does not exist"
And no consumer receives a 500 response during or after the migration
```

```gherkin
Given the JWT minting feature is not yet deployed
When someone attempts to apply the "drop web_anon" database migration
Then a pre-flight check fails with a clear message pointing at this feature as the blocker
And the migration is not applied
```

**Edge Cases:**

- The rollback path for the `web_anon` drop must be exercised and documented — if minting fails, the operator can re-create `web_anon` with the original grants from a recorded snapshot.
- A dashboard, script, or third-party tool is still using the old anonymous path — those callers are inventoried and migrated before the drop.

---

### US-4: The target database role has exactly the schema access the product promises (P2)

**As a** data platform maintainer,
**I want to** grant the target database role USAGE and SELECT on the silver, gold, mart, and scoring schemas the product exposes,
**so that** a valid client request actually succeeds at the database layer and the proxy-layer allowlist is the only thing gating per-consumer access.

**Acceptance Scenarios:**

```gherkin
Given the JWT minting feature has switched every authenticated request to the target database role
When the role runs a SELECT against any table in mol_silver, mol_gold, mol_api, hcs_silver, hcs_gold, ind_silver, ind_gold, hcp_silver, hcp_gold, ip_silver, ip_gold, mart, or scoring
Then the query succeeds
And no schema returns "permission denied" for a granted caller
And the same query from a tier that is not allowed the schema still fails at the proxy allowlist layer with 403
```

```gherkin
Given a new table is added to a granted schema after the feature lands
When a client reads the new table
Then the read succeeds without requiring a manual GRANT for that specific table
```

```gherkin
Given the target role attempts to write, delete, or alter any object
When the proxy forwards that request
Then the database rejects it because only SELECT and EXECUTE are granted
```

**Edge Cases:**

- Schemas that are listed in `PGRST_DB_SCHEMAS` but were intentionally never meant to be client-facing (e.g. `staging`, `application`, `public`) do not receive grants to the target role.
- Resolve functions across every hub are executable by the target role (extends the prior migration that granted `EXECUTE` on `mol_silver.resolve_molecule`).

---

### US-5: Observability and operator confidence (P2)

**As a** platform operator on call,
**I want to** see at a glance that JWT minting is healthy, that every forwarded request carries a valid token, and that no anonymous-role queries are leaking through,
**so that** I can verify the feature is working after deploy and catch regressions before consumers notice.

**Acceptance Scenarios:**

```gherkin
Given the metering proxy is running
When the operator views the dk-data metering proxy dashboard
Then there is a panel showing the rate of JWTs minted per second, broken down by consumer tier
And there is a panel showing the count of PostgREST requests that executed as the anonymous role over the last 5 minutes (should be zero)
And there is an alert that fires if the minted-JWT success rate drops below 99.9 percent over 5 minutes
```

```gherkin
Given the signing secret is misconfigured in either the proxy or PostgREST
When the proxy boots
Then the readiness probe fails within the startup budget
And the container logs include a structured error identifying which side is out of sync
And no traffic is routed to the pod until the mismatch is resolved
```

**Edge Cases:**

- The metric is bound to a dashboard panel **and** at least one alerting rule at launch — per the project's three-way binding rule, a metric without a consumer is dead code.

---

## Requirements

### Functional Requirements

- **FR-001**: After the metering proxy validates a consumer's API key and allowlist, it MUST attach a bearer JWT to every request it forwards to the upstream database API gateway; the forwarded request MUST NOT carry the consumer's raw API key in any header.
- **FR-002**: The attached JWT MUST be signed with the shared signing secret that PostgREST is configured to validate, so PostgREST accepts it without additional wiring.
- **FR-003**: The JWT MUST contain a role claim whose value is a real database role that exists in `pg_roles`; the claim value MUST be derived from the consumer's tier according to a documented mapping table.
- **FR-004**: The JWT MUST contain a subject claim whose value is the consumer's alias (not the raw API key), so downstream logs and audit trails can correlate requests to consumers without leaking credentials.
- **FR-005**: The JWT MUST contain an issuer claim identifying the metering proxy, an issued-at timestamp, and an expiration timestamp no more than sixty seconds in the future.
- **FR-006**: The signing secret MUST be read from the container environment at startup, cached for the process lifetime, and never re-read from disk on a per-request basis.
- **FR-007**: The metering proxy MUST verify at startup that the signing secret is present and meets the minimum length required by the signing algorithm; if either check fails, the readiness probe MUST remain failed and no traffic MUST be routed to the pod.
- **FR-008**: The metering proxy MUST expose a liveness self-test that mints a token and sends a lightweight call to PostgREST to confirm end-to-end JWT acceptance; if the self-test fails, readiness MUST flip to not-ready and remain that way until it succeeds.
- **FR-009**: For every successful authenticated request, the metering proxy MUST increment a "jwt minted" counter labeled by consumer tier; the counter MUST be bound to a Grafana dashboard panel and at least one alerting rule in the same release.
- **FR-010**: The metering proxy MUST expose a gauge or counter that identifies how many requests reached PostgREST as the anonymous database role in the last window; the expected steady-state value is zero.
- **FR-011**: The database target role MUST be granted USAGE on every schema the product currently exposes as a client-readable surface — mol_silver, mol_gold, mol_api, hcs_silver, hcs_gold, ind_silver, ind_gold, hcp_silver, hcp_gold, ip_silver, ip_gold, mart, and scoring — and MUST be granted SELECT on every existing table in those schemas.
- **FR-012**: The grants MUST use `ALTER DEFAULT PRIVILEGES` so that tables added to a granted schema after the feature lands inherit the same SELECT grant automatically.
- **FR-013**: The target role MUST be granted EXECUTE on every `resolve_*` function across every hub — extending the existing grant that only covered `mol_silver.resolve_molecule`.
- **FR-014**: The target role MUST NOT be granted INSERT, UPDATE, DELETE, TRUNCATE, or DDL privileges on any schema, table, or function; write paths MUST remain reserved for dedicated service accounts.
- **FR-015**: Client requests for a schema not in the consumer's per-consumer allowlist MUST be rejected by the proxy's existing allowlist check BEFORE a JWT is minted; the unauthorized schema MUST NOT appear in any JWT claim.
- **FR-016**: The PostgREST configuration MUST be changed so that an unauthenticated request (one without a valid JWT) is rejected at the database API gateway layer instead of being served as the anonymous database role.
- **FR-017**: The existing "drop web_anon" database migration MUST be applied in the same deploy window as this feature, OR applied after this feature is verified healthy; applying the migration before this feature deploys MUST be prevented by a pre-flight check.
- **FR-018**: The live integration test suite for the dk-data-client package MUST be updated to run against the real cluster path (client → metering proxy → PostgREST → database) and MUST pass before the feature is declared complete.
- **FR-019**: Operator documentation — consumer-onboarding, metering-proxy-401-debug runbook, rollback-web-anon-drop runbook — MUST be updated to describe the actual behavior introduced here; the current drift between docs and code MUST NOT be carried forward.
- **FR-020**: The feature MUST NOT log or emit the raw API key, the minted JWT, or the signing secret to any structured log, audit sink, or telemetry stream; correlation between a log line and a consumer MUST happen via the consumer alias only.

### Key Entities

| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| Consumer | A registered caller of dk-data identified by API key and tier | alias, tier, allowed_schemas, rpm_limit, max_in_flight, api_keys |
| Consumer Tier | A category that determines which database role the proxy mints a JWT for | tier name, mapped_db_role |
| Minted JWT | A short-lived signed token the proxy attaches to every forwarded request | subject (consumer alias), role (db role), issuer, iat, exp |
| Target Database Role | The database identity every authenticated request executes as | role name, granted schemas, granted functions, granted privilege set |
| Schema Grant | A mapping of target role to schema with a specific privilege set | role, schema, privilege set, default-privilege flag |

---

## Success Criteria

- **SC-001**: A live integration test that exercises the dk-data-client against the real cluster completes successfully for at least one hub-read method (e.g. resolve a known molecule) on the first attempt after the feature is deployed.
- **SC-002**: The count of PostgREST requests executed as the anonymous database role, over any rolling 5-minute window measured after the feature is deployed, is zero.
- **SC-003**: The p99 added latency of the JWT minting step on the metering proxy hot path is under one millisecond when measured over a representative sample of at least 1,000 requests.
- **SC-004**: After the `web_anon` database role is dropped, the error rate of the metering-proxy-to-PostgREST leg remains indistinguishable from its pre-drop baseline, measured over a rolling 15-minute window.
- **SC-005**: Zero regressions are introduced in the existing metering-proxy test suites (auth, schema allowlist, audit, concurrency, rate limiting).
- **SC-006**: No raw API key, minted JWT, or signing secret appears in any log stream, audit record, or telemetry event after the feature is deployed; a reviewer can grep the ingestion of a full day's logs for a known API key prefix and find zero matches.
- **SC-007**: Every schema the product advertises as client-readable responds successfully to a SELECT from the target database role on the first attempt; a reviewer can check this by running one representative query per advertised schema.
- **SC-008**: The feature's observability metric for minted JWTs is bound to at least one live Grafana dashboard panel and at least one alerting rule in the same release that introduces the metric.
- **SC-009**: The consumer-onboarding and metering-proxy-401-debug documents, after this feature merges, describe the actual runtime behavior; an external reviewer following either document end-to-end reaches a working consumer without needing to consult the code.

---

## Assumptions

- The existing per-consumer allowlist layer in the metering proxy is correct and stays in place; this feature does not change how the proxy decides *whether* to forward a request, only *how* the request is identified to the database gateway once it has been cleared.
- The consumer registry's shape (raw API keys under each consumer) is accepted as the starting point. Hashing, rotation automation, and a platform-side provisioning API are tracked separately and are explicitly out of scope.
- The shared signing secret is already wired into the PostgREST container and has a length acceptable to the signing algorithm; this feature adds the same wiring to the metering proxy side.
- Only a single database role (`api_user`) is needed for the first cut. A second, more privileged role (e.g. `analyst`) can be added later as a follow-on if a consumer tier needs write or fuzzy-search paths that `api_user` does not have.
- Per-row access control is not required for this feature; allowlist-at-proxy plus schema-level grants are the two defense-in-depth layers.
- The live integration test environment has at least one row of silver-hub data for a well-known test molecule (e.g. aspirin) by the time this feature is validated; if the WAL-archiving and silver-transform work is not yet complete, the integration test runs against a seeded fixture dataset instead of the full production silver.
- The deploy window for this feature can be coordinated with the deploy window for the already-merged migration 218 (drop `web_anon`); the two must land together or in the order: this feature first, then the migration.
- Migration numbering picks up where existing SQL migrations left off; the new schema-grant migration takes the next available number (228) without colliding with any unmerged migration.
- Operators have read-only access to the metering proxy logs via Loki and to the PostgREST logs via the same sink; there is no separate audit pipeline required for this feature to meet its observability bar.

## Clarifications

### Session 2026-04-14 (autonomous, dk.auto)

- **Q:** How should PostgREST reject unauthenticated requests — unset `PGRST_DB_ANON_ROLE` entirely, or point it at a permission-less role?
  **A:** Create a new permission-less database role `dk_data_no_anon` with zero grants on any schema, and point `PGRST_DB_ANON_ROLE` at it. Unsetting is not an option because PostgREST 12.2.3 requires the setting. Reusing `web_anon` with stripped grants conflicts with migration 218 which drops it. This is the minimal defensive pattern.

- **Q:** Does the proxy support dual-secret rotation for the JWT signing secret, or does it rely on short TTL + per-request minting to make rotation safe?
  **A:** Rely on short TTL + per-request minting. A 60-second JWT TTL means a secret rotation propagates to every in-flight token within sixty seconds with zero dual-secret complexity. Dual-secret support is deferred to a follow-on if operators ever hit a real rotation scenario this does not cover.

- **Q:** Is the end-to-end self-test (mint a token, call PostgREST, verify acceptance) startup-only or periodic?
  **A:** Startup-only. A periodic self-test would add a hot-loop call to PostgREST and is only useful if the signing secret can change under a running process — which it cannot, because the secret is read once at startup. Rolling-deploy readiness probes catch the same condition with zero extra code.

- **Q:** How is the ordering guaranteed so that the drop-`web_anon` migration runs AFTER the schema-grant migration?
  **A:** Rename the drop-`web_anon` migration from `218_drop_web_anon.sql` to `229_drop_web_anon.sql` on this feature branch (same for its rollback companion). The new schema-grant migration is 228. The migration runner sorts by numeric prefix, so 228 applies before 229. This is safe because 218 was merged in PR #280 but has not been applied to any environment yet — the rename is effectively "the migration was always 229". (The original design used a pre-flight DO block inside 218, but that design is broken because the runner stops on first failure: if 218 runs before 228, the DO block raises and 228 never runs. Rename is the correct fix.)

- **Q:** How does the live integration test run — in CI on every pull request, in a scheduled job, or only manually?
  **A:** Manual-trigger GitHub Actions workflow (`workflow_dispatch`) that runs against `data.behaviorlabs.ai` with a test consumer API key stored in GitHub Actions secrets. CI-on-every-PR would require a disposable cluster or a fixture-based stub that would not validate the cluster path. Unit tests cover the regression bar; the integration workflow captures the intent of "does it actually work end-to-end against the real cluster".

### Integration of decisions into the spec

- FR-016 is interpreted to mean: PostgREST is configured with `PGRST_DB_ANON_ROLE=dk_data_no_anon`, and `dk_data_no_anon` is created in migration 228 with zero schema grants.
- FR-017's ordering enforcement is implemented by renaming the drop-web-anon migration from 218 to 229 so it sorts after 228 in the migration runner (a DO-block pre-flight guard is not used because the runner stops on first failure, which would deadlock 228 behind a guard in 218).
- FR-018's live integration test is a manual-trigger GitHub Actions workflow, not part of per-PR CI.
- FR-008's self-test runs once at container startup, not periodically.
- The JWT TTL is exactly 60 seconds and the proxy does NOT support dual-secret rotation in this release.
