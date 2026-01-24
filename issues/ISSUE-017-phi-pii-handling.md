# ISSUE-017: Unclear PII/PHI Data Handling

**Project**: dk-data-FE
**Category**: Compliance
**Priority**: P2 - Medium
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The platform handles healthcare facility data that may contain Protected Health Information (PHI) or Personally Identifiable Information (PII). There's no explicit data classification, no PHI handling procedures, and no data masking for non-production environments.

---

## Data Classification Analysis

### Data Sources Ingested

| Source | Data Types | PHI Risk | PII Risk |
|--------|------------|----------|----------|
| CMS Medicare Inpatient | Hospital aggregate stats | Low | Low |
| CMS Hospital Info | Facility addresses, phones | Low | Low |
| CMS Cost Reports | Financial metrics | Low | Low |
| ACC TVC | Facility certifications | Low | Low |
| HRSA | Shortage area designations | Low | Low |

### Potential PHI Elements

| Field | Table | Risk Assessment |
|-------|-------|-----------------|
| `provider_id` | Multiple | Facility ID, not patient ID - **Low risk** |
| `hospital_name` | Multiple | Public information - **No risk** |
| `address/phone` | cms_hospital_info | Public facility info - **Low risk** |
| Procedure volumes | cms_medicare_inpatient | Aggregate data - **Low risk** |

**Initial Assessment**: Current data appears to be facility-level aggregates, not patient-level PHI. However, proper documentation and controls should still be implemented.

---

## Compliance Framework Requirements

### HIPAA (if PHI present)

| Requirement | Current Status |
|-------------|---------------|
| Data classification | ❌ Not documented |
| Access controls | ⚠️ Basic roles exist |
| Encryption at rest | ❌ Not verified |
| Encryption in transit | ⚠️ Depends on deployment |
| Audit logging | ❌ Not implemented |
| Breach notification | ❌ No procedure |
| Business Associate Agreement | ❓ Unknown |

### Data Protection Principles

| Principle | Status |
|-----------|--------|
| Data minimization | ⚠️ All available fields collected |
| Purpose limitation | ❌ Not documented |
| Storage limitation | ❌ No retention policy |
| Data masking (non-prod) | ❌ Not implemented |

---

## Recommended Solutions

### Phase 1: Data Classification Documentation

#### 1.1 Data Inventory Document

```markdown
# Data Classification Inventory

## Classification Levels

| Level | Description | Examples |
|-------|-------------|----------|
| Public | Freely available | Hospital names, addresses |
| Internal | Business confidential | Scores, tier classifications |
| Restricted | PHI/PII if applicable | N/A currently |

## Data Source Classification

### CMS Medicare Inpatient
- **Classification**: Internal
- **Contains PHI**: No (aggregate data only)
- **Contains PII**: No
- **Sensitivity**: Medium (competitive intelligence)
- **Retention**: 7 years

### Scoring Data
- **Classification**: Internal
- **Contains PHI**: No
- **Contains PII**: No
- **Sensitivity**: High (proprietary algorithm output)
- **Retention**: 7 years
```

#### 1.2 Database Column Classification

```sql
-- Add classification to data catalog
ALTER TABLE meta.data_sources
ADD COLUMN data_classification VARCHAR(20) DEFAULT 'internal',
ADD COLUMN contains_phi BOOLEAN DEFAULT FALSE,
ADD COLUMN contains_pii BOOLEAN DEFAULT FALSE,
ADD COLUMN retention_years INTEGER DEFAULT 7;

-- Classification metadata per table
CREATE TABLE meta.column_classification (
    classification_id SERIAL PRIMARY KEY,
    schema_name VARCHAR(100) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    column_name VARCHAR(100) NOT NULL,
    data_classification VARCHAR(20) NOT NULL,
    is_phi BOOLEAN DEFAULT FALSE,
    is_pii BOOLEAN DEFAULT FALSE,
    masking_strategy VARCHAR(50),
    notes TEXT,
    classified_at TIMESTAMPTZ DEFAULT NOW(),
    classified_by VARCHAR(100),
    UNIQUE (schema_name, table_name, column_name)
);

-- Classify current columns
INSERT INTO meta.column_classification
(schema_name, table_name, column_name, data_classification, is_phi, is_pii, masking_strategy)
VALUES
('raw', 'cms_hospital_info', 'provider_id', 'internal', false, false, null),
('raw', 'cms_hospital_info', 'hospital_name', 'public', false, false, null),
('raw', 'cms_hospital_info', 'phone_number', 'public', false, true, 'partial_mask'),
('raw', 'cms_hospital_info', 'address', 'public', false, false, null),
('scoring', 'target_scores', 'total_trs', 'internal', false, false, null),
('scoring', 'target_scores', 'tier_classification', 'internal', false, false, null);
```

### Phase 2: Data Masking for Non-Production

#### 2.1 Masking Functions

```sql
-- Masking functions for non-prod environments
CREATE OR REPLACE FUNCTION mask_phone(phone TEXT)
RETURNS TEXT AS $$
BEGIN
    IF phone IS NULL THEN RETURN NULL; END IF;
    -- Show last 4 digits: XXX-XXX-1234
    RETURN 'XXX-XXX-' || RIGHT(regexp_replace(phone, '[^0-9]', '', 'g'), 4);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION mask_email(email TEXT)
RETURNS TEXT AS $$
BEGIN
    IF email IS NULL THEN RETURN NULL; END IF;
    -- Show first 2 chars and domain: jo***@example.com
    RETURN LEFT(email, 2) || '***@' || split_part(email, '@', 2);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION scramble_name(name TEXT)
RETURNS TEXT AS $$
BEGIN
    IF name IS NULL THEN RETURN NULL; END IF;
    -- Preserve length, replace with consistent fake
    RETURN 'Hospital ' || md5(name)::VARCHAR(8);
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

#### 2.2 Masked Views for Non-Prod

```sql
-- Create masked schema for non-prod
CREATE SCHEMA IF NOT EXISTS masked;

-- Masked hospital info view
CREATE OR REPLACE VIEW masked.cms_hospital_info AS
SELECT
    id,
    provider_id,
    scramble_name(hospital_name) AS hospital_name,
    address,  -- Public info
    city,
    state,
    zip_code,
    county_name,
    mask_phone(phone_number) AS phone_number,
    hospital_type,
    hospital_ownership,
    emergency_services,
    hospital_overall_rating,
    _loaded_at,
    _source_hash
FROM raw.cms_hospital_info;

-- Grant access to masked schema for non-prod roles
GRANT USAGE ON SCHEMA masked TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA masked TO analyst;
```

#### 2.3 Environment-Based Schema Selection

```python
# ingestion/utils/database.py
import os

def get_schema_prefix():
    """Return appropriate schema based on environment."""
    env = os.getenv('ENVIRONMENT', 'development')
    if env == 'production':
        return 'raw'
    else:
        return 'masked'  # Use masked views in non-prod

def get_hospital_query():
    schema = get_schema_prefix()
    return f"SELECT * FROM {schema}.cms_hospital_info"
```

### Phase 3: Encryption Verification

#### 3.1 At-Rest Encryption Check

```sql
-- Check if tablespace is encrypted (PostgreSQL 16+)
SELECT
    spcname AS tablespace,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace;

-- For CloudNativePG, verify encryption in cluster spec
-- spec.storage.pvcTemplate.storageClassName should use encrypted storage class
```

#### 3.2 In-Transit Encryption

```yaml
# docker-compose.yml - Force SSL
postgres:
  command: >
    -c ssl=on
    -c ssl_cert_file=/var/lib/postgresql/server.crt
    -c ssl_key_file=/var/lib/postgresql/server.key

postgrest:
  environment:
    # Force SSL connection
    PGRST_DB_URI: "postgres://...?sslmode=require"
```

### Phase 4: Access Control Enhancement

```sql
-- Create role for PHI access (future-proofing)
CREATE ROLE phi_access NOLOGIN;

-- If PHI tables are added, restrict access
-- GRANT SELECT ON phi_schema.patient_data TO phi_access;

-- Audit PHI access attempts
CREATE OR REPLACE FUNCTION audit_phi_access()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT pg_has_role(current_user, 'phi_access', 'USAGE') THEN
        RAISE EXCEPTION 'PHI access requires phi_access role';
    END IF;

    INSERT INTO audit.phi_access_log (user_name, table_name, action, timestamp)
    VALUES (current_user, TG_TABLE_NAME, TG_OP, NOW());

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

## Data Handling Procedures

### Non-Production Environment Setup

```bash
#!/bin/bash
# scripts/setup_nonprod_data.sh

# 1. Copy production structure only (no data)
pg_dump -h prod-host -U postgres -d edwards_tavr --schema-only > schema.sql

# 2. Restore to non-prod
psql -h nonprod-host -U postgres -d edwards_tavr < schema.sql

# 3. Create masked views
psql -h nonprod-host -U postgres -d edwards_tavr < sql/masked_views.sql

# 4. Generate synthetic test data
python scripts/generate_synthetic_data.py --tables all --rows 1000

# Never copy production data directly to non-prod
```

### Data Export Checklist

Before exporting any data:
- [ ] Verify data classification level
- [ ] Confirm recipient authorization
- [ ] Apply appropriate masking
- [ ] Log the export in audit trail
- [ ] Use encrypted transfer method

---

## Implementation Checklist

- [ ] Create data classification documentation
- [ ] Add classification columns to meta.data_sources
- [ ] Create meta.column_classification table
- [ ] Implement masking functions
- [ ] Create masked schema and views
- [ ] Configure environment-based schema selection
- [ ] Verify encryption at rest
- [ ] Verify encryption in transit
- [ ] Document data handling procedures
- [ ] Train team on PHI/PII handling

---

## References

- [HIPAA Security Rule](https://www.hhs.gov/hipaa/for-professionals/security/index.html)
- [NIST SP 800-122: PII Guide](https://csrc.nist.gov/publications/detail/sp/800-122/final)
- [PostgreSQL: Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [Data Masking Best Practices](https://owasp.org/www-project-data-security-top-10/)
