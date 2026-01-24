# ISSUE-007: Tight Coupling to Edwards/TAVR Use Case

**Project**: dk-data-FE
**Category**: Architecture
**Priority**: P3 - Low
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The codebase is tightly coupled to the Edwards Lifesciences TAVR use case with hardcoded client names, domain-specific table names, and TAVR-specific business logic. This prevents code reuse for other clients or therapeutic areas without significant refactoring.

---

## Affected Files

| File | Coupling Type |
|------|---------------|
| `src/dk_data/docker-compose.yml` | `edwards_tavr` database name |
| `src/dk_data/sql/init_database.sql` | TAVR-specific table structures |
| `src/dk_data/sqlmesh/models/` | TAVR-specific transformations |
| `src/dk_data/ingestion/fetchers/base.py` | User-Agent mentions Edwards |
| `.gitops/base/namespace.yaml` | `tavr-data` namespace |

---

## Evidence from Codebase

### docker-compose.yml (line 35)

```yaml
POSTGRES_DB: "${POSTGRES_DB:-edwards_tavr}"
```

### init_database.sql - Table Names

```sql
CREATE TABLE IF NOT EXISTS raw.cms_medicare_inpatient (...)
CREATE TABLE IF NOT EXISTS raw.acc_tvc_certification (...)
CREATE TABLE IF NOT EXISTS staging.tavr_volumes (...)
CREATE TABLE IF NOT EXISTS mart.fact_tavr_program (...)
```

### base.py (lines 47-48)

```python
self.session.headers.update({
    'User-Agent': 'TAVR-Data-Platform/1.0 (Edwards Medical; Data Integration)',
```

### Container Names

```yaml
container_name: tavr-postgres
container_name: tavr-postgrest
container_name: tavr-job-trigger
container_name: tavr-metabase
```

---

## Coupling Analysis

### Client-Specific Elements

| Element | Current Value | Issue |
|---------|---------------|-------|
| Database name | `edwards_tavr` | Client name in infrastructure |
| Namespace | `tavr-data` | Therapeutic area in K8s |
| User-Agent | `Edwards Medical` | Client in HTTP headers |
| Table prefix | `tavr_*` | Domain lock-in |
| Container names | `tavr-*` | Domain in container registry |

### Domain-Specific Business Logic

| Component | TAVR-Specific Logic |
|-----------|---------------------|
| `scoring/target_scores.sql` | TAVR program scoring formula |
| `cms_inpatient.py` | DRG codes 266/267 (TAVR-specific) |
| `acc_tvc.py` | Transcatheter Valve Certifications |
| Tier classification | A-E tiers specific to Edwards model |

---

## Impact Assessment

### Reuse Scenarios

| Scenario | Current Difficulty |
|----------|-------------------|
| New Edwards project (non-TAVR) | Medium - need new tables, keep infra |
| New client, same domain (TAVR) | High - client names hardcoded |
| New client, new domain | Very High - complete rewrite |
| Multi-tenant deployment | Impossible - single DB design |

### Technical Debt Accumulation

```
Single Client      →    New Client Request    →    Fork Codebase
(Edwards TAVR)          (Medtronic TAVR?)          (Copy everything)
                                                         ↓
                                            Duplicate maintenance burden
                                            Divergent feature sets
                                            No shared improvements
```

---

## Recommended Solutions

### Phase 1: Parameterize Client-Specific Values

#### 1.1 Configuration File

```yaml
# config/deployment.yaml
client:
  name: "edwards"
  display_name: "Edwards Lifesciences"
  contact_email: "support@datakinetic.com"

domain:
  name: "tavr"
  display_name: "TAVR Targeting"
  therapeutic_area: "structural_heart"

infrastructure:
  database_name: "${CLIENT}_${DOMAIN}"  # edwards_tavr
  namespace: "${DOMAIN}-data"           # tavr-data
  container_prefix: "${DOMAIN}"         # tavr-*
```

#### 1.2 Environment Variable Injection

```yaml
# docker-compose.yml
services:
  postgres:
    environment:
      POSTGRES_DB: "${CLIENT_CODE:-dk}_${DOMAIN_CODE:-data}"

  postgrest:
    container_name: "${DOMAIN_CODE:-dk}-postgrest"
```

### Phase 2: Abstract Domain Logic

#### 2.1 Generic Table Structure

```sql
-- Instead of:
CREATE TABLE IF NOT EXISTS staging.tavr_volumes (...)

-- Use:
CREATE TABLE IF NOT EXISTS staging.procedure_volumes (
    hospital_id VARCHAR(10) NOT NULL,
    fiscal_year INTEGER NOT NULL,
    procedure_category VARCHAR(50) NOT NULL,  -- 'tavr', 'tmvr', 'watchman', etc.
    procedure_code VARCHAR(10) NOT NULL,
    medicare_discharges INTEGER NOT NULL,
    -- ...
    PRIMARY KEY (hospital_id, fiscal_year, procedure_category, procedure_code)
);
```

#### 2.2 Configurable Procedure Codes

```yaml
# config/domain/tavr.yaml
procedure_codes:
  - code: "266"
    name: "TAVR w/o MCC"
    category: "tavr"
  - code: "267"
    name: "TAVR w/ MCC"
    category: "tavr"

certifications:
  - type: "ACC TVC"
    source: "acc_tvc"

# config/domain/watchman.yaml
procedure_codes:
  - code: "273"
    name: "Left Atrial Appendage Closure"
    category: "watchman"
```

### Phase 3: Multi-Tenant Architecture (Future)

#### 3.1 Schema-Per-Client Pattern

```sql
-- Each client gets their own schema
CREATE SCHEMA IF NOT EXISTS client_edwards;
CREATE SCHEMA IF NOT EXISTS client_medtronic;
CREATE SCHEMA IF NOT EXISTS client_abbott;

-- Shared reference data
CREATE SCHEMA IF NOT EXISTS shared;

-- Client-specific views use search_path
SET search_path TO client_edwards, shared, public;
```

#### 3.2 Row-Level Security (Alternative)

```sql
-- Single schema, row-level tenant isolation
ALTER TABLE scoring.target_scores ADD COLUMN tenant_id VARCHAR(50);

CREATE POLICY tenant_isolation ON scoring.target_scores
    USING (tenant_id = current_setting('app.tenant_id'));
```

---

## Refactoring Roadmap

### Short-Term (Current Project)

1. **Parameterize infrastructure names** via environment variables
2. **Document client-specific assumptions** in README
3. **Abstract User-Agent** to configuration

### Medium-Term (New Client)

1. **Create config templates** for domain/client settings
2. **Genericize table names** where possible
3. **Build deployment automation** for new client setup

### Long-Term (Platform)

1. **Extract reusable core** into `datakinetic-core` library
2. **Build client provisioning tooling**
3. **Implement multi-tenant architecture** if business requires

---

## Implementation Checklist

- [ ] Create `config/deployment.yaml` template
- [ ] Replace hardcoded `edwards_tavr` with env var
- [ ] Replace hardcoded `tavr-*` container names
- [ ] Update User-Agent to use configuration
- [ ] Document domain-specific business logic
- [ ] Create procedure code configuration file
- [ ] Add `CLIENT_CODE` and `DOMAIN_CODE` to `.env.example`
- [ ] Update Makefile to validate config before deploy

---

## Migration Path for New Clients

```bash
# New client setup process
./scripts/setup_client.sh \
  --client-code "medtronic" \
  --client-name "Medtronic" \
  --domain-code "tavr" \
  --domain-name "TAVR Targeting"

# Generated artifacts:
# - config/clients/medtronic.yaml
# - .env.medtronic
# - kubernetes manifests with medtronic namespace
# - database: medtronic_tavr
```

---

## References

- [12-Factor App: Config](https://12factor.net/config)
- [PostgreSQL: Schema-Based Multi-Tenancy](https://www.postgresql.org/docs/current/ddl-schemas.html)
- [Multi-Tenant SaaS Patterns](https://docs.microsoft.com/en-us/azure/architecture/guide/multitenant/considerations/tenancy-models)
