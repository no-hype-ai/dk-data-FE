# Principle Tags

> One tag per constraint. If you can't write a test for it, it's not a tag — it's a guideline.
> Tags are enforced at CI. Guidelines go in the constitution.

## Active Tags

*Tags activated for this project. Violation is a build failure, not a warning.*

| Tag | Principle | Enforcement |
|-----|-----------|-------------|
| `[IDMPT]` | All write operations are idempotent and resumable from a persisted checkpoint | Test: kill mid-run, restart, verify zero duplicate rows (FR-026) |
| `[GITOP]` | All k8s changes via ArgoCD GitOps — no manual `kubectl apply` | ArgoCD sync required; manual kubectl on cluster → alert |
| `[SECRT]` | No secrets in YAML manifests or container images — Doppler only | CI grep YAML for hardcoded keys → fail |
| `[TESTE]` | All public interfaces have tests | pytest coverage gate on CI; integration tests run against real CNPG postgres (no DB mocks) |
| `[WALMX]` | No single SQL transaction may produce more than 2 GB WAL | Application-side accounting via `pg_current_wal_lsn()` brackets writing to `meta.transform_runs`; CI audit script estimates WAL pre-merge for any model touching tables >1M rows |
| `[DSN]` | All Python DB connections via `dk_data.ingestion.utils.database.build_dsn()` | CI grep: any `psycopg2.connect(` outside `database.py` → fail |
| `[SVANT]` | Silver models contain none of the 5 banned antipatterns S1–S5 (OR-joins on hub-eligible identifiers; leading-wildcard `LIKE`; correlated scalar subqueries; global `DISTINCT ON` over UNION ALL; trigram similarity in OR with `=`) | CI grep `src/dk_data/sqlmesh/models/**/silver/*.sql` for the five regex signatures → fail on any match |
| `[CARRY]` | Every silver model carries forward every non-system bronze column | pytest contract test using SQLMesh `Context.dag.upstream()` introspection → fail on missing column |
| `[JOBLK]` | Cross-pod coordination uses `meta.job_locks` — no session-scoped `pg_try_advisory_lock` | CI grep: `pg_try_advisory_lock` outside the migration files that define `meta.job_locks` itself → fail |
| `[PGBOU]` | Long-running fetcher and short-lived transform pods route through PgBouncer (`POSTGRES_HOST`); SQLMesh and PL/pgSQL procedures use `POSTGRES_HOST_DIRECT` | Helm/Kustomize lint: every Deployment / CronJob env block must reference both vars; integration test asserts `pg_stat_activity.client_addr` distribution |
| `[ZVAL]`  | All API inputs validated with Pydantic schemas | CI grep: FastAPI route handlers must declare typed Pydantic body/query params — no raw `Request.json()` access |
| `[VERSN]` | All API contracts versioned | FastAPI routers must include `/v{n}/` prefix; CI grep `app.include_router` for unversioned prefixes → fail |
| `[RBAC]`  | Every endpoint has explicit role/permission assertion | Middleware/dependency test: unauthenticated request → 401; missing-role → 403 |
| `[STRM]`  | LLM/streaming responses — no blocking await on bodies | CI grep: no `await response.aread()` / `.json()` on `anthropic` or `openai` stream clients |
| `[NOLOG]` | No secrets, tokens, or credentials in logs | CI grep `structlog`/`loguru` call sites for key/token/password patterns → fail |
| `[BRKR]`  | Circuit breaker on all external service calls (Anthropic, OpenAI, CMS PUF, etc.) | `tenacity` retry wrapper required; raw `httpx`/`requests` calls outside the wrapper module → fail |
| `[AUDIT]` | All state mutations emit an audit event | Test: assert audit row written to `meta.audit_log` on every INSERT/UPDATE/DELETE in service layer |
| `[HIPAA]` | No ePHI outside encrypted, access-controlled storage | Storage class validation; PVC encryption annotation check; periodic audit log review |
| `[NCMPL]` | No PII/PHI in log output, error messages, or external response bodies | CI grep src/ for log/return statements containing PHI field names → fail |

## Available Tags

*Universal starter tags. Activate what applies to your project.*

### Code Quality

| Tag | Principle | Enforcement |
|-----|-----------|-------------|
| `[TYPED]` | Strict typing — no `any` or equivalent escape hatches | Type checker strict mode |
| `[DRYBK]` | Dry-run mode required on destructive actions | Test: `dryRun: true` no-ops |

### Architecture

| Tag | Principle | Enforcement |
|-----|-----------|-------------|
| `[SEGMN]` | All data access scoped to tenant/org/user segment | Queries must include scope parameter |
| `[IMMUT]` | Audit/event logs are append-only, never modified | Write test: attempt delete → must reject |

### Frontend

| Tag | Principle | Enforcement |
|-----|-----------|-------------|
| `[NOHYD]` | No SSR/client hydration mismatch | `useEffect`-gated renders; Playwright check |
| `[LATBK]` | Interaction response < 200ms before streaming starts | Lighthouse CI budget + timing test |
| `[A11Y]`  | WCAG 2.1 AA compliance on all interactive elements | axe-core integration test |
| `[CNTXT]` | Components must not break React context chain | Integration test: render in full provider tree |

### Infrastructure

| Tag | Principle | Enforcement |
|-----|-----------|-------------|
| `[PKI]`   | All internal TLS via CA — no self-signed certs | cert-manager issuer annotation required |

## Usage

Annotate code, tests, and commits with active tags:

```
# File headers
# [ZVAL][AUDIT][RBAC]
# UserService — handles user CRUD with org scoping

# Test names
def test_audit_user_creation():  # [AUDIT]
    ...

# Commit messages
feat(users): add org-scoped user service [ZVAL][AUDIT][RBAC]
fix(auth): scrub PHI from error responses [NCMPL]
```

## Adding New Tags

1. Name it — 3-6 chars, UPPERCASE, self-describing
2. Define it — one sentence, unambiguous
3. Write the CI check first — enforcement before usage
4. Add to Active Tags above
5. Run `.dk/scripts/bash/update-agent-context.sh` to propagate
