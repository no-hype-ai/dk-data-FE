# ISSUE-002: Insecure JWT Secret Configuration

**Project**: dk-data-FE
**Category**: Security
**Priority**: P0 - Critical
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The PostgREST JWT secret configuration lacks security controls. Empty/weak secrets enable authentication bypass, and there's no mechanism to ensure production deployments use cryptographically strong secrets.

---

## Affected Files

| File | Line | Issue |
|------|------|-------|
| `src/dk_data/docker-compose.yml` | 72 | Empty default JWT secret |
| `ARCHITECTURE.md` | 1229-1230 | Placeholder secret in docs |
| `.gitops/base/postgrest/configmap.yaml` | (if exists) | Secret in ConfigMap |

---

## Evidence from Codebase

### docker-compose.yml (line 72)

```yaml
PGRST_JWT_SECRET: "${PGRST_JWT_SECRET:-}"
```

**Critical Issue**: Empty default means PostgREST starts with JWT validation disabled or using a weak/empty secret.

### ARCHITECTURE.md (lines 1229-1230)

```python
token = jwt.encode(
    {
        "role": "analyst",
        "exp": datetime.utcnow() + timedelta(hours=24)
    },
    "your-secret-key",  # Placeholder in documentation
    algorithm="HS256"
)
```

---

## Risk Assessment

### Security Impact Matrix

| Scenario | Risk Level | Attack Vector |
|----------|------------|---------------|
| Empty JWT secret | Critical | Complete auth bypass |
| Weak secret (<32 chars) | Critical | Brute force in minutes |
| Secret in ConfigMap | High | K8s RBAC bypass exposes secret |
| Secret committed to git | Critical | Permanent exposure |
| No secret rotation | Medium | Increased exposure window |

### Attack Scenarios

#### 1. Empty Secret Bypass

If `PGRST_JWT_SECRET` is empty, PostgREST may:
- Accept any JWT without verification
- Fall back to anonymous access only
- Expose role-based endpoints to all users

```bash
# Attacker can forge tokens:
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYXBpX3VzZXIifQ.signature_ignored" \
  http://localhost:3030/targets
```

#### 2. Weak Secret Brute Force

```python
# 8-character secret cracked in seconds
import hashlib
import itertools
import string

def crack_jwt(token, charset=string.ascii_lowercase, max_len=8):
    for length in range(1, max_len + 1):
        for guess in itertools.product(charset, repeat=length):
            secret = ''.join(guess)
            # Test if secret produces valid signature
            ...
```

---

## Current Configuration Analysis

### PostgREST JWT Behavior

| Configuration | PostgREST Behavior |
|---------------|-------------------|
| `PGRST_JWT_SECRET=""` | JWT validation disabled, anon role only |
| `PGRST_JWT_SECRET="short"` | Accepts JWTs but vulnerable to brute force |
| `PGRST_JWT_SECRET` (32+ chars) | Proper JWT validation enabled |
| No secret + `PGRST_JWT_AUD` | Uses JWKS endpoint for validation |

### Current Role Permissions

From `init_database.sql`:

```sql
-- web_anon: Public access
GRANT SELECT ON ALL TABLES IN SCHEMA api TO web_anon;

-- analyst: Financial and scoring data
GRANT SELECT ON ALL TABLES IN SCHEMA scoring TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO analyst;

-- api_user: Full read access to all schemas
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO api_user;
```

**Risk**: Without proper JWT validation, sensitive scoring and financial data is exposed.

---

## Recommended Solutions

### Phase 1: Immediate Fixes

#### 1.1 Require JWT Secret at Startup

```yaml
# docker-compose.yml
postgrest:
  environment:
    PGRST_JWT_SECRET: "${PGRST_JWT_SECRET:?JWT secret is required - see .env.example}"
```

#### 1.2 Add Secret Validation Script

```python
#!/usr/bin/env python3
# scripts/validate_jwt_secret.py
import os
import sys
import base64
import secrets

def validate_jwt_secret():
    secret = os.getenv('PGRST_JWT_SECRET', '')

    errors = []

    # Check if empty
    if not secret:
        errors.append("PGRST_JWT_SECRET is empty")

    # Check minimum length (256 bits = 32 bytes)
    elif len(secret) < 32:
        errors.append(f"PGRST_JWT_SECRET too short ({len(secret)} chars, need 32+)")

    # Check for placeholder values
    elif any(placeholder in secret.lower() for placeholder in [
        'change', 'secret', 'example', 'default', 'your-'
    ]):
        errors.append("PGRST_JWT_SECRET contains placeholder text")

    # Check entropy (simple check)
    elif len(set(secret)) < 10:
        errors.append("PGRST_JWT_SECRET has low entropy (too few unique characters)")

    if errors:
        print("JWT Secret Validation FAILED:")
        for error in errors:
            print(f"  - {error}")
        print("\nGenerate a secure secret with:")
        print(f"  openssl rand -base64 32")
        print(f"  # or: python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
        return False

    print("JWT Secret Validation PASSED")
    return True

if __name__ == '__main__':
    sys.exit(0 if validate_jwt_secret() else 1)
```

#### 1.3 Update .env.example

```bash
# JWT Configuration (REQUIRED for authenticated access)
# Generate with: openssl rand -base64 32
PGRST_JWT_SECRET=REPLACE_WITH_32_CHAR_MINIMUM_SECRET

# JWT audience (optional, for JWKS validation)
# PGRST_JWT_AUD=https://your-domain.com
```

### Phase 2: Secure Secret Generation

#### 2.1 Add Makefile Target

```makefile
.PHONY: generate-secrets
generate-secrets:
	@echo "Generating secure secrets..."
	@echo "POSTGRES_PASSWORD=$$(openssl rand -base64 24)" > .env.generated
	@echo "POSTGREST_PASSWORD=$$(openssl rand -base64 24)" >> .env.generated
	@echo "PGRST_JWT_SECRET=$$(openssl rand -base64 32)" >> .env.generated
	@echo ""
	@echo "Generated secrets saved to .env.generated"
	@echo "Review and copy to .env before starting services"
```

#### 2.2 Pre-start Hook

```yaml
# docker-compose.yml
services:
  secret-validator:
    image: python:3.11-slim
    command: python /scripts/validate_jwt_secret.py
    environment:
      PGRST_JWT_SECRET: "${PGRST_JWT_SECRET:-}"
    volumes:
      - ./scripts:/scripts:ro
    restart: "no"

  postgrest:
    depends_on:
      secret-validator:
        condition: service_completed_successfully
```

### Phase 3: Production Deployment

#### 3.1 Kubernetes Secrets (not ConfigMaps!)

```yaml
# .gitops/base/postgrest/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgrest-secrets
type: Opaque
stringData:
  jwt-secret: "" # Populated by External Secrets Operator or CI/CD
---
# .gitops/base/postgrest/deployment.yaml
spec:
  containers:
    - name: postgrest
      env:
        - name: PGRST_JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: postgrest-secrets
              key: jwt-secret
```

#### 3.2 External Secrets Operator Integration

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: postgrest-jwt
spec:
  refreshInterval: 24h
  secretStoreRef:
    name: doppler-store
    kind: ClusterSecretStore
  target:
    name: postgrest-secrets
    creationPolicy: Owner
  data:
    - secretKey: jwt-secret
      remoteRef:
        key: PGRST_JWT_SECRET
```

### Phase 4: JWT Key Rotation

#### 4.1 JWKS Endpoint Support

For proper key rotation, configure PostgREST to use JWKS:

```yaml
# docker-compose.yml
postgrest:
  environment:
    PGRST_JWT_SECRET: "@/run/secrets/jwt_secret"  # Or JWKS
    PGRST_JWT_SECRET_IS_BASE64: "false"
    # For JWKS validation (production):
    # PGRST_JWT_AUD: "https://api.tavr-platform.com"
```

#### 4.2 Rotation Schedule

```yaml
# CronJob for secret rotation notification
apiVersion: batch/v1
kind: CronJob
metadata:
  name: jwt-rotation-reminder
spec:
  schedule: "0 0 1 * *"  # Monthly
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: reminder
              image: curlimages/curl
              command:
                - /bin/sh
                - -c
                - |
                  curl -X POST "$SLACK_WEBHOOK" -H 'Content-type: application/json' \
                    --data '{"text":"JWT secret rotation reminder: Review and rotate PGRST_JWT_SECRET"}'
```

---

## Verification Testing

### Test 1: Verify Secret Requirement

```bash
# Should fail with empty secret
unset PGRST_JWT_SECRET
docker compose up postgrest
# Expected: Container fails to start
```

### Test 2: Validate Token Generation

```python
import jwt
import os

secret = os.getenv('PGRST_JWT_SECRET')
token = jwt.encode(
    {"role": "analyst", "exp": datetime.utcnow() + timedelta(hours=1)},
    secret,
    algorithm="HS256"
)

# Verify token works
response = requests.get(
    "http://localhost:3030/targets",
    headers={"Authorization": f"Bearer {token}"}
)
assert response.status_code == 200
```

### Test 3: Verify Invalid Token Rejection

```bash
# Forge token with wrong secret
FAKE_TOKEN=$(python -c "import jwt; print(jwt.encode({'role': 'api_user'}, 'wrong-secret', algorithm='HS256'))")

curl -w "%{http_code}" -o /dev/null \
  -H "Authorization: Bearer $FAKE_TOKEN" \
  http://localhost:3030/targets
# Expected: 401
```

---

## Implementation Checklist

- [ ] Add `${VAR:?error}` syntax for JWT secret in docker-compose.yml
- [ ] Create `validate_jwt_secret.py` script
- [ ] Add `generate-secrets` Makefile target
- [ ] Update `.env.example` with JWT secret guidance
- [ ] Move JWT secret to Kubernetes Secret (not ConfigMap)
- [ ] Configure External Secrets Operator for production
- [ ] Add pre-commit hook to detect weak/placeholder secrets
- [ ] Document JWT token generation for API consumers
- [ ] Set up rotation reminder/policy

---

## References

- [PostgREST: JWT Configuration](https://postgrest.org/en/stable/references/configuration.html#jwt-secret)
- [OWASP: JSON Web Token Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [RFC 7519: JSON Web Token (JWT)](https://datatracker.ietf.org/doc/html/rfc7519)
- [Kubernetes: Secrets Best Practices](https://kubernetes.io/docs/concepts/configuration/secret/#best-practices)
