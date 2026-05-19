# Changelog

## Session 2026-04-13T08:16:40Z
- Feature created: external-integration-foundation

## Session 2026-04-13 — Implement narrow Wave 1 (safe file-only tasks)

**Scope chosen**: Pre-flight blocked full `/dk.swarm` execution because 198 tasks
span 5 repos, require cluster access, hit hard sequencing gates, and have human
sign-off requirements (see session transcript + pre-flight analysis). Instead
executed only the truly safe file-only tasks in this repo sequentially via
`/dk.implement`.

**Committed**:
- `1acbdc1` feat(002): add external-integration-foundation spec artifacts
  - 15 files, 3349 insertions: spec.md, plan.md, tasks.md, research.md,
    data-model.md, contracts/, quickstart.md, memory/, checklists/,
    and the `.dk/memory/decisions.md` drift-fix revert (removes D008-D015
    from global memory per F-D018 commit discipline).
- `db6c7df` T010: sync postgrest.conf db-schemas to match k8s production
- `01b3611` T011: sync docker-compose PGRST_DB_SCHEMAS to match k8s production
- `3f531e5` T012+T013: skip mol_api/ip_api in lineage + document resolver limitation

**Tasks completed**: T010, T011, T012, T013 (4 tasks marked [x] in tasks.md).

**Tasks NOT started** (intentionally deferred, require human supervision or
cluster access):
- T001–T009 (Phase 1 verification: row counts, TCP probes, Loki capacity,
  drug_labels columns, internal consumer audit, FastAPI auth state check,
  parent cronjob feature verification) — require kubectl/prod postgres
- T001a–T001d, T002a, T004b, T004c, T024c, T024d, T024e, T068a, T088a–T088c,
  T127a–T127d (Phase 1b/2/4 stability + cluster ops) — require kubectl/infra team
- T014–T018 (prometheus annotations on metering-proxy/batch-api deployments,
  scrape job verification, job-complete endpoint fix, lineage CronJob create)
  — GitOps operations touching deployed state
- T019–T029 (metering proxy API key provisioning, JWT rotation runbook,
  FastAPI auth dependency) — Platform API access + production behavior change
- Phases 3–9 (adapter package, migrations, consumer migration, metrics cleanup,
  docs, cronjob cleanup, telemetry-driven hydration, polish) — either not safe
  to swarm headlessly or not yet in scope for this session

**Verification**:
- `python3 -c 'import ast; ast.parse(...)'` passed on modified
  `build_model_lineage.py` after T012/T013
- `_SKIP_SCHEMAS` now contains `api`, `mol_api`, `ip_api` (verified via runtime
  parse of the file)
- git log shows 4 clean sequential commits, one per task
- `.claude/commands/add-datasource.md` intentionally left uncommitted
  (unrelated pre-existing session edit; not in feature scope)

**Notable finding**: commit `ba065a5` (Apr 12, 2026-04-12) already introduced
multi-year fiscal-year expansion with per-year checkpoint resume for CMS
fetchers (`_stream_cms_api_multi_year_to_db`). This validates F-D016's sequential
backfill design — the pattern already exists in the codebase. Chembl/pubchem
consolidation (T127a–d, US-20) can reference this existing pattern rather than
invent a new one.

**No blockers encountered.** Memory not updated beyond this changelog entry —
principles unchanged, stack unchanged, no new decisions beyond what was already
captured in `memory/decisions.md` during prior sessions.
