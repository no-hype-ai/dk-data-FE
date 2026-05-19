# Blockers — 211-ws4-staging-main-reconcile

## B001 — SC-001 baseline cannot use live golden capture (2026-05-19)
**Workaround**: T003 reframed. main's MCP tools make live external HTTP; golden-response capture is flaky/non-deterministic and not senior. SC-001 ("zero default behavior change") is instead proven by a **gate-off invariant test** in `tests/test_mcp_dbfirst_dispatch.py`: with `MCP_DBFIRST_ENABLED` unset/false the dispatch helper returns `None` without resolving any adapter or touching a pool, so `router.invoke_tool` runs its existing httpx path byte-unchanged. No `baseline-mcp.json` artifact is produced.
**Status**: Resolved (design decision)
**Affects**: T003, T024 (T024 becomes "gate-off invariant test green" rather than golden diff)
