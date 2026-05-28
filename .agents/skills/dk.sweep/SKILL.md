---
description: Orchestrated observability-driven debug loop — queries logs and metrics from Grafana/Loki/Mimir, dispatches parallel sub-agent fixes in worktrees, merges PRs, verifies zero drift. Config-driven for any project.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty). The user may specify:

- A specific service or component to focus on (e.g., "platform-api", "probe-service")
- A specific issue to investigate (e.g., "structlog crash", "500 errors")
- A time range (e.g., "last hour", "last 24h") — default from config
- Additional context files to read
- Whether to auto-merge or wait for approval

If no input, run a full sweep across all services listed in `.dk/debug-sweep-config.json`.

## Principles

Read `.dk/memory/principles.md` before acting. All output must honor the project's principles: **simple, complete, senior**.

Key principles for this command:

1. **Never create drift** — all changes go through PRs, squash-merged to main
2. **Evidence before assertions** — always query logs/metrics before claiming a fix
3. **Sub-agents work in worktrees** — isolated branches, no conflicts with main
4. **Consult history first** — check `.dk/memory/lessons.md` and `.dk/bugs/` for known issues before investigating
5. **Document significant bugs** — create `.dk/bugs/<date>-<desc>/report.md` BEFORE dispatching fixes

## Overview

You are a **debug-loop orchestrator**. Your job is to run an end-to-end observability-driven fix cycle: pull errors from logs/metrics, triage them, dispatch parallel sub-agents in worktrees to apply fixes, merge PRs, verify zero drift, and repeat until clean.

## Configuration

Read `.dk/debug-sweep-config.json` — this file is created automatically by `dkify init` from the template. If it is missing (e.g., the project predates this feature), copy `.dk/debug-sweep-config.template.json` to `.dk/debug-sweep-config.json` and proceed.

**Before running the loop, validate that placeholder values have been replaced.** Halt with a clear error message listing the unfilled fields if any of these checks fail:

- `grafana.url` ≠ `https://grafana.example.com` and not empty
- `grafana.api_key_source` must not contain `<project>` or `<env>` placeholder tokens
- `grafana.datasources.loki_uid` must not be empty
- `targets.services` must not equal `["example-api", "example-worker"]` or be empty

If validation fails, print:

```
Debug sweep config is not filled in. Edit .dk/debug-sweep-config.json and set:
  - grafana.url                       (your Grafana instance URL)
  - grafana.api_key_source            (shell command that prints your API key)
  - grafana.datasources.loki_uid      (from Grafana → Connections → Data sources)
  - targets.services                  (list of service/container names to sweep)
```

Required config fields:

- `grafana.url` — Grafana instance URL
- `grafana.api_key_source` — shell command to retrieve the API key
- `grafana.datasources.loki_uid` — Loki datasource UID
- `grafana.datasources.mimir_uid` — Mimir datasource UID (optional)
- `targets.services` — list of service/container names to sweep
- `targets.default_time_range_minutes` — default lookback window
- `filters.error_patterns` — regex for error detection
- `filters.exclude_patterns` — patterns to suppress (e.g., health checks)
- `validation.sync_scripts` — scripts to run after merging dashboard/alert changes
- `execution.max_parallel_agents` — parallel worktree workers (default 5)
- `execution.max_iterations` — max loop cycles (default 3)

## Loop Execution

### Phase 0: Consult History

1. Read `.dk/memory/lessons.md` — look for previously documented issues in the target scope
2. List recent entries in `.dk/bugs/` (last 30 days) — skip re-investigating recently fixed issues
3. If the user named a specific issue, check if it matches any past `.dk/bugs/<date>-*/report.md` — if so, read the fix and consider whether this is a regression

### Phase 1: Gather Evidence

1. **Sync main**:

   ```bash
   git checkout main && git fetch origin --prune && git reset --hard origin/main
   ```

2. **Load Grafana API key** by executing the command in `grafana.api_key_source` from config

3. **Query Loki for errors** across target services (from `targets.services`, over `targets.default_time_range_minutes`):
   - Build LogQL query using `filters.error_patterns` and `filters.exclude_patterns`
   - Deduplicate by first 80 chars, count occurrences
   - Report unique error patterns with sample lines

4. **Query Mimir for anomalies** (if `grafana.datasources.mimir_uid` is set):
   - Check alert states via `/api/prometheus/grafana/api/v1/rules`
   - Check for metric gaps (expected metrics missing)
   - Check for high error rates

5. **Read any user-provided context files** (e.g., gap analysis docs, issue reports)

### Phase 2: Triage & Documentation

1. **Classify each issue** by severity:
   - **Critical**: Service crashes, data loss, security — fix immediately
   - **High**: Broken functionality, misleading dashboards, stale data
   - **Medium**: Missing features, suboptimal UX, incomplete instrumentation
   - **Low**: Cosmetic, documentation, nice-to-have

2. **For each Critical or High issue**, create a bug report in `.dk/bugs/YYYY-MM-DD-<short-desc>/report.md` **before** dispatching a fix. Use `.dk/templates/bug-report-template.md` as the starting structure and fill in severity, symptoms, reproduction, root cause, and planned fix.

3. **Create TaskCreate tasks** for each actionable issue:
   - Subject: imperative description of what to fix
   - Description: root cause, affected files, fix approach, bug report path
   - Set dependencies between tasks (zero-drift task blocked by all fixes)

4. **Always create a final "Verify zero drift" task** blocked by all other tasks

5. **Skip issues that are**:
   - Pre-existing and out of scope (document in `.dk/bugs/` but don't fix)
   - Already tracked in GitHub issues
   - Require user decision before acting

### Phase 3: Dispatch Sub-Agents

1. **Group tasks** that can run in parallel (different files/services)

2. **Dispatch sub-agents** using the Agent tool with `isolation: "worktree"`:
   - Each agent receives a complete, self-contained prompt with:
     - Path to the `.dk/bugs/<date>-<desc>/report.md` for context
     - Exact file paths to read and modify
     - The fix approach (be specific — don't leave design decisions to the sub-agent)
     - Instructions to create a branch, commit, push, and open a PR
     - Instructions to append `fix.md` to the same `.dk/bugs/` directory on completion
   - Commit message format:

     ```
     fix(<scope>): <description>

     <optional body>

     Co-Authored-By: Codex Opus 4.6 (1M context) <noreply@anthropic.com>
     ```

   - Sub-agents must run all `validation.scripts` from config before committing
   - Sub-agents must NOT merge PRs — only create them

3. **Parallelism limit**: `execution.max_parallel_agents` from config (default 5)

### Phase 4: Merge & Sync

1. **Check CI status** for each PR:

   ```bash
   gh pr checks <PR_NUMBER> | grep fail
   ```

2. **If CI fails**: read failure logs and determine fault:
   - Sub-agent's fault → fix in the orchestrator (small edit + push to same branch)
   - Pre-existing → note and merge if the fix itself is correct

3. **Squash merge each PR** sequentially (respect `execution.auto_merge` in config — if false, wait for user approval):

   ```bash
   gh pr merge <PR_NUMBER> --squash --subject "<title> (#<PR_NUMBER>)"
   ```

4. **Mark tasks as completed** after successful merge

5. **Run sync scripts** from `validation.sync_scripts` in config (e.g., Grafana dashboard/alert sync)

### Phase 5: Zero Drift Verification

1. **Sync main**:

   ```bash
   git checkout main && git fetch origin --prune && git reset --hard origin/main
   ```

2. **Clean up**:
   - Remove worktrees: `git worktree remove <path> --force`
   - Delete merged local branches

3. **Verify**:
   - `git branch` — only `main`
   - `git worktree list` — only repo root
   - `git status --short` — only expected untracked files
   - Run all `validation.scripts` from config — 0 errors
   - `gh pr list --state open` — 0 open PRs from this sweep
   - Alert health check via Grafana API — all alerts healthy

4. **Persist iteration state** to `.dk/debug-sweep-state.json` (gitignored):

   ```json
   {
     "iteration": N,
     "timestamp": "<ISO-8601>",
     "issues_found": [...],
     "prs_merged": [...],
     "bugs_documented": [...],
     "status": "clean" | "in_progress" | "stuck"
   }
   ```

### Phase 6: Repeat or Complete

1. **Re-run Phase 1** to check if fixes introduced new issues
2. **If new issues found**: create new tasks and dispatch agents (go to Phase 2)
3. **If no new issues**:
   - Report "Clean — no actionable issues found"
   - If any non-obvious patterns were discovered, append an entry to `.dk/memory/lessons.md` via the `lessons-learned` skill
   - Complete
4. **Maximum iterations**: `execution.max_iterations` from config (default 3). If issues persist, report remaining issues and ask user for guidance.

## Output Format

After each loop iteration, report:

```
## Sweep Loop — Iteration N

### Issues Found
| # | Severity | Issue | Root Cause | Bug Report | Fix |
|---|----------|-------|------------|------------|-----|

### PRs Merged
| PR | Title |
|----|-------|

### Remaining Issues
| # | Issue | Reason Not Fixed |
|---|-------|------------------|

### Lessons Appended
| File | Summary |
|------|---------|

### Zero Drift Status
| Check | Result |
|-------|--------|
```

## Grafana API Reference

All URLs, UIDs, and credentials come from `.dk/debug-sweep-config.json`. Example commands:

```bash
# Load config values
GRAFANA_URL=$(jq -r .grafana.url .dk/debug-sweep-config.json)
LOKI_UID=$(jq -r .grafana.datasources.loki_uid .dk/debug-sweep-config.json)
MIMIR_UID=$(jq -r .grafana.datasources.mimir_uid .dk/debug-sweep-config.json)
API_KEY_SOURCE=$(jq -r .grafana.api_key_source .dk/debug-sweep-config.json)
GRAFANA_API_KEY=$(eval "$API_KEY_SOURCE")

# Query Loki logs
curl -s -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -G "${GRAFANA_URL}/api/datasources/proxy/uid/${LOKI_UID}/loki/api/v1/query_range" \
  --data-urlencode 'query={container="<service>"} |~ "<error_pattern>"' \
  --data-urlencode "start=$(python3 -c 'import time; print(int(time.time()-1800))')" \
  --data-urlencode "end=$(python3 -c 'import time; print(int(time.time()))')" \
  --data-urlencode 'limit=50'

# Query Mimir metrics
curl -s -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -G "${GRAFANA_URL}/api/datasources/proxy/uid/${MIMIR_UID}/api/v1/query" \
  --data-urlencode 'query=up{job=~".*platform.*"}'

# Check alert states
curl -s -H "Authorization: Bearer $GRAFANA_API_KEY" \
  "${GRAFANA_URL}/api/prometheus/grafana/api/v1/rules"
```

## Safety Rules

- **No destructive git operations** without approval (no force-push, no branch deletion without verification)
- **No unauthenticated operations** — always source API keys from config
- **No silent failures** — every error is logged and surfaced in the report
- **Hard stop on zero-drift failure** — if verification fails after a merge, halt and ask user
- **Respect `execution.max_iterations`** — no infinite loops

