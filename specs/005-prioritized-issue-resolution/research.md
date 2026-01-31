# Research: Prioritized Issue Resolution

**Feature**: 005-prioritized-issue-resolution
**Date**: 2026-01-30
**Status**: Complete

## Research Topics

### 1. JWT Secret Security Best Practices

**Question**: What is the minimum JWT secret length for HS256 algorithm security?

**Decision**: Require minimum 256-bit (32-byte) JWT secret

**Rationale**:
- NIST SP 800-131A recommends at least 256 bits for symmetric keys
- HS256 uses HMAC-SHA256 which has a 256-bit output
- PostgREST documentation recommends 256-bit minimum
- Shorter secrets are vulnerable to brute-force attacks

**Alternatives Considered**:
- 128-bit: Insufficient for modern security standards
- 512-bit: Overkill, no added security benefit for HS256

**Implementation**:
```bash
# Validation in init container
if [ -z "$PGRST_JWT_SECRET" ] || [ ${#PGRST_JWT_SECRET} -lt 32 ]; then
  echo "ERROR: JWT secret must be at least 32 characters (256 bits)"
  exit 1
fi
```

---

### 2. PostgREST Anonymous Role Hardening

**Question**: How should anonymous access be restricted in PostgREST?

**Decision**: Use explicit view-level GRANT with REVOKE before GRANT pattern

**Rationale**:
- PostgREST uses the `db-anon-role` for unauthenticated requests
- By default, `web_anon` should have NO access to sensitive data
- Explicit GRANT to specific views (health, data_catalog) is safer than blanket access
- REVOKE before GRANT ensures clean permission state even if previous grants existed

**Implementation**:
```sql
-- Revoke any existing broad permissions
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA api FROM web_anon;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_api FROM web_anon;

-- Grant only to specific public views
GRANT USAGE ON SCHEMA api TO web_anon;
GRANT SELECT ON api.health TO web_anon;
GRANT SELECT ON api.data_catalog TO web_anon;
```

**Alternatives Considered**:
- Keep blanket SELECT on API schema: Security risk, exposes sensitive data
- Disable anonymous role entirely: Breaks health checks and public APIs
- Use RLS instead: More complex, RLS still requires base table access

---

### 3. SQL Heredoc Escaping in Kubernetes Jobs

**Question**: How to properly escape PL/pgSQL `DO $$...$$` blocks in shell heredocs?

**Decision**: Use `<<'SQL'` (single-quoted heredoc) with explicit EOF delimiter

**Rationale**:
- Single-quoted heredocs (`<<'SQL'`) prevent shell variable expansion
- The `$$` PostgreSQL delimiter is passed literally to psql
- This avoids conflicts between shell and PostgreSQL quoting
- Tested pattern from existing 003-alchemy-cluster-deploy implementation

**Implementation**:
```bash
psql -d dk_data <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticator') THEN
    CREATE ROLE authenticator LOGIN NOINHERIT;
  END IF;
END $$;
SQL
```

**Current Issue**: The existing db-init-job.yaml already uses `<<'SQL'` correctly, but may have issues with the `DO $$` blocks if they span multiple heredocs or have nested quotes.

**Alternatives Considered**:
- Use `$tag$...$tag$` instead of `$$`: More explicit but same escaping rules
- Write SQL to ConfigMap: Adds complexity, harder to maintain inline

---

### 4. PostgreSQL Health Check View Design

**Question**: What should the health check view return for Kubernetes probes?

**Decision**: Simple view returning status and timestamp

**Rationale**:
- Kubernetes probes need fast, reliable responses
- Minimal query ensures quick response (<10ms)
- Timestamp helps debugging but isn't required for probe
- No external dependencies (no joins, no function calls)

**Implementation**:
```sql
CREATE OR REPLACE VIEW api.health AS
SELECT
  'ok'::text AS status,
  now() AS timestamp,
  current_database() AS database;
```

**PostgREST Response**:
```json
[{"status": "ok", "timestamp": "2026-01-30T12:00:00Z", "database": "dk_data"}]
```

**Alternatives Considered**:
- Include database connection count: Adds complexity, may be slow
- Include schema versions: Good for debugging but not for health probe
- Use stored function: Overkill for simple health check

---

### 5. Data Catalog View Structure

**Question**: What metadata should the data_catalog view expose?

**Decision**: Show data source name, last update timestamp, and record count

**Rationale**:
- Helps operators understand data freshness
- Provides API consumers with source metadata
- Read-only, safe for anonymous access
- Uses PostgreSQL system catalogs for metadata

**Implementation**:
```sql
CREATE OR REPLACE VIEW api.data_catalog AS
SELECT
  schemaname,
  tablename,
  n_live_tup AS row_count,
  last_vacuum,
  last_analyze
FROM pg_stat_user_tables
WHERE schemaname IN ('raw', 'staging', 'mart', 'mol_raw', 'mol_bronze', 'mol_silver', 'mol_gold')
ORDER BY schemaname, tablename;
```

**Alternatives Considered**:
- Manual metadata table: Requires maintenance, can drift from reality
- Include column definitions: Too detailed for catalog overview
- Filter to specific tables only: Less flexible, requires updates

---

### 6. GitHub Actions CI Best Practices

**Question**: What CI workflow structure is appropriate for this project?

**Decision**: Separate CI (test) and CD (build-push) workflows

**Rationale**:
- CI runs on pull requests to provide fast feedback
- CD runs on merge to main/staging to build and push images
- Separation allows faster PR checks without full image builds
- pytest + ruff provides Python testing and linting

**Implementation**:
```yaml
# .github/workflows/ci.yaml
name: CI
on:
  pull_request:
    branches: [main, staging]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install .[dev]
      - run: ruff check .
      - run: pytest tests/
```

**Alternatives Considered**:
- Single workflow with conditional jobs: More complex, harder to maintain
- Matrix testing for multiple Python versions: Overkill for single-version project
- Use pre-built test image: Adds image build overhead

---

### 7. ServiceMonitor CRD Availability

**Question**: How to safely enable ServiceMonitor when CRDs may not exist?

**Decision**: Check CRD existence before enabling, keep disabled by default

**Rationale**:
- ServiceMonitor is a Prometheus Operator CRD
- Applying resources for missing CRDs causes ArgoCD sync failures
- dk-alchemy may or may not have Prometheus Operator installed
- Better to fail gracefully with warnings than break deployment

**Implementation**:
1. Keep ServiceMonitor and PrometheusRule commented in kustomization.yaml by default
2. Document CRD verification step in quickstart.md
3. Enable only after verifying CRDs exist:
   ```bash
   kubectl get crd servicemonitors.monitoring.coreos.com
   kubectl get crd prometheusrules.monitoring.coreos.com
   ```

**Alternatives Considered**:
- Always include (fail if missing): Blocks deployment unnecessarily
- Conditional Kustomize: Not natively supported, requires Helm
- ArgoCD ignoreDifferences: Doesn't prevent initial sync failure

---

## Summary

All research topics have been resolved with clear decisions and implementation guidance. No NEEDS CLARIFICATION items remain. Ready to proceed with Phase 1 design artifacts.

| Topic | Decision | Impact |
|-------|----------|--------|
| JWT Secret Length | 256-bit minimum | Security hardening |
| Anonymous Access | Explicit view-level GRANT | Security hardening |
| Heredoc Escaping | Single-quoted with SQL delimiter | DB init fix |
| Health View | Simple status+timestamp | API schema creation |
| Data Catalog | pg_stat_user_tables view | API schema creation |
| CI Workflow | Separate CI/CD, pytest+ruff | CI/CD pipeline |
| ServiceMonitor | Check CRD before enable | Observability |
