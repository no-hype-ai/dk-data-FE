# Research: DK Molecule Data Platform

**Feature**: 012-dk-data-platform
**Created**: 2026-01-24
**Status**: Complete

---

## Technical Decisions

### 1. Database & Storage

**Decision**: PostgreSQL 14+ with JSONB for Raw layer, typed columns for Bronze/Silver/Gold

**Rationale**:
- JSONB provides flexible schema for raw API responses while maintaining queryability
- Typed columns in Bronze enable efficient SQL queries without runtime JSON parsing
- PostgreSQL pg_trgm extension supports fuzzy name matching for identifier resolution
- Single database simplifies operations vs. polyglot persistence

**Alternatives Considered**:
- MongoDB: Better for unstructured data but lacks relational capabilities for entity resolution
- Snowflake/BigQuery: Cloud-only, conflicts with on-premises requirement
- TimescaleDB: Overkill for non-time-series workload

---

### 2. Data Architecture

**Decision**: Extended Medallion Architecture (Raw → Bronze → Silver → Gold)

**Rationale**:
- Industry standard for pharmaceutical data platforms (Databricks/Delta Lake pattern)
- Raw layer preserves original API responses for audit/compliance
- Bronze maintains source-native column structure for debugging
- Silver performs entity resolution using InChI Key as master identifier
- Gold provides pre-aggregated decision-ready data

**Alternatives Considered**:
- Lambda Architecture: Too complex, unnecessary real-time processing
- Data Vault: Better for slowly-changing dimensions, overkill for this use case
- Direct ETL to single layer: Loses auditability and reprocessing capability

---

### 3. Pipeline Orchestration

**Decision**: SQLMesh for Bronze → Silver → Gold transformations

**Rationale**:
- Plan/apply workflows prevent accidental data corruption
- Virtual data environments enable testing without production impact
- Incremental model support reduces processing time for delta updates
- SQL + Python model definitions suit the team's skills

**Alternatives Considered**:
- dbt: Good but lacks plan/apply workflow
- Airflow: More operational complexity, better for complex DAGs
- Prefect: Newer, less battle-tested in pharma domain

---

### 4. API Layer

**Decision**: PostgREST for auto-generated REST API from PostgreSQL schema

**Rationale**:
- Zero custom API code for CRUD operations on Gold layer
- Automatic filtering, sorting, pagination from query parameters
- JWT integration for authentication
- OpenAPI documentation auto-generated

**Alternatives Considered**:
- FastAPI: More flexible but requires manual endpoint coding
- GraphQL (Hasura): More complex, not needed for current use cases
- Custom REST: Maximum control but significant development overhead

---

### 5. Deployment

**Decision**: Kubernetes (k3s or bare metal) on local/on-premises infrastructure

**Rationale**:
- Full container orchestration with auto-scaling
- Self-healing capabilities for high availability
- No cloud vendor dependency (data sovereignty)
- Helm charts for repeatable deployments

**Alternatives Considered**:
- Docker Compose: Simpler but lacks auto-scaling and self-healing
- AWS ECS/EKS: Cloud dependency conflicts with on-premises requirement
- Bare metal without containers: Harder to manage, less portable

---

### 6. Backup & Recovery

**Decision**: pgBackRest with WAL archiving, RTO 1 hour, RPO 15 minutes

**Rationale**:
- Continuous WAL archiving enables point-in-time recovery
- Full backups weekly, incremental daily balances storage vs. recovery time
- 1-hour RTO achievable with warm standby
- 15-minute RPO ensures minimal data loss

**Alternatives Considered**:
- pg_dump only: No point-in-time recovery, longer RTO
- Barman: Similar capabilities, less documentation
- Cloud-managed backups: Conflicts with on-premises requirement

---

### 7. Entity Resolution

**Decision**: InChI Key as master identifier with source precedence DrugBank > ChEMBL > PubChem > Others

**Rationale**:
- InChI Key is universal structure-based identifier for small molecules
- DrugBank is FDA-linked and manually curated (highest trust)
- ChEMBL is EBI-curated with structure validation
- Clear precedence eliminates ambiguity in data merging

**Alternatives Considered**:
- PubChem CID as master: Broadest coverage but less curation
- Consensus voting: Complex, may select wrong value
- Property-specific rules: Too complex to maintain

---

### 8. Fuzzy Name Matching

**Decision**: Levenshtein + trigram similarity using PostgreSQL pg_trgm extension

**Rationale**:
- Handles typos well (asprin → aspirin)
- Good balance of speed and accuracy
- Native PostgreSQL - no external service needed
- Configurable similarity threshold (default 0.3)

**Alternatives Considered**:
- Elasticsearch fuzzy: Requires separate service
- Jaro-Winkler: Better for short strings but not as good for drug names
- Soundex/Metaphone: Phonetic matching less useful for scientific names

---

### 9. Authentication

**Decision**: Standalone JWT with username/password + optional MFA

**Rationale**:
- Self-contained, no external IdP dependency
- RBAC with 4 roles: viewer, analyst, data_ops, admin
- JWT tokens integrate with PostgREST row-level security
- Optional MFA for enhanced security

**Alternatives Considered**:
- OAuth2/OIDC with external IdP: More complex, requires IdP setup
- API keys only: No user-level access control
- Session-based auth: Doesn't scale as well, harder to integrate with PostgREST

---

### 10. Data Freshness

**Decision**: Tiered refresh schedule based on data criticality

**Rationale**:
- Clinical trials and FDA labels change frequently → daily refresh
- Safety data (FAERS) needs timely updates → weekly refresh
- Reference data (ChEMBL, DrugBank) is stable → monthly refresh
- Balances freshness with API rate limits

**Alternatives Considered**:
- All daily: Excessive API usage, may hit rate limits
- All weekly: Clinical trial data too stale
- On-demand only: Unpredictable data freshness

---

### 11. Low-Confidence Resolution

**Decision**: Quarantine workflow - promote to Silver with `needs_review=true`, exclude from Gold

**Rationale**:
- Prevents bad data from propagating to decision-ready Gold layer
- Records still visible in Silver for review
- Manual review queue enables human curation
- Approved records automatically flow to Gold

**Alternatives Considered**:
- Block at Bronze: May never get reviewed
- Auto-accept with low score: Bad data reaches users
- Best-guess: Same problem as auto-accept

---

### 12. Testing Strategy

**Decision**: End-to-end testing with real API samples

**Rationale**:
- Data pipelines are inherently integration-heavy
- Real API samples catch format changes
- Tests verify complete Raw → Bronze → Silver → Gold flow
- Golden datasets enable regression detection

**Alternatives Considered**:
- Unit tests only: Miss integration issues
- Property-based testing: Complex to set up for data pipelines
- Production monitoring only: Catches issues too late

---

## Dependencies Verified

| Dependency | Version | Purpose | Status |
|------------|---------|---------|--------|
| PostgreSQL | 14+ | Primary database | Available |
| pgBackRest | Latest | Backup/recovery | Available |
| PostgREST | v14 | REST API generation | Available |
| SQLMesh | Latest | Pipeline orchestration | Available |
| RDKit | Latest | SMILES → InChI conversion | Available |
| pg_trgm | Built-in | Fuzzy matching | Available |
| Kubernetes | 1.28+ | Container orchestration | Available |
| Prometheus | Latest | Metrics collection | Available |
| Grafana | Latest | Dashboards | Available |

---

## Open Questions

None - all technical decisions have been made through the clarification sessions.

---

## References

- [PostgREST Documentation](https://docs.postgrest.org/en/v14/)
- [SQLMesh Documentation](https://sqlmesh.readthedocs.io/)
- [pgBackRest User Guide](https://pgbackrest.org/user-guide.html)
- [Medallion Architecture - Databricks](https://www.databricks.com/glossary/medallion-architecture)
- [InChI Key Specification](https://www.inchi-trust.org/)
