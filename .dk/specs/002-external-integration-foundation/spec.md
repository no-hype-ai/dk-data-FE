# Feature: dk-data External Integration Foundation

## Summary

Make dk-data-FE the authoritative read surface for every external DataKinetic consumer by (1) shipping a standardized client package (TS + Python) from `packages/dk-data-client/` in this repo with auto-fallback, caching, and telemetry; (2) closing every unauthenticated access path so the metering proxy gateway is the only way in; (3) filling the missing consumer-visible data surfaces; and (4) driving future hydration decisions from real usage telemetry instead of guesswork — so that consuming teams stop writing per-app connectors to upstream APIs and every external request is authenticated, metered, and observable.

## Scope

**This spec covers everything that happens inside the dk-data-FE repository**, including the client package as an in-repo subdirectory under `packages/dk-data-client/`. The consuming-app-side migration (replacing hand-rolled clients inside behavior-labs-ai / ground-truth-charlie / trials-predictor repos) is tracked separately in each consumer's own spec and is **out of scope** here. Infrastructure repos (Loki retention, cluster-level configs not in `k8s/apps/`) are also out of scope.

## User Scenarios & Testing

### US-1: Standardized adapter package for every consumer (P1)

**As a** developer of any DataKinetic consuming app, **I want to** obtain dk-data entities through a single typed client with caching, auto-fallback, and telemetry, **so that** I never write a custom hook to fetch molecule / trial / publication data again and my app contributes to dk-data population as a side effect of normal traffic.

**Acceptance Scenarios:**

```gherkin
Given the standardized dk-data client is installed in a consuming app
When the app previously fetched molecule data via a hand-rolled function
Then the same call now goes through the client with no observable behavior change from the caller's perspective

Given a request for a molecule that dk-data does not yet have
And the client is configured with automatic-hydration behavior
When the caller asks for the molecule profile
Then the client fetches from the upstream source, returns the result to the caller, and records the result in dk-data for future callers
And the caller's code does not contain any reference to the upstream source

Given the client is in use across multiple consuming apps
When dk-data adds a new field to an existing entity
Then the client's type definitions update automatically in the next release without consumer code changes

Given an authentication failure
When the client surfaces the error to the caller
Then the caller receives a typed authentication error (not a generic error)
And the caller can handle it distinctly from a not-found error, a rate-limit error, or a stale-data error

Given a cache hit on a recently fetched entity
When the same entity is requested again within its freshness window
Then the second request is served from the local cache without contacting dk-data
And cache freshness respects the entity type (identifiers cached for days, trial status for hours, resolution queue never cached)
```

**Edge Cases:**

- A consuming app receives a stale response (data older than its staleness threshold) — the client must surface this distinctly so the caller can choose to proceed or trigger a refresh.
- A rate-limit rejection from dk-data — the client retries with backoff and only surfaces the error if retries are exhausted.
- A consuming app's API key is revoked mid-session — the next request surfaces a typed authentication error with a clear cause.
- The client's hydration fallback triggers but the upstream source is also unreachable — the caller receives a typed upstream error distinct from a dk-data error.
- A consuming app uses the client with strict mode (no hydration fallback) in a context that should not implicitly fetch from upstream sources (e.g., an evidence pipeline) — the client must refuse to fall through.

---

### US-2: Every read path behind authentication (P1)

**As a** dk-data operator, **I want to** ensure every consumer-facing read path requires a valid credential, **so that** no data leaves dk-data anonymously and every external access is auditable.

**Acceptance Scenarios:**

```gherkin
Given dk-data is reachable through its public gateway
When a request arrives without an authentication credential
Then the request is rejected before any data is read from the warehouse

Given dk-data is reachable through its public gateway
When a request arrives with an unknown or expired credential
Then the request is rejected with a clear reason

Given the legacy anonymous read role exists in the database
When the lockdown completes
Then the role no longer exists and cannot be recreated without explicit administrator action

Given the cluster's health monitoring
When the lockdown completes
Then liveness, readiness, and startup checks continue to pass without any anonymous carve-out

Given a consuming app authenticates successfully
When its request is forwarded to the read layer
Then the request is tagged with the consumer's identity for audit and rate-limit accounting
```

**Edge Cases:**

- A legitimate consumer's credential is provisioned but not yet propagated to the gateway — the request fails cleanly and a runbook exists to diagnose.
- A credential is leaked — a documented rotation procedure exists and completes within minutes.
- An internal cluster service bypasses the gateway by connecting directly to the warehouse — that path must also require authentication or be explicitly documented as an exempt internal path.
- A new consuming app arrives and needs access — onboarding requires updating the consumer registry before the app can read anything.

---

### US-3: Consumer onboarding through an enforced gateway (P1)

**As a** dk-data operator, **I want to** issue every consuming app its own credential, rate-limit budget, and explicit schema allowlist, **so that** usage is attributed, abuse is contained, and a new consumer cannot accidentally access data outside its scope.

**Acceptance Scenarios:**

```gherkin
Given the consumer registry has entries for every active consuming app
When a request arrives
Then the gateway identifies the consumer from its credential and applies the consumer's rate limit and schema allowlist

Given a consumer is restricted to a specific list of schemas
When the consumer requests data from a schema not on its list
Then the gateway rejects the request before it reaches the warehouse

Given a consumer exceeds its per-minute rate limit
When the next request arrives within the same window
Then the gateway rejects the request with a rate-limit error

Given any request reaches the gateway
When the request completes
Then an audit record captures the consumer identity, the resource accessed, the status code, and the latency

Given the internal service consumer used to have an unrestricted wildcard allowlist
When the consumer registry is updated
Then the internal consumer is scoped to an explicit list of schemas and any new internal caller must update the list
```

**Edge Cases:**

- A consumer's allowlist needs to expand because a new domain is added to dk-data — the change is a single registry edit, not a code change.
- Two consumers share the same underlying infrastructure but have different rate limits — the gateway still attributes usage per credential.
- The audit log is unavailable temporarily — requests still succeed but a monitoring alert fires on audit-log write failures.

---

### US-4: Complete the molecule data surface that consumers already call (P1)

**As a** consuming-app developer, **I want to** call every documented molecule endpoint (boxed warnings, contraindications, competitive scores, companies, publications) and receive real data, **so that** my admin UI stops showing "not found" for resources that the rest of the system implies should exist.

**Acceptance Scenarios:**

```gherkin
Given dk-data has molecule data ingested
When a consumer requests boxed warnings for a specific molecule
Then a structured response is returned with the warning text and severity

Given dk-data has molecule data ingested
When a consumer requests contraindications for a specific molecule
Then a structured response is returned

Given dk-data has competitive landscape data for an indication
When a consumer requests competitive scores for a molecule in that indication
Then numeric scores are returned

Given dk-data has company hub data
When a consumer requests a company by identifier
Then a flattened company profile with identifiers and names is returned

Given dk-data has publication data ingested
When a consumer requests publications for a molecule
Then a unified response with PubMed and OpenAlex entries is returned — the caller does not need to call two different endpoints
```

**Edge Cases:**

- A molecule has no boxed warning — the endpoint returns an empty structured response, not a not-found error.
- A molecule exists in silver but has no gold-layer aggregation — the endpoint returns what's available and flags the gap.
- The publications endpoint encounters a row with a missing canonical field (DOI, PMID) — the row is still returned with null for the missing field.

---

### US-5: All silver-hub resolve operations reachable from consumers (P1)

**As a** consuming-app developer, **I want to** canonically resolve any entity type (molecule, drug product, target, condition, company, provider, facility, researcher, patent, trademark, design) from a name or identifier, **so that** my app links external data to dk-data canonical IDs without running its own normalization logic.

**Acceptance Scenarios:**

```gherkin
Given all 11 silver-hub resolve operations exist in dk-data
When a consumer calls any of them with a name or identifier
Then the canonical entity ID, confidence score, and match tier are returned

Given a caller passes an identifier of a specific type
When the resolve operation runs
Then the type is used as a hint to prioritize the correct identifier tier

Given the same name is resolved twice
When the second call arrives within the cache freshness window
Then it is served from the client cache without contacting dk-data
```

**Edge Cases:**

- A name that has no canonical match — the response indicates "not found" with a confidence score of 0.
- A name that matches multiple canonical entities at high confidence — the response returns the top match and a list of alternatives.
- A caller passes an invalid identifier format — the resolve operation returns a structured validation error.

---

### US-6: Consistent domain-prefix naming across all data surfaces (P2)

**As a** dk-data developer, **I want to** ensure every publication, regulatory, patent, and news surface is named with its canonical domain prefix, **so that** the schema discipline used throughout the codebase is not broken by a legacy set of unprefixed endpoints.

**Acceptance Scenarios:**

```gherkin
Given the 10 unprefixed publication and regulatory surfaces exist in the legacy namespace
When the rename completes
Then each surface is available under its canonical domain-prefixed name
And the legacy unprefixed name continues to work as a deprecated alias

Given consumers have migrated to the prefixed names
When the follow-up cleanup runs
Then the deprecated aliases are removed
And no consumer references the legacy names

Given a new surface is added in the future
When a reviewer checks the pull request
Then the surface is in a domain-prefixed namespace or explicitly justified as a cross-domain exception
```

**Edge Cases:**

- A consumer is still referencing the legacy unprefixed name after the rename — the deprecated alias serves the request but the access is logged for migration follow-up.
- A surface spans multiple domains — the canonical home is documented and cross-linked.

---

### US-7: Hydration priorities come from real usage telemetry (P2)

**As a** dk-data product owner, **I want to** prioritize the next data ingestion based on how often consuming apps actually fall through to upstream sources, **so that** we ingest the sources that consumers need most, not the ones guessed at planning time.

**Acceptance Scenarios:**

```gherkin
Given the standardized client has been in production for at least two weeks
When the hydration heat map dashboard is reviewed
Then it displays per-method hit/miss/fallthrough counts and latency percentiles

Given the heat map shows a specific method has the highest fallthrough volume
When the next ingestion cycle is planned
Then the corresponding upstream source is prioritized for ingestion

Given a new upstream source has been ingested into dk-data
When consuming apps next call the method backed by that source
Then the outcome shifts from fallthrough to cache hit or warehouse hit
```

**Edge Cases:**

- A method has high fallthrough volume but the underlying upstream source is licensed or paywalled — the prioritization decision defers to a build-vs-buy review.
- A method's fallthrough volume is dominated by one consumer — the prioritization review attributes usage per consumer to identify skew.

---

### US-8: Verified warehouse state before any consumer cutover (P1)

**As a** dk-data operator, **I want to** confirm the gold-layer aggregation tables have real data before exposing them to consumers, **so that** consuming apps do not see empty responses for endpoints that imply the data should exist.

**Acceptance Scenarios:**

```gherkin
Given the deployed dk-data cluster
When the operator queries the gold-layer aggregation tables for molecule profile, safety signals, lifecycle stages, competitive landscape, and company pipeline
Then every table has a non-zero row count

Given the nightly aggregation job runs
When the job completes
Then row counts in the gold tables stay constant or grow — never drop to zero

Given any gold table has been empty for more than 24 hours
When monitoring runs
Then an alert fires identifying the empty table
```

**Edge Cases:**

- A gold table is intentionally empty during an initial backfill — the alert is suppressed during the known backfill window.
- The nightly aggregation job fails — the row count stays constant (not zero) and a separate alert fires on the job failure.

---

### US-9: Consistent dk-data developer experience across environments (P2)

**As a** dk-data developer running the platform locally, **I want to** see the same set of exposed schemas whether I'm on my laptop, docker-compose, or the production cluster, **so that** local reproductions of bugs match production behavior.

**Acceptance Scenarios:**

```gherkin
Given a developer starts dk-data locally via the standalone or docker-compose path
When the developer queries the gateway for the list of exposed schemas
Then the list matches the production cluster's schema list

Given a new schema is added to production
When the dev configs are updated to match
Then local starts automatically expose the new schema on the next restart
```

**Edge Cases:**

- A production-only schema — document the exception explicitly in the dev configs.

---

### US-10: Single canonical gold-profile table name (P3)

**As a** dk-data developer, **I want to** have exactly one canonical "molecule profile" table in the gold layer, **so that** the generated type definitions and the data contracts are unambiguous.

**Acceptance Scenarios:**

```gherkin
Given the two current molecule profile tables (one singular, one plural)
When the consolidation completes
Then only one table exists
And the canonical choice is documented in the project-wide schema reference
And any view or code referencing the dropped name is updated
```

**Edge Cases:**

- Historical audit logs or analytics dashboards reference the dropped name — they are updated in the same change.

---

### US-11: Lineage graph stays accurate as sources are added and renamed (P2)

**As a** dk-data developer or operator, **I want to** have the pipeline lineage dashboard correctly classify every new ingestion source, every new consumer-visible surface, and every renamed endpoint, **so that** "where does this data come from and where does it go" remains answerable from a single place.

**Acceptance Scenarios:**

```gherkin
Given a new upstream source has been added with its bronze/silver/gold tables
When the lineage graph is rebuilt
Then the new source and its downstream edges appear in the correct domain and subdomain

Given the publication, regulatory, and patent surfaces have been renamed to domain-prefixed schemas
When the lineage graph is rebuilt
Then no edges break (the legacy unprefixed schema was already excluded from lineage tracking)

Given a new indication terminology source (UMLS, SNOMED, ICD) is added
When the lineage graph is rebuilt
Then the source is classified under a dedicated terminology subdomain, not the generic indication catalog bucket

Given a model is added that depends on a silver-hub resolve function
When the lineage graph is rebuilt
Then the model is tracked correctly, even though the function call is invisible to the SQL dependency parser
And the parser's known limitation is documented in code

Given any deploy that adds warehouse models
When a scheduled lineage rebuild runs afterward
Then the lineage graph reflects the new state without manual intervention
```

**Edge Cases:**

- A model introduces a new schema that is not yet classified — the rebuild reports it as "unclassified" and the developer adds a mapping before merging.
- A model rename breaks an existing edge — the rebuild detects the orphan and reports it.

---

### US-12: Every dashboard panel reflects real emitted metrics (P1)

**As a** dk-data operator or developer, **I want to** ensure every metric referenced by a monitoring dashboard is actually emitted by the running code and every metrics endpoint is actually scraped by the monitoring system, **so that** operational dashboards are not silently lying.

**Acceptance Scenarios:**

```gherkin
Given the platform is running with all metric endpoints exposed
When the monitoring system collects metrics
Then every metric endpoint is reachable and being scraped
And the scrape job name matches what dashboards filter on

Given every metric definition in the codebase
When a coverage check runs
Then every defined metric either has a corresponding emission call site or is deleted

Given every panel in every monitoring dashboard
When a coverage check runs
Then every metric name referenced by a panel is defined in the codebase AND has at least one emission call site

Given a developer adds a new metric definition
When the pull request is reviewed
Then the definition, the emission call site, and the dashboard panel must all be present or the check fails the build

Given the partially-broken job completion endpoint
When a batch job reports completion through it
Then all batch-job metrics (success timestamp, duration, records processed, failure count) are recorded, not just the success timestamp
```

**Edge Cases:**

- A metric was used by a single dashboard panel that is later removed — the coverage check flags the metric as orphaned and the developer either deletes it or re-attaches it to another panel.
- An emission call site is behind a feature flag that is disabled in production — the coverage check considers the emission present but the operator documents the gap in the runbook.

---

### US-13: REMOVED — consumer-side migration is tracked in the consuming-app repos

*US-13 covered behavior-labs-ai, ground-truth-charlie, and trials-predictor code changes that replace their hand-rolled dk-data clients with the standardized package. Those edits happen in separate repositories and are tracked in each consuming app's own spec. This spec no longer contains consumer-side tasks. FR-030 (API keys provisioned before role drop) and SC-024 (pre-drop consumer audit) still ensure dk-data-FE does not ship the lockdown until every consumer is verified working.*

---

### US-14: Automated tests prevent regression of every gap closed here (P2)

**As a** dk-data maintainer, **I want to** have automated tests that catch client regressions, broken grants in migrations, and dashboard panels referencing undefined metrics, **so that** no future pull request reintroduces the failure modes this initiative had to clean up.

**Acceptance Scenarios:**

```gherkin
Given the client package test suite
When tests run
Then every fallback mode is covered, every typed error is covered, and type generation is verified against an ephemeral dk-data instance

Given a pull request that adds a new warehouse model
When CI runs
Then the lineage builder picks up the new model, the grant checks pass for both analyst and api_user roles, and the metric coverage check passes

Given any pull request that touches a monitoring dashboard file
When CI runs
Then a smoke test verifies the dashboard renders in a test monitoring instance
And every metric reference in the dashboard is cross-checked against the codebase

Given the client version is bumped
When a contract test runs against the deployed dk-data version
Then the test fails if the type schema fingerprint no longer matches
```

**Edge Cases:**

- A test for a metric emission call site runs but the metric is only emitted behind a feature flag — the test suite explicitly handles flagged metrics.
- An ephemeral dk-data instance for integration tests is slow to spin up — the test strategy caches the instance across test runs when possible.

---

### US-15: Every direct warehouse-platform read route also requires authentication (P1)

**As a** dk-data operator, **I want to** ensure every direct route into the warehouse platform (not just the primary read gateway) requires a valid credential, **so that** the authentication lockdown actually closes all anonymous access, not just one of several paths.

**Acceptance Scenarios:**

```gherkin
Given the warehouse platform has a direct read surface alongside the primary gateway
When an unauthenticated request arrives on the direct surface
Then the request is rejected with a structured error

Given a valid credential minted by the gateway
When the same request is retried with the credential
Then the direct surface accepts it and returns the data

Given a credential with a role that is not allowed on the direct surface
Then the request is rejected with a clear role-mismatch error
```

**Edge Cases:**

- A k8s probe hits the direct surface — the probe continues to work because probes run at the TCP layer (not the data plane) per existing deployment config.
- A legacy credential with a now-removed role arrives — it is rejected as an invalid role, not a token-decoding failure.

---

### US-16: Documentation, runbooks, and captured lessons (P2)

**As a** future engineer working on dk-data or any consuming app, **I want to** read runbooks for the common operational failures, an updated getting-started guide, and captured lessons from past audits, **so that** I do not have to re-derive what this initiative spent weeks auditing.

**Acceptance Scenarios:**

```gherkin
Given the runbook directory after the initiative ships
When an engineer searches for "rotate signing secret", "rollback anonymous role drop", "gateway 401 debug", "telemetry fallthrough spike", or "dashboard no data"
Then a runbook exists for each with a documented procedure

Given the project README
When an engineer reads it after the initiative ships
Then it describes the client, the auth model, and the environment variables required to access dk-data

Given a new consuming-app team
When they read the consumer onboarding guide
Then they know how to request a credential, install the client, and make their first query

Given the lessons-learned memory file
When a future engineer reviews it
Then it contains the concrete lessons from this initiative, not just generic platitudes
```

**Edge Cases:**

- A runbook becomes stale because the underlying procedure changes — each runbook includes a "last verified" date and a pointer to the code it depends on.

---

### US-17: Cost, capacity, and operational sign-off (P2)

**As a** dk-data product owner, **I want to** have the cost and capacity implications of this initiative reviewed before the lockdown ships, **so that** infrastructure budget conversations happen before storage, compute, or log-ingestion volumes become surprises.

**Acceptance Scenarios:**

```gherkin
Given the planning artifacts for this initiative
When the infrastructure team reviews them
Then per-resource cost estimates exist for gateway compute, CI runs, log-ingestion volume, warehouse storage growth, and any new shared caching infrastructure

Given the log-ingestion path for client telemetry
When the team verifies it
Then the cluster has confirmed headroom for the expected telemetry volume

Given the new ingestion sources planned
When warehouse capacity is reviewed
Then the circuit breakers on the backfill orchestrator are confirmed to cover the new sources

Given the gateway will mint credentials on every request
When the connection pool is reviewed
Then the pool is sized appropriately for the new load
```

**Edge Cases:**

- A capacity decision cannot be made without more data — the decision defaults to the conservative option and is revisited after telemetry is live.

---

### US-18: Clarify the agents schema collision (P3)

**As a** dk-data developer, **I want to** have the relationship between the three agents schemas (unprefixed and two domain-prefixed) clarified, **so that** the same kind of collision that happened for the molecule profile tables does not repeat in the agents domain.

**Acceptance Scenarios:**

```gherkin
Given the three agents schemas
When the clarification completes
Then either they are documented as intentionally separate with a canonical purpose each, or a consolidation plan is recorded for follow-up
And the authoritative choice is captured in the project-wide schema reference
```

**Edge Cases:**

- A consolidation plan is adopted but cannot ship in the current phase window — the plan is deferred to a tracked follow-up with a concrete owner.

---

### US-19: Naming convention carve-outs documented (P3)

**As a** dk-data developer, **I want to** have the list of unprefixed schemas that are intentionally exempt from the domain-prefix rule documented in the project reference, **so that** new code reviewers do not flag them as violations or try to rename them mid-flight.

**Acceptance Scenarios:**

```gherkin
Given the project-wide schema reference
When a reviewer opens a pull request that adds a new unprefixed schema
Then the reference contains a clear list of exempt schemas and the rationale for each
And a new addition either matches an existing exemption category or requires justification

Given the existing unprefixed operational schemas
When the documentation ships
Then each one is listed with its purpose
```

**Edge Cases:**

- A previously exempt schema is later renamed to a prefixed form — the reference is updated in the same pull request.

---

### US-20: Cronjob consolidation, naming alignment, dead-job removal (P2)

**As a** dk-data infrastructure operator, **I want to** have redundant year-split cronjobs collapsed into **sequential parameterized jobs**, source naming aligned across the backfill state, raw tables, and ingestion modules, and known dead cronjobs removed, **so that** deployment syncs are faster, source naming is not ambiguous between layers, and operators do not run scheduled jobs that can never succeed.

**Dispatch model (per drift audit F-D016):** the consolidated chembl and pubchem cronjobs run **one year / one range per tick** via the existing backfill orchestrator. No parallel fan-out. Each tick reads `meta.backfill_state`, fetches the next un-processed year/range, updates state, exits. 17 ticks complete the chembl backfill; 6 ticks complete the pubchem backfill. After initial backfill, subsequent ticks keep the latest period current.

**Acceptance Scenarios:**

```gherkin
Given the cronjob base directory
When the consolidation completes
Then exactly one chembl-activities cronjob exists, running sequentially via the backfill orchestrator
And exactly one pubchem cronjob exists, running sequentially via the backfill orchestrator
And the 23 redundant per-year or per-range files are deleted

Given the consolidated chembl-activities cronjob
When it runs on a given cron tick
Then it reads meta.backfill_state to find the next un-backfilled year
And fetches exactly that year
And updates meta.backfill_state.last_year_processed
And exits
And no two ticks of the same job run concurrently (enforced by meta.job_locks)

Given the full initial backfill of chembl (17 years)
When the orchestrator runs every 10 minutes
Then the backfill completes within 170 minutes minimum wall clock
And no single tick's transaction exceeds the 2 GB WAL budget

Given the backfill state table and the raw table names
When the alignment completes
Then every source has a single canonical name used in the backfill state, the raw table, and the ingestion module
And a continuous check prevents future drift

Given the two dead cronjobs that target non-existent upstream data
When the cleanup completes
Then both are deleted
And nothing references them in runbooks, dashboards, or alerts

Given the deployment sync before and after
When comparing file counts
Then at least 25 fewer YAML files are synced
And no scheduled job behavior regresses
```

**Edge Cases:**

- A previously failing dead cronjob had its alerts muted — the cleanup also removes the mute rule.
- A consumer's allowlist referenced the old source name — the allowlist update ships in the same pull request.

---

## Requirements

### Functional Requirements

- **FR-001**: The platform MUST provide a single standardized client package (in the primary consuming-app language environments) that every consuming app uses to access dk-data entities.
- **FR-002**: The client MUST support three fallback modes for missing data: strict (fail), upstream (fetch from source, do not persist), hydrate (fetch from source and persist back to dk-data). v0.1 ships with strict + upstream; hydrate ships in v1.0 after the warehouse's ingestion endpoints are verified idempotent. After v1.0, all three modes MUST remain supported.
- **FR-003**: The client MUST emit exactly one structured telemetry event per call (no batching in v0.1; batching is deferred to v1.1 as an optimization). Each event contains outcome (hit/miss/stale/fallthrough/error), latency, and caller identity.
- **FR-004**: The client MUST generate its type definitions from dk-data's machine-readable API specification rather than hand-writing them.
- **FR-005**: The client MUST provide a two-tier cache: an in-process L1 (short-lived, per-handler) and a shared L2 (Redis in production, file-backed store in developer environments) with per-resource freshness windows.
- **FR-006**: The client MUST throw distinct typed errors for authentication failure, authorization failure, not found, stale data, upstream failure, rate limit, and server error.
- **FR-007**: The client MUST follow semantic versioning with type regeneration on minor releases and coordinated migrations on major releases.
- **FR-008**: dk-data MUST NOT have an anonymous read role after the lockdown; every request must present a valid credential.
- **FR-009**: The configuration that tells the read layer which role to use for unauthenticated requests MUST be unset across all environments (production, docker, standalone).
- **FR-010**: Every read response to an unauthenticated request MUST be a rejection at the authentication layer, including the health endpoint.
- **FR-011**: Every initialization script and migration that creates the legacy anonymous role MUST be removed and replaced with a guard that fails loudly on any reintroduction attempt.
- **FR-012**: The public gateway MUST reject requests with missing or unknown credentials with a clear error before any data is read.
- **FR-013**: The public gateway MUST mint short-lived credentials for the warehouse read layer from validated consumer API keys.
- **FR-014**: The public gateway MUST enforce per-consumer schema allowlists and reject out-of-allowlist requests.
- **FR-015**: The public gateway MUST audit every request with consumer identity, resource, status, and latency.
- **FR-016**: Every active consuming app MUST have a consumer registry entry with a provisioned credential.
- **FR-017**: The internal service consumer MUST have an explicit schema allowlist, not an unrestricted wildcard.
- **FR-018**: Each consuming app's allowlist MUST be sized to the schemas it actually needs, not broader.
- **FR-019**: A documented rotation procedure for the gateway's signing secret MUST exist before the lockdown ships.
- **FR-020**: Every direct warehouse-platform read route outside the primary gateway MUST also require a valid credential via a router-level authentication dependency.
- **FR-021**: The missing boxed warnings, contraindications, competitive scores, companies, and publications surfaces MUST be created with grants to authenticated roles only (not the anonymous role).
- **FR-022**: The boxed warnings and contraindications surfaces MUST source from the existing silver-layer drug-label columns, not from a non-existent drug-label-sections table.
- **FR-023**: The publications surface MUST unify the existing PubMed and OpenAlex publication feeds after they are relocated to their canonical domain-prefixed homes.
- **FR-024**: All 11 silver-hub resolve operations MUST be callable from consumers via a grant to authenticated roles.
- **FR-025**: Thin wrapper routes MUST exist for the non-molecule resolve operations (drug product, target, condition, company, provider, facility, researcher, patent, trademark, design) on the warehouse platform's direct surface.
- **FR-026**: The 10 unprefixed publication, regulatory, patent, and news surfaces MUST be relocated to their canonical domain-prefixed schemas.
- **FR-027**: Deprecated aliases in the legacy unprefixed schema MUST continue to serve requests during the migration window.
- **FR-028**: A follow-up cleanup MUST drop the deprecated aliases 30 calendar days after the last consuming app's migration to the prefixed names is verified in telemetry (no consumer should call the legacy alias during the 30-day observation window).
- **FR-029**: The migrations implementing the items in this initiative MUST be sequenced correctly: rename first, then missing views, then resolve-function grants, then anonymous-role drop.
- **FR-030**: Consumer credential provisioning MUST land before the anonymous-role drop to avoid a window where consumers are broken.
- **FR-031**: A rollback procedure for the anonymous-role drop MUST be documented and tested before the change ships. The rollback MUST restore only the minimum grants needed to unblock (USAGE on the public namespace + SELECT on health and catalog endpoints), NOT the full set of grants from the legacy migrations.
- **FR-032**: Every gold-layer aggregation table MUST be confirmed non-empty on production before consuming apps are cut over.
- **FR-033**: The standalone and docker-compose gateway configurations MUST expose the same schema list as the production cluster.
- **FR-034**: The duplicate molecule profile table (singular and plural) MUST be consolidated into exactly one canonical name.
- **FR-035**: Every new upstream source MUST be classified into the correct domain and subdomain in the lineage classifier in the same pull request that adds the source.
- **FR-036**: A dedicated indication-terminology subdomain MUST be created for UMLS, SNOMED, ICD, MeSH, and ATC.
- **FR-037**: The lineage rebuild MUST run on a schedule so the graph never goes stale relative to the deployed models.
- **FR-038**: The lineage classifier's inability to track SQL-function dependencies MUST be documented as a known limitation in the classifier code.
- **FR-039**: Every metric endpoint MUST be discoverable by the monitoring system.
- **FR-040**: The monitoring scrape job name MUST match the label selector used by every dashboard.
- **FR-041**: Every metric defined in the codebase MUST have at least one emission call site, or be deleted.
- **FR-042**: The pipeline processing duration and bronze ingestion duration metrics MUST be actively emitted.
- **FR-043**: The job completion endpoint MUST emit all four batch-job metrics (success timestamp, duration, records processed, failure count).
- **FR-044**: All 18 CMS-related metrics referenced by the CMS pipeline health dashboard MUST be emitted by the corresponding agent code paths.
- **FR-045**: A continuous-integration check MUST fail the build on: a metric definition with zero emission sites, a dashboard reference to an undefined metric, a warehouse model without proper grants, a lineage edge that cannot be classified, or a cronjob source name that drifts from the backfill state.
- **FR-046**: The three-way binding principle ("never add a metric definition without simultaneously adding an emission call site and a dashboard panel") MUST be recorded in the project-wide principles reference.
- **FR-047**: REMOVED — consumer-app upstream-call replacement is tracked in each consumer's own spec.
- **FR-048**: REMOVED — consumer-app localhost fallback removal is tracked in each consumer's own spec.
- **FR-049**: REMOVED — consumer-app typed-error catch-block handling is tracked in each consumer's own spec.
- **FR-050**: The client package test suite (in `packages/dk-data-client/`) MUST cover all fallback modes and all typed error classes.
- **FR-051**: The migration test suite MUST verify each migration in this initiative applies cleanly, has correct grants, and is reversible where applicable.
- **FR-052**: A dashboard smoke test MUST run in CI on every pull request that touches a dashboard file.
- **FR-053**: A hydration heat-map dashboard MUST exist and be ingesting client telemetry.
- **FR-054**: Six sources with mismatched names MUST be aligned across the backfill state, raw tables, and ingestion modules.
- **FR-055**: The 17 per-year chembl-activities cronjobs and 6 per-range pubchem cronjobs MUST be consolidated into 2 parameterized cronjobs driven by the backfill orchestrator.
- **FR-056**: Two dead cronjobs (cms-puf-all aggregate, cms-cost-reports-puf-lines HCRIS job) MUST be deleted.
- **FR-057**: The operational documentation deliverables MUST all land in the same phase as the code.
- **FR-058**: The existing k8s TCP health probes MUST continue to pass throughout the lockdown (no HTTP health dependency).
- **FR-059**: The log-ingestion path for client telemetry MUST be verified to accept events from external apps before the lockdown ships.
- **FR-060**: REMOVED — Loki retention policy and disk capacity are infrastructure-repo concerns, not dk-data-FE concerns. Tracked separately by the infra team.

### Key Entities

| Entity | Description | Key Attributes |
|---|---|---|
| Consuming App | An external application that reads from dk-data | Name, alias, allowed_schemas, rate_limit, tier, credentials |
| Client Package | The standardized typed library every consumer uses | Package name, version, supported fallback modes, supported error types, cache TTL table |
| Molecule | A canonical drug/compound entity | id, inchi_key, generic_name, brand_names, drug_type, regulatory_status, identifiers, pharmacology, targets |
| Molecule Profile | The full gold-layer aggregated view of a molecule | Derived from Molecule + all gold aggregations (lifecycle, competitive, safety, regulatory, trials) |
| Silver Hub | A canonical entity-resolution hub table for one of 10 domains | Hub identifier, identifier crosswalk, name index, resolve function |
| Resolve Operation | A stable parallel-safe function that canonicalizes a name or identifier to a hub ID | Entity type, input, canonical id, confidence, match tier |
| Consumer Credential | The credential issued to a consuming app that the public gateway validates | Key, consumer identity, allowed schemas, rate limit budget |
| Gateway Token | The short-lived role-bearing credential the gateway mints for the warehouse read layer | Role claim, expiry, signing secret |
| Anonymous Role | The legacy role that granted unauthenticated read access (to be dropped) | Role name, grants (to be revoked), membership (to be revoked) |
| Metric | A monitoring counter/gauge/histogram | Name, type, labels, emission call sites, dashboard references |
| Dashboard | A monitoring visualization | Uid, panels, metric references, label selectors |
| Lineage Edge | A dependency between two warehouse models | Source model, target model, source schema, target schema, source layer, target layer, domain, subdomain |
| Data Source | An upstream fetcher that populates raw tables | Source name, raw table, bronze/silver/gold descendants, subdomain classification, refresh cadence |
| Cronjob | A scheduled job that fetches or transforms data | Name, schedule, source, orchestrator-driven flag, last success |

## Success Criteria

- **SC-001**: The standardized client package (`packages/dk-data-client/`) is published from this repo (npm + PyPI) with all fallback modes, typed errors, caching, and telemetry implemented. Consumer-side adoption is tracked and measured by each consuming-app's own spec, not this one.
- **SC-002**: An unauthenticated request to any dk-data public endpoint (including the health endpoint) is rejected.
- **SC-003**: The legacy anonymous read role does not exist in the database.
- **SC-004**: The standalone and docker-compose gateway configurations expose the same schema list as production.
- **SC-005**: Every gold-layer aggregation table (molecule profile, safety signals, lifecycle stages, competitive landscape, company pipeline) has a non-zero row count on production.
- **SC-006**: A consuming app's call to a fully-ingested molecule returns within 200 ms at the 99th percentile.
- **SC-007**: An identifier-resolution call for a canonical entity returns within 200 ms at the 99th percentile.
- **SC-008**: Every monitoring dashboard panel renders real data.
- **SC-009**: The hydration heat-map dashboard displays per-method hit/miss/fallthrough counts with latency percentiles.
- **SC-010**: The 10 unprefixed legacy surfaces are relocated to their canonical domain-prefixed schemas, with deprecated aliases still working until consumer cutover is complete.
- **SC-011**: The number of cronjob YAML files is reduced by at least 25.
- **SC-012**: Every source has a single canonical name used consistently across the backfill state, raw tables, and ingestion modules.
- **SC-013**: A continuous-integration check fails the build on: dead metrics, dashboard references to undefined metrics, missing warehouse-model grants, lineage classifier unable to classify a new schema, or source-name drift.
- **SC-014**: The five operational runbooks (rotation, rollback, gateway-401, telemetry-spike, dashboard-no-data) exist and are verified current.
- **SC-015**: A new consuming-app team can go from zero to a successful first query by following the consumer onboarding guide without operator intervention.
- **SC-016**: The hydration roadmap for the next quarter is driven by telemetry volume rankings, not planning-time guesses.
- **SC-017**: Adding a new warehouse model does not require a manual lineage rebuild step; the scheduled rebuild picks it up automatically.
- **SC-018**: Adding a new consumer-visible endpoint does not require a consumer code change to pick up new fields.
- **SC-019**: Rotating the gateway signing secret completes within 5 minutes without bringing dk-data down.
- **SC-020**: The rollback of the anonymous-role drop (if ever needed) completes within 5 minutes.
- **SC-021**: The public gateway (metering proxy) runs with ≥ 2 replicas and a `PodDisruptionBudget` with `minAvailable: 1`; a failover test (one replica killed) recovers in ≤ 5 seconds with no failed consumer requests.
- **SC-022**: `PGRST_DB_POOL` and the cluster's `max_connections` are sized to accommodate the post-lockdown adapter fleet with at least 20% headroom. Documented in `docs/reports/capacity-audit-2026-Q2.md` before Phase 2 ships.
- **SC-023**: REMOVED — Loki retention is an infra-repo concern, tracked separately.
- **SC-024**: Consumer audit complete: no internal service currently reads `hcs_silver` or `hcs_gold` via `web_anon` (or if it does, an API key is provisioned before migration 218 runs).
- **SC-025**: Migration 218 execution on staging completes within 60 seconds total wall clock and holds no single ACCESS EXCLUSIVE lock longer than 5 seconds.
- **SC-026**: Adapter v0.2.0 is published to npm + PyPI within 7 days of migration 216 landing. Consumer-side verification of v0.2 adoption is tracked in each consuming app's own spec.
- **SC-027**: Feature branch is rebased onto main at least weekly during the active implementation window; any merge conflicts resolved within 2 business days.
- **SC-028**: Every verification task (T001-T009, T067a, T088a-c) produces a dated artifact under `docs/reports/` before the task is marked complete.
- **SC-029**: `.dk/memory/decisions.md` and `.dk/memory/tags.md` updates (D008-D015, tag activations) land in the same PR as feature merge — NOT before.
- **SC-030**: Before T089a (production web_anon drop): `/dk.analyze` re-run is green, all Phase 1b SCs verified current, all consumers confirmed on adapter v0.2, on-call engineer signed off.

## Assumptions

- The primary consuming-app language environments are covered by publishing the client in the two languages most consumers use (assumed: TypeScript and Python based on the audit of existing consuming apps).
- The cluster already has a log-ingestion stack; if its ingestion path does not accept events from external apps, an alternative path (gateway-mediated) is used.
- The public gateway is the only path into the warehouse read layer from outside the cluster (verified: ingress routes all external traffic to the gateway, not directly to the read layer).
- The k8s health probes run at the TCP layer, not the HTTP layer (verified in deployment configuration); the anonymous-role drop therefore does not require a health-endpoint carve-out.
- Existing cluster-internal service connections continue to use direct database credentials (not the gateway), and this is acceptable because those paths are not reachable from outside the cluster.
- The five upstream ingestion sources consumers currently maintain locally (BioRxiv, Semantic Scholar, Europe PMC, DailyMed, OpenFDA) will remain local until telemetry volume justifies ingestion.
- The gateway (metering proxy) currently exists as a deployed component; this initiative hardens its configuration but does not rebuild it.
- The backfill orchestrator is load-bearing and is the correct place to drive per-year and per-range ingestion scheduling.
- The lineage classifier's parser is SQL-based and cannot detect function-call dependencies; this limitation is accepted and documented rather than re-engineered.
- The project's naming convention enforces domain prefixes for new schemas; the unprefixed schemas that exist today are either intentional operational exceptions or legacy.
- Consuming apps will tolerate a short migration window during which the standardized client coexists with hand-rolled clients.
- Test infrastructure supports spinning up ephemeral dk-data instances for integration and contract tests.
- The cluster has headroom for the expected telemetry volume (~7M events/day estimated); if not, telemetry batching ships in a later phase.
- The legacy anonymous read role in PostgreSQL is named `web_anon` (created by early initialization scripts). Migration 218 drops it; the rollback contract references the same name. Every grant audit in this initiative searches for `GRANT ... TO web_anon` specifically.
- The public gateway component is called the **metering proxy** in code (`src/dk_data/metering_proxy/`) and k8s manifests (`k8s/apps/metering-proxy/`). The spec uses "metering proxy" and "gateway" interchangeably where context is clear.

## Non-Goals (explicit)

The following are intentionally OUT OF SCOPE for this initiative, even though they are adjacent to the work. They are tracked as follow-ups.

- **`mol_raw.chembl` → `mol_raw.chembl_molecules` table rename** (drift audit D15). US-20 aligns the `meta.backfill_state` source name to `chembl_molecules` but does NOT rename the raw table. A rename would require updating every downstream SQLMesh model that references `mol_raw.chembl` — larger-than-planned scope. Deferred to a follow-up initiative. Migration 220 only touches `meta.backfill_state` rows.
- **Consolidating the three `agents` / `mol_agents` / `hcs_agents` schemas** (US-18 P3). Deferred pending audit of which cluster services write to each.
- **Real-world evidence ingestion sources** (Optum, Flatiron, TriNetX, All of Us). Not a 2026 target.
- **Commercial/paid pharma intelligence sources** (Cortellis, Pharmaprojects, Citeline, BioMedTracker, GlobalData, IQVIA). Build-vs-buy decision deferred until adapter telemetry shows fallthrough volume justifying the cost.
- **Rebuilding the metering proxy**. This initiative hardens its configuration (provisioning API keys, scoping the internal consumer, adding HA) but does not rewrite the proxy.
- **Fan-out orchestrator feature** (originally proposed in drift audit D2, reverted to single-sequential-job per F-D016). The backfill orchestrator keeps its existing max-1-concurrent contract.
- **Re-enabling `PGRST_OPENAPI_MODE` in production**. Type generation uses an ephemeral CI-only PostgREST instance.
- **Splitting `mol-targets`, `mol-genomics`, `ip-*` DAG subdomains** (US-11 option). Only `ind-terminology` is added.

## Clarifications

### Session 2026-04-13 (autonomous — dk.auto)

- **Q: Should the standardized client ship in both TypeScript and Python simultaneously, or phase Python to a later release?**
  → **A: Ship both simultaneously in v0.1.** Three of the five verified consuming apps are TypeScript (behavior-labs-ai admin, behavior-labs-ai CI, behavior-labs-ai research agents) and two are Python (trials-predictor and internal tools). Phasing Python would leave trials-predictor without a migration path and would force a second cutover window. Reasoning: both language environments are load-bearing consumers; a phased rollout creates coordination debt.
  - Category: Integration & External Dependencies
  - Options considered: (A) both simultaneously, (B) TS first, Python v0.2, (C) Python-only shim around TS
  - Chosen: A
  - Sections updated: FR-001 reaffirmed; US-13 acceptance scenarios cover both TS and Python consumers

- **Q: What backs the client's shared (L2) cache in production?**
  → **A: Redis in production, local file-backed store (SQLite) in developer environments.** Redis is already deployed in the cluster for other services and supports cross-pod cache sharing, which is a hard requirement for multi-replica consumer deployments. SQLite keeps the dev experience free of external dependencies. Reasoning: no new infrastructure needed in production; developers get fast local iteration.
  - Category: Non-Functional Quality Attributes
  - Options considered: (A) Redis prod + SQLite dev, (B) Redis everywhere, (C) SQLite everywhere (no shared L2), (D) Memcached
  - Chosen: A
  - Sections updated: FR-005 refined (two-tier = in-process L1 + Redis L2 in prod, SQLite L2 in dev)

- **Q: How are telemetry events emitted — per-call or batched?**
  → **A: Per-call immediate emission in v0.1. Batching is deferred to v1.1 as an optimization after steady-state volume is measured.** Per-call emission gives the cleanest causality for debugging and keeps the implementation simple. If the ~7M events/day estimate in the assumptions turns out to strain the log-ingestion pipeline, batching ships as a non-breaking v1.1. Reasoning: prefer simplicity until measurement justifies complexity.
  - Category: Non-Functional Quality Attributes
  - Options considered: (A) per-call immediate, (B) time-window batching (5s), (C) count-window batching (100 events), (D) hybrid
  - Chosen: A
  - Sections updated: FR-003 clarified as "emit one event per call"; Assumptions note batching is a v1.1 deferral

- **Q: When the anonymous-role drop is rolled back in an emergency, does the rollback restore all prior grants or only the minimum needed to unblock?**
  → **A: Minimum only — restore the role with USAGE on the public namespace plus SELECT on the health and catalog endpoints, nothing more.** Restoring the broad grants from the legacy migrations is dangerous and re-opens every hole the lockdown closed. If the minimum rollback is insufficient, the operator's next step is a forward-fix (provision the missing consumer credential) rather than a deeper rollback. Reasoning: rollbacks should be the smallest change that restores service, not a full undo of the security improvement.
  - Category: Edge Cases & Failure Handling
  - Options considered: (A) minimum-only (health + catalog), (B) restore api-schema grants, (C) full restoration of all prior grants
  - Chosen: A
  - Sections updated: FR-031 refined ("rollback restores minimum grants only"); US-2 edge cases updated

- **Q: How long do the deprecated unprefixed aliases live after the domain-prefix rename?**
  → **A: 30 calendar days after the last consuming app's migration to the prefixed names is verified in telemetry.** A hard deadline prevents the aliases from becoming permanent; tying it to telemetry verification (not a calendar date) prevents dropping them while a lagging consumer is still using them. Reasoning: time-boxed deprecation with an observable gating condition.
  - Category: Constraints & Tradeoffs
  - Options considered: (A) 30 days after last verified migration, (B) 90 days calendar, (C) indefinite (never drop), (D) immediate deprecation with no alias window
  - Chosen: A
  - Sections updated: FR-028 refined with the 30-day telemetry-gated window; US-6 acceptance scenarios include the telemetry gate

- **Q: SEC EDGAR access — free public API or paid service?**
  → **A: Free public API.** SEC EDGAR publishes structured filings (XBRL + plain text) via its public endpoint with fair-use rate limits. Paid aggregators add convenience but no unique data for the SEC filings use case. If rate limits bite in production, revisit.
  - Category: Integration & External Dependencies
  - Options considered: (A) free public API, (B) Intrinio paid, (C) scrape EDGAR HTML
  - Chosen: A

- **Q: `mol_silver` direct exposure vs `mol_api` curated — keep both, or revoke direct silver/gold once `mol_api` is the supported surface?**
  → **A: Keep both exposed for now. Revisit after the adapter is in production and telemetry shows which surface consumers hit.** `mol_api` is a curated/denormalized surface; `mol_silver` is the raw hub for power users (e.g., carbon-5) who need cross-domain analytical queries. Revoking direct silver access is security-positive but requires confirming no legitimate usage depends on it.
  - Category: Terminology & Consistency
  - Options considered: (A) keep both, (B) revoke mol_silver from external, promote mol_api canonical, (C) merge mol_silver into mol_api
  - Chosen: A

- **Q: `carbon-5` consumer currently has stale `allowed_schemas: [mart, api, bronze, silver, gold]` (unprefixed legacy schemas). What's the correct scope?**
  → **A: Query the carbon-5 owner. If no response within 1 week, apply conservative scope `[api, mart, mol_api, scoring]` matching behavior-labs-ai. The old bronze/silver/gold unprefixed references are legacy SQLMesh output schemas that may not even exist — verify and scope accordingly.**
  - Category: Constraints & Tradeoffs
  - Options considered: (A) ask owner then default conservative, (B) keep stale scope, (C) revoke all access until owner responds
  - Chosen: A
