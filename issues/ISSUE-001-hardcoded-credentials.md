# ISSUE-001: Hardcoded Credentials in Docker Compose and SQL

**Project**: dk-data-FE
**Category**: Security
**Priority**: P0 - Critical
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The dk-data-FE codebase contains hardcoded default credentials in multiple configuration files that are committed to version control. This creates significant security risks if these defaults are used in production environments.

---

## Affected Files

| File | Line | Credential Type |
|------|------|-----------------|
| `src/dk_data/docker-compose.yml` | 33-35 | PostgreSQL credentials |
| `src/dk_data/docker-compose.yml` | 60 | PostgREST authenticator password |
| `src/dk_data/docker-compose.yml` | 100-101 | Job trigger DB credentials |
| `src/dk_data/sql/init_database.sql` | 413 | Authenticator role password |

---

## Evidence from Codebase

### docker-compose.yml (lines 33-35, 60)

```yaml
environment:
  POSTGRES_USER: "${POSTGRES_USER:-postgres}"
  POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:-postgres}"
  POSTGRES_DB: "${POSTGRES_DB:-edwards_tavr}"
```

```yaml
PGRST_DB_URI: "postgres://authenticator:${POSTGREST_PASSWORD:-postgrest_secret_change_me}@postgres:5432/${POSTGRES_DB:-edwards_tavr}"
```

### init_database.sql (line 413)

```sql
CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'postgrest_secret_change_me';
```

**Critical Issue**: The SQL file hardcodes the password directly without any environment variable substitution capability.

---

## Risk Assessment

### Attack Vectors

| Vector | Likelihood | Impact |
|--------|------------|--------|
| Accidental production deployment with defaults | High | Critical |
| Repository access by unauthorized party | Medium | Critical |
| Credential stuffing attacks | Medium | High |
| Insider threat | Low | Critical |

### Compliance Implications

- **SOC 2**: Fails CC6.1 (Logical and Physical Access Controls)
- **HIPAA**: Potential violation of 164.312(d) (Authentication)
- **PCI-DSS**: Fails Requirement 2.1 (Vendor-supplied defaults)

---

## Current State Analysis

### Environment Variable Support

The `docker-compose.yml` uses the `${VAR:-default}` pattern, which provides environment variable override capability. However:

1. **No `.env.example` file** exists to guide users on required variables
2. **No validation** that environment variables are set before startup
3. **SQL initialization** cannot use environment variables at all
4. **Documentation** does not emphasize changing defaults

### Secret Detection

```bash
# Secrets found in codebase:
$ grep -r "password" --include="*.yml" --include="*.sql" src/dk_data/
docker-compose.yml:33:      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:-postgres}"
init_database.sql:413:        CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'postgrest_secret_change_me';
```

---

## Recommended Solutions

### Phase 1: Immediate Mitigations

#### 1.1 Create `.env.example` file

```bash
# .env.example - Copy to .env and configure
# REQUIRED - Change these before starting services
POSTGRES_PASSWORD=CHANGE_ME_STRONG_PASSWORD
POSTGREST_PASSWORD=CHANGE_ME_DIFFERENT_PASSWORD
PGRST_JWT_SECRET=CHANGE_ME_32_CHAR_MINIMUM

# Optional overrides
POSTGRES_USER=postgres
POSTGRES_DB=edwards_tavr
POSTGRES_PORT=5433
POSTGREST_PORT=3030
JOB_TRIGGER_PORT=8000
```

#### 1.2 Add startup validation script

```bash
#!/bin/bash
# scripts/validate_env.sh
REQUIRED_VARS=(
    "POSTGRES_PASSWORD"
    "POSTGREST_PASSWORD"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ] || [ "${!var}" == "postgres" ] || [[ "${!var}" == *"CHANGE_ME"* ]]; then
        echo "ERROR: $var is not set or using default value"
        exit 1
    fi
done

# Check minimum password length
if [ ${#POSTGRES_PASSWORD} -lt 16 ]; then
    echo "ERROR: POSTGRES_PASSWORD must be at least 16 characters"
    exit 1
fi

echo "Environment validation passed"
```

#### 1.3 Modify docker-compose.yml

```yaml
services:
  postgres:
    environment:
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
```

The `${VAR:?error}` syntax will fail if the variable is unset or empty.

### Phase 2: SQL Initialization Fix

#### 2.1 Use Docker secrets or init script

```yaml
# docker-compose.yml
services:
  postgres:
    volumes:
      - ./sql:/docker-entrypoint-initdb.d:ro
      - ./scripts/create_roles.sh:/docker-entrypoint-initdb.d/01_create_roles.sh:ro
    environment:
      POSTGREST_PASSWORD: "${POSTGREST_PASSWORD:?required}"
```

```bash
#!/bin/bash
# scripts/create_roles.sh
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
            CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD '$POSTGREST_PASSWORD';
        END IF;
    END
    \$\$;
EOSQL
```

#### 2.2 Remove hardcoded password from init_database.sql

```sql
-- Replace line 413 with:
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
        -- Password must be set via environment variable in create_roles.sh
        RAISE NOTICE 'authenticator role should be created by 01_create_roles.sh';
    END IF;
END
$$;
```

### Phase 3: Production Secret Management

#### 3.1 Doppler Integration (Kubernetes)

```yaml
# .gitops/base/postgrest/deployment.yaml
spec:
  containers:
    - name: postgrest
      env:
        - name: PGRST_DB_URI
          valueFrom:
            secretKeyRef:
              name: postgrest-secrets
              key: db-uri
```

#### 3.2 External Secrets Operator

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: postgrest-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: doppler-store
    kind: ClusterSecretStore
  target:
    name: postgrest-secrets
  data:
    - secretKey: db-uri
      remoteRef:
        key: PGRST_DB_URI
```

---

## Implementation Checklist

- [ ] Create `.env.example` with clear instructions
- [ ] Add `.env` to `.gitignore`
- [ ] Create `validate_env.sh` script
- [ ] Update `docker-compose.yml` to require env vars
- [ ] Create `create_roles.sh` for dynamic password
- [ ] Remove hardcoded password from `init_database.sql`
- [ ] Update Makefile to run validation before `up`
- [ ] Update README with security configuration section
- [ ] Configure Doppler for staging/production
- [ ] Add pre-commit hook to detect hardcoded secrets

---

## Verification Commands

```bash
# Check for remaining hardcoded secrets
grep -rn "password\|secret" --include="*.yml" --include="*.sql" src/dk_data/ | grep -v "#" | grep -v "secretKeyRef"

# Validate env file exists and has required vars
[ -f src/dk_data/.env ] && grep -q "POSTGRES_PASSWORD" src/dk_data/.env && echo "OK" || echo "FAIL"

# Test startup validation
./scripts/validate_env.sh && echo "Validation passed"
```

---

## References

- [OWASP: Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Docker Compose: Environment Variables](https://docs.docker.com/compose/environment-variables/)
- [Doppler: Docker Integration](https://docs.doppler.com/docs/docker)
- [PostgreSQL: Password Authentication](https://www.postgresql.org/docs/current/auth-password.html)
