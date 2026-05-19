# Quickstart — WS4 SP1 (CI-faithful dev & verify)

> SP1 is implemented on a branch off **canonical `main`** (this feature was
> bootstrapped in an isolated worktree at `.agents/ws4` based on `origin/main`).
> SP2/SP3 are separate cycles.

## Run tests like CI

CI installs the package from the PR checkout (`pip install -e ".[dev]"`), so new
modules import without any path hack. **Do NOT add `tests/conftest.py` sys.path
hacks** — they break the Lint job (ruff `E402`) and are out of scope.

```bash
# From the worktree root (.agents/ws4):
PYTHONPATH="$PWD/src" .venv/bin/python -m pytest \
  tests/test_mcp_adapters.py \
  tests/test_mcp_dbfirst_dispatch.py \
  tests/test_mcp_data_tools_isolation.py \
  --no-cov --no-header -q -p no:cacheprovider
```

- Unit H1-matrix tests use an in-process fake pool + `asyncio.run` (no live DB).
- The integration leg (real CNPG, tag `[TESTE]`) runs in CI under
  `pytest tests/ -v` (not `-m "not integration"`). Locally, ~27 failed + 5
  errors are **pre-existing** live-PostgREST noise (test_security / test_api /
  test_log_to_meta) that pass in CI's DB service — not regressions.

## Lint like CI

```bash
~/.pyenv/versions/3.14.3/bin/ruff check . --exclude .claude
```
CI Lint is `ruff check .` — a stray `E402` etc. fails it. Verify before push.

## Exercise the gate locally

```bash
# default = inert (must equal pre-change behavior)
unset MCP_DBFIRST_ENABLED MCP_DBFIRST_SOURCES

# enable one validated source
export MCP_DBFIRST_ENABLED=true
export MCP_DBFIRST_SOURCES=ema
```

## Verification gate (ALL required before merging SP1 to `main`)

1. `gh pr checks <#>` shows **Lint = pass**, **Test = pass**,
   **Validate SQLMesh Models = pass**, **Validate Kubernetes Manifests = pass**
   — confirmed against the verified head SHA
   (`gh pr view <#> --json headRefOid`; re-check after any force-push).
2. db_query H1 matrix real-passes (0 xfail) and `test_mcp_data_tools_isolation`
   passes.
3. `python -c "import dk_data.api.routes"` clean.
4. With gate off: a representative `invoke_tool` call is byte-identical to the
   pre-change baseline (SC-001).
5. **No auto-merge.** Manual merge only (FR-013).

## Rollback

`MCP_DBFIRST_ENABLED=false` (instant, no code deploy) or empty
`MCP_DBFIRST_SOURCES`; or clean `git revert` of the squash-merge (additive only).
