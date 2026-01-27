# Implementation Plan: DK Molecule Data Platform (012)

**Spec**: `/Users/pschloz/Desktop/DataKinetic/dk-data-FE/specs/012-dk-data-platform/spec.md`
**Generated**: 2026-01-23
**Updated**: 2026-01-24 (Post-Clarification)
**Priority**: P0 - Core Infrastructure

## Related Documents

- **Research**: `research.md` - Technical decisions and rationale
- **Data Model**: `data-model.md` - Entity schemas and relationships
- **API Contracts**: `contracts/` - OpenAPI specifications
- **Quickstart**: `quickstart.md` - Development setup guide

---

## Technical Context

### Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Backend** | Python 3.11+ / FastAPI | Existing stack, async support |
| **Database** | PostgreSQL 16 with pgvector | JSONB for Bronze, pg_trgm for fuzzy matching |
| **Pipeline** | SQLMesh | Plan/apply workflows, incremental models |
| **Cache** | Redis | Async processing, caching |
| **Auth** | JWT with RBAC | Standalone, configurable |
| **Chemistry** | RDKit | SMILES → InChI Key conversion |
| **Monitoring** | Prometheus + Grafana | Existing infrastructure |

### Project Structure

```
app/backend/
├── src/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── bronze.py           # Bronze layer endpoints
│   │   │   ├── silver.py           # Silver layer endpoints
│   │   │   ├── gold.py             # Gold layer endpoints
│   │   │   ├── onboarding.py       # Molecule onboarding wizard
│   │   │   ├── resolution.py       # Identifier resolution
│   │   │   ├── lifecycle.py        # Lifecycle stage APIs
│   │   │   ├── validation.py       # Stage validation
│   │   │   ├── evidence.py         # Evidence requirements
│   │   │   ├── alerts.py           # Alert configuration
│   │   │   ├── monitoring.py       # Pipeline monitoring
│   │   │   └── data_sources.py     # Data source management
│   │   └── middleware/
│   │       └── rbac.py             # Role-based access control
│   ├── services/
│   │   ├── data_platform/
│   │   │   ├── identifier_resolver.py    # Cross-source ID resolution
│   │   │   ├── fuzzy_matcher.py          # pg_trgm name matching
│   │   │   ├── inchi_resolver.py         # RDKit InChI conversion
│   │   │   ├── external_resolver.py      # PubChem/ChEMBL API calls
│   │   │   ├── data_source_registry.py   # Source configuration
│   │   │   ├── bronze_ingestion.py       # Raw data ingestion
│   │   │   ├── silver_transformation.py  # Bronze→Silver ETL
│   │   │   ├── gold_aggregation.py       # Silver→Gold aggregation
│   │   │   ├── lifecycle_detection.py    # Stage auto-detection
│   │   │   ├── molecule_onboarding.py    # 10-step wizard
│   │   │   ├── stage_validation.py       # Evidence validation
│   │   │   ├── evidence_requirements.py  # Gap detection
│   │   │   ├── alert_service.py          # Alert delivery
│   │   │   ├── pipeline_monitoring.py    # Health tracking
│   │   │   ├── retention_manager.py      # 90-day cleanup
│   │   │   ├── schema_detector.py        # Auto-schema detection
│   │   │   ├── credential_store.py       # Secure credential storage
│   │   │   └── bulk_onboarding.py        # CSV/Excel upload
│   │   └── auth/
│   │       └── jwt_service.py            # JWT authentication
│   ├── models/
│   │   ├── bronze/                # Raw data tables
│   │   │   ├── clinicaltrials.py
│   │   │   ├── openfda_labels.py
│   │   │   ├── openfda_faers.py
│   │   │   ├── chembl.py
│   │   │   └── drugbank.py
│   │   ├── silver/                # Normalized tables
│   │   │   ├── molecules.py
│   │   │   ├── identifier_mappings.py
│   │   │   ├── molecule_aliases.py
│   │   │   ├── clinical_trials.py
│   │   │   ├── drug_labels.py
│   │   │   └── adverse_events.py
│   │   ├── gold/                  # Aggregated tables
│   │   │   ├── molecule_profile.py
│   │   │   ├── competitive_landscape.py
│   │   │   ├── safety_signals.py
│   │   │   ├── lifecycle_stages.py
│   │   │   └── lifecycle_evidence.py
│   │   ├── application/           # User-facing tables
│   │   │   ├── tracked_molecules.py
│   │   │   ├── annotations.py
│   │   │   ├── alert_configs.py
│   │   │   ├── alert_history.py
│   │   │   └── audit_log.py
│   │   └── data_platform/         # Infrastructure tables
│   │       ├── data_source.py
│   │       ├── molecule.py
│   │       └── pipeline_runs.py
│   ├── data/
│   │   └── migrations/
│   │       ├── 030_bronze_tables.sql
│   │       ├── 031_silver_tables.sql
│   │       ├── 032_gold_tables.sql
│   │       ├── 033_onboarding_tables.sql
│   │       └── 034_enable_extensions.sql
│   └── config/
│       ├── lifecycle_requirements.yaml
│       └── grafana/
│           └── pipeline_health.json
├── sqlmesh/
│   ├── config.yaml
│   └── models/
│       ├── silver/
│       │   └── clinical_trials.sql
│       └── gold/
│           └── molecule_profile.sql
└── tests/
    └── integration/
        └── test_data_platform.py
```

---

## Clarified Requirements (2026-01-24)

The following decisions were made during the clarification session:

| Question | Decision | Impact |
|----------|----------|--------|
| Disaster Recovery Objectives | **RTO: 1 hour, RPO: 15 minutes** | pgBackRest with WAL archiving, warm standby |
| Source Precedence | **DrugBank > ChEMBL > PubChem > Others** | Entity resolution merge order |
| Data Freshness | **Tiered**: Daily (trials), Weekly (FAERS), Monthly (reference) | Scheduler configuration |
| Low-Confidence Resolution | **Quarantine**: Silver with `needs_review=true`, excluded from Gold | Review queue required |
| Testing Strategy | **End-to-end testing** with real API samples | Golden datasets, pipeline integration tests |

---

## Architecture Decisions

### AD-001: Extended Medallion Architecture (Raw → Bronze → Silver → Gold)

**Decision**: Implement extended Medallion pattern with Raw layer for audit compliance

**Rationale**:
- **Raw**: JSONB storage of original API responses for audit/compliance (indefinite retention)
- **Bronze**: Typed columns extracted from Raw, source structure preserved
- **Silver**: Entity resolution using InChI Key, cross-source linking
- **Gold**: Pre-computed aggregations for sub-second queries
- Each layer has distinct retention and transformation rules

**Alternatives Considered**:
- Direct ETL to single layer: Rejected - loses auditability
- Lambda architecture: Rejected - overkill for batch-oriented workloads
- Data Vault: Rejected - better for slowly-changing dimensions, overkill here

### AD-002: InChI Key as Canonical Identifier

**Decision**: Use InChI Key as the master identifier for small molecules

**Rationale**:
- Structure-based hash provides deterministic identity
- 27-character format is storage-efficient
- Widely supported across ChEMBL, PubChem, BindingDB
- 95% coverage for small molecules

**Fallback**: DrugBank ID or UniProt ID for biologics (no InChI Key)

### AD-003: SQLMesh for Pipeline Orchestration

**Decision**: Use SQLMesh instead of dbt or Airflow

**Rationale**:
- Plan/apply workflow prevents accidental data changes
- Virtual data environments for testing
- Native incremental model support
- SQL and Python model definitions
- Better fit for data quality-first approach

### AD-004: Fuzzy Matching with pg_trgm

**Decision**: Use PostgreSQL pg_trgm extension for name resolution

**Rationale**:
- Handles typos well (Levenshtein + trigram similarity)
- Good balance of speed and accuracy
- No external service dependency
- GIN index support for fast queries

**Configuration**: Similarity threshold 0.3 (maps to ~0.7 confidence)

### AD-005: Separate Tracking Records per Indication

**Decision**: One `user_tracked_molecules` row per molecule+indication combination

**Rationale**:
- Molecules can have different lifecycle stages per indication
- Example: Drug X at Phase 3 for oncology, Phase 2 for autoimmune
- Enables indication-specific alerts and validation

### AD-006: Automatic Data Loading with Change Detection

**Decision**: Implement incremental sync with checksum-based change detection

**Rationale**:
- Hash each record to detect changes without full comparison
- Only process new/modified records in each sync
- Source-specific handlers respect API rate limits
- Tiered refresh schedule balances freshness vs. API load

**Refresh Schedule**:
| Tier | Sources | Frequency |
|------|---------|-----------|
| Daily | ClinicalTrials.gov, OpenFDA Labels | 02:00 UTC |
| Weekly | OpenFDA FAERS, OpenAlex | Sunday 02:00 UTC |
| Monthly | ChEMBL, DrugBank, PubChem, UniProt, PDB, SIDER | 1st of month |

### AD-007: PostgREST for Gold Layer API

**Decision**: Use PostgREST instead of custom FastAPI endpoints for Gold layer

**Rationale**:
- Zero custom code for CRUD operations
- Automatic filtering, sorting, pagination
- JWT integration with PostgreSQL RLS
- OpenAPI auto-generated

**Custom Endpoints**: FastAPI still used for:
- Fuzzy search (`/resolve/search`)
- Entity resolution (`/resolve`)
- Pipeline operations (`/pipeline/*`)

### AD-008: Quarantine Workflow for Low-Confidence Resolution

**Decision**: Records with resolution confidence <0.8 are quarantined

**Implementation**:
- Promote to Silver with `needs_review=true` flag
- Exclude from Gold layer views
- Manual review queue in application layer
- Approved records automatically flow to Gold

---

## Data Model Summary

### Key Entities

| Entity | Layer | Purpose |
|--------|-------|---------|
| `bronze_{source}` | Bronze | Raw API responses (JSONB) |
| `silver_molecules` | Silver | Canonical molecule records |
| `silver_identifier_mappings` | Silver | Cross-reference mappings |
| `silver_molecule_aliases` | Silver | Name variants for fuzzy matching |
| `silver_clinical_trials` | Silver | Normalized trial data |
| `gold_molecule_profile` | Gold | Pre-aggregated profiles |
| `gold_lifecycle_stages` | Gold | Detected lifecycle stages |
| `gold_lifecycle_evidence` | Gold | Evidence supporting stages |
| `user_tracked_molecules` | Application | User tracking records |
| `user_annotations` | Application | Manual evidence additions |
| `onboarding_audit_log` | Application | Compliance audit trail |

### Key Relationships

```
silver_molecules (1) ──── (*) silver_identifier_mappings
silver_molecules (1) ──── (*) silver_molecule_aliases
silver_molecules (1) ──── (1) gold_molecule_profile
gold_molecule_profile (1) ──── (*) gold_lifecycle_stages
gold_lifecycle_stages (1) ──── (*) gold_lifecycle_evidence
silver_molecules (1) ──── (*) user_tracked_molecules
user_tracked_molecules (1) ──── (*) user_annotations
```

---

## API Endpoints Summary

### Bronze Layer

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/bronze/sources` | Register new data source |
| GET | `/api/v1/bronze/sources` | List registered sources |
| POST | `/api/v1/bronze/ingest/{source_id}` | Trigger ingestion |
| GET | `/api/v1/bronze/{source}/records` | Query raw records |

### Silver Layer

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/silver/transform/{source}` | Trigger transformation |
| GET | `/api/v1/silver/molecules` | Query normalized molecules |
| GET | `/api/v1/silver/molecules/{id}` | Get molecule details |

### Resolution

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/resolve` | Resolve any identifier to molecule_id |
| GET | `/api/v1/resolve/search` | Fuzzy name search |

### Gold Layer

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/gold/profiles/{molecule_id}` | Get aggregated profile |
| GET | `/api/v1/gold/lifecycle/{molecule_id}` | Get lifecycle stage |
| GET | `/api/v1/gold/competitive/{indication}` | Get competitive landscape |

### Onboarding

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/onboarding/start` | Start onboarding wizard |
| PUT | `/api/v1/onboarding/{tracking_id}/step/{n}` | Update wizard step |
| POST | `/api/v1/onboarding/{tracking_id}/complete` | Complete onboarding |
| POST | `/api/v1/onboarding/bulk` | Bulk upload molecules |

### Validation & Evidence

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/evidence/{molecule_id}` | Get evidence requirements |
| POST | `/api/v1/validation/{molecule_id}` | Validate stage |
| POST | `/api/v1/annotations` | Add manual evidence |

### Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/alerts/config` | Configure alerts |
| GET | `/api/v1/alerts/history` | Get alert history |

### Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/monitoring/health` | Pipeline health status |
| GET | `/api/v1/monitoring/metrics` | Prometheus metrics |
| POST | `/api/v1/monitoring/run` | Trigger pipeline run |

---

## Security Model

### Roles (RBAC)

| Role | Permissions |
|------|-------------|
| `viewer` | Read Gold layer, own tracked molecules |
| `analyst` | + Onboard molecules, add annotations, configure alerts |
| `data_ops` | + Trigger pipelines, manage data sources, view Bronze/Silver |
| `admin` | + User management, system configuration |

### JWT Token Structure

```json
{
  "sub": "user_id",
  "email": "user@example.com",
  "roles": ["analyst"],
  "exp": 1706000000,
  "iat": 1705900000
}
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| New source to Bronze | < 30 minutes |
| Bronze→Silver 1M records | < 10 minutes |
| Identifier resolution (cached) | < 500ms |
| Identifier resolution (API) | < 3s |
| Gold query response | < 1 second |
| Molecule onboarding (known drug) | < 2 minutes |
| Lifecycle stage accuracy | 90% |
| 99.9% availability | < 8.76 hours downtime/year |

---

## Implementation Phases

### Phase 1: Foundation (Weeks 1-2)
**Objective**: Database infrastructure and core schema

- [ ] Deploy PostgreSQL 14+ with pg_trgm, pgvector extensions
- [ ] Configure pgBackRest (RTO 1hr, RPO 15min)
- [ ] Create schema namespaces: raw, bronze, silver, gold, app
- [ ] Database migrations for Raw layer (10 JSONB tables)
- [ ] Set up connection pooling (PgBouncer)
- [ ] JWT authentication service
- [ ] RBAC middleware (viewer, analyst, data_ops, admin)

**Deliverables**: PostgreSQL running, backup validated, auth working

### Phase 2: Raw + Bronze Layer (Weeks 3-4)
**Objective**: Data ingestion with source structure preservation

- [ ] Implement source-specific fetchers (10 sources)
- [ ] Rate limiting and retry logic per source
- [ ] Checksum-based change detection
- [ ] Bronze table migrations (typed columns)
- [ ] SQLMesh models for Raw → Bronze transformation
- [ ] Data source registry service
- [ ] Ingestion monitoring (Prometheus metrics)

**Deliverables**: All sources loading to Bronze, change detection working

### Phase 3: Entity Resolution + Silver Layer (Weeks 5-6)
**Objective**: Cross-source linking via InChI Key

- [ ] Identifier mapping table
- [ ] InChI Key resolution (RDKit SMILES → InChI)
- [ ] External API resolution (PubChem, ChEMBL)
- [ ] Fuzzy name matching (pg_trgm, threshold 0.3)
- [ ] Confidence scoring algorithm
- [ ] Quarantine workflow (needs_review flag)
- [ ] Silver table migrations
- [ ] SQLMesh models for Bronze → Silver transformation

**Deliverables**: Entity resolution running, 95%+ accuracy on known molecules

### Phase 4: Gold Layer + API (Weeks 7-8)
**Objective**: Decision-ready views and REST API

- [ ] Gold views: molecule_profile, safety_signals, competitive_landscape
- [ ] PostgREST configuration
- [ ] Row-level security policies
- [ ] Search endpoint (fuzzy matching)
- [ ] Cross-reference endpoint
- [ ] Safety signals endpoint
- [ ] SQLMesh models for Silver → Gold aggregation

**Deliverables**: API serving <200ms queries, OpenAPI documentation

### Phase 5: Automatic Data Loading (Weeks 9-10)
**Objective**: Scheduled sync with tiered freshness

- [ ] Kubernetes CronJobs for each tier (daily/weekly/monthly)
- [ ] Incremental sync logic
- [ ] Full refresh capability (manual trigger)
- [ ] Sync job tracking and history
- [ ] Error handling and alerting
- [ ] Rate limit monitoring

**Deliverables**: Automated sync running on schedule, alerts configured

### Phase 6: Testing + Validation (Weeks 11-12)
**Objective**: Comprehensive E2E testing

- [ ] Unit tests for resolution functions
- [ ] Integration tests with testcontainers
- [ ] E2E pipeline tests with real API samples
- [ ] Golden datasets (Core 100, Edge Cases, Conflict Set)
- [ ] Performance benchmarks (bulk load, query latency)
- [ ] Security testing (auth, RLS)

**Deliverables**: 90%+ coverage on resolution, golden dataset passing

### Phase 7: Deployment + Operations (Week 13)
**Objective**: Production-ready deployment

- [ ] Kubernetes manifests (Helm chart)
- [ ] Secrets management
- [ ] Grafana dashboards (pipeline health, data quality)
- [ ] Alerting rules (sync failures, quarantine queue)
- [ ] Backup/restore validation
- [ ] Operations documentation

**Deliverables**: Production deployment, runbooks complete

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| External API rate limits | Data freshness delays | Exponential backoff, distributed scheduling, tiered refresh |
| InChI Key coverage gaps | 5% biologics unresolved | Fallback to DrugBank ID, biologic_mappings table |
| Fuzzy matching false positives | Bad data in Gold | Quarantine workflow, confidence threshold 0.8, manual review |
| Low entity resolution accuracy | Decision quality impact | Source precedence (DrugBank > ChEMBL > PubChem), golden datasets |
| Pipeline failures | Data staleness | Raw layer preservation, idempotent transformations, retry logic |
| Schema changes in source APIs | Sync failures | Version detection, schema validation, graceful degradation |
| Large data volumes | Storage/query performance | Partitioning, incremental loads, index optimization |
| Security breach | Data exposure | JWT auth, RLS, audit logging, MFA for admin |
| Disaster recovery failure | Extended downtime | pgBackRest with WAL archiving, RTO 1hr/RPO 15min tested |

---

## Dependencies

- PostgreSQL 14+ with pg_trgm, pgvector extensions
- pgBackRest for backup/recovery
- PostgREST v14 for API generation
- RDKit Python library
- SQLMesh
- Redis
- Prometheus + Grafana (existing)
- Kubernetes (k3s or bare metal)

---

## External Data Sources

| Source | Records Available | API Type | Rate Limit | Priority |
|--------|-------------------|----------|------------|----------|
| ChEMBL | 2.4M molecules | REST | 1 req/sec | High |
| PubChem | 116M compounds | REST | 5 req/sec | High |
| ClinicalTrials.gov | 500K+ studies | REST | 3 req/sec | High |
| OpenFDA FAERS | 28M+ events | REST | 240/min | High |
| OpenFDA Labels | 175K+ labels | REST | 240/min | Medium |
| DrugBank | 16K drugs | REST | API key | High |
| UniProt | 250M+ proteins | REST | 25 req/sec | Medium |
| RCSB PDB | 220K+ structures | REST | 10 req/sec | Medium |
| SIDER | 1.4K drugs | Flat files | N/A | Medium |
| OpenAlex | 250M+ works | REST | 100K/day | Low |

---

## Data Volume Estimates (5-Year)

| Layer | Current | Year 1 | Year 5 |
|-------|---------|--------|--------|
| Raw | 0 | 50 GB | 250 GB |
| Bronze | 0 | 100 GB | 500 GB |
| Silver | 0 | 50 GB | 250 GB |
| Gold | 0 | 10 GB | 50 GB |

Storage recommendation: Start with 500 GB, scale to 2 TB
