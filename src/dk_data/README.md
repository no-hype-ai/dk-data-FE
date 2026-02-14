# TAVR Data Infrastructure Platform

A comprehensive data platform for TAVR (Transcatheter Aortic Valve Replacement) clinic targeting, featuring automated data ingestion, transformation, scoring, and API access.

## Overview

This platform ingests healthcare data from multiple sources, transforms it through a SQLMesh pipeline, calculates Target Readiness Scores (TRS) for hospital prioritization, and exposes results via a REST API.

### Key Features

- **Multi-source data ingestion**: CMS Medicare, Hospital Info, Cost Reports, ACC TVC, HRSA
- **SQLMesh transformation pipeline**: Raw → Staging → Mart → Scoring
- **Target Readiness Scoring**: 5-domain scoring system (max 1000 points)
- **REST API**: PostgREST-powered anonymous read access
- **AI Enrichment**: Claude-powered hospital data enrichment
- **Data Quality Monitoring**: Automated freshness and quality checks

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Data Sources                              │
├──────────┬──────────┬──────────┬──────────┬────────────────────┤
│ CMS      │ CMS      │ CMS Cost │ ACC TVC  │ HRSA               │
│ Inpatient│ Hospital │ Reports  │          │ (API)              │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴──────┬─────────────┘
     │          │          │          │            │
     └──────────┴──────────┴──────────┴────────────┘
                           │
                    ┌──────▼──────┐
                    │  Ingestion  │ Python scripts
                    │   Layer     │ (edwards/ingestion/)
                    └──────┬──────┘
                           │
              ┌────────────▼────────────┐
              │     Raw Schema          │
              │  (raw.cms_*, raw.acc_*) │
              └────────────┬────────────┘
                           │
                    ┌──────▼──────┐
                    │  SQLMesh    │ Transformation
                    │  Pipeline   │ pipeline
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
┌────────▼─────┐  ┌────────▼─────┐  ┌────────▼─────┐
│   Staging    │  │    Mart      │  │   Scoring    │
│   Schema     │  │   Schema     │  │   Schema     │
└──────────────┘  └──────────────┘  └──────┬───────┘
                                           │
                                    ┌──────▼──────┐
                                    │  PostgREST  │
                                    │    API      │
                                    └──────┬──────┘
                                           │
                                    ┌──────▼──────┐
                                    │   Clients   │
                                    │  (REST API) │
                                    └─────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- PostgREST (for API)

### Installation

1. **Clone and setup**:
   ```bash
   cd edwards
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.local .env
   # Edit .env with your PostgreSQL credentials
   ```

3. **Initialize database**:
   ```bash
   psql -h localhost -p 5433 -U postgres -f sql/init_database.sql
   psql -h localhost -p 5433 -U postgres -d dk_data -f sql/seed_data_sources.sql
   psql -h localhost -p 5433 -U postgres -d dk_data -f sql/score_history_trigger.sql
   ```

4. **Load data**:
   ```bash
   # Load HRSA data (API-based)
   python -m ingestion.main hrsa

   # Load CMS data (file-based)
   python -m ingestion.main cms_hospital_info --file data/hospital_info.csv
   python -m ingestion.main cms_inpatient --file data/cms_inpatient.csv --fiscal-year 2023
   ```

5. **Run transformations**:
   ```bash
   ./scripts/run_sqlmesh.sh run
   ```

6. **Start API**:
   ```bash
   ./scripts/start_api.sh
   ```

7. **Query API**:
   ```bash
   # Get all targets
   curl http://localhost:3000/targets

   # Filter by tier
   curl "http://localhost:3000/targets?tier_classification=eq.A"

   # Filter by state
   curl "http://localhost:3000/targets?state=eq.CA&order=total_trs.desc"
   ```

## Project Structure

```
edwards/
├── ingestion/              # Data ingestion layer
│   ├── sources/            # Source-specific ingestors
│   │   ├── cms_inpatient.py
│   │   ├── cms_hospital_info.py
│   │   ├── cms_cost_reports.py
│   │   ├── acc_tvc.py
│   │   └── hrsa.py
│   ├── utils/              # Shared utilities
│   │   ├── database.py     # Connection pooling
│   │   ├── retry.py        # Exponential backoff
│   │   └── validators.py   # Pydantic models
│   └── main.py             # CLI entry point
├── sqlmesh/                # SQLMesh transformation
│   ├── models/
│   │   ├── raw/            # External table definitions
│   │   ├── staging/        # Cleaned, deduplicated data
│   │   ├── mart/           # Analytics-ready tables
│   │   └── scoring/        # TRS calculations
│   ├── audits/             # Data quality audits
│   ├── macros/             # Reusable SQL macros
│   └── config.yaml         # SQLMesh configuration
├── claude_sdk/             # AI enrichment agents
│   ├── enrichment.py       # Hospital enrichment
│   └── scoring_agent.py    # Score validation
├── scripts/                # Automation scripts
│   ├── run_sqlmesh.sh      # SQLMesh runner
│   ├── start_api.sh        # API startup
│   ├── refresh_data.sh     # Data refresh orchestration
│   ├── check_freshness.py  # Quality monitoring
│   ├── purge_history.py    # History retention
│   ├── run_enrichment.py   # AI enrichment batch
│   └── validate_api.py     # API spec validation
├── sql/                    # SQL scripts
│   ├── init_database.sql   # Schema creation
│   ├── seed_data_sources.sql
│   └── score_history_trigger.sql
├── logs/                   # Log files
├── postgrest.conf          # PostgREST configuration
├── crontab.txt             # Cron schedule reference
├── requirements.txt        # Python dependencies
└── .env.local              # Environment template
```

## Target Readiness Score (TRS)

The TRS is a composite score (0-1000 points) across five domains:

| Domain | Max Points | Factors |
|--------|------------|---------|
| Clinical Readiness | 250 | TAVR volume, certification, quality rating, growth |
| Operational Readiness | 250 | Bed count, hospital type, emergency services |
| Strategic Alignment | 200 | Network tier, market priority, HPSA status |
| Financial Capacity | 150 | Operating margin, margin quartile |
| Champion Access | 150 | Health system presence, EMR system |

### Tier Classification

| Tier | Score Range | Description |
|------|-------------|-------------|
| A | 800+ | Top targets - high priority |
| B | 600-799 | Strong candidates |
| C | 400-599 | Moderate potential |
| D | 200-399 | Lower priority |
| E | <200 | Not recommended |

## API Endpoints

### Data Views

| Endpoint | Description | Auth Required |
|----------|-------------|---------------|
| `GET /targets` | Scored TAVR clinic targets (full) | Yes |
| `GET /targets_public` | Basic target list (limited fields) | No |
| `GET /hospitals` | Hospital details with certifications | No |
| `GET /scoring_details` | Detailed scoring factor breakdown | Yes |

### Catalog & Jobs

| Endpoint | Description | Auth Required |
|----------|-------------|---------------|
| `GET /catalog` | Full data catalog with health status | Yes |
| `GET /catalog_public` | Public catalog (limited fields) | No |
| `GET /jobs` | Batch job definitions and status | Yes |
| `GET /job_runs` | Job execution history | Yes |
| `GET /health` | System health check | No |

### Query Examples

```bash
# Top 10 Tier A targets in California
curl "http://localhost:3030/targets?tier_classification=eq.A&state=eq.CA&limit=10&order=total_trs.desc"

# Hospitals with TAVR certification
curl "http://localhost:3030/hospitals?has_tavr_certification=eq.true"

# Scoring breakdown for a specific hospital
curl "http://localhost:3030/scoring_details?hospital_id=eq.030064"

# Data catalog with health status
curl "http://localhost:3030/catalog"

# Filter catalog by topic tags (uses PostgREST array operators)
curl "http://localhost:3030/catalog?topic_tags=cs.{cms}"

# System health check
curl "http://localhost:3030/health"

# Batch jobs list
curl "http://localhost:3030/jobs?is_enabled=eq.true"
```

## Make Targets

The project includes comprehensive Makefile targets for common operations:

### Development

```bash
make dev            # Start development environment (PostgREST)
make up             # Start services
make down           # Stop services
make status         # Show system status
make logs           # Show recent logs
```

### Database

```bash
make init-db        # Initialize database schema
make db-shell       # Open PostgreSQL shell
make db-status      # Check database status and record counts
```

### Data Fetching & Ingestion

```bash
make fetch          # Show available fetch commands
make fetch-all      # Fetch data from ALL external sources
make fetch-cms-hospitals    # Fetch CMS Hospital Info
make fetch-cms-inpatient    # Fetch CMS Medicare Inpatient
```

### Catalog & Batch Jobs

```bash
make catalog-refresh    # Refresh catalog semantic metadata
make catalog-status     # Show catalog health summary
make batch-status       # Show batch job status
make batch-trigger JOB=fetch-cms-all    # Trigger a batch job
make batch-runs         # Show recent job runs
```

### SQLMesh

```bash
make sqlmesh-info   # Show SQLMesh project info
make sqlmesh-plan   # Preview SQLMesh changes
make sqlmesh-run    # Apply SQLMesh transformations
```

### API Testing

```bash
make api-test       # Show API endpoints and examples
```

## Data Refresh

### Manual Refresh

```bash
# Refresh all sources
make fetch-all

# Refresh specific source
make fetch-cms-hospitals

# Refresh catalog metadata
make catalog-refresh

# Run SQLMesh transformations
make sqlmesh-run
```

### Batch Job Triggers (via API)

```bash
# Trigger a job via the job-trigger service
make batch-trigger JOB=fetch-cms-all

# Or via curl
curl -X POST http://localhost:8000/jobs/fetch-cms-all/trigger
```

### Scheduled Refresh

Jobs are defined in `meta.batch_jobs` and can be run via:
- Kubernetes CronJobs (production)
- Manual triggers via Job Trigger API
- Makefile targets (development)

See `.gitops/` for Kubernetes CronJob definitions.

## AI Enrichment

The platform includes Claude-powered enrichment for hospital data:

```bash
# Run enrichment on hospitals missing health system/EMR data
python scripts/run_enrichment.py --limit 50

# Dry run to see what would be processed
python scripts/run_enrichment.py --dry-run
```

Requires `ANTHROPIC_API_KEY` environment variable.

## Data Quality

Monitor data freshness and quality:

```bash
# Check all sources
python scripts/check_freshness.py

# Check specific source
python scripts/check_freshness.py --source cms_hospital_info

# JSON output
python scripts/check_freshness.py --json
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | localhost | PostgreSQL host |
| `POSTGRES_PORT` | 5433 | PostgreSQL port |
| `POSTGRES_USER` | postgres | Database user |
| `POSTGRES_PASSWORD` | postgres | Database password |
| `POSTGRES_DB` | dk_data | Database name |
| `ANTHROPIC_API_KEY` | - | For AI enrichment |

### PostgREST

Edit `postgrest.conf` to configure:
- Connection string
- Anonymous role
- Max rows per request
- Server port

## Development

### Running Tests

```bash
# Run SQLMesh audits
./scripts/run_sqlmesh.sh audit

# Validate API spec
python scripts/validate_api.py
```

### Adding a New Data Source

1. Create ingestor in `ingestion/sources/`
2. Add Pydantic model in `ingestion/utils/validators.py`
3. Register in `ingestion/main.py`
4. Add raw table in `sql/init_database.sql`
5. Create SQLMesh models for transformation
6. Add quality checks in `scripts/check_freshness.py`

## License

Proprietary - Edwards Lifesciences

## Support

For issues or questions, contact the Edwards TAVR Data Team.
