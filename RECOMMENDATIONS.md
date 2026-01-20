# Data Foundation Recommendations
## Scalable & Robust Infrastructure for Pharma Platform Behavior Labs AI

**Project**: dk-data-FE
**Assessment Date**: 2026-01-19
**Based on**: Codebase analysis + 20 open GitHub issues

---

## Executive Summary

The dk-data-FE platform provides a solid MVP foundation for TAVR data infrastructure with PostgREST API, SQLMesh transformations, and GitOps deployment. To evolve into a production-grade, enterprise-ready data foundation for pharma AI/ML workloads, the following areas require attention:

| Priority | Category | Issues | Risk Level |
|----------|----------|--------|------------|
| **P0** | Security | 3 | 🔴 Critical |
| **P1** | Operations & Reliability | 5 | 🟠 High |
| **P2** | Compliance & Governance | 4 | 🟡 Medium |
| **P3** | Architecture & Quality | 8 | 🟢 Low |

---

## 🔴 P0: Critical Security Issues

### 1. Credential Management (Issue #2)

**Current State**: Hardcoded credentials in `docker-compose.yml` and `init_database.sql`

**Recommendations**:
```bash
# 1. Use external secrets management
# Kubernetes: External Secrets Operator + AWS Secrets Manager/Vault
# Local: .env files (gitignored) with docker-compose env_file

# 2. Remove hardcoded passwords from SQL files
# Use environment variable substitution via init scripts
```

**Action Items**:
- [ ] Install External Secrets Operator in Kubernetes
- [ ] Migrate credentials to AWS Secrets Manager or HashiCorp Vault
- [ ] Create `.env.example` template, gitignore actual `.env`
- [ ] Replace SQL hardcoded passwords with entrypoint script substitution
- [ ] Add pre-commit hook to scan for secrets (gitleaks)

### 2. JWT Secret Configuration (Issue #3)

**Current State**: Weak default JWT secret, no rotation mechanism

**Recommendations**:
```yaml
# Generate strong secrets (32+ bytes, base64 encoded)
PGRST_JWT_SECRET: "${JWT_SECRET}"  # From secrets manager
PGRST_JWT_SECRET_IS_BASE64: "true"

# Add JWT claim validation
PGRST_JWT_AUD: "tavr-api"  # Audience claim
PGRST_JWT_ROLE_CLAIM_KEY: ".role"
```

**Action Items**:
- [ ] Generate 256-bit minimum JWT secrets
- [ ] Implement secret rotation procedure
- [ ] Add audience claim validation
- [ ] Configure token expiration (short-lived: 15-60 min)
- [ ] Add refresh token mechanism for long sessions

### 3. API Access Control (Issue #4)

**Current State**: Overly permissive `web_anon` role with access to sensitive data

**Recommendations**:
```sql
-- Principle of least privilege
-- web_anon: Only public catalog and health endpoints
GRANT SELECT ON api.catalog_public TO web_anon;
GRANT SELECT ON api.health TO web_anon;
REVOKE ALL ON api.targets FROM web_anon;
REVOKE ALL ON api.scoring FROM web_anon;

-- Create tiered access roles
CREATE ROLE internal_api;  -- Internal services
CREATE ROLE analyst;       -- Data analysts
CREATE ROLE ml_service;    -- AI/ML pipelines

-- Row-level security for multi-tenancy
ALTER TABLE targeting.targeting_scores ENABLE ROW LEVEL SECURITY;
CREATE POLICY region_isolation ON targeting.targeting_scores
    USING (region = current_setting('app.current_region', true));
```

**Action Items**:
- [ ] Audit all `GRANT` statements and reduce permissions
- [ ] Implement row-level security for sensitive tables
- [ ] Create service-specific API roles
- [ ] Add API key authentication for external integrations
- [ ] Implement rate limiting at the API gateway level

---

## 🟠 P1: Operations & Reliability

### 4. Observability Stack (Issue #11)

**Current State**: No centralized logging, metrics, or tracing

**Recommendations**:
```yaml
# Recommended Stack: OpenTelemetry + Prometheus + Grafana + Loki

# 1. Structured Logging (Python)
import structlog
logger = structlog.get_logger()
logger.info("batch_job_started", job_name="cms_inpatient", run_id=uuid)

# 2. Metrics (Prometheus)
# - API latency histograms
# - Job success/failure counters
# - Data freshness gauges
# - Row count metrics by table

# 3. Tracing (OpenTelemetry)
# - Request traces through API → DB
# - Job execution spans
# - External API call traces
```

**Architecture**:
```
┌─────────────────────────────────────────────────────────────┐
│                    Observability Stack                      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │ Grafana │    │ Loki    │    │Prometheus│   │ Jaeger  │  │
│  │Dashboard│◄───│ Logs    │    │ Metrics │   │ Traces  │  │
│  └────▲────┘    └────▲────┘    └────▲────┘   └────▲────┘  │
│       │              │              │             │        │
│       └──────────────┴──────────────┴─────────────┘        │
│                           ▲                                 │
│                 OpenTelemetry Collector                     │
├─────────────────────────────────────────────────────────────┤
│  PostgREST │ Job Trigger │ Ingestion Jobs │ PostgreSQL     │
└─────────────────────────────────────────────────────────────┘
```

**Action Items**:
- [ ] Add structlog to Python services
- [ ] Deploy Prometheus + Grafana in Kubernetes
- [ ] Create dashboards for data freshness, job health, API latency
- [ ] Add alerting rules for critical failures
- [ ] Integrate with PagerDuty/Slack for on-call alerts

### 5. Database Backup & Recovery (Issue #13)

**Current State**: No defined backup strategy

**Recommendations**:
```yaml
# For Pharma/Healthcare: RPO < 1 hour, RTO < 4 hours

# 1. PostgreSQL Continuous Archiving (WAL)
# Enable WAL archiving to S3
archive_mode = on
archive_command = 'aws s3 cp %p s3://backups/wal/%f'

# 2. Daily Logical Backups
# CronJob: pg_dump with encryption
0 2 * * * pg_dump -Fc edwards_tavr | gpg --encrypt -r backup@company.com | aws s3 cp - s3://backups/daily/$(date +%Y%m%d).dump.gpg

# 3. Point-in-Time Recovery (PITR)
# Using pgBackRest for managed PITR
```

**For Production**: Consider managed PostgreSQL (AWS RDS, Cloud SQL) with:
- Automated backups with 35-day retention
- Multi-AZ deployment for HA
- Read replicas for analytics queries
- Automatic failover

**Action Items**:
- [ ] Enable WAL archiving to S3
- [ ] Create backup CronJob with encryption
- [ ] Document and test recovery procedures
- [ ] Implement backup verification (restore to staging weekly)
- [ ] Consider managed PostgreSQL for production

### 6. Kubernetes Resource Management (Issue #12)

**Current State**: No resource limits defined, risk of OOMKill and noisy neighbor

**Recommendations**:
```yaml
# .gitops/base/postgrest/deployment.yaml
spec:
  containers:
  - name: postgrest
    resources:
      requests:
        memory: "256Mi"
        cpu: "100m"
      limits:
        memory: "512Mi"
        cpu: "500m"

# Ingestion jobs (bursty workloads)
# .gitops/base/ingestion/cronjob-cms-all.yaml
spec:
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: ingestion
            resources:
              requests:
                memory: "512Mi"
                cpu: "200m"
              limits:
                memory: "2Gi"
                cpu: "1000m"
```

**Resource Guidelines**:
| Service | Memory Request | Memory Limit | CPU Request | CPU Limit |
|---------|---------------|--------------|-------------|-----------|
| PostgREST | 256Mi | 512Mi | 100m | 500m |
| Job Trigger | 128Mi | 256Mi | 50m | 200m |
| Ingestion Jobs | 512Mi | 2Gi | 200m | 1000m |
| SQLMesh Jobs | 1Gi | 4Gi | 500m | 2000m |

**Action Items**:
- [ ] Add resource requests/limits to all deployments
- [ ] Configure HorizontalPodAutoscaler for PostgREST
- [ ] Set up PodDisruptionBudgets for high availability
- [ ] Add namespace resource quotas

### 7. External API Resilience (Issue #5)

**Current State**: Basic retry with no circuit breaker, jitter, or caching

**Recommendations**:
```python
# Enhanced retry with exponential backoff + jitter
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=1, max=60, jitter=5),
    retry=retry_if_exception_type((RequestException, Timeout))
)
def fetch_with_resilience(url: str) -> Response:
    return session.get(url, timeout=30)

# Circuit breaker pattern
from pybreaker import CircuitBreaker
cms_breaker = CircuitBreaker(
    fail_max=5,
    reset_timeout=300,  # 5 minutes
    exclude=[HTTPError(404)]  # Don't trip on 404s
)

@cms_breaker
def fetch_cms_data():
    ...

# Response caching for idempotent requests
# Use Redis or S3 for caching API responses with TTL
```

**Action Items**:
- [ ] Replace urllib3 Retry with tenacity
- [ ] Add circuit breaker pattern (pybreaker)
- [ ] Implement response caching layer
- [ ] Add fallback data sources (CSV snapshots)
- [ ] Create monitoring for external API health

### 8. Job Monitoring & Alerting (Issue #6)

**Current State**: Silent CronJob failures, no freshness monitoring

**Recommendations**:
```yaml
# 1. Job failure alerting
# .gitops/base/ingestion/cronjob-cms-all.yaml
spec:
  failedJobsHistoryLimit: 3
  successfulJobsHistoryLimit: 3

# 2. Data freshness monitoring
# SQL view for freshness
CREATE VIEW meta.data_freshness AS
SELECT
    source_name,
    MAX(ingested_at) as last_ingested,
    NOW() - MAX(ingested_at) as age,
    CASE
        WHEN NOW() - MAX(ingested_at) > refresh_interval THEN 'STALE'
        ELSE 'FRESH'
    END as status
FROM meta.data_sources ds
LEFT JOIN meta.batch_job_runs bjr ON ds.job_name = bjr.job_name
GROUP BY ds.source_name, ds.refresh_interval;

# 3. Prometheus alerting rules
groups:
- name: data-freshness
  rules:
  - alert: DataStale
    expr: data_freshness_age_hours > 48
    for: 1h
    labels:
      severity: warning
    annotations:
      summary: "Data source {{ $labels.source }} is stale"
```

**Action Items**:
- [ ] Add Prometheus metrics for job runs
- [ ] Create data freshness monitoring view
- [ ] Configure alerting for job failures
- [ ] Add Slack/PagerDuty integration
- [ ] Implement job dependency tracking

---

## 🟡 P2: Compliance & Governance

### 9. Audit Trail (Issue #17)

**Current State**: No audit logging for data changes or API access

**Recommendations for Healthcare/Pharma**:
```sql
-- 1. Change Data Capture (CDC) with temporal tables
CREATE TABLE targeting.targeting_scores_history (
    id UUID,
    hospital_id VARCHAR(20),
    score NUMERIC,
    valid_from TIMESTAMP DEFAULT NOW(),
    valid_to TIMESTAMP DEFAULT 'infinity',
    changed_by TEXT DEFAULT current_user,
    operation CHAR(1)  -- I/U/D
);

-- Trigger for audit trail
CREATE OR REPLACE FUNCTION audit_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO targeting.targeting_scores_history
        VALUES (OLD.*, NOW(), 'infinity', current_user, 'D');
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO targeting.targeting_scores_history
        VALUES (OLD.*, NOW(), 'infinity', current_user, 'U');
        RETURN NEW;
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO targeting.targeting_scores_history
        VALUES (NEW.*, NOW(), 'infinity', current_user, 'I');
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 2. API access logging
-- PostgREST logs + structured log aggregation
-- Or: pgAudit extension for comprehensive logging
```

**Action Items**:
- [ ] Enable pgAudit extension for SQL audit logging
- [ ] Create history tables for sensitive data
- [ ] Implement CDC triggers
- [ ] Configure log retention (7 years for healthcare)
- [ ] Add log shipping to immutable storage (S3 Glacier)

### 10. PII/PHI Data Handling (Issue #18)

**Current State**: Unclear classification and handling of sensitive data

**Recommendations**:
```sql
-- 1. Data classification schema
CREATE TABLE meta.data_classification (
    table_schema TEXT,
    table_name TEXT,
    column_name TEXT,
    classification TEXT CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'PHI')),
    pii_type TEXT,  -- name, address, email, phone, medical_record
    masking_rule TEXT,
    retention_days INT
);

-- 2. Column-level encryption for PHI
-- Use pgcrypto for encryption at rest
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Encrypt sensitive columns
ALTER TABLE targeting.champions
    ADD COLUMN email_encrypted BYTEA;
UPDATE targeting.champions
    SET email_encrypted = pgp_sym_encrypt(email, current_setting('app.encryption_key'));

-- 3. Dynamic data masking for analysts
CREATE VIEW api.champions_masked AS
SELECT
    id,
    hospital_id,
    CASE WHEN current_user = 'analyst'
         THEN regexp_replace(email, '(.{2}).*@', '\1***@')
         ELSE email
    END as email,
    role
FROM targeting.champions;
```

**Action Items**:
- [ ] Inventory all data fields and classify sensitivity
- [ ] Implement encryption for PHI columns
- [ ] Create masked views for analyst access
- [ ] Document data flow diagrams showing PHI paths
- [ ] Add data processing agreements (DPA) documentation

### 11. Data Retention Policy (Issue #19)

**Current State**: No defined retention or deletion procedures

**Recommendations**:
```sql
-- 1. Retention policy table
CREATE TABLE meta.retention_policies (
    schema_name TEXT,
    table_name TEXT,
    retention_days INT NOT NULL,
    archive_strategy TEXT CHECK (archive_strategy IN ('DELETE', 'ARCHIVE', 'ANONYMIZE')),
    legal_hold BOOLEAN DEFAULT FALSE
);

-- 2. Automated retention enforcement
-- CronJob to enforce retention
CREATE OR REPLACE FUNCTION enforce_retention()
RETURNS void AS $$
DECLARE
    policy RECORD;
BEGIN
    FOR policy IN SELECT * FROM meta.retention_policies WHERE NOT legal_hold
    LOOP
        EXECUTE format(
            'DELETE FROM %I.%I WHERE created_at < NOW() - INTERVAL ''%s days''',
            policy.schema_name,
            policy.table_name,
            policy.retention_days
        );
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- 3. Retention periods by data type
-- Raw ingested data: 3 years
-- Audit logs: 7 years (healthcare compliance)
-- Job run history: 1 year
-- Analytics/mart tables: 5 years
```

**Action Items**:
- [ ] Define retention periods by data classification
- [ ] Create automated retention enforcement job
- [ ] Implement legal hold capability
- [ ] Document data lifecycle in compliance docs
- [ ] Add retention audit reports

### 12. Database Migration Strategy (Issue #9)

**Current State**: No versioned migrations, manual SQL execution

**Recommendations**:
```python
# Use Alembic or Flyway for migrations

# Directory structure
migrations/
├── versions/
│   ├── 001_initial_schema.sql
│   ├── 002_add_audit_tables.sql
│   ├── 003_add_retention_policies.sql
│   └── ...
├── alembic.ini
└── env.py

# Migration workflow
# 1. Create migration
alembic revision --autogenerate -m "add_audit_tables"

# 2. Review and edit generated migration
# 3. Apply to dev
alembic upgrade head

# 4. Test thoroughly
# 5. Apply to staging/prod via GitOps
```

**Action Items**:
- [ ] Choose migration tool (Alembic recommended for Python)
- [ ] Convert existing SQL to versioned migrations
- [ ] Add migration CI checks
- [ ] Document rollback procedures
- [ ] Integrate with GitOps deployment

---

## 🟢 P3: Architecture & Quality

### 13. Multi-Tenancy & Generalization (Issue #8)

**Current State**: Tight coupling to Edwards/TAVR use case

**Recommendations**:
```yaml
# 1. Configuration-driven naming
# config/project.yaml
project:
  name: "${PROJECT_NAME:-dk-data}"
  database: "${DATABASE_NAME:-data_platform}"
  namespace: "${K8S_NAMESPACE:-data-platform}"

data_domains:
  - name: tavr
    enabled: true
    schemas: [raw_tavr, staging_tavr, mart_tavr]
  - name: oncology
    enabled: false
    schemas: [raw_onc, staging_onc, mart_onc]

# 2. Schema isolation per domain
# raw_tavr, staging_tavr, mart_tavr
# raw_oncology, staging_oncology, mart_oncology

# 3. Generic table naming
# raw.hospital_info (not raw.cms_hospital_info)
# staging.procedure_volumes (not staging.tavr_volumes)
```

**Action Items**:
- [ ] Create configuration layer for project naming
- [ ] Implement domain-based schema partitioning
- [ ] Generalize table names where possible
- [ ] Document multi-tenancy patterns
- [ ] Create template for new therapeutic areas

### 14. Test Coverage (Issue #15)

**Current State**: Unknown test coverage, minimal automated testing

**Recommendations**:
```python
# Test pyramid for data platform

# 1. Unit tests (fast, isolated)
# tests/unit/test_validators.py
def test_hospital_validator_rejects_invalid_ccn():
    with pytest.raises(ValidationError):
        HospitalRecord(ccn="invalid", name="Test")

# 2. Integration tests (database required)
# tests/integration/test_ingestion.py
@pytest.fixture
def test_db(postgresql):
    """Ephemeral test database."""
    ...

def test_cms_ingestor_loads_data(test_db):
    ingestor = CMSInpatientIngestor(test_db)
    result = ingestor.ingest(sample_data)
    assert result.rows_inserted == 100

# 3. Contract tests (API schema validation)
# tests/contract/test_api_contract.py
def test_api_matches_openapi_spec():
    spec = load_openapi_spec("contracts/openapi.yaml")
    response = requests.get(f"{API_URL}/hospitals")
    validate_response(response, spec, "/hospitals", "get")

# 4. Data quality tests (Great Expectations)
# tests/data_quality/test_hospital_data.py
@pytest.fixture
def ge_context():
    return gx.get_context()

def test_hospital_ccn_format(ge_context):
    batch = ge_context.get_batch("hospitals")
    result = batch.expect_column_values_to_match_regex("ccn", r"^\d{6}$")
    assert result.success
```

**Coverage Targets**:
| Layer | Target | Current |
|-------|--------|---------|
| Unit tests | 80% | Unknown |
| Integration tests | Critical paths | Minimal |
| Contract tests | All API endpoints | None |
| Data quality tests | All staging tables | None |

**Action Items**:
- [ ] Add pytest-cov to measure coverage
- [ ] Write unit tests for validators and utilities
- [ ] Add integration tests with pytest-postgresql
- [ ] Implement Great Expectations for data quality
- [ ] Add CI gates for coverage thresholds

### 15. Error Handling (Issue #14)

**Current State**: Incomplete error handling in fetchers

**Recommendations**:
```python
# Structured error handling pattern
from dataclasses import dataclass
from enum import Enum

class ErrorSeverity(Enum):
    WARNING = "warning"    # Partial success, continue
    ERROR = "error"        # Task failed, retry possible
    CRITICAL = "critical"  # System failure, human intervention

@dataclass
class IngestionError:
    source: str
    severity: ErrorSeverity
    message: str
    context: dict
    timestamp: datetime
    recoverable: bool

class IngestionResult:
    def __init__(self):
        self.rows_processed = 0
        self.rows_inserted = 0
        self.rows_updated = 0
        self.errors: List[IngestionError] = []

    @property
    def success(self) -> bool:
        return not any(e.severity == ErrorSeverity.CRITICAL for e in self.errors)

    def to_metrics(self) -> dict:
        return {
            "rows_processed": self.rows_processed,
            "rows_inserted": self.rows_inserted,
            "error_count": len(self.errors),
            "error_types": Counter(e.severity.value for e in self.errors)
        }
```

**Action Items**:
- [ ] Define error taxonomy and severity levels
- [ ] Implement structured IngestionResult returns
- [ ] Add error aggregation and reporting
- [ ] Create runbooks for common error scenarios
- [ ] Add error metrics to observability stack

### 16. Dependency Management (Issue #20)

**Current State**: Loose version constraints, no lock file

**Recommendations**:
```toml
# pyproject.toml with version bounds
[project]
name = "dk-data-fe"
version = "1.0.0"
requires-python = ">=3.11,<3.13"

dependencies = [
    "sqlmesh>=0.90.0,<1.0.0",
    "psycopg2-binary>=2.9.9,<3.0.0",
    "pandas>=2.0.0,<3.0.0",
    "pydantic>=2.5.0,<3.0.0",
    "requests>=2.31.0,<3.0.0",
    "fastapi>=0.109.0,<1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
]

# Generate lock file
# uv pip compile pyproject.toml -o requirements.lock
```

**Action Items**:
- [ ] Add upper version bounds to all dependencies
- [ ] Generate and commit lock file (uv.lock or requirements.lock)
- [ ] Split dev/prod dependencies
- [ ] Configure Dependabot for automated updates
- [ ] Add security scanning (safety, pip-audit)

### 17. Version Alignment (Issue #21)

**Current State**: PostgREST version mismatch between docker-compose and k8s

**Recommendations**:
```yaml
# Single source of truth: versions.yaml
versions:
  postgrest: "v12.2.3"
  postgres: "16-alpine"
  metabase: "v0.50.26"
  python: "3.11-slim"

# Reference in docker-compose
postgrest:
  image: postgrest/postgrest:${POSTGREST_VERSION:-v12.2.3}

# Reference in kustomization.yaml via patch
images:
  - name: postgrest/postgrest
    newTag: v12.2.3  # Keep in sync with versions.yaml
```

**Action Items**:
- [ ] Create versions.yaml as single source of truth
- [ ] Align all version references
- [ ] Add CI check for version consistency
- [ ] Document version upgrade procedures

---

## AI/ML Platform Integration Recommendations

For use as a data foundation for Behavior Labs AI:

### Data Access Patterns

```python
# 1. Feature Store Integration
# Expose materialized features via PostgREST
CREATE MATERIALIZED VIEW ml.hospital_features AS
SELECT
    h.hospital_id,
    h.bed_count,
    h.teaching_status,
    t.volume_2023,
    t.yoy_growth,
    f.operating_margin,
    s.target_score
FROM mart.dim_hospital h
JOIN mart.fact_tavr_program t USING (hospital_id)
JOIN mart.fact_financial_metrics f USING (hospital_id)
JOIN scoring.target_scores s USING (hospital_id);

# 2. Batch prediction data export
# Schedule nightly export to S3 for ML training
CREATE OR REPLACE FUNCTION ml.export_training_data()
RETURNS void AS $$
BEGIN
    COPY (SELECT * FROM ml.hospital_features)
    TO PROGRAM 'aws s3 cp - s3://ml-data/features/hospitals_$(date +%Y%m%d).parquet'
    WITH (FORMAT parquet);
END;
$$ LANGUAGE plpgsql;

# 3. Real-time inference via API
# POST /rpc/get_prediction_features
CREATE FUNCTION api.get_prediction_features(p_hospital_ids TEXT[])
RETURNS SETOF ml.hospital_features AS $$
    SELECT * FROM ml.hospital_features
    WHERE hospital_id = ANY(p_hospital_ids);
$$ LANGUAGE sql SECURITY DEFINER;
```

### Model Metadata Integration

```sql
-- Track ML model deployments and predictions
CREATE SCHEMA ml_ops;

CREATE TABLE ml_ops.models (
    model_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    trained_at TIMESTAMP DEFAULT NOW(),
    metrics JSONB,  -- {"accuracy": 0.85, "f1": 0.82}
    feature_schema JSONB,
    artifact_path TEXT,
    status TEXT CHECK (status IN ('training', 'validated', 'deployed', 'deprecated'))
);

CREATE TABLE ml_ops.predictions (
    prediction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id UUID REFERENCES ml_ops.models,
    hospital_id VARCHAR(20),
    prediction JSONB,
    confidence NUMERIC,
    predicted_at TIMESTAMP DEFAULT NOW(),
    feedback JSONB  -- Ground truth when available
);
```

### Recommended Architecture for AI Platform

```
┌─────────────────────────────────────────────────────────────────┐
│                     Behavior Labs AI Platform                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  ML Models  │  │  LLM Agents │  │  Analytics Dashboards   │ │
│  └──────┬──────┘  └──────┬──────┘  └────────────┬────────────┘ │
│         │                │                      │               │
│         └────────────────┼──────────────────────┘               │
│                          │                                      │
│                          ▼                                      │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    API Gateway                            │ │
│  │         (Authentication, Rate Limiting, Caching)          │ │
│  └───────────────────────────────────────────────────────────┘ │
│                          │                                      │
├──────────────────────────┼──────────────────────────────────────┤
│                          │                                      │
│                          ▼                                      │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                   PostgREST API                           │ │
│  │    /hospitals  /features  /predictions  /rpc/...          │ │
│  └───────────────────────────────────────────────────────────┘ │
│                          │                                      │
│                          ▼                                      │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    PostgreSQL                              │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────┐  │ │
│  │  │   raw   │ │ staging │ │   mart  │ │     ml_ops      │  │ │
│  │  │ schemas │ │ schemas │ │ schemas │ │ models/preds    │  │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────────┘  │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                 Data Ingestion Layer                       │ │
│  │     CMS │ HRSA │ ACC │ Internal CRM │ Model Feedback       │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

### Phase 1: Security Hardening (Week 1-2)
1. Credential management (Issue #2, #3)
2. API access control (Issue #4)
3. Basic audit logging

### Phase 2: Operations Foundation (Week 3-4)
1. Observability stack deployment
2. Backup strategy implementation
3. Kubernetes resource limits
4. Job monitoring and alerting

### Phase 3: Compliance & Governance (Week 5-6)
1. Full audit trail implementation
2. PII/PHI data classification
3. Retention policy enforcement
4. Migration tooling

### Phase 4: Quality & Scale (Week 7-8)
1. Test coverage improvement
2. Error handling standardization
3. Dependency management
4. Documentation automation

### Phase 5: AI Platform Integration (Week 9-10)
1. ML feature store views
2. Prediction logging tables
3. Model metadata tracking
4. API optimizations for ML workloads

---

## Summary of Open Issues by Priority

| Issue | Title | Priority | Category |
|-------|-------|----------|----------|
| #2 | Hardcoded Credentials | P0 | Security |
| #3 | Insecure JWT Secret | P0 | Security |
| #4 | Overly Permissive API Access | P0 | Security |
| #11 | No Observability Stack | P1 | Operations |
| #12 | No K8s Resource Limits | P1 | Operations |
| #13 | No Backup Strategy | P1 | Operations |
| #5 | Brittle External APIs | P1 | Reliability |
| #6 | Silent Job Failures | P1 | Reliability |
| #9 | No Migration Strategy | P2 | Governance |
| #17 | No Audit Trail | P2 | Compliance |
| #18 | Unclear PII/PHI Handling | P2 | Compliance |
| #19 | No Retention Policy | P2 | Compliance |
| #7 | Tight Coupling to TAVR | P3 | Architecture |
| #8 | SQLMesh Dependencies | P3 | Architecture |
| #10 | Data Validation Gaps | P3 | Quality |
| #14 | Incomplete Error Handling | P3 | Quality |
| #15 | Unknown Test Coverage | P3 | Quality |
| #16 | Documentation Drift | P3 | Quality |
| #20 | Dependency Versions | P3 | Dependencies |
| #21 | PostgREST Version Mismatch | P3 | Dependencies |

---

## References

- [PostgREST Security Best Practices](https://postgrest.org/en/stable/auth.html)
- [PostgreSQL Security Hardening](https://www.postgresql.org/docs/current/auth-methods.html)
- [HIPAA Technical Safeguards](https://www.hhs.gov/hipaa/for-professionals/security/guidance/index.html)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [Great Expectations](https://docs.greatexpectations.io/)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)

---

*Document generated: 2026-01-19*
*Next review: Monthly or after major changes*
