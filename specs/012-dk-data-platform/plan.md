# Implementation Plan: DK Molecule Data Platform (012)

**Spec**: `/Users/pschloz/Desktop/DataKinetic/trials-predictor/.specify/specs/012-dk-data-platform/spec.md`
**Generated**: 2026-01-23
**Priority**: P0 - Core Infrastructure

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

## Architecture Decisions

### AD-001: Medallion Architecture (Bronze/Silver/Gold)

**Decision**: Implement industry-standard Medallion pattern for data refinement

**Rationale**:
- Bronze preserves raw data for regulatory audit trails
- Silver provides normalized, deduplicated entities
- Gold delivers pre-computed aggregations for sub-second queries
- Each layer has distinct retention and transformation rules

**Alternatives Considered**:
- Direct ETL to single layer: Rejected - loses auditability
- Lambda architecture: Rejected - overkill for batch-oriented workloads

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
- Database migrations for all layers
- Core services: IdentifierResolver, FuzzyMatcher
- JWT authentication and RBAC
- Base models for Bronze/Silver/Gold

### Phase 2: Bronze + Silver (Weeks 3-4)
- Data source registration
- Bronze ingestion service
- Silver transformation pipeline
- Entity resolution across sources

### Phase 3: Gold + Lifecycle (Weeks 5-6)
- Gold aggregation service
- Lifecycle stage detection
- Evidence linking
- Confidence scoring

### Phase 4: Onboarding Application (Weeks 7-8)
- 10-step wizard implementation
- Evidence requirements
- Stage validation
- Audit logging

### Phase 5: Operations + Polish (Weeks 9-10)
- Pipeline monitoring dashboard
- Incremental updates
- Alert service
- Bulk onboarding
- Documentation

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| External API rate limits | Exponential backoff, request queuing |
| InChI Key coverage gaps | Fallback to DrugBank ID for biologics |
| Fuzzy matching false positives | Confidence threshold + manual review queue |
| Pipeline failures | Bronze preservation, idempotent transformations |
| Schema changes in source APIs | Graceful degradation, alerting |

---

## Dependencies

- PostgreSQL 16+ with pg_trgm extension
- RDKit Python library
- SQLMesh
- Redis
- Prometheus + Grafana (existing)
- External APIs: ClinicalTrials.gov, OpenFDA, ChEMBL, PubChem
