---
description: End-to-end app audit — health checks, route discovery, user story generation, Chrome DevTools testing, GitHub issue filing, and fix loop until zero issues remain. Config-driven — works with any project.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Phase 0: Config Generation

**FIRST**: Check if `.dk/debug-e2e-config.json` exists at the project root.

- **If it exists**: Read it, parse it, store as `CONFIG`, and skip to Argument Parsing.
- **If it does NOT exist**: Auto-generate it by introspecting the project (steps below), write the result to `.dk/debug-e2e-config.json`, then store as `CONFIG`.

### Auto-Generation Steps

Read the template schema from `.dk/debug-e2e-config.template.json` for the expected structure. Then populate every field by introspecting the project:

#### 1. Project Name

- Read `package.json` at the repo root (or monorepo root). Use the `name` field.
- If a monorepo, prefer the root `package.json` name. Fall back to the directory basename.

#### 2. Deployment Type

Detect from project files:
- `Dockerfile` or `docker-compose.yml` → `"docker"`
- `vercel.json` or `.vercel/` → `"vercel"`
- K3s/Kubernetes manifests (`k8s/`, `deploy/`, `*.yaml` with `kind: Deployment`) → `"k3s"`
- None of the above → `"custom"`

#### 3. Environments & Services

- **Services**: Scan for apps in the monorepo (`apps/*/` directories) or treat a single-app repo as one service named after the package.
- **Ports**: Read each app's `package.json` `scripts.dev` for port numbers, or check `next.config.*` / `vite.config.*` for port settings. Default: 3000 for the first app, incrementing for each additional.
- **Local environment**: Build from discovered services + ports (e.g., `"web": "http://localhost:3000"`).
- **Staging/Production**: If a context file or deployment config mentions domains, use them. Otherwise, leave only `"local"` and set `default_environment` to `"local"`.

#### 4. Health Endpoints

- Grep for health/readiness routes: `Grep` for `health`, `readiness`, `liveness` in API route files.
- Common patterns: `/api/health`, `/health`, `/health/liveness`.
- If none found, set to `"/api/health"` as a default (will be tested in Phase 1 and updated if 404).

#### 5. Auth Detection

- `"none"` if no auth dependencies found.
- Detect provider by checking `package.json` dependencies across all apps:
  - `@clerk/nextjs` → `"clerk"`, selectors: `input[name='identifier']`, `input[name='password']`, `button[data-localization-key='formButtonPrimary']`
  - `next-auth` / `@auth/core` → `"nextauth"`, selectors: generic form inputs
  - `@auth0/nextjs-auth0` → `"auth0"`, selectors: generic form inputs
- If no auth package found, set `"provider": "none"` and omit `sign_in_selectors`.
- Look for sign-in page files to determine `sign_in_path` (e.g., `app/sign-in/`, `app/(auth)/sign-in/`).

#### 6. Route Discovery Patterns

- Build glob patterns from the actual app structure:
  - For each app directory, generate `"<app_path>/**/page.tsx"` for pages.
  - For API routes: `"<app_path>/api/**/route.ts"`.
  - For webhooks: look for `webhooks/` directories in API apps.
  - For cron: look for `cron/` directories.
- If single app (not monorepo), use relative paths like `"src/app/**/page.tsx"`.

#### 7. GitHub Repo

- Run `git remote get-url origin` and parse `owner/repo` from the result.
- If no remote, leave as `""` and warn that GitHub issue filing will be skipped.

#### 8. Logs Command

- If deployment type is `"k3s"`, set to `null` (logs require cluster access — user can override).
- If `"docker"`, set to `"docker compose logs --tail=50 --since=1h"` if `docker-compose.yml` exists.
- Otherwise, `null`.

### Write & Confirm

Write the generated config to `.dk/debug-e2e-config.json`. Print a summary of what was detected:

```
Config generated → .dk/debug-e2e-config.json

  Project:      <name>
  Deployment:   <type>
  Services:     <list>
  Auth:         <provider or "none">
  GitHub:       <owner/repo or "no remote">
  Environments: <list of env names>
```

Ask the user to confirm or adjust before proceeding. If `$ARGUMENTS` contains `--auto`, skip confirmation and proceed immediately.

### Config Schema Reference

```json
{
  "project": "string — project name",
  "deployment": {
    "type": "string — k3s|vercel|docker|custom",
    "environments": {
      "<env_name>": {
        "<service_name>": "https://url"
      }
    },
    "default_environment": "string — which env to use by default",
    "health_endpoints": {
      "<service_name>": "/path/to/health"
    },
    "logs_command": "string|null — shell command to fetch recent logs, or null if unavailable"
  },
  "auth": {
    "provider": "string — clerk|auth0|nextauth|custom|none",
    "sign_in_path": "/sign-in",
    "sign_in_selectors": {
      "email_input": "CSS selector",
      "password_input": "CSS selector",
      "continue_button": "CSS selector"
    }
  },
  "route_discovery": {
    "page_patterns": ["glob patterns for page files"],
    "api_patterns": ["glob patterns for API route files"],
    "webhook_patterns": ["glob patterns for webhook handlers"],
    "cron_patterns": ["glob patterns for cron jobs"]
  },
  "github": {
    "repo": "owner/repo",
    "labels": ["label1", "label2"]
  }
}
```

## Argument Parsing

Parse `$ARGUMENTS` to extract:

- **`--env <name>`** (optional): Environment to test — must match a key in `CONFIG.deployment.environments`. Defaults to `CONFIG.deployment.default_environment`.
- **Email**: Any argument containing `@` (e.g., `nick@example.com`)
- **Password**: The argument immediately following the email
- **`--resume`**: If present, load saved state from `.dk/debug-e2e-state.json` and skip to the last incomplete phase
- **`--service <name>`** (optional): Test only a specific service (e.g., `--service app`). Defaults to all services.

Example invocations:
- `/dk.debug nick@example.com MyPassword`
- `/dk.debug --env production nick@example.com MyPassword`
- `/dk.debug --env local --service app`
- `/dk.debug --resume`

If credentials are not provided and `CONFIG.auth.provider` is not `none`, warn that auth-protected flows cannot be tested automatically and ask whether to proceed with public-only testing.

---

## Resume Check

If `--resume` was passed:

1. Read `.dk/debug-e2e-state.json`
2. Parse `current_phase` and skip completed phases
3. Restore `urls`, `user_stories`, `bugs_found` from state
4. Jump to the incomplete phase below

If the state file does not exist, warn and start from Phase 1.

---

## Phase 1: Reconnaissance

**Goal**: Assess deployed health and build a complete route map.

### Step 1.1 — Deployment Health

For each service in the selected environment's URLs:

```bash
for service in <services from CONFIG.deployment.environments[env]>; do
  URL="<service_url><health_endpoint>"
  STATUS=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 "$URL" 2>/dev/null || echo "unreachable")
  echo "$service: $STATUS ($URL)"
done
```

If `CONFIG.deployment.logs_command` is not null, run it to capture recent error logs.

Record any unhealthy services.

### Step 1.2 — Route Discovery

For each pattern in `CONFIG.route_discovery`:

- **Pages**: Glob each pattern in `page_patterns`
- **API routes**: Glob each pattern in `api_patterns`
- **Webhooks**: Glob each pattern in `webhook_patterns`
- **Cron jobs**: Glob each pattern in `cron_patterns`

### Step 1.3 — Categorize Routes

Organize discovered routes into a table dynamically. For monorepos with multiple apps, group by app:

| App | Category | Routes |
|-----|----------|--------|
| app | Public | `/`, `/sign-in`, `/sign-up` |
| app | Auth | `/(organization)/*` |
| api | Webhooks | `/webhooks/stripe`, `/webhooks/github`, ... |
| web | Public | `/`, `/blog`, `/pricing`, ... |

> **Note**: Build this table entirely from Glob results — never hardcode routes.

### Step 1.4 — Observability Check

Check for Sentry, OpenTelemetry, or other observability:

```bash
# Check for Sentry
ls **/sentry.*.config.* 2>/dev/null
# Check for OTEL
grep -r "opentelemetry\|@repo/observability" --include="*.ts" -l | head -5
```

Note what observability is active.

### Step 1.5 — Save State

Save initial state to `.dk/debug-e2e-state.json`:

```json
{
  "project": "<CONFIG.project>",
  "environment": "<selected env>",
  "urls": { "<service>": "<url>", ... },
  "started_at": "<ISO timestamp>",
  "current_phase": 1,
  "route_map": {
    "<app>": {
      "pages": [...],
      "api": [...],
      "webhooks": [...],
      "cron": [...]
    }
  },
  "health": { "<service>": "<status>", ... },
  "user_stories": [],
  "bugs_found": []
}
```

### Step 1.6 — Report

Print the full route table, health status, and any log errors found.

---

## Phase 2: User Story Generation

**Goal**: Create testable user stories covering every discovered route, and file each as a GitHub issue.

### Step 2.1 — Generate Stories

Analyze the discovered routes and generate user stories. Group stories by:

1. **Public flows** — visitor-facing pages across all services
2. **Auth flows** — sign-in, sign-up, onboarding
3. **Core product flows** — one story per major section
4. **API health** — all API endpoints return expected status codes
5. **Integration flows** — webhook endpoints, external service connections
6. **Admin flows** — settings, billing, integrations

Each story must:
- Reference specific routes from the discovered route map
- List preconditions (authentication state, data requirements)
- Include test steps that can be executed via Chrome DevTools
- Cover at least one route — every route must appear in at least one story

### Step 2.2 — Create GitHub Issues

Ensure labels exist:

```bash
for label in <CONFIG.github.labels>; do
  gh label create "$label" --description "E2E debug audit" --color "D93F0B" --repo <CONFIG.github.repo> 2>/dev/null || true
done
```

For each user story, create a GitHub issue in `CONFIG.github.repo`:

```bash
gh issue create --repo <CONFIG.github.repo> --title "E2E: US-XX — <story title>" --label "<labels>" --body "$(cat <<'EOF'
## User Story
**As a** <user type>, **I want to** <action>, **so that** <outcome>.

## Preconditions
- <list preconditions>

## Test Steps
1. Navigate to <URL>
2. <action>
...

## Expected Results
- [ ] <expected outcome 1>
- [ ] <expected outcome 2>

## Status
- [ ] Tested
- [ ] All checks passed
EOF
)"
```

Record each issue number in the state file.

### Step 2.3 — Update State

Update `current_phase` to 2 and record all user stories with their GitHub issue numbers.

---

## Phase 3: Systematic Testing via Chrome DevTools

**Goal**: Execute every user story using Chrome DevTools MCP, capture all issues.

### Step 3.0 — Browser Setup

1. Use `list_pages` to check for available browser targets
2. If no pages exist, use `new_page` to create one
3. Use `select_page` to ensure we're on the right target

### Step 3.1 — Test Public Flows

For stories requiring no authentication, for each service URL:

1. `navigate_page` to the service URL
2. `take_screenshot` — verify page renders
3. `list_console_messages` — check for JavaScript errors
4. `list_network_requests` — check for failed requests (4xx/5xx)
5. `click` on navigation elements to visit each public page
6. `take_screenshot` at each page
7. Repeat console + network checks at each step

### Step 3.2 — Authenticate

If credentials were provided and `CONFIG.auth.provider` is not `none`:

1. `navigate_page` to `<primary_app_url><CONFIG.auth.sign_in_path>`
2. `take_screenshot` — capture sign-in page
3. `wait_for` the email input using `CONFIG.auth.sign_in_selectors.email_input`
4. `fill` the email field with the provided email
5. `click` the continue button using `CONFIG.auth.sign_in_selectors.continue_button`
6. `wait_for` the password field using `CONFIG.auth.sign_in_selectors.password_input`
7. `fill` the password field with the provided password
8. `click` the continue button again
9. `wait_for` navigation to complete
10. `take_screenshot` — verify successful login
11. `list_console_messages` — check for auth errors

> **If sign-in fails**: Use `take_snapshot` to inspect the DOM, adapt selectors dynamically. If all attempts fail, note that auth-protected stories cannot be tested.

### Step 3.3 — Test Auth-Protected Flows

For each authenticated user story, execute sequentially:

1. `navigate_page` to the target route
2. `wait_for` page content to load
3. `take_screenshot` — capture initial state
4. `list_console_messages` — record any errors
5. `list_network_requests` — record any failures
6. Perform story-specific actions using `fill`, `click`, `wait_for`, `evaluate_script`
7. `take_screenshot` after each action
8. Check console + network after each action

### Step 3.4 — Test API Endpoints

For API routes that cannot be browser-tested, use Bash:

```bash
for route in <discovered_api_routes>; do
  URL="<api_service_url>$route"
  STATUS=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 "$URL" 2>/dev/null || echo "timeout")
  echo "$route: $STATUS"
done
```

For authenticated endpoints, extract auth cookies from browser session via `evaluate_script` first.

### Step 3.5 — File Bug Issues

For **every issue found** during testing — no matter how small:

```bash
gh issue create --repo <CONFIG.github.repo> --title "Bug: <concise description>" --label "<labels joined>" --body "$(cat <<'EOF'
## Bug Report

**Found during**: US-XX — <story title>
**Severity**: critical | major | minor | cosmetic
**Service**: <service name>
**Route**: <URL where issue was found>

## Reproduction Steps
1. Navigate to <URL>
2. <action>
3. Observe: <what went wrong>

## Expected Behavior
<what should happen>

## Actual Behavior
<what actually happened>

## Evidence
- Console errors: <paste relevant console messages>
- Network failures: <paste relevant failed requests>
- Screenshot: <description of what screenshot shows>

## Related Files
- <file paths that likely need fixing>
EOF
)"
```

> **CRITICAL**: No issues left behind. Every console error, every failed network request, every visual bug, every broken interaction — all get an issue.

### Step 3.6 — Update State

After testing each story, update the state:
- Mark story `status` as `"tested"`
- Add bugs to `bugs_found` with GitHub issue numbers
- Update parent story issue with test results comment

---

## Phase 4: Fix Loop

**Goal**: Resolve every open bug issue.

### Step 4.1 — Get Open Bugs

```bash
gh issue list --repo <CONFIG.github.repo> --label "<labels>" --state open --json number,title,body --limit 100
```

If zero open bugs, skip to Phase 5.

### Step 4.2 — Fix Each Bug

For each open bug, sequentially:

1. **Read** the issue body for reproduction steps
2. **Investigate** root cause — read source files, use Grep, use Agent tool for parallel investigation
3. **Implement** the fix — edit minimum files, follow existing patterns
4. **Re-test** the affected route via Chrome DevTools
5. **Close or update** the issue:
   - Fixed: `gh issue close <number> --repo <CONFIG.github.repo> --reason completed --comment "Fixed. Verified via Chrome DevTools."`
   - Partial: `gh issue comment <number> --repo <CONFIG.github.repo> --body "Partial fix. Remaining: <details>"`

### Step 4.3 — Regression Check

After fixing bugs, re-check affected routes for new issues. If found, create new bug issues and add to loop.

### Step 4.4 — Loop Until Clear

```
REPEAT:
  bugs = gh issue list --label "<labels>" --state open
  IF bugs is empty: BREAK → Phase 5
  ELSE: Step 4.2 with next bug
```

Rules:
- Never "won't fix" — every issue must be resolved
- Never remove a feature to fix a bug
- If genuinely blocked (third-party dependency), document in issue but do NOT close
- Use Agent tool for parallel investigation of unrelated bugs

### Step 4.5 — Update State

Update `.dk/debug-e2e-state.json` after each fix cycle.

---

## Phase 5: Verification

**Goal**: Confirm all user stories pass with zero issues remaining.

### Step 5.1 — Full Re-test

Re-run ALL user stories from Phase 3:

1. Execute all test steps per story
2. Screenshot + console + network at each step
3. If ANY new issues found → create bug issues → loop back to Phase 4

### Step 5.2 — Final Audit

```bash
# Zero open bugs
gh issue list --repo <CONFIG.github.repo> --label "<labels>" --state open --json number,title

# Total found and fixed
gh issue list --repo <CONFIG.github.repo> --label "<labels>" --state closed --json number | jq length

# All story issues
gh issue list --repo <CONFIG.github.repo> --label "dk-debug" --state all --json number,title,state
```

### Step 5.3 — Close Story Issues

```bash
gh issue close <number> --repo <CONFIG.github.repo> --reason completed --comment "All test steps passed in final verification."
```

### Step 5.4 — Summary Report

```
============================================
  E2E DEBUG AUDIT — FINAL REPORT
============================================

Project:     <CONFIG.project>
Environment: <selected env>
Started:     <timestamp>
Completed:   <timestamp>

SERVICES:
  <service>: <health status> (<url>)
  ...

USER STORIES:
  US-01: <title>    PASS
  US-02: <title>    PASS
  ...

ISSUES:
  Total found:    XX
  Total fixed:    XX
  Still open:     0

ROUTES TESTED:
  Pages:     X/X covered
  API:       X/X covered
  Webhooks:  X/X covered
  Cron:      X/X covered

ALL CLEAR — Zero open issues remaining.
============================================
```

### Step 5.5 — Cleanup State

```bash
rm -f .dk/debug-e2e-state.json
```

---

## Error Handling

- **Config generation fails**: If introspection cannot determine a required field, write the config with placeholder values and ask the user to fill in the missing fields before proceeding
- **Chrome DevTools connection lost**: `list_pages` to reconnect. If fails, ask user to restart browser and `--resume`.
- **GitHub CLI not authenticated**: `gh auth status`. If not logged in, instruct `! gh auth login`.
- **Auth sign-in changes**: `take_snapshot` to inspect DOM, adapt selectors dynamically.
- **Rate limits**: Pause 60s and retry on `gh issue create` rate limits.
- **Service unreachable**: Mark as unhealthy, skip routes for that service, file a bug issue for the outage.

