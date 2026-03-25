# dk CLI Gaps and Recommendations

**Created:** 2026-03-25
**Context:** Testing dk CLI v0.1.0 against dk-data-FE for full dk-managed adoption
**Auth:** nick@datakinetic.com — local config role was `readonly` (stale cache), API-resolved role: `developer`

---

## Test Log

### Commands Tested

| Command | Result | Gap? | Notes |
|---------|--------|------|-------|
| `dk doctor` | PASS | No | Binary v0.1.0, config found, auth OK, Platform API healthy, gh CLI authenticated |
| `dk whoami` | PASS | Yes | Returns `developer` from API but local config cached `readonly` (G1) |
| `dk --help` | PASS | Yes | Missing commands: `status`, `review`, `list`, `labels`, `data` (G2) |
| `dk promote status` | PASS | Yes | Shows "No deployment" despite active ArgoCD deployments (G5) |
| `dk promote preview --help` | PASS | No | |
| `dk adopt --verify` (readonly) | FAIL | Yes | Required developer role for read-only check (G3) |
| `dk adopt --verify` (developer) | PASS | No | Found 2 missing: `k8s/apps` (per-service), `build-deploy.yaml` (naming) |
| `dk onboard --status` (readonly) | FAIL | Yes | Required developer role for read-only check (G3) |
| `dk onboard --status` (developer) | PASS | No | 4/7 checks pass (see Onboard Results below) |
| `dk list` | FAIL | Yes | "unknown command" — not shipped in v0.1.0 (G2) |
| `dk labels` | FAIL | Yes | "unknown command" — not shipped in v0.1.0 (G2) |
| `dk data` | FAIL | Yes | "unknown command" — not shipped in v0.1.0 (G2) |
| `dk status` | FAIL | Yes | "unknown command" — not shipped in v0.1.0 (G2) |
| `dk review` | FAIL | Yes | "unknown command" — not shipped in v0.1.0 (G2) |
| `dk plugin --help` | PASS | No | Subcommands: install, update |
| `dk create --help` | PASS | No | |

### dk adopt --verify Results

After creating all platform files:
```
✓ .dk-standards.yaml: product=dk-data, team=data-platform
✗ Missing 2 platform files:
    k8s/apps                            ← expects per-service layout (Phase 4 in plan)
    .github/workflows/build-deploy.yaml ← expects exact name (we have build-push.yaml)
```

### dk onboard --status Results

```
✓ .dk-standards.yaml exists and is valid
✓ ArgoCD applications defined in .gitops/
✗ Kubernetes manifests in k8s/          ← expects k8s/apps/ per-service structure
✗ CI workflow uses shared build-deploy.yaml  ← expects shared workflow reference
✓ Grafana dashboard and alerts in monitoring/
✗ GitHub labels synced to platform taxonomy  ← needs dk labels sync (command not shipped)
✓ dk-alchemy bootstrap PR submitted

4/7 complete
```

### Commands Not Tested (require side effects)

| Command | Reason |
|---------|--------|
| `dk login` | Would overwrite current auth; requires interactive browser flow |
| `dk promote preview` | Would create a live deployment |
| `dk promote staging` | Would open GitHub approval issue |
| `dk promote production` | Requires admin role |
| `dk create` | Would scaffold a new repo |
| `dk plugin install` | Would modify Claude Code plugins |

---

## Gaps Found

### G1. Role Mismatch Between Local Config and API (FIXED MANUALLY)

**Severity:** HIGH — blocked all developer-level commands

`dk doctor` reported `readonly` from `~/.dk/config.yaml`. `dk whoami` returned `developer` from API.
All `requireRole("developer")` checks use the local cached value.

**Root cause:** `getCurrentRole()` reads `config.auth?.role ?? "readonly"`. The role was cached at login time and never refreshed.

**Workaround applied:** Manually edited `~/.dk/config.yaml` to set `role: developer`.

**Fix needed in CLI:**
1. `dk doctor` should flag when local role differs from API role
2. CLI should refresh role from API when local role is insufficient (try API before failing)
3. Consider role TTL — re-validate periodically

### G2. Commands Documented in Source But Not Shipped in v0.1.0

**Severity:** MEDIUM

Not available in v0.1.0 despite being in dk-alchemy source:
- `dk status` — repo health dashboard
- `dk review` — platform compliance audit
- `dk list` — list all dk-managed projects
- `dk labels sync/audit` — GitHub label taxonomy management
- `dk data keys` — data API key management

**Impact:** Cannot validate compliance or manage labels via CLI. `dk onboard --status` partially fills the gap but `dk labels sync` is needed to pass the labels check.

### G3. Read-Only Flags Require Developer Role

**Severity:** MEDIUM

- `dk adopt --verify` — explicitly read-only but requires `developer`
- `dk onboard --status` — explicitly read-only but requires `developer`

**Fix:** These should require `readonly` role since they make no changes.

### G4. dk adopt --verify Expects Exact File Names

**Severity:** LOW

`dk adopt --verify` checks for `.github/workflows/build-deploy.yaml` specifically. dk-data-FE has `.github/workflows/build-push.yaml` which serves the same purpose but uses a different name.

**Fix options:**
1. CLI should check for any workflow that builds and deploys (pattern match)
2. Or document that `build-deploy.yaml` is the canonical name repos must use
3. dk-data-FE could create a `build-deploy.yaml` wrapper (Choice 5B already decided against this)

### G5. Promotion Status Doesn't Detect Legacy Deployments

**Severity:** LOW

`dk promote status` shows "No deployment" for all stages despite dk-data-FE having active ArgoCD deployments in `dk-data-staging` and `dk-data-prod` namespaces.

**Root cause:** The promotion system only tracks deployments created through `dk promote` commands. Legacy deployments managed directly via ArgoCD are invisible.

**Fix:** Platform API should query ArgoCD for existing Application resources matching the product name.

### G6. dk onboard Labels Check Has No Remediation Path

**Severity:** MEDIUM

`dk onboard --status` reports "GitHub labels synced to platform taxonomy" as failing, but the `dk labels sync` command needed to fix it doesn't exist in v0.1.0.

**Impact:** Users cannot reach 7/7 onboarding completion without a command that isn't shipped.

### G7. k8s/apps Per-Service Structure is Mandatory

**Severity:** MEDIUM — affects all legacy repos

Both `dk adopt --verify` and `dk onboard --status` expect `k8s/apps/<service>/` structure. Legacy repos using `k8s/base/` + `k8s/overlays/` pattern fail this check.

**Impact:** All repos predating the template must restructure their K8s manifests to pass adoption checks. This is a significant migration for repos with many resources.

**Recommendation:** Either:
1. Accept `k8s/base/` + `k8s/overlays/` as a legacy-compatible alternative
2. Or provide a `dk migrate k8s` command to automate the restructure

---

## Recommendations

### For dk CLI team (dk-alchemy)

| Priority | Recommendation | Gap |
|----------|---------------|-----|
| P0 | Fix role resolution — refresh from API when local cache is stale | G1 |
| P0 | Relax role requirements for `--verify` and `--status` flags | G3 |
| P1 | Ship `dk labels sync` — needed to pass onboarding check | G2, G6 |
| P1 | Ship `dk status` and `dk review` — highest-value repo management commands | G2 |
| P2 | Accept `build-push.yaml` as alternative to `build-deploy.yaml` | G4 |
| P2 | Detect legacy ArgoCD deployments in `dk promote status` | G5 |
| P2 | Support legacy `k8s/base/` layout or provide migration tool | G7 |
| P3 | Ship `dk list` and `dk data` commands | G2 |

### For dk-data-FE (remaining work from dk-data-prod.md)

| Priority | Item | Status |
|----------|------|--------|
| Done | `.dk-standards.yaml` full schema | ✓ |
| Done | `.dk-os/config.yaml` | ✓ (manual, dk adopt blocked) |
| Done | CODEOWNERS | ✓ |
| Done | renovate.json | ✓ |
| Done | `/ready` endpoint | ✓ |
| Done | Monitoring dashboards + alerts | ✓ |
| Done | `_dk-alchemy-pr/README.md` | ✓ |
| Done | Archive specs to docs/archive | ✓ |
| Phase 4 | Restructure `k8s/` to per-service layout | Needed to pass `dk adopt --verify` |
| Phase 5 | Rename Doppler project to `dk-data-applications` | Maintenance window needed |
| Phase 7 | Add shared standards workflow or rename `build-push.yaml` | Needed to pass `dk onboard` |
| Blocked | `dk labels sync` for GitHub label taxonomy | Command not shipped (G6) |

### dk onboard Score After This Session

**Before:** Not runnable (role blocked)
**After:** 4/7 (57%)
**Achievable without CLI fixes:** 5/7 (rename workflow to `build-deploy.yaml`)
**Achievable with Phase 4 k8s restructure:** 6/7 (85%)
**Full 7/7 requires:** `dk labels sync` command to be shipped
