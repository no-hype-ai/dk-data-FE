# Requirements Checklist — Metering Proxy JWT Minting

Pre-merge gate. Every box must be ticked before this feature merges to main.

## Specification quality

- [ ] All 20 functional requirements are testable with no ambiguous language
- [ ] Every user story has at least one Gherkin acceptance scenario
- [ ] Every success criterion is measurable and technology-agnostic
- [ ] Assumptions are explicit and reviewed by the on-call platform operator

## Core implementation

- [ ] Metering proxy mints a signed JWT and injects it into the forwarded request
- [ ] JWT claims match FR-003, FR-004, FR-005 (role, sub, iss, iat, exp ≤ 60s)
- [ ] Signing secret is read once at startup from container env
- [ ] Startup self-test verifies secret length and end-to-end JWT acceptance
- [ ] Readiness probe fails if the self-test fails, no traffic until resolved
- [ ] Raw API key is not forwarded in any header (grep the running pod config)

## Database access

- [ ] Migration grants USAGE on mol_silver, mol_gold, mol_api, hcs_silver, hcs_gold, ind_silver, ind_gold, hcp_silver, hcp_gold, ip_silver, ip_gold, mart, scoring
- [ ] Migration grants SELECT on ALL TABLES in each granted schema
- [ ] Migration sets ALTER DEFAULT PRIVILEGES for future tables
- [ ] Migration grants EXECUTE on every resolve_* function
- [ ] No INSERT/UPDATE/DELETE/TRUNCATE/DDL is granted to the target role
- [ ] Migration is idempotent (can re-run without error)

## PostgREST configuration

- [ ] Unauthenticated requests are rejected at PostgREST, not served as anon role
- [ ] PGRST configuration change is deployed before migration 218 runs
- [ ] Pre-flight check blocks migration 218 if this feature is not yet deployed

## Observability

- [ ] "JWT minted" counter is defined, emitted, and bound to a dashboard panel
- [ ] "Requests executed as anon role" counter is defined, emitted, and alerted on
- [ ] Alert rule fires when minted-JWT success rate drops below 99.9%
- [ ] Metrics follow the three-way binding rule (definition + emission + consumption)
- [ ] Test `tests/observability/test_metric_coverage.py` passes with the new metric

## Test coverage

- [ ] Unit test: JWT mint produces a token PostgREST's jwt library can decode
- [ ] Unit test: signing-secret mismatch is detected at startup and fails readiness
- [ ] Unit test: tier → role mapping is exhaustive (one test per tier)
- [ ] Unit test: raw API key never appears in forwarded headers
- [ ] Integration test: full client → proxy → PostgREST → database path succeeds
- [ ] Zero regressions in existing metering proxy test suites
- [ ] Zero regressions in metering proxy latency test (SC-003)

## Security

- [ ] Signing secret is not logged (review log output from a load test)
- [ ] Raw API key is not logged in any format (review log output)
- [ ] Minted JWT is not logged in any format (review log output)
- [ ] Consumer alias is used in logs instead of key or JWT
- [ ] JWT has short TTL (≤ 60 seconds)

## Documentation

- [ ] consumer-onboarding.md updated to match the actual running behavior
- [ ] metering-proxy-401-debug.md updated with the correct JWT flow
- [ ] rollback-web-anon-drop.md describes the rollback path for dropping web_anon
- [ ] A new runbook or section describes rotating the JWT signing secret end-to-end
- [ ] The issue (#283) is referenced in the PR description

## Deploy readiness

- [ ] Feature deploys cleanly to staging and all readiness probes become green
- [ ] Migration 228 (schema grants) runs cleanly on staging
- [ ] Migration 218 (drop web_anon) runs cleanly on staging after this feature is live
- [ ] Production deploy window is coordinated with the platform operator
- [ ] Rollback plan is documented and tested in staging
