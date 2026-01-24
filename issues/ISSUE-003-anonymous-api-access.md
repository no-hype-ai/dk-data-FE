# ISSUE-003: Overly Permissive Anonymous API Access

**Project**: dk-data-FE
**Category**: Security
**Priority**: P1 - High
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The `web_anon` role has read access to all tables in the `api` schema by default, exposing hospital targeting scores, financial indicators, and competitive intelligence data to unauthenticated users. This violates the principle of least privilege and creates data exposure risks.

---

## Affected Files

| File | Line | Issue |
|------|------|-------|
| `src/dk_data/sql/init_database.sql` | 428-430 | Blanket SELECT grant to web_anon |
| `src/dk_data/docker-compose.yml` | 62 | PostgREST configured with web_anon as default |

---

## Evidence from Codebase

### init_database.sql (lines 428-430)

```sql
-- Anonymous role: limited access (public views only)
GRANT SELECT ON ALL TABLES IN SCHEMA api TO web_anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO web_anon;
```

**Issue**: Despite the comment "limited access (public views only)", the grant provides access to ALL tables including sensitive views.

### API Views Exposed

```sql
-- All these views are accessible without authentication:
api.targets          -- Hospital scores, tier classifications
api.hospitals        -- Hospital details with certifications
api.data_catalog     -- System metadata
api.scoring_details  -- Factor breakdowns with raw values
```

### docker-compose.yml (line 62)

```yaml
PGRST_DB_ANON_ROLE: "web_anon"
```

---

## Data Exposure Analysis

### Sensitive Data in api.targets

| Column | Sensitivity | Business Impact |
|--------|-------------|-----------------|
| `total_trs` | High | Proprietary scoring algorithm output |
| `tier_classification` | High | Target prioritization (competitive intelligence) |
| `clinical_readiness_score` | Medium | Assessment of hospital capabilities |
| `financial_capacity_score` | High | Financial health indicators |
| `champion_access_score` | High | Sales strategy data |
| `latest_tavr_volume` | Medium | Procedure volumes (market intelligence) |

### Sensitive Data in api.scoring_details

| Column | Sensitivity | Business Impact |
|--------|-------------|-----------------|
| `raw_value` | High | Underlying data points |
| `points_awarded` | High | Scoring methodology exposure |
| `confidence_level` | Medium | Data quality indicators |
| `data_source` | Medium | Reveals data supply chain |

---

## Risk Assessment

### Business Risks

| Risk | Likelihood | Impact |
|------|------------|--------|
| Competitor scrapes target list | High | Loss of competitive advantage |
| Hospital discovers their score | Medium | Relationship damage |
| Scoring methodology reverse-engineered | Medium | IP theft |
| Sales strategy exposed | High | Competitive disadvantage |

### Compliance Risks

| Framework | Requirement | Current State |
|-----------|-------------|---------------|
| Edwards NDA | Data confidentiality | Violated - public access |
| SOC 2 | Access control | Weak - no authentication required |
| HIPAA | Minimum necessary | Potentially violated (if PHI exposed) |

---

## Current Access Model

```
                              ┌─────────────────┐
                              │   PostgREST     │
                              │   API Layer     │
                              └────────┬────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
       ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
       │  web_anon   │          │   analyst   │          │  api_user   │
       │  (default)  │          │  (JWT role) │          │  (JWT role) │
       └──────┬──────┘          └──────┬──────┘          └──────┬──────┘
              │                        │                        │
              │ SELECT on api.*        │ + scoring.*           │ + raw.*
              │ (CURRENT - TOO BROAD)  │ + mart.*              │ + staging.*
              │                        │ + meta.*              │
              ▼                        ▼                        ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │                        api schema                                 │
       │  targets | hospitals | data_catalog | scoring_details            │
       └──────────────────────────────────────────────────────────────────┘
```

---

## Recommended Solutions

### Phase 1: Create Tiered Access Views

#### 1.1 Public View (Limited Data)

```sql
-- Create restricted public view
CREATE OR REPLACE VIEW api.targets_public AS
SELECT
    hospital_id,
    hospital_name,
    state,
    city,
    -- Expose tier but not exact score
    CASE
        WHEN tier_classification IN ('A', 'B') THEN 'High Priority'
        WHEN tier_classification = 'C' THEN 'Medium Priority'
        ELSE 'Standard'
    END AS priority_level,
    -- Don't expose exact scores
    NULL::INTEGER AS total_trs,
    -- Don't expose sub-scores at all
    score_date
FROM api.targets;

-- Create restricted hospitals view
CREATE OR REPLACE VIEW api.hospitals_public AS
SELECT
    hospital_id,
    hospital_name,
    state,
    city,
    county,
    hospital_type,
    -- Don't expose certification details
    has_tavr_certification
FROM api.hospitals;
```

#### 1.2 Revoke Full Table Access

```sql
-- Revoke existing grants
REVOKE SELECT ON api.targets FROM web_anon;
REVOKE SELECT ON api.hospitals FROM web_anon;
REVOKE SELECT ON api.scoring_details FROM web_anon;

-- Grant only to public views
GRANT SELECT ON api.targets_public TO web_anon;
GRANT SELECT ON api.hospitals_public TO web_anon;
GRANT SELECT ON api.data_catalog TO web_anon;  -- Catalog is okay
GRANT SELECT ON api.health TO web_anon;  -- Health check is okay
```

### Phase 2: Implement Row-Level Security

#### 2.1 Enable RLS on Sensitive Tables

```sql
-- Enable row-level security
ALTER TABLE scoring.target_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE mart.dim_hospital ENABLE ROW LEVEL SECURITY;

-- Policy: Authenticated users see all, anon sees nothing
CREATE POLICY targets_anon_policy ON scoring.target_scores
    FOR SELECT
    TO web_anon
    USING (false);  -- Deny all

CREATE POLICY targets_auth_policy ON scoring.target_scores
    FOR SELECT
    TO analyst, api_user
    USING (true);  -- Allow all for authenticated
```

#### 2.2 View with Security Barrier

```sql
CREATE OR REPLACE VIEW api.targets WITH (security_barrier) AS
SELECT
    h.hospital_id,
    -- ... columns ...
    CASE
        WHEN current_user = 'web_anon' THEN NULL
        ELSE s.total_trs
    END AS total_trs,
    CASE
        WHEN current_user = 'web_anon' THEN 'Unknown'
        ELSE s.tier_classification
    END AS tier_classification
FROM mart.dim_hospital h
JOIN scoring.target_scores s ON h.hospital_key = s.hospital_key;
```

### Phase 3: Require Authentication for Sensitive Endpoints

#### 3.1 PostgREST Configuration

```yaml
# docker-compose.yml
postgrest:
  environment:
    PGRST_DB_ANON_ROLE: "web_anon"
    PGRST_DB_SCHEMAS: "api"
    # Optionally disable anonymous access entirely:
    # PGRST_DB_ANON_ROLE: ""  # No anonymous access
```

#### 3.2 Update API Documentation

```markdown
## Authentication Required Endpoints

The following endpoints require a valid JWT:

| Endpoint | Required Role | Data |
|----------|--------------|------|
| `/targets` | analyst, api_user | Full scoring data |
| `/scoring_details` | analyst, api_user | Score breakdowns |
| `/hospitals` | analyst, api_user | Full hospital data |

## Public Endpoints

| Endpoint | Auth Required | Data |
|----------|--------------|------|
| `/targets_public` | No | Limited hospital list |
| `/hospitals_public` | No | Basic hospital info |
| `/data_catalog` | No | System metadata |
| `/health` | No | Health check |
```

### Phase 4: Add Rate Limiting

#### 4.1 Use PostgREST Pre-Request Hook

```sql
CREATE OR REPLACE FUNCTION api.rate_limit_check()
RETURNS void AS $$
DECLARE
    client_ip TEXT;
    request_count INT;
BEGIN
    client_ip := current_setting('request.header.x-forwarded-for', true);

    -- Check rate limit for anonymous users
    IF current_user = 'web_anon' THEN
        SELECT COUNT(*) INTO request_count
        FROM meta.api_rate_limits
        WHERE ip_address = client_ip
        AND window_start > NOW() - INTERVAL '1 minute';

        IF request_count > 60 THEN  -- 60 req/min for anon
            RAISE EXCEPTION 'Rate limit exceeded'
                USING ERRCODE = 'P0001';
        END IF;

        INSERT INTO meta.api_rate_limits (ip_address, window_start)
        VALUES (client_ip, NOW());
    END IF;
END;
$$ LANGUAGE plpgsql;
```

---

## Implementation SQL Script

```sql
-- migrations/002_restrict_anonymous_access.sql

BEGIN;

-- 1. Create public views with limited data
CREATE OR REPLACE VIEW api.targets_public AS
SELECT
    hospital_id,
    hospital_name,
    state,
    city,
    CASE
        WHEN tier_classification IN ('A', 'B') THEN 'High'
        WHEN tier_classification = 'C' THEN 'Medium'
        ELSE 'Standard'
    END AS priority_level,
    score_date
FROM api.targets;

CREATE OR REPLACE VIEW api.hospitals_public AS
SELECT
    hospital_id,
    hospital_name,
    state,
    city,
    hospital_type,
    has_tavr_certification
FROM api.hospitals;

-- 2. Revoke existing grants from web_anon
REVOKE SELECT ON api.targets FROM web_anon;
REVOKE SELECT ON api.hospitals FROM web_anon;
REVOKE SELECT ON api.scoring_details FROM web_anon;

-- 3. Grant access to public views only
GRANT SELECT ON api.targets_public TO web_anon;
GRANT SELECT ON api.hospitals_public TO web_anon;
GRANT SELECT ON api.data_catalog TO web_anon;

-- 4. Ensure authenticated roles still have full access
GRANT SELECT ON api.targets TO analyst, api_user;
GRANT SELECT ON api.hospitals TO analyst, api_user;
GRANT SELECT ON api.scoring_details TO analyst, api_user;
GRANT SELECT ON api.targets_public TO analyst, api_user;
GRANT SELECT ON api.hospitals_public TO analyst, api_user;

COMMIT;

-- Verify changes
DO $$
BEGIN
    RAISE NOTICE 'Anonymous access now limited to: targets_public, hospitals_public, data_catalog';
    RAISE NOTICE 'Full access requires authentication with analyst or api_user role';
END
$$;
```

---

## Verification Tests

### Test 1: Anonymous Access Restricted

```bash
# Should return limited data
curl http://localhost:3030/targets_public | jq '.[0] | keys'
# Expected: ["hospital_id", "hospital_name", "state", "city", "priority_level", "score_date"]

# Should return 401 or empty
curl -w "%{http_code}" http://localhost:3030/targets
# Expected: 401 or no data

curl -w "%{http_code}" http://localhost:3030/scoring_details
# Expected: 401 or no data
```

### Test 2: Authenticated Access Works

```bash
TOKEN=$(python -c "import jwt; print(jwt.encode({'role': 'analyst'}, '$PGRST_JWT_SECRET', algorithm='HS256'))")

curl -H "Authorization: Bearer $TOKEN" http://localhost:3030/targets | jq '.[0] | keys'
# Expected: Full column set including total_trs, tier_classification, etc.
```

---

## Implementation Checklist

- [ ] Create `api.targets_public` view with limited columns
- [ ] Create `api.hospitals_public` view with limited columns
- [ ] Revoke SELECT on sensitive views from web_anon
- [ ] Grant SELECT on public views to web_anon
- [ ] Update API documentation with access tiers
- [ ] Add integration tests for access control
- [ ] Consider rate limiting for anonymous access
- [ ] Review with Edwards on acceptable public data

---

## References

- [PostgREST: Role-Based Access Control](https://postgrest.org/en/stable/auth.html)
- [PostgreSQL: Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [OWASP: Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html)
