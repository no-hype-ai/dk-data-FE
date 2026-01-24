# ISSUE-020: PostgREST Version Compatibility

**Project**: dk-data-FE
**Category**: Dependencies
**Priority**: P3 - Low
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

PostgREST version differs between docker-compose.yml (v12.2.3) and Kubernetes manifests (v12.0.2). Configuration format and feature availability vary between versions, risking deployment failures or behavior differences between environments.

---

## Current State

### Version Discrepancies

| Location | Version |
|----------|---------|
| `docker-compose.yml` | `postgrest/postgrest:v12.2.3` |
| `.gitops/base/kustomization.yaml` | `newTag: v12.0.2` |
| Documentation | Various/unspecified |

### Configuration Differences

```yaml
# docker-compose.yml
PGRST_DB_URI: "postgres://authenticator:..."
PGRST_DB_SCHEMAS: "api"
PGRST_DB_ANON_ROLE: "web_anon"
PGRST_DB_POOL: "10"
PGRST_MAX_ROWS: "1000"
PGRST_LOG_LEVEL: "info"
PGRST_OPENAPI_MODE: "follow-privileges"
```

---

## PostgREST Version History

### Breaking Changes

| Version | Changes |
|---------|---------|
| v12.0.0 | New `PGRST_DB_AGGREGATES_ENABLED`, config validation |
| v11.0.0 | JWT claim structure changes, OpenAPI 3.1 |
| v10.0.0 | Removed deprecated options, new pool settings |

### Feature Availability

| Feature | v12.0.2 | v12.2.3 |
|---------|---------|---------|
| OpenAPI 3.1 | ✅ | ✅ |
| Aggregates | ✅ | ✅ |
| Prepared statements | ✅ | ✅ |
| JWT role claim | ✅ | ✅ (improved) |
| Connection pooling fixes | ⚠️ | ✅ |

---

## Risk Assessment

| Risk | Impact |
|------|--------|
| Dev/Prod version mismatch | Behavior differences |
| Upgrade without testing | Breaking changes |
| Security patches missed | Vulnerability exposure |
| Config format changes | Deployment failures |

---

## Recommended Solutions

### Phase 1: Version Alignment

#### 1.1 Single Source of Truth

```yaml
# versions.yaml (project root)
versions:
  postgrest: "v12.2.3"
  postgres: "16-alpine"
  metabase: "v0.50.26"
```

#### 1.2 Update All References

```yaml
# docker-compose.yml
postgrest:
  image: postgrest/postgrest:${POSTGREST_VERSION:-v12.2.3}
```

```yaml
# .gitops/base/kustomization.yaml
images:
  - name: postgrest/postgrest
    newTag: v12.2.3  # Match docker-compose
```

### Phase 2: Configuration Validation

#### 2.1 Startup Validation Script

```bash
#!/bin/bash
# scripts/validate_postgrest_config.sh

REQUIRED_VARS=(
    "PGRST_DB_URI"
    "PGRST_DB_SCHEMAS"
    "PGRST_DB_ANON_ROLE"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo "ERROR: Required variable $var is not set"
        exit 1
    fi
done

# Version-specific validation
VERSION=$(docker inspect postgrest --format '{{.Config.Image}}' 2>/dev/null | grep -oP 'v\d+\.\d+\.\d+')
echo "PostgREST version: $VERSION"

# Check for deprecated options
if [ -n "$PGRST_DB_PRE_REQUEST" ]; then
    echo "WARNING: PGRST_DB_PRE_REQUEST may behave differently in v12+"
fi
```

#### 2.2 Health Check Enhancement

```yaml
# docker-compose.yml
postgrest:
  healthcheck:
    test: |
      wget -q -O - http://localhost:3000/ | grep -q "swagger"
    interval: 30s
    timeout: 10s
    retries: 3
```

### Phase 3: Upgrade Testing Process

#### 3.1 Version Upgrade Checklist

```markdown
## PostgREST Version Upgrade Checklist

### Pre-Upgrade
- [ ] Read release notes for target version
- [ ] Identify breaking changes
- [ ] Review deprecated options in current config
- [ ] Backup current configuration

### Testing
- [ ] Update docker-compose.yml to new version
- [ ] Run `docker compose up` locally
- [ ] Test all API endpoints
- [ ] Verify OpenAPI spec generation
- [ ] Test JWT authentication
- [ ] Test role switching
- [ ] Check connection pool behavior
- [ ] Verify error responses

### Deployment
- [ ] Update .gitops/base/kustomization.yaml
- [ ] Deploy to staging
- [ ] Run integration tests
- [ ] Monitor for errors
- [ ] Deploy to production

### Post-Upgrade
- [ ] Update documentation
- [ ] Update versions.yaml
- [ ] Close upgrade ticket
```

#### 3.2 Integration Tests for PostgREST

```python
# tests/integration/test_postgrest.py
import pytest
import requests

POSTGREST_URL = "http://localhost:3030"

class TestPostgRESTVersion:
    """Tests to verify PostgREST configuration."""

    def test_health_endpoint(self):
        """PostgREST is responding."""
        response = requests.get(f"{POSTGREST_URL}/")
        assert response.status_code == 200

    def test_openapi_spec(self):
        """OpenAPI spec is generated."""
        response = requests.get(f"{POSTGREST_URL}/")
        data = response.json()
        assert "openapi" in data
        assert data["openapi"].startswith("3.")

    def test_anonymous_role(self):
        """Anonymous role can access public endpoints."""
        response = requests.get(f"{POSTGREST_URL}/health")
        assert response.status_code in (200, 404)  # Depends on view existence

    def test_max_rows_limit(self):
        """Max rows limit is enforced."""
        response = requests.get(f"{POSTGREST_URL}/targets?limit=10000")
        data = response.json()
        # Should be limited to PGRST_MAX_ROWS
        assert len(data) <= 1000

    def test_jwt_authentication(self):
        """JWT authentication works."""
        import jwt
        import os

        secret = os.getenv("PGRST_JWT_SECRET", "test-secret")
        token = jwt.encode({"role": "analyst"}, secret, algorithm="HS256")

        response = requests.get(
            f"{POSTGREST_URL}/targets",
            headers={"Authorization": f"Bearer {token}"}
        )
        # Should not be 401 with valid token
        assert response.status_code != 401
```

### Phase 4: Automated Version Management

#### 4.1 Renovate Configuration

```json
// renovate.json
{
  "extends": ["config:base"],
  "packageRules": [
    {
      "matchPackageNames": ["postgrest/postgrest"],
      "matchUpdateTypes": ["minor", "patch"],
      "automerge": false,
      "labels": ["dependencies", "postgrest"]
    },
    {
      "matchPackageNames": ["postgrest/postgrest"],
      "matchUpdateTypes": ["major"],
      "enabled": false
    }
  ],
  "regexManagers": [
    {
      "fileMatch": ["docker-compose\\.ya?ml$"],
      "matchStrings": [
        "postgrest/postgrest:(?<currentValue>v[0-9.]+)"
      ],
      "depNameTemplate": "postgrest/postgrest",
      "datasourceTemplate": "docker"
    },
    {
      "fileMatch": ["\\.gitops/.*kustomization\\.ya?ml$"],
      "matchStrings": [
        "name: postgrest/postgrest\\n\\s+newTag: (?<currentValue>v[0-9.]+)"
      ],
      "depNameTemplate": "postgrest/postgrest",
      "datasourceTemplate": "docker"
    }
  ]
}
```

---

## Version Compatibility Matrix

| dk-data-FE Version | PostgREST | PostgreSQL | Notes |
|--------------------|-----------|------------|-------|
| 1.0.x | v12.2.3 | 16 | Current target |
| 1.1.x | v12.x | 16 | Future |

---

## Configuration Reference

### v12.x Configuration Options

```yaml
# Full configuration with descriptions
environment:
  # Database connection
  PGRST_DB_URI: "postgres://user:pass@host:5432/db"
  PGRST_DB_SCHEMAS: "api"  # Comma-separated list
  PGRST_DB_ANON_ROLE: "web_anon"
  PGRST_DB_POOL: "10"
  PGRST_DB_POOL_ACQUISITION_TIMEOUT: "10"
  PGRST_DB_PREPARED_STATEMENTS: "true"

  # Server settings
  PGRST_SERVER_HOST: "0.0.0.0"
  PGRST_SERVER_PORT: "3000"

  # Query limits
  PGRST_MAX_ROWS: "1000"

  # Logging
  PGRST_LOG_LEVEL: "info"  # error, warn, info, debug

  # OpenAPI
  PGRST_OPENAPI_MODE: "follow-privileges"

  # JWT Authentication
  PGRST_JWT_SECRET: ""  # Base64 or plain
  PGRST_JWT_SECRET_IS_BASE64: "false"
  PGRST_JWT_ROLE_CLAIM_KEY: ".role"
  PGRST_JWT_AUD: ""  # Optional audience

  # Advanced (v12+)
  PGRST_DB_AGGREGATES_ENABLED: "true"
  PGRST_DB_PRE_CONFIG: ""  # SQL to run on startup
```

---

## Implementation Checklist

- [ ] Align PostgREST version across all files
- [ ] Create versions.yaml for centralized version management
- [ ] Add startup validation script
- [ ] Create version upgrade checklist
- [ ] Write integration tests for PostgREST
- [ ] Configure Renovate for automated updates
- [ ] Document configuration options
- [ ] Schedule quarterly version review

---

## References

- [PostgREST Releases](https://github.com/PostgREST/postgrest/releases)
- [PostgREST Configuration](https://postgrest.org/en/stable/references/configuration.html)
- [PostgREST Migration Guide](https://postgrest.org/en/stable/references/migrations.html)
- [Docker: Image Tags](https://docs.docker.com/develop/dev-best-practices/)
