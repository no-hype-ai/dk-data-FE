# Medallion Architecture

This document describes the medallion data architecture implemented in the DK Data Platform.

## Overview

The platform implements a **four-layer medallion architecture** for data management:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MEDALLION ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐   │
│  │   RAW    │ ────▶│  BRONZE  │ ────▶│  SILVER  │ ────▶│   GOLD   │   │
│  │          │      │          │      │          │      │          │   │
│  │ Unmodified│      │ Source-  │      │ Entity-  │      │ Business │   │
│  │ API       │      │ native   │      │ resolved │      │ ready    │   │
│  │ responses │      │ typed    │      │ normalized│      │ views    │   │
│  └──────────┘      └──────────┘      └──────────┘      └──────────┘   │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    APPLICATION LAYER                               │ │
│  │  User preferences, tracked molecules, onboarding status            │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

## Layers

### Raw Layer (`raw` schema)

**Purpose**: Store unmodified API responses for audit and reprocessing.

**Characteristics**:
- Complete API response bodies stored as JSONB
- Request metadata (endpoint, params, timestamp)
- Response hash for deduplication
- `processed_to_bronze` flag for pipeline tracking

**Tables**:
- `raw.api_responses` - Generic API response storage
- `raw.sync_schedules` - Data source sync configuration
- `raw.silver_transformation_rules` - Bronze→Silver transformation rules

### Bronze Layer (`bronze` schema)

**Purpose**: Source-native typed data, parsed from raw responses.

**Characteristics**:
- One table per data source
- Typed columns matching source schema
- Preserves original field names where possible
- `processed_to_silver` flag for pipeline tracking
- `raw_json` column for fallback access

**Tables** (examples):
- `bronze.chembl_molecules`
- `bronze.clinicaltrials`
- `bronze.drugbank_data`
- `bronze.openfda_faers`
- `bronze.pubchem_compounds`
- `bronze.uniprot`
- `bronze.orange_book_products`

### Silver Layer (`silver` schema)

**Purpose**: Entity-resolved, normalized, deduplicated data.

**Characteristics**:
- Entity-centric tables (molecules, targets, trials)
- Cross-source identifier linking
- Standardized naming conventions
- Deduplication via identifier resolution

**Tables**:
- `silver.molecules` - Unified molecule records
- `silver.targets` - Protein targets
- `silver.clinical_trials` - Normalized trial data
- `silver.adverse_events` - Safety signals
- `silver.publications` - Scientific literature
- `silver.patents` - Patent information

### Gold Layer (`gold` schema)

**Purpose**: Pre-aggregated analytics and decision-ready views.

**Characteristics**:
- Aggregated metrics and scores
- Business-ready views
- Optimized for dashboards/reports
- May include computed fields and rankings

**Tables/Views**:
- `gold.molecule_profile` - Comprehensive molecule view
- `gold.safety_signals` - Aggregated safety metrics
- `gold.competitive_landscape` - Market analysis
- `gold.company_pipeline` - Company drug pipelines

### Application Layer (`application` schema)

**Purpose**: User-specific data and platform metadata.

**Tables**:
- `application.tracked_molecules` - User watchlists
- `application.alert_configs` - Alert configurations
- `application.annotations` - User annotations
- `application.onboarding_status` - Data ingestion tracking

## Data Flow

### Ingestion Pipeline

```
External API → Raw Layer → Bronze Layer → Silver Layer → Gold Layer
     │              │            │              │            │
     │              │            │              │            └── Dashboards/Reports
     │              │            │              └── API Endpoints
     │              │            └── Entity Resolution
     │              └── Type Parsing
     └── API Call & Storage
```

### Transformation Services

1. **Raw → Bronze**: `bronze_ingestion.py`
   - Parse JSON responses into typed columns
   - Handle source-specific data formats

2. **Bronze → Silver**: `silver_transformation.py` / `dynamic_silver_transformation.py`
   - Entity resolution and linking
   - Deduplication
   - Standardization

3. **Silver → Gold**: `gold_aggregation.py`
   - Aggregation and metrics calculation
   - View generation

## Dynamic Source Onboarding

New data sources can be added without code changes:

1. **Register Source**: Add entry to `raw.sync_schedules`
2. **Configure Credentials**: Store in `raw.data_source_credentials`
3. **Define Schema**: Auto-detect or manually configure
4. **Generate Bronze Table**: System creates table automatically
5. **Add Transformation Rules**: Configure in `raw.silver_transformation_rules`
6. **SQLMesh Model**: Auto-generated for transformations

### API Endpoints

```bash
# Register new source
POST /api/v1/data-sources/register

# Store credentials
POST /api/v1/data-sources/{source}/credentials

# Detect schema
POST /api/v1/data-sources/{source}/detect-schema

# Generate bronze table
POST /api/v1/data-sources/{source}/generate-table

# Trigger sync
POST /api/v1/data-sources/{source}/sync
```

## SQLMesh Integration

The platform uses SQLMesh for declarative transformations:

```
sqlmesh/
├── config.yaml              # Project config
├── audits/                  # Data quality audits
├── macros/                  # Reusable SQL functions
└── molecules/
    ├── bronze/              # Bronze layer models
    ├── silver/              # Silver layer models
    └── gold/                # Gold layer models
```

### Running Transformations

```bash
# Run all transformations
make sqlmesh-run

# Or via API
curl -X POST http://localhost:8000/api/v1/pipeline/sqlmesh
```

## Data Quality

### Audits

Data quality is enforced via SQLMesh audits:

- **not_null**: Required fields present
- **unique**: Primary key uniqueness
- **accepted_values**: Enumeration validation
- **referential_integrity**: Foreign key validation

### Monitoring

- `meta.data_catalog` - Data source health
- `meta.job_runs` - Pipeline execution history
- Data freshness checks via scheduled jobs

## Best Practices

1. **Never modify raw data** - Raw layer is immutable
2. **Document transformations** - Use SQLMesh for traceable changes
3. **Version schema changes** - Use migrations for DDL
4. **Monitor data freshness** - Set up alerts for stale data
5. **Test transformations** - Use staging environment first
