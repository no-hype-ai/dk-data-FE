# Example Stage Status — worked example

> **Note**: This is a real-world `stage-status.md` from a cluster/platform feature.
> Project-specific names (Doppler, k3s-slave, dk-alchemy, feature/001, etc.) are
> kept verbatim to preserve the realistic texture — how a long feature actually
> reads after three stages closed and two deferrals. Your own `stage-status.md`
> will use your domain's vocabulary. Refer to this when `/dk.stage init` is
> uncertain about stage granularity, deferral framing, or cumulative-prod rows.

---

# Feature 001 — Stage Status (as of 2026-04-10)

Living document summarizing what's done, what's deferred, and what's blocked
across the seven stages. Updated after each stage closes. Use this instead
of scanning `tasks.md` for the current-state view.

## Branch: `feature/001-platform-hardening-cleanup`

```
Stage 1 ✅  Stage 2 ✅  Stage 3 ✅  Stage 4 ⏳  Stage 5 ✅  Stage 6 ⏳  Stage 7 ⏳
```

## Commits on this branch

```
05e4c97 Stage 1 — spec (spec.md, plan, research, data-model, contracts, quickstart,
        tasks, checklist, canonical-projects, consumers.yaml, decisions D001-D012)
        + Stage 1 artifacts (k3s-sqlite-backup base/overlay, grafana/alerts/
        cert-expiry.yaml, k3s-datastore-backup.yaml)
51aa003 Stage 1 — orphaned CNPG replica cleanup (bug report, remediation narrative)
fc8879b Stage 2 — US-3 auth tests (conftest + test_auth + test_promotion +
        test_webhooks), T016 system-upgrade-controller kustomize, T017 sync-wave
        merge generator across 33 components, D014 decision
0b1b95f Stage 3 — CI guard (consumer-coupling-check.yaml, issue template),
        Doppler inventory script + 1974-line output, consolidate script,
        canonical-projects.yaml revised, consolidation plan, grafana-pr-preview
        paths extension, fresh dk-alchemy project created in DK-Master workspace
439682f Stage 3 follow-up — cross-workspace Doppler migration script +
        140-key apply to dk-alchemy/prd
efa1522 Stage 5 — provisioning API (models + saga + audit + registry + cnpg
        + doppler-admin + router), 25 tests, dk-cli provision commands,
        consumer guide, gh-projects-sync workflow
```

6 commits, roughly 7,500 lines net addition. All commits atomic and
individually reversible.

## Stage 1 — WS0 quick wins + scaffolding ✅

**Gate**: cert healthy, etcd (SQLite) backup path validated, bug report filed.

- ✅ T001 `consumers.yaml` inventory (4 active + 3 deprecated repos)
- ✅ T002 `canonical-projects.yaml`
- ✅ T003 feature-scoped `memory/context.md`
- ✅ T010 wildcard cert — healthy 79 days (brief's 31-day deadline was stale)
- ✅ T011 SQLite backup CronJob + secret deployed + suspended (manual apply)
- ✅ T012 `grafana/alerts/k3s-datastore-backup.yaml`
- ✅ T013 `grafana/alerts/cert-expiry.yaml`
- ✅ T014 Reflector — verified self-healed
- ✅ T015 chemikus-prod ns — verified already gone
- ✅ Unplanned: ~10,000 Failed-phase pod cleanup, orphaned CNPG replica
  cleanup (430GB recovered), slave-1 VM disk expansion 1000→1500G via
  Proxmox API, CNPG `postgres-cluster-14` HA rebuild triggered
- 📄 `.dk/bugs/2026-04-10-slave-disk-pressure/report.md`

**Deferred from Stage 1**: T011 smoke test — CronJob is deployed but suspended
because master-1 is at the 110-pod cap from pre-existing ImagePullBackOff /
CrashLoop pods. Natural schedule will fire at the next 6-hour window once
master-1 has headroom; alternatively unsuspend manually via
`kubectl -n kube-system patch cronjob k3s-sqlite-backup -p '{"spec":{"suspend":false}}'`.

## Stage 2 — Auth + sync-wave + upgrade controller ✅

**Gate**: `pytest tests/test_auth.py tests/test_promotion.py tests/test_webhooks.py` — 37 passing in 0.44s.

- ✅ T016 `k8s/infrastructure/system-upgrade-controller/` kustomize base
  (Rancher v0.15.2 remote resources + prod overlay, sync-wave 1)
- ✅ T017 merge-generator sync-wave map in `.gitops/root/dk-cluster-infrastructure.yaml`
  — 33 components across waves 0-4, Go template syntax
- ✅ T050-T056, T070 **audit finding**: already implemented in a different
  (better) architecture than literal FR-012 — see D014. OAuth exchange +
  platform session tokens instead of per-request JWKS.
- ✅ T053 `tests/test_auth.py` — 19 tests (device code, OAuth callback, me, revoke,
  refresh, role permission matrix parametrized)
- ✅ T056 `tests/test_promotion.py` + `tests/test_webhooks.py` — 18 tests
  (signature validation unit + integration, role gating, input validation)

**Deferred from Stage 2**: T053 (extended auth coverage — every edge case) and
`tests/test_observability.py` (tracer setup). Not blocking.

## Stage 3 — Parallel offline subset ✅

**Gate**: CI guard in place, tracking issues verified OPEN, Doppler consolidation
applied to dk-alchemy/prd (140 keys).

- ✅ T100 (effectively) — fresh `dk-alchemy` project created in workspace
  `f7d2d9a43d9511c24623` (DK-Master) via the DK-ALCHEMY service-account token
- ✅ T101 `scripts/doppler/inventory.sh` (read-only)
- ✅ T102 `scripts/doppler/consolidate.sh` (dry-run template) + new
  `scripts/doppler/migrate-to-dk-alchemy.py` (cross-workspace migration)
- ✅ T103 `doppler-inventory.md` (1974 lines, 59 projects) + `doppler-consolidation-plan.md`
- ✅ T107 (skipped, replaced) — T102/T108 combined: migration script with
  first-wins priority order and collision report
- ✅ T108 consolidation executed — 140 keys written to `dk-alchemy/prd` via the
  cross-workspace migration script with 8 collisions resolved in favor of
  `dk-infrastructure` baseline
- ✅ T109 CLAUDE.md — **verified no-op**, no Doppler references exist
- ✅ T120 `.github/workflows/consumer-coupling-check.yaml` reusable workflow
  — added-lines-only diff scan, 3 patterns (FAIL/FAIL/WARN), injection-safe
- ✅ T121 `.github/ISSUE_TEMPLATE/consumer-coupling-tracking.md`
- ✅ T122 Tracking issues verified OPEN with correct labels:
  `data-kinetic/behavior-labs-ai#883`, `data-kinetic/dk-data-FE#271`,
  `data-kinetic/DK-OS#258`, `ATARI-Foundation/surgeo#46`
- ✅ T080 grafana-pr-preview.yaml — added `packages/dk-preview-daemon/**` path

**Deferred from Stage 3** (with explicit reason):
- ⏸ T104-T106 DopplerSecret CRD rewire — the cluster still references the OLD
  workspace projects. This is the cutover step; belongs in its own atomic commit
  that can be reviewed and rolled back cleanly. Not destructive to defer.
- ⏸ T090-T095 preview daemon cutover — substantial production work, deserves
  dedicated stage focus.
- ⏸ T071-T075, T076-T079 per-service OTel fan-out — touches live pods.
- ⏸ T126 CI smoke-test of consumer-coupling-check.yaml — needs a PR in a
  consumer repo with a test coupling addition to prove the check fires.

## Stage 4 — Cluster HA ⏳ BLOCKED

**Blocked on**: scarecrow hardware procurement (per brief).

- ⏸ T020-T028 — scarecrow provisioning + QDevice + K3s HA join + failure drill
- ⏸ T029a SQLite→etcd migration (D013) — ready to run once Stage 4 is unblocked;
  commented Plan CRD template waiting in `k8s/infrastructure/system-upgrade-controller/overlays/prod/`
- Stage 1 already delivered: etcd backup (SQLite-based interim) + sync-wave scaffolding

## Stage 5 — Provisioning API + CLI + Roadmap automation ✅

**Gate**: `pytest tests/test_provisioning.py` — 25 passing in 0.38s. Full suite 64/64.

- ✅ T030 Provisioning router skeleton with Pydantic models + role gating
- ✅ T031 CNPG adapter (`clients/cnpg.py`) with `CnpgMode` feature-detect
  (DECLARATIVE stub + PSQL real path), strict identifier validation,
  password rotation on re-create
- ✅ T036 Doppler admin client (`clients/doppler_admin.py`) — Bearer auth HTTPS,
  never logs response bodies, idempotent delete
- ✅ T037 Saga executor (`services/provisioning_saga.py`) — forward+compensate
  in reverse order, every step audited
- ✅ T038 Audit store (`services/audit_store.py`) — in-memory ABC, Postgres swap
  is a follow-up
- ✅ T039 `POST /dk/v1/resources/postgres/database` end-to-end
- ✅ T040 `GET /dk/v1/resources` + `DELETE /dk/v1/resources/{id}` (teardown saga)
- ✅ T042 wired in `main.py`
- ✅ T044 25 tests (auth, role gating, happy path, idempotency, saga compensation
  with reverse-order drop_database→drop_role, compensation-failure-recorded,
  body validation, 501 stubs, list, delete, 503-when-unconfigured)
- ✅ T045 `dk provision db|bucket|redis|llm-key|namespace|list|destroy`
- ✅ T046 wired in `src/dk-cli/src/index.ts`
- ✅ T047 `docs/platform-consumer-guide.md` — 9 sections
- ✅ T140, T141 `.github/workflows/gh-projects-sync.yaml` — label → column via
  GraphQL mutations, injection-safe

**Deferred from Stage 5** (with explicit reason):
- ⏸ T032-T035 MinIO/Redis/LiteLLM/K8s client adapters — identical pattern to CNPG,
  ~200 lines each. Router returns 501 for all four today with a clear message.
- ⏸ T038 Postgres-backed audit store — in-memory works for tests + single-instance
  deploys; multi-replica needs a swap at startup.
- ⏸ T041 service-account token CRUD endpoints — Pydantic models defined, router
  endpoints not wired. Needs a token-storage design choice (Redis+JWT vs.
  dedicated Postgres table).
- ⏸ T043 **OPERATOR SIGN-OFF REQUIRED** — platform-api deployment RBAC +
  `DOPPLER_PROVISIONING_TOKEN` env var. Blast-radius decision (workspace scope
  vs. consumer-tier scope) is explicit per D012.
- ⏸ T144 `scripts/gh-roadmap-status.sh` — aggregator, independent script.
- ⏸ T164 SC-004 wall-clock verification — gated on T043 landing.
- ⏸ T165 FR-019 trace chain verification — gated on full OTel fan-out.

## Stage 6 — Consumer retarget + LiteLLM + decommission ⏳

Not started. Has multiple **OPERATOR SIGN-OFF** gates (T096 VM 101 decom,
T123-T125 deprecated consumer removal, T136 LiteLLM cutover).

## Stage 7 — Polish + verification closure ⏳

Not started. Depends on Stages 4-6 completing.

---

## What's running against production right now

As a result of Stages 1-5 (manual applies + scripts):

| Change | Where | Reversal |
|---|---|---|
| `kube-system/k3s-sqlite-backup` CronJob (suspended) | k3s-master-1 | `kubectl delete cronjob -n kube-system k3s-sqlite-backup` |
| `kube-system/k3s-sqlite-backup-minio` Secret | master | `kubectl delete secret -n kube-system k3s-sqlite-backup-minio` |
| `kube-state-metrics` scaled 1 (was 0 during cascade) | infra namespace | was the original state; fine |
| `k3s-slave-1` VM disk 1500G (was 1000G) | krang Proxmox | not reversible without VM shrink (not recommended) |
| `postgres-cluster-14-join-*` replica rebuild | CNPG | if it completes, HA; if not, kill the pod (it'll retry) |
| `dk-alchemy` project in DK-Master Doppler workspace | workspace f7d2d9a43d9511c24623 | `doppler projects delete dk-alchemy` |
| 140 secrets in `dk-alchemy/prd` | DK-Master Doppler workspace | same |

## What lands on merge to `main`

Stage-by-stage, what the commits would do to `main` once merged:

- **05e4c97 Stage 1 spec + artifacts**: docs + YAML files. The
  `k8s/infrastructure/k3s-sqlite-backup/` directory becomes discoverable by
  the `dk-infrastructure` ApplicationSet. ⚠️ **The prod overlay has a
  DopplerSecret referencing `dk-infrastructure` project and key
  `MC_HOST_minio` which does NOT exist in the source Doppler project.**
  ArgoCD will attempt to sync this and the DopplerSecret will fail to
  materialize its K8s secret. The CronJob itself is suspended, so no impact.
  **Recommended action before merge**: either remove the DopplerSecret from
  the overlay (I manually created the K8s secret with the right value) OR
  set `MC_HOST_minio` in the legacy `dk-infrastructure/prd` Doppler project.
- **51aa003 Stage 1 bug report**: docs only. No cluster effect.
- **fc8879b Stage 2 auth tests + sync-wave**: tests only run in CI;
  `.gitops/root/dk-cluster-infrastructure.yaml` merge-generator change is
  the biggest ArgoCD behavior change. ⚠️ **Untested in a real ArgoCD
  environment.** If the Go template syntax has a bug, every Application
  generation fails. **Recommended action before merge**: apply the
  ApplicationSet manifest to a sandbox namespace and confirm all 33
  Applications generate cleanly before merging to main.
  Also: `k8s/infrastructure/system-upgrade-controller/` becomes a new
  production deploy — ArgoCD will fetch Rancher v0.15.2 and apply it.
  Well-tested upstream component, likely safe, but it IS new infra.
- **0b1b95f Stage 3**: CI workflows + scripts + docs. No cluster effect.
  The `consumer-coupling-check.yaml` workflow only runs when a consumer
  repo calls it. The `gh-projects-sync.yaml` workflow will fire on every
  issue/PR event but gracefully skips if the required secrets are unset.
- **439682f Stage 3 migration script**: script only. No auto-run.
- **efa1522 Stage 5**: new Python modules under `src/platform-api/src/platform_api/`.
  **The provisioning router will be mounted in the FastAPI app** — every
  request to `POST /dk/v1/resources/*` returns 503 until `app.state.cnpg_client`
  and `app.state.doppler_admin` are initialized in the lifespan. **Platform-api
  will need a deploy to pick up the new router, but the 503 fallback means
  there's no downtime.** New dk-cli command works only after a CLI release
  (`.github/workflows/dk-cli-release.yaml` fires on tag).

## Recommended pre-merge actions

Before opening or merging a PR to main, address these in priority order:

1. **Fix the k3s-sqlite-backup prod overlay** to not reference an unset
   Doppler key — either set the key in the legacy project OR remove the
   DopplerSecret and commit the manually-created secret as a sealed secret
   (not ideal) OR move the component into the ApplicationSet's excludes
   list until Stage 6 consumer retarget.
2. **Validate the ApplicationSet merge generator** in a sandbox before
   merge. `kustomize build` alone doesn't exercise ArgoCD's Go template
   renderer — the safest test is `argocd appset generate` via the CLI.
3. **Decide whether the provisioning API should land** without T043
   (deployment RBAC + token wiring). Landing without T043 is safe (returns
   503) but means the router is a "looks real but unreachable" surface
   until the operator sign-off happens.
4. **Review the consumer guide** — it documents a contract consumers should
   follow; if the contract changes after merge, docs drift.

## Recommended PR strategy

Given the scope (~7,500 lines, 6 commits, touching cluster infra + API + CLI
+ docs + workflows), one big PR is acceptable but must be a **draft** with
a detailed description and self-reviewed before un-drafting. Alternative:
split into 3 smaller PRs:

- **PR-A** (safe / docs / tests): Stage 2 auth tests, Stage 3 CI guard +
  consumer guide + tracking issue template, Stage 5 platform-api tests
  only. Roughly 2500 lines, no cluster effect. Mergeable immediately.
- **PR-B** (provisioning API): Stage 5 platform-api code (models, services,
  clients, router, CLI command). ~3500 lines. Mergeable once reviewers
  confirm the saga pattern + role gating + CNPG identifier handling.
- **PR-C** (cluster infra): Stage 1 spec + k3s-sqlite-backup + Stage 2
  ApplicationSet sync-wave + system-upgrade-controller + Stage 3 Doppler
  scripts. The most-risky chunk. Needs the ArgoCD sandbox validation
  above before merge.

My recommendation: **one draft PR** with the detailed description, and
the pre-merge checklist above gates un-drafting. Splitting retroactively
into 3 PRs is high effort for marginal review-quality gain; the commit
boundaries already segment the work clearly.
