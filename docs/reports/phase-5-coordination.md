# Phase 5 Coordination — Consumer App Migration Status

**Feature**: 002-external-integration-foundation (T160)
**Date**: 2026-04-13
**Status**: READ-ONLY coordination pointer

## Purpose

Migration 218 (T089a — drop `web_anon` in production) MUST NOT fire
until every consumer app has its own feature-002 migration checked
off in its own repo. This document is the cross-repo coordination
checkpoint. It is read-only — we don't own the consumers' specs, we
just track them.

## Consumer inventory

| Consumer | Owner | Repo | Spec reference | Status |
|---|---|---|---|---|
| behavior-labs-ai | BehaviorLabs | `behavior-labs-ai` | `.specify/specs/XXX-dk-data-adapter/` | pending |
| carbon-5 | Platform squad | `carbon-5` | `.specify/specs/XXX-dk-data-adapter/` | pending |
| dk-os | Platform squad | `dk-os` | `.specify/specs/XXX-dk-data-adapter/` | pending |
| ground-truth-charlie | Research squad | `ground-truth-charlie` | `.specify/specs/XXX-dk-data-adapter/` | pending |
| trials-predictor | Research squad | `trials-predictor` | `.specify/specs/XXX-dk-data-adapter/` | pending |

## What "checked off" means for each consumer

The consumer's own feature 002 spec must confirm:

1. **API key provisioned**: `consumers.yaml` has the consumer's hash
   under the right tier
2. **Env var wired**: the consumer's k8s deployment sets
   `DK_DATA_API_KEY` from a k8s secret
3. **Adapter installed**: `@datakinetic/dk-data-client` (TS) or
   `dk-data-client` (PyPI) is added to the consumer's deps at the
   current version
4. **Calls migrated**: every direct read of `hcs_silver` / `hcs_gold`
   / `mol_silver` / any non-api schema is routed through the adapter
5. **Smoke test green on staging**: the consumer's integration test
   hits dk-data staging through the proxy and gets 200s
6. **Staging deploy green for 48h**: no unexpected 401/403/429 in the
   metering proxy logs

## Coordination rhythm

- **Daily stand-up** while Phase 5 is active: each consumer owner
  reports their status against the 6 items above.
- **Weekly rollup** filed into this document: update the Status
  column, re-commit the file.
- **Blocker escalation**: any item stuck for > 3 days pages the
  dk-data on-call + consumer owner + product owner on a shared
  incident channel.

## T089a gating checklist

T089a (production migration 218) can only fire when ALL of the
following are true:

- [ ] All 5 consumer Status values above are `complete`
- [ ] 48h of clean staging deploys across every consumer
- [ ] `docs/reports/capacity-audit-2026-Q2.md` signed off
- [ ] `docs/reports/capacity-signoff.md` signed off by infra
- [ ] `docs/reports/hcs-silver-consumer-audit.md` shows 0 unidentified
      IPs and 0 blocked legitimate consumers
- [ ] Rollback drill performed in staging
      (`docs/runbooks/rollback-web-anon-drop.md`) — rollback < 5 min
- [ ] dk-data on-call scheduled for the production window

Any unchecked item → POSTPONE T089a.

## Rollback coordination

If T089a has to roll back, each consumer that was already upgraded
needs to know immediately. The rollback runbook triggers a Slack
broadcast to `#dk-data-consumers` with:

- Estimated time to re-upgrade
- Whether the old `web_anon` path is fully restored (minimum path
  per F-D014 — so many consumers will still fail on broad schema
  reads)

The rollback is DELIBERATELY minimum-only (see F-D014 and the
rollback SQL file). Consumers that depend on broad `web_anon` grants
will still fail — the correct remediation is to forward-fix by
provisioning their API key, not to restore the broad grants.

## Related

- `src/dk_data/sql/migrations/218_drop_web_anon.sql`
- `docs/runbooks/rollback-web-anon-drop.md`
- `docs/reports/capacity-signoff.md`
- Each consumer repo's `.specify/specs/XXX-dk-data-adapter/` spec
