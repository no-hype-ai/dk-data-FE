# ISSUE-016: No Audit Trail for Data Changes and API Access

**Project**: dk-data-FE
**Category**: Compliance
**Priority**: P1 - High
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The platform lacks comprehensive audit trails for:
1. **API Access**: Who accessed what data, when
2. **Data Changes**: Who/what modified records, with before/after values
3. **AI Decisions**: What inputs produced what scoring outputs
4. **System Actions**: Job executions, data purges, administrative changes

This creates compliance risks for healthcare data handling and makes incident investigation difficult.

---

## Current Audit Capabilities

| Area | Tracking | Detail Level |
|------|----------|--------------|
| Data ingestion | ✅ meta.refresh_log | Job-level only |
| API access | ❌ None | - |
| Data changes | ❌ None | - |
| AI decisions | ❌ None | - |
| User actions | ❌ None | - |
| Score changes | ⚠️ scoring.score_history | Limited (final scores only) |

---

## Evidence from Codebase

### meta.refresh_log (init_database.sql lines 293-304)

```sql
CREATE TABLE IF NOT EXISTS meta.refresh_log (
    log_id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES meta.data_sources(source_id),
    refresh_started_at TIMESTAMP,
    refresh_completed_at TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    records_fetched INTEGER,
    records_inserted INTEGER,
    records_updated INTEGER,
    error_message TEXT,
    _logged_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Limitation**: Tracks job execution but not:
- Individual record changes
- Who triggered the job
- Which API users accessed results

### purge_history.py (lines 94-97)

```python
cur.execute("""
    DELETE FROM scoring.score_history
    WHERE score_date < %s
""", (cutoff_date.date(),))
```

**Compliance Issue**: Data deletion with minimal audit trail.

---

## Regulatory Requirements

### 21 CFR Part 11 (FDA Electronic Records)

| Requirement | Status |
|-------------|--------|
| Audit trail for record creation | ❌ Not implemented |
| Audit trail for record modification | ❌ Not implemented |
| Audit trail for record deletion | ❌ Not implemented |
| User attribution | ❌ No user tracking |
| Timestamp accuracy | ⚠️ Partial |
| Protection against tampering | ❌ No immutability |

### ALCOA+ Data Integrity Principles

| Principle | Status |
|-----------|--------|
| **A**ttributable | ❌ No user attribution |
| **L**egible | ⚠️ Logs in JSON/stdout |
| **C**ontemporaneous | ⚠️ Timestamps present |
| **O**riginal | ❌ Can be overwritten |
| **A**ccurate | ⚠️ Validation exists |
| **C**omplete | ❌ Purging removes data |
| **C**onsistent | ⚠️ Single system |
| **E**nduring | ❌ No retention policy |
| **A**vailable | ⚠️ Database accessible |

---

## Comprehensive Audit Implementation

### Phase 1: Audit Schema

```sql
-- Create audit schema
CREATE SCHEMA IF NOT EXISTS audit;

-- API Access Log
CREATE TABLE audit.api_access_log (
    access_id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    request_id UUID DEFAULT gen_random_uuid(),

    -- User context
    user_id TEXT,
    user_role TEXT,
    jwt_claims JSONB,

    -- Request details
    method VARCHAR(10) NOT NULL,
    path TEXT NOT NULL,
    query_params JSONB,
    request_headers JSONB,

    -- Response details
    status_code INTEGER,
    response_time_ms INTEGER,
    row_count INTEGER,

    -- Client info
    client_ip INET,
    user_agent TEXT,

    -- Audit metadata
    audit_timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_api_access_timestamp ON audit.api_access_log(timestamp DESC);
CREATE INDEX idx_api_access_user ON audit.api_access_log(user_id, timestamp DESC);
CREATE INDEX idx_api_access_path ON audit.api_access_log(path, timestamp DESC);

-- Data Change Log
CREATE TABLE audit.data_changes (
    change_id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Table info
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    operation VARCHAR(10) NOT NULL,  -- INSERT, UPDATE, DELETE

    -- Record identification
    primary_key_columns TEXT[] NOT NULL,
    primary_key_values TEXT[] NOT NULL,

    -- Change details
    old_values JSONB,
    new_values JSONB,
    changed_columns TEXT[],

    -- Attribution
    changed_by TEXT NOT NULL,  -- User, job, or system
    change_source TEXT,  -- 'api', 'ingestion', 'sqlmesh', 'manual'
    job_run_id INTEGER,
    request_id UUID,

    -- Audit metadata
    audit_timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_data_changes_table ON audit.data_changes(schema_name, table_name, timestamp DESC);
CREATE INDEX idx_data_changes_key ON audit.data_changes USING GIN(primary_key_values);

-- AI Decision Audit
CREATE TABLE audit.ai_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Model info
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,

    -- Decision context
    decision_type TEXT NOT NULL,  -- 'scoring', 'enrichment', 'classification'
    entity_type TEXT NOT NULL,  -- 'hospital', 'score', etc.
    entity_id TEXT NOT NULL,

    -- Input/Output
    input_hash TEXT NOT NULL,  -- SHA256 of input
    input_summary JSONB,  -- Key fields only (not full data)
    output JSONB NOT NULL,
    confidence DECIMAL(5,4),

    -- Reasoning
    reasoning TEXT,
    factors_used JSONB,

    -- Human review
    human_reviewed BOOLEAN DEFAULT FALSE,
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    review_outcome TEXT,  -- 'approved', 'rejected', 'modified'
    review_notes TEXT,

    -- Audit metadata
    audit_timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_decisions_entity ON audit.ai_decisions(entity_type, entity_id, timestamp DESC);
CREATE INDEX idx_ai_decisions_unreviewed ON audit.ai_decisions(human_reviewed) WHERE human_reviewed = FALSE;
```

### Phase 2: Change Capture Trigger

```sql
-- Generic audit trigger function
CREATE OR REPLACE FUNCTION audit.capture_changes()
RETURNS TRIGGER AS $$
DECLARE
    pk_cols TEXT[];
    pk_vals TEXT[];
    changed_cols TEXT[];
    col_name TEXT;
BEGIN
    -- Get primary key columns
    SELECT array_agg(a.attname)
    INTO pk_cols
    FROM pg_index i
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
    WHERE i.indrelid = TG_RELID AND i.indisprimary;

    -- Get primary key values
    IF TG_OP = 'DELETE' THEN
        pk_vals := ARRAY(
            SELECT (row_to_json(OLD)->>col)::TEXT
            FROM unnest(pk_cols) AS col
        );
    ELSE
        pk_vals := ARRAY(
            SELECT (row_to_json(NEW)->>col)::TEXT
            FROM unnest(pk_cols) AS col
        );
    END IF;

    -- For UPDATE, get changed columns
    IF TG_OP = 'UPDATE' THEN
        changed_cols := ARRAY(
            SELECT key
            FROM jsonb_each(row_to_json(NEW)::jsonb)
            WHERE row_to_json(OLD)::jsonb->key IS DISTINCT FROM row_to_json(NEW)::jsonb->key
        );
    END IF;

    INSERT INTO audit.data_changes (
        schema_name,
        table_name,
        operation,
        primary_key_columns,
        primary_key_values,
        old_values,
        new_values,
        changed_columns,
        changed_by,
        change_source,
        request_id
    ) VALUES (
        TG_TABLE_SCHEMA,
        TG_TABLE_NAME,
        TG_OP,
        pk_cols,
        pk_vals,
        CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN row_to_json(OLD)::jsonb END,
        CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN row_to_json(NEW)::jsonb END,
        changed_cols,
        COALESCE(current_setting('app.current_user', true), 'system'),
        COALESCE(current_setting('app.change_source', true), 'unknown'),
        NULLIF(current_setting('app.request_id', true), '')::UUID
    );

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Apply to sensitive tables
CREATE TRIGGER audit_raw_cms_hospital_info
AFTER INSERT OR UPDATE OR DELETE ON raw.cms_hospital_info
FOR EACH ROW EXECUTE FUNCTION audit.capture_changes();

CREATE TRIGGER audit_scoring_target_scores
AFTER INSERT OR UPDATE OR DELETE ON scoring.target_scores
FOR EACH ROW EXECUTE FUNCTION audit.capture_changes();

CREATE TRIGGER audit_meta_batch_jobs
AFTER INSERT OR UPDATE OR DELETE ON meta.batch_jobs
FOR EACH ROW EXECUTE FUNCTION audit.capture_changes();
```

### Phase 3: API Access Logging

```python
# ingestion/batch/middleware.py
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import time

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Extract user info from JWT
        user_id = None
        user_role = 'web_anon'
        if 'authorization' in request.headers:
            # Parse JWT to get user info
            try:
                token = request.headers['authorization'].replace('Bearer ', '')
                claims = decode_jwt(token)
                user_id = claims.get('sub')
                user_role = claims.get('role', 'web_anon')
            except:
                pass

        start_time = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start_time) * 1000)

        # Log to audit table
        await log_api_access(
            request_id=request_id,
            user_id=user_id,
            user_role=user_role,
            method=request.method,
            path=str(request.url.path),
            query_params=dict(request.query_params),
            status_code=response.status_code,
            response_time_ms=duration_ms,
            client_ip=request.client.host,
            user_agent=request.headers.get('user-agent'),
        )

        response.headers['X-Request-ID'] = request_id
        return response
```

### Phase 4: AI Decision Logging

```python
# claude_sdk/audit.py
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict

@dataclass
class AIDecisionAudit:
    model_name: str
    model_version: str
    decision_type: str
    entity_type: str
    entity_id: str
    input_data: Dict[str, Any]
    output: Dict[str, Any]
    confidence: float = None
    reasoning: str = None

    def get_input_hash(self) -> str:
        """Generate hash of input for deduplication."""
        return hashlib.sha256(
            json.dumps(self.input_data, sort_keys=True, default=str).encode()
        ).hexdigest()

    def get_input_summary(self) -> Dict[str, Any]:
        """Extract key fields for audit log (not full data)."""
        return {
            'record_count': len(self.input_data.get('records', [])),
            'entity_id': self.entity_id,
            'timestamp': datetime.utcnow().isoformat(),
        }

    def log(self, db_connection) -> str:
        """Log decision to audit table."""
        with db_connection.cursor() as cur:
            cur.execute("""
                INSERT INTO audit.ai_decisions (
                    model_name, model_version, decision_type,
                    entity_type, entity_id, input_hash, input_summary,
                    output, confidence, reasoning
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING decision_id
            """, (
                self.model_name,
                self.model_version,
                self.decision_type,
                self.entity_type,
                self.entity_id,
                self.get_input_hash(),
                json.dumps(self.get_input_summary()),
                json.dumps(self.output),
                self.confidence,
                self.reasoning,
            ))
            return str(cur.fetchone()[0])

# Usage in scoring agent
def score_hospital(hospital_data: dict) -> dict:
    audit = AIDecisionAudit(
        model_name="claude-3-sonnet",
        model_version="20240229",
        decision_type="scoring",
        entity_type="hospital",
        entity_id=hospital_data['hospital_id'],
        input_data=hospital_data,
        output={},  # Populated below
    )

    # Call AI model
    result = call_claude_for_scoring(hospital_data)

    audit.output = result
    audit.confidence = result.get('confidence')
    audit.reasoning = result.get('reasoning')

    # Log decision
    decision_id = audit.log(get_connection())

    return {**result, 'decision_id': decision_id}
```

---

## Audit Retention Policy

| Data Type | Retention Period | Storage |
|-----------|-----------------|---------|
| API access logs | 90 days online, 2 years archive | PostgreSQL → S3 |
| Data changes | 2 years online | PostgreSQL |
| AI decisions | 5 years | PostgreSQL + S3 |
| Score history | 7 years | PostgreSQL + S3 |

---

## Implementation Checklist

- [ ] Create `audit` schema
- [ ] Create `audit.api_access_log` table
- [ ] Create `audit.data_changes` table
- [ ] Create `audit.ai_decisions` table
- [ ] Implement `audit.capture_changes()` trigger function
- [ ] Apply triggers to sensitive tables
- [ ] Add FastAPI audit middleware
- [ ] Implement AI decision logging
- [ ] Configure retention and archival
- [ ] Create audit query views for reporting
- [ ] Add audit dashboard to Grafana

---

## References

- [21 CFR Part 11](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/part-11-electronic-records-electronic-signatures-scope-and-application)
- [ALCOA+ Principles](https://www.fda.gov/files/drugs/published/Data-Integrity-and-Compliance-With-Drug-CGMP-Questions-and-Answers-Guidance-for-Industry.pdf)
- [PostgreSQL: Audit Triggers](https://wiki.postgresql.org/wiki/Audit_trigger)
- [pgAudit: PostgreSQL Audit Extension](https://www.pgaudit.org/)
