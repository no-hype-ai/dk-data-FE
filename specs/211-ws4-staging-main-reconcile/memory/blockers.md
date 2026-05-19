# Blockers — 211-ws4-staging-main-reconcile

## B001 — SC-001 baseline cannot use live golden capture (2026-05-19)
**Workaround**: T003 reframed. main's MCP tools make live external HTTP; golden-response capture is flaky/non-deterministic and not senior. SC-001 ("zero default behavior change") is instead proven by a **gate-off invariant test** in `tests/test_mcp_dbfirst_dispatch.py`: with `MCP_DBFIRST_ENABLED` unset/false the dispatch helper returns `None` without resolving any adapter or touching a pool, so `router.invoke_tool` runs its existing httpx path byte-unchanged. No `baseline-mcp.json` artifact is produced.
**Status**: Resolved (design decision)
**Affects**: T003, T024 (T024 becomes "gate-off invariant test green" rather than golden diff)

## B002 — Pre-existing red check "Prestaged Hydration Smoke (005)" (2026-05-19)
**Symptom**: PR #429 CI shows `Prestaged Hydration Smoke (005)` = fail (23s),
step `mypy --strict on new modules`: `dk_data/ingestion/prestaged.py:988
error: Name "backlog" already defined on line 829 [no-redef]`; `:995
Incompatible types in assignment (None vs HydrationBacklogWriter)`.
**Determination**: NOT an SP1 regression. `git diff origin/main..HEAD --
src/dk_data/ingestion/` is empty; `prestaged.py` last changed on origin/main at
#322 and is byte-identical on this branch. Pre-existing feature-005 mypy debt.
**Status**: RESOLVED 2026-05-19 — user directed full-green before merge. Minimal
correct fix: single authoritative `backlog: HydrationBacklogWriter | None = None`
declaration in `main()` before first use; removed the redundant re-annotation at
~988. Behaviour-preserving (assignment flow-narrows). Exact CI `mypy --strict`
on the 6 modules → Success, 0 issues.
**Affects**: none of T001-T026 (SP1 touches no ingestion/ file).

## B002b — Prestaged Hydration Smoke (005) kubectl dry-run flake (2026-05-19)
**Symptom**: after B002, the job's LAST step `kubectl --dry-run=client apply
-f deploy/jobs/prestaged-hydrate.yaml` fails: `failed to download openapi:
Get http://localhost:8080/openapi/v2: connection refused`. Pre-existing
kubectl-version-drift (stable.txt kubectl does server-side schema validation
even in client dry-run; no cluster in CI). `.github/workflows/ci.yaml` is
unchanged by SP1 (pre-existing on main). NOT an SP1 regression.
**Workaround/fix**: ci.yaml:493 += `--validate=false` (kubectl's own prescribed
remedy). Offline structural YAML/kind checks still run. User-directed full-green.
**Status**: Resolved. **Affects**: none of SP1's product code.
