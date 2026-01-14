# TAVR Data Infrastructure Platform - Architecture Guide

## Overview

This document describes the data ingestion and processing architecture of the TAVR Data Infrastructure Platform. The platform follows a layered approach: **Fetch → Ingest → Transform → Expose**.

```
External Sources (APIs/CSV/Web)
       ↓
   Fetchers (Strategy Pattern)
       ↓
   Raw Data Files (./data/raw/)
       ↓
   Sources/Ingestors (Validation + Load)
       ↓
   PostgreSQL (raw schema)
       ↓
   SQLMesh Pipeline (DAG transformations)
       ↓
   staging → mart → scoring schemas
       ↓
   PostgREST API / Metabase / Claude SDK
```

---

## 1. Fetcher Pattern

### Purpose
Fetchers are responsible for retrieving data from external sources. Each fetcher encapsulates the logic for a specific data provider, handling authentication, pagination, retries, and format conversion.

### Base Class: `BaseFetcher`

Location: `ingestion/fetchers/base.py`

```python
from abc import ABC, abstractmethod

class BaseFetcher(ABC):
    SOURCE_NAME: str = "base"
    BASE_URL: str = ""

    @abstractmethod
    def fetch(self, **kwargs) -> dict:
        """Fetch data from the source. Returns metadata about the fetch."""
        pass

    @abstractmethod
    def get_latest_url(self) -> str:
        """Return the URL for the most recent data."""
        pass
```

### Built-in Capabilities

| Method | Purpose |
|--------|---------|
| `download_file(url, filename)` | Stream download with 8KB chunking |
| `calculate_hash(filepath)` | MD5 hash for deduplication |
| `fetch_json(url, params)` | JSON API requests with error handling |
| `log_fetch_result(result)` | Standardized logging with timestamps |
| `_get_session()` | HTTP session with retry strategy (429, 500, 502, 503, 504) |

### Configuration

```python
# Environment-driven configuration
DATA_DIR = os.getenv('DATA_DIR', './data/raw')
USER_AGENT = "TAVR-Data-Platform/1.0 (Edwards Medical; Data Integration)"

# Retry strategy
max_retries = 3
backoff_factor = 1
status_forcelist = [429, 500, 502, 503, 504]
```

### Current Fetchers

| Fetcher | Source | Strategy |
|---------|--------|----------|
| `CMSInpatientFetcher` | CMS Medicare DRG volumes | API-first, CSV fallback |
| `CMSHospitalInfoFetcher` | CMS Hospital Compare | API with multiple endpoints |
| `CMSCostReportsFetcher` | HCRIS cost reports | ZIP download + extraction |
| `ACCTVCFetcher` | ACC certifications | API → Scraping → CSV chain |
| `HRSAFetcher` | HPSA designations | Paginated API |

### Fetcher Registration

Location: `ingestion/fetch_data.py`

```python
FETCHERS = {
    'cms_inpatient': CMSInpatientFetcher,
    'cms_hospital_info': CMSHospitalInfoFetcher,
    'cms_cost_reports': CMSCostReportsFetcher,
    'acc_tvc': ACCTVCFetcher,
    'hrsa': HRSAFetcher,
}
```

---

## 2. Data Source / Ingestor Pattern

### Purpose
Sources (ingestors) validate and load fetched data into the PostgreSQL `raw` schema. They handle type coercion, deduplication, and metadata tracking.

### Standard Module Structure

Each source module follows this pattern:

```python
# ingestion/sources/{source_name}.py

def calculate_file_hash(filepath: str) -> str:
    """Generate MD5 hash for deduplication."""
    pass

def parse_date(value: str) -> Optional[date]:
    """Parse dates with multiple format support."""
    pass

def load_{source}_file(filepath: str, conn, **kwargs) -> dict:
    """
    Main ingestion function.
    Returns: {records_processed, records_inserted, records_updated, errors}
    """
    pass

def update_{source}_metadata(conn, result: dict) -> None:
    """Log to meta.refresh_log and meta.data_sources."""
    pass

def main():
    """CLI entry point."""
    pass
```

### Validation with Pydantic

Location: `ingestion/utils/validators.py`

```python
from pydantic import BaseModel, Field, field_validator

class CMSMedicareInpatientRecord(BaseModel):
    provider_id: str = Field(..., min_length=6, max_length=6)
    fiscal_year: int = Field(..., ge=2015, le=2030)
    drg_code: str
    total_discharges: int = Field(..., ge=0)
    average_covered_charges: Decimal
    average_total_payments: Decimal
    average_medicare_payments: Decimal

    @field_validator('provider_id')
    @classmethod
    def validate_provider_id(cls, v):
        if not v.isdigit():
            raise ValueError('Provider ID must be numeric')
        return v
```

### Database Utilities

Location: `ingestion/utils/database.py`

```python
from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool

# Connection pooling
pool = ThreadedConnectionPool(minconn=1, maxconn=10, **db_config)

@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)

@contextmanager
def get_cursor():
    """High-level cursor context manager."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            yield cur
```

### Upsert Pattern

```python
def upsert_records(cursor, table: str, records: list, conflict_columns: list):
    """Generic INSERT ... ON CONFLICT handler."""
    # Builds INSERT with ON CONFLICT DO UPDATE
    # Handles batch processing for performance
    pass
```

### Source Registration

Location: `ingestion/main.py`

```python
SOURCES = {
    'cms_inpatient': {
        'loader': load_cms_inpatient_file,
        'requires_file': True,
        'requires_fiscal_year': True,
        'description': 'CMS Medicare Inpatient DRG data'
    },
    'hrsa': {
        'loader': load_hrsa_data,
        'requires_file': False,  # API-based
        'requires_fiscal_year': False,
        'description': 'HRSA shortage area designations'
    },
    # ...
}
```

---

## 3. SQLMesh Processing Layer

### Purpose
SQLMesh manages the transformation pipeline from raw data to analytics-ready tables using SQL models organized in a DAG.

### Schema Layers

| Schema | Purpose | Example Tables |
|--------|---------|----------------|
| `raw` | Ingested data with metadata | `cms_medicare_inpatient`, `acc_tvc_certification` |
| `staging` | Cleaned, denormalized | `stg_hospitals`, `stg_tavr_volumes` |
| `mart` | Business dimensions/facts | `dim_hospital`, `fact_tavr_program` |
| `scoring` | Analytics models | `score_factors`, `target_scores` |

### Configuration

Location: `sqlmesh/config.yaml`

```yaml
gateways:
  local:
    connection:
      type: postgres
      host: localhost
      port: 5433
      database: edwards_tavr
      user: postgres
      password: postgres

physical_schema_mapping:
  raw: raw
  staging: staging
  mart: mart
  scoring: scoring

model_defaults:
  dialect: postgres
  start: '2024-01-01'
```

### Model Structure

```
sqlmesh/
├── config.yaml
├── models/
│   ├── staging/
│   │   ├── stg_hospitals.sql
│   │   └── stg_tavr_volumes.sql
│   ├── mart/
│   │   ├── dim_hospital.sql
│   │   └── fact_tavr_program.sql
│   └── scoring/
│       └── target_scores.sql
├── macros/
│   └── scoring_functions.sql
└── audits/
    └── data_quality.sql
```

### Example Model

```sql
-- models/staging/stg_hospitals.sql
MODEL (
    name staging.stg_hospitals,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at
    ),
    cron '@daily'
);

SELECT
    provider_id,
    hospital_name,
    city,
    state,
    overall_rating,
    _loaded_at
FROM raw.cms_hospital_info
WHERE _loaded_at BETWEEN @start_dt AND @end_dt
```

---

## 4. Directory Structure

```
dk_data/
├── ingestion/
│   ├── __init__.py
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── base.py              # BaseFetcher ABC
│   │   ├── cms_inpatient.py
│   │   ├── cms_hospital_info.py
│   │   ├── cms_cost_reports.py
│   │   ├── acc_tvc.py
│   │   └── hrsa.py
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── cms_inpatient.py
│   │   ├── cms_hospital_info.py
│   │   ├── cms_cost_reports.py
│   │   ├── acc_tvc.py
│   │   └── hrsa.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── database.py          # Connection pooling, cursors
│   │   ├── validators.py        # Pydantic models
│   │   └── retry.py             # @retry_with_backoff decorator
│   ├── fetch_data.py            # Fetcher CLI
│   └── main.py                  # Ingestor CLI
├── sqlmesh/
│   ├── config.yaml
│   ├── models/
│   ├── macros/
│   └── audits/
├── scripts/
│   ├── setup_logging.py
│   ├── run_enrichment.py
│   └── ...
├── claude_sdk/
│   ├── enrichment.py
│   └── scoring_agent.py
├── Makefile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 5. CLI Usage

### Fetching Data

```bash
# Fetch from a specific source
python -m ingestion.fetch_data --source cms_inpatient --year 2023

# Fetch from all sources
python -m ingestion.fetch_data --source all

# List available fetchers
python -m ingestion.fetch_data --list
```

### Ingesting Data

```bash
# Ingest a file-based source
python -m ingestion.main cms_inpatient \
    --file data/raw/cms_inpatient_2023.csv \
    --fiscal-year 2023

# Ingest an API-based source (no file needed)
python -m ingestion.main hrsa

# Dry run (validate without loading)
python -m ingestion.main cms_inpatient --file data.csv --dry-run

# List available sources
python -m ingestion.main --list
```

### SQLMesh Transformations

```bash
# Preview changes
sqlmesh plan

# Apply transformations
sqlmesh apply

# Run specific model
sqlmesh run staging.stg_hospitals
```

---

## 6. Design Patterns

| Pattern | Usage |
|---------|-------|
| **Strategy** | Fetchers implement different retrieval strategies (API, CSV, scraping) |
| **Template Method** | BaseFetcher defines framework; subclasses implement `fetch()` |
| **Registry** | FETCHERS and SOURCES dicts for runtime discovery |
| **Decorator** | `@retry_with_backoff` for resilient operations |
| **Context Manager** | `get_connection()`, `get_cursor()` for resource management |
| **Adapter** | Column mapping adapts various CSV formats to schema |
| **Validator** | Pydantic models ensure data integrity before insert |

---

## 7. Recommended Enhancements

### 7.1 Abstract Base Source Class

Create a `BaseSource` to standardize ingestor implementations:

```python
# ingestion/sources/base.py
from abc import ABC, abstractmethod
from typing import Optional, Any
from pydantic import BaseModel

class BaseSource(ABC):
    """Abstract base class for data sources/ingestors."""

    SOURCE_NAME: str = "base"
    TARGET_SCHEMA: str = "raw"
    TARGET_TABLE: str = ""
    CONFLICT_COLUMNS: list[str] = []

    # Pydantic model for validation
    RECORD_MODEL: type[BaseModel] = None

    @abstractmethod
    def parse_record(self, row: dict) -> Optional[BaseModel]:
        """Parse and validate a single record."""
        pass

    @abstractmethod
    def get_column_mapping(self) -> dict[str, str]:
        """Map source columns to target columns."""
        pass

    def load_file(self, filepath: str, conn, **kwargs) -> dict:
        """Standard file loading with validation."""
        # Shared implementation
        pass

    def load_api(self, conn, **kwargs) -> dict:
        """Standard API loading (override if needed)."""
        raise NotImplementedError("API loading not supported")
```

### 7.2 Source Discovery with Entry Points

Use Python entry points for plugin-style source registration:

```toml
# pyproject.toml
[project.entry-points."dk_data.sources"]
cms_inpatient = "dk_data.ingestion.sources.cms_inpatient:CMSInpatientSource"
hrsa = "dk_data.ingestion.sources.hrsa:HRSASource"
```

```python
# ingestion/main.py
from importlib.metadata import entry_points

def discover_sources() -> dict:
    """Discover sources from entry points."""
    sources = {}
    eps = entry_points(group='dk_data.sources')
    for ep in eps:
        sources[ep.name] = ep.load()
    return sources
```

### 7.3 Enhanced Retry Configuration

Add per-source retry configuration:

```python
@dataclass
class RetryConfig:
    max_attempts: int = 3
    initial_delay: float = 60.0
    backoff_factor: float = 2.0
    max_delay: float = 900.0
    retryable_exceptions: tuple = (ConnectionError, TimeoutError)
    retryable_status_codes: tuple = (429, 500, 502, 503, 504)

class BaseFetcher(ABC):
    RETRY_CONFIG: RetryConfig = RetryConfig()
```

### 7.4 Structured Logging

Add structured logging for observability:

```python
import structlog

logger = structlog.get_logger()

class BaseFetcher(ABC):
    def log_fetch_start(self, **context):
        logger.info("fetch_started",
                    source=self.SOURCE_NAME,
                    **context)

    def log_fetch_complete(self, result: dict):
        logger.info("fetch_completed",
                    source=self.SOURCE_NAME,
                    records=result.get('records_fetched'),
                    duration_ms=result.get('duration_ms'))
```

### 7.5 Data Quality Metrics

Add automatic data quality tracking:

```python
@dataclass
class QualityMetrics:
    total_records: int
    valid_records: int
    invalid_records: int
    null_counts: dict[str, int]
    duplicate_count: int
    validation_errors: list[str]

class BaseSource(ABC):
    def calculate_quality_metrics(self, records: list) -> QualityMetrics:
        """Calculate quality metrics for loaded data."""
        pass

    def log_quality_metrics(self, metrics: QualityMetrics):
        """Log to meta.quality_metrics table."""
        pass
```

### 7.6 Async Fetcher Support

Add async fetchers for concurrent downloads:

```python
import aiohttp
import asyncio

class AsyncBaseFetcher(BaseFetcher):
    async def fetch_async(self, **kwargs) -> dict:
        """Async implementation of fetch."""
        pass

    async def download_files_concurrent(self, urls: list[str]) -> list[str]:
        """Download multiple files concurrently."""
        async with aiohttp.ClientSession() as session:
            tasks = [self._download_one(session, url) for url in urls]
            return await asyncio.gather(*tasks)
```

### 7.7 Schema Evolution Support

Add schema migration tracking:

```python
class SchemaManager:
    """Manage schema versions and migrations."""

    def get_current_version(self, table: str) -> int:
        """Get current schema version for table."""
        pass

    def apply_migration(self, table: str, version: int):
        """Apply a schema migration."""
        pass

    def validate_schema(self, table: str) -> bool:
        """Validate current schema matches expected."""
        pass
```

### 7.8 Incremental Fetch Support

Track fetch state for incremental updates:

```python
class FetchState:
    """Persist fetch state for incremental fetching."""

    def get_last_fetch(self, source: str) -> Optional[datetime]:
        """Get timestamp of last successful fetch."""
        pass

    def get_watermark(self, source: str) -> Optional[str]:
        """Get high-water mark for incremental fetch."""
        pass

    def update_state(self, source: str, timestamp: datetime, watermark: str):
        """Update fetch state after successful fetch."""
        pass
```

---

## 8. Template CLI for New Data Sources

### 8.1 Proposed CLI Interface

```bash
# Generate a new data source
python -m ingestion.generate source weather_data \
    --description "NOAA weather station data" \
    --source-type api \
    --base-url "https://api.weather.gov" \
    --target-table raw.weather_observations

# Options
--source-type     # api, csv, or hybrid (default: hybrid)
--base-url        # Base URL for API sources
--target-table    # Target table in format schema.table
--conflict-cols   # Comma-separated conflict columns for upsert
--has-pagination  # Add pagination support (API sources)
--auth-type       # none, api_key, oauth2, basic
```

### 8.2 Template Generator Implementation

```python
# ingestion/generate.py
import argparse
from pathlib import Path
from jinja2 import Environment, PackageLoader

class SourceGenerator:
    """Generate fetcher and source boilerplate."""

    def __init__(self):
        self.env = Environment(
            loader=PackageLoader('ingestion', 'templates')
        )

    def generate(self, config: dict) -> dict[str, str]:
        """Generate all files for a new source."""
        files = {}

        # Generate fetcher
        fetcher_template = self.env.get_template('fetcher.py.j2')
        files[f"fetchers/{config['name']}.py"] = fetcher_template.render(**config)

        # Generate source/ingestor
        source_template = self.env.get_template('source.py.j2')
        files[f"sources/{config['name']}.py"] = source_template.render(**config)

        # Generate Pydantic model
        model_template = self.env.get_template('model.py.j2')
        files[f"models/{config['name']}_model.py"] = model_template.render(**config)

        # Generate SQLMesh staging model
        sqlmesh_template = self.env.get_template('sqlmesh_staging.sql.j2')
        files[f"../sqlmesh/models/staging/stg_{config['name']}.sql"] = \
            sqlmesh_template.render(**config)

        # Generate tests
        test_template = self.env.get_template('test_source.py.j2')
        files[f"tests/test_{config['name']}.py"] = test_template.render(**config)

        return files

def main():
    parser = argparse.ArgumentParser(description='Generate a new data source')
    parser.add_argument('command', choices=['source'])
    parser.add_argument('name', help='Source name (snake_case)')
    parser.add_argument('--description', required=True)
    parser.add_argument('--source-type', choices=['api', 'csv', 'hybrid'], default='hybrid')
    parser.add_argument('--base-url', default='')
    parser.add_argument('--target-table', required=True)
    parser.add_argument('--conflict-cols', default='id')
    parser.add_argument('--has-pagination', action='store_true')
    parser.add_argument('--auth-type', choices=['none', 'api_key', 'oauth2', 'basic'], default='none')
    parser.add_argument('--dry-run', action='store_true')

    args = parser.parse_args()

    config = {
        'name': args.name,
        'class_name': ''.join(word.title() for word in args.name.split('_')),
        'description': args.description,
        'source_type': args.source_type,
        'base_url': args.base_url,
        'target_schema': args.target_table.split('.')[0],
        'target_table': args.target_table.split('.')[1],
        'conflict_columns': args.conflict_cols.split(','),
        'has_pagination': args.has_pagination,
        'auth_type': args.auth_type,
    }

    generator = SourceGenerator()
    files = generator.generate(config)

    for filepath, content in files.items():
        if args.dry_run:
            print(f"Would create: {filepath}")
        else:
            path = Path(__file__).parent / filepath
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            print(f"Created: {filepath}")

if __name__ == '__main__':
    main()
```

### 8.3 Fetcher Template

```jinja2
{# templates/fetcher.py.j2 #}
"""{{ description }} - Fetcher

Auto-generated by: python -m ingestion.generate source {{ name }}
"""
import os
from typing import Optional
from .base import BaseFetcher


class {{ class_name }}Fetcher(BaseFetcher):
    """Fetcher for {{ description }}."""

    SOURCE_NAME = "{{ name }}"
    BASE_URL = "{{ base_url }}"

    def __init__(self):
        super().__init__()
        self.data_dir = os.getenv('DATA_DIR', './data/raw')

    def get_latest_url(self) -> str:
        """Return URL for the most recent data."""
        return self.BASE_URL

    def fetch(self, **kwargs) -> dict:
        """
        Fetch data from {{ description }}.

        Args:
            **kwargs: Additional fetch parameters

        Returns:
            dict with keys: success, filepath, records_fetched, error
        """
        result = {
            'success': False,
            'source': self.SOURCE_NAME,
            'filepath': None,
            'records_fetched': 0,
            'error': None
        }

        try:
            {% if source_type == 'api' or source_type == 'hybrid' %}
            # API fetch implementation
            url = self.get_latest_url()
            {% if has_pagination %}
            data = self._fetch_paginated(url)
            {% else %}
            data = self.fetch_json(url)
            {% endif %}

            if data:
                filepath = os.path.join(self.data_dir, f'{{ name }}.json')
                self._save_json(filepath, data)
                result['filepath'] = filepath
                result['records_fetched'] = len(data) if isinstance(data, list) else 1
                result['success'] = True
            {% endif %}

            {% if source_type == 'csv' or source_type == 'hybrid' %}
            # CSV download fallback
            if not result['success']:
                csv_url = self._get_csv_url()
                filepath = os.path.join(self.data_dir, f'{{ name }}.csv')
                self.download_file(csv_url, filepath)
                result['filepath'] = filepath
                result['success'] = True
            {% endif %}

        except Exception as e:
            result['error'] = str(e)
            self.logger.error(f"Fetch failed: {e}")

        self.log_fetch_result(result)
        return result

    {% if has_pagination %}
    def _fetch_paginated(self, base_url: str, page_size: int = 1000) -> list:
        """Fetch all pages of data."""
        all_data = []
        offset = 0

        while True:
            params = {'$skip': offset, '$top': page_size}
            page = self.fetch_json(base_url, params=params)

            if not page:
                break

            all_data.extend(page)

            if len(page) < page_size:
                break

            offset += page_size

        return all_data
    {% endif %}

    def _save_json(self, filepath: str, data) -> None:
        """Save data as JSON file."""
        import json
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    {% if source_type == 'csv' or source_type == 'hybrid' %}
    def _get_csv_url(self) -> str:
        """Return CSV download URL."""
        # TODO: Implement CSV URL logic
        return f"{self.BASE_URL}/download.csv"
    {% endif %}
```

### 8.4 Source Template

```jinja2
{# templates/source.py.j2 #}
"""{{ description }} - Source/Ingestor

Auto-generated by: python -m ingestion.generate source {{ name }}
"""
import csv
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..utils.database import get_cursor
from ..utils.validators import {{ class_name }}Record

logger = logging.getLogger(__name__)


# Column mapping: source column -> database column
COLUMN_MAPPING = {
    # TODO: Define column mappings
    # 'source_column': 'db_column',
}


def calculate_file_hash(filepath: str) -> str:
    """Calculate MD5 hash of file for deduplication."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_{{ name }}_file(
    filepath: str,
    conn,
    dry_run: bool = False,
    **kwargs
) -> dict:
    """
    Load {{ description }} data from file.

    Args:
        filepath: Path to data file
        conn: Database connection
        dry_run: If True, validate without inserting
        **kwargs: Additional parameters

    Returns:
        dict with processing statistics
    """
    result = {
        'source': '{{ name }}',
        'filepath': filepath,
        'records_processed': 0,
        'records_inserted': 0,
        'records_updated': 0,
        'records_skipped': 0,
        'errors': [],
        'started_at': datetime.utcnow().isoformat(),
    }

    file_hash = calculate_file_hash(filepath)

    # Check for duplicate file
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM {{ target_schema }}.{{ target_table }}
            WHERE _source_hash = %s LIMIT 1
        """, (file_hash,))
        if cur.fetchone():
            logger.info(f"File already processed: {filepath}")
            result['records_skipped'] = 'duplicate_file'
            return result

    records = []

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row_num, row in enumerate(reader, start=2):
            result['records_processed'] += 1

            try:
                # Map columns
                mapped = {
                    db_col: row.get(src_col, '').strip()
                    for src_col, db_col in COLUMN_MAPPING.items()
                }

                # Validate with Pydantic
                record = {{ class_name }}Record(**mapped)

                records.append({
                    **record.model_dump(),
                    '_source_file': Path(filepath).name,
                    '_source_hash': file_hash,
                    '_loaded_at': datetime.utcnow(),
                })

            except Exception as e:
                result['errors'].append(f"Row {row_num}: {e}")
                logger.warning(f"Validation error row {row_num}: {e}")

    if dry_run:
        logger.info(f"Dry run: would insert {len(records)} records")
        result['records_inserted'] = len(records)
        return result

    # Upsert records
    if records:
        with conn.cursor() as cur:
            from psycopg2.extras import execute_values

            columns = list(records[0].keys())
            values = [[r[c] for c in columns] for r in records]

            conflict_cols = {{ conflict_columns }}
            update_cols = [c for c in columns if c not in conflict_cols and not c.startswith('_')]

            sql = f"""
                INSERT INTO {{ target_schema }}.{{ target_table }} ({', '.join(columns)})
                VALUES %s
                ON CONFLICT ({', '.join(conflict_cols)})
                DO UPDATE SET {', '.join(f'{c} = EXCLUDED.{c}' for c in update_cols)},
                    _loaded_at = EXCLUDED._loaded_at
            """

            execute_values(cur, sql, values)
            result['records_inserted'] = cur.rowcount

    result['completed_at'] = datetime.utcnow().isoformat()
    logger.info(f"Loaded {result['records_inserted']} records from {filepath}")

    return result


def main():
    """CLI entry point."""
    import argparse
    from ..utils.database import get_connection

    parser = argparse.ArgumentParser(description='Load {{ description }}')
    parser.add_argument('filepath', help='Path to data file')
    parser.add_argument('--dry-run', action='store_true', help='Validate without loading')

    args = parser.parse_args()

    with get_connection() as conn:
        result = load_{{ name }}_file(args.filepath, conn, dry_run=args.dry_run)
        print(f"Processed: {result['records_processed']}")
        print(f"Inserted: {result['records_inserted']}")
        if result['errors']:
            print(f"Errors: {len(result['errors'])}")


if __name__ == '__main__':
    main()
```

### 8.5 Pydantic Model Template

```jinja2
{# templates/model.py.j2 #}
"""{{ description }} - Pydantic Model

Auto-generated by: python -m ingestion.generate source {{ name }}
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class {{ class_name }}Record(BaseModel):
    """Validation model for {{ description }}."""

    # TODO: Define fields based on source schema
    id: str = Field(..., description="Primary identifier")

    # Example fields (customize for your source):
    # name: str = Field(..., max_length=255)
    # value: Decimal = Field(..., ge=0)
    # recorded_at: date
    # is_active: bool = True

    class Config:
        str_strip_whitespace = True
        validate_assignment = True

    @field_validator('id')
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v:
            raise ValueError('ID cannot be empty')
        return v
```

### 8.6 SQLMesh Staging Model Template

```jinja2
{# templates/sqlmesh_staging.sql.j2 #}
-- {{ description }} - Staging Model
-- Auto-generated by: python -m ingestion.generate source {{ name }}

MODEL (
    name staging.stg_{{ name }},
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at
    ),
    cron '@daily',
    description '{{ description }} - cleaned and standardized'
);

SELECT
    -- Primary key
    id,

    -- TODO: Add transformed columns
    -- UPPER(name) as name,
    -- COALESCE(value, 0) as value,

    -- Metadata
    _source_file,
    _source_hash,
    _loaded_at
FROM {{ target_schema }}.{{ target_table }}
WHERE _loaded_at BETWEEN @start_dt AND @end_dt
```

### 8.7 Test Template

```jinja2
{# templates/test_source.py.j2 #}
"""Tests for {{ description }} source.

Auto-generated by: python -m ingestion.generate source {{ name }}
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from ingestion.fetchers.{{ name }} import {{ class_name }}Fetcher
from ingestion.sources.{{ name }} import load_{{ name }}_file
from ingestion.utils.validators import {{ class_name }}Record


class Test{{ class_name }}Fetcher:
    """Tests for {{ class_name }}Fetcher."""

    def test_source_name(self):
        fetcher = {{ class_name }}Fetcher()
        assert fetcher.SOURCE_NAME == "{{ name }}"

    def test_get_latest_url(self):
        fetcher = {{ class_name }}Fetcher()
        url = fetcher.get_latest_url()
        assert url.startswith('http')

    @pytest.mark.integration
    def test_fetch_real(self):
        """Integration test - requires network access."""
        fetcher = {{ class_name }}Fetcher()
        result = fetcher.fetch()
        assert result['success'] is True
        assert result['filepath'] is not None


class Test{{ class_name }}Source:
    """Tests for {{ name }} source/ingestor."""

    def test_validate_record(self):
        """Test Pydantic validation."""
        record = {{ class_name }}Record(
            id="test123",
            # TODO: Add required fields
        )
        assert record.id == "test123"

    def test_validate_record_invalid(self):
        """Test validation rejects invalid data."""
        with pytest.raises(ValueError):
            {{ class_name }}Record(id="")

    def test_load_file_dry_run(self, tmp_path):
        """Test dry run mode."""
        # Create test CSV
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("id\ntest123\n")

        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = None  # No duplicate
        conn.cursor.return_value.__enter__ = lambda s: cursor
        conn.cursor.return_value.__exit__ = lambda s, *a: None

        result = load_{{ name }}_file(str(csv_path), conn, dry_run=True)

        assert result['records_processed'] > 0
```

---

## 9. Implementation Checklist for New Sources

When adding a new data source, complete this checklist:

### Phase 1: Planning
- [ ] Document source API/file format
- [ ] Identify primary key / conflict columns
- [ ] Define column mapping
- [ ] Determine fetch strategy (API, CSV, hybrid)
- [ ] Check rate limits and authentication requirements

### Phase 2: Generate Boilerplate
```bash
python -m ingestion.generate source {name} \
    --description "{description}" \
    --source-type {api|csv|hybrid} \
    --target-table raw.{table_name} \
    --conflict-cols {cols}
```

### Phase 3: Implement
- [ ] Customize fetcher `fetch()` method
- [ ] Define Pydantic model fields and validators
- [ ] Complete column mapping in source
- [ ] Add to FETCHERS registry in `fetch_data.py`
- [ ] Add to SOURCES registry in `main.py`

### Phase 4: Database
- [ ] Create target table in `raw` schema
- [ ] Add indexes on conflict columns
- [ ] Grant permissions

### Phase 5: SQLMesh
- [ ] Create staging model
- [ ] Add to mart dimension/fact if needed
- [ ] Run `sqlmesh plan` to validate

### Phase 6: Test
- [ ] Run unit tests
- [ ] Test fetch with `--dry-run`
- [ ] Test ingest with `--dry-run`
- [ ] Run full integration test

### Phase 7: Deploy
- [ ] Update Makefile targets
- [ ] Add to crontab if scheduled
- [ ] Update documentation

---

## 10. Future Roadmap

1. **Template CLI Tool** - Implement the generator described in Section 8
2. **Abstract BaseSource** - Add base class for sources (Section 7.1)
3. **Entry Point Discovery** - Plugin-style source registration (Section 7.2)
4. **Async Fetchers** - Concurrent download support (Section 7.6)
5. **Data Quality Dashboard** - Automated quality metrics (Section 7.5)
6. **Schema Versioning** - Migration tracking (Section 7.7)
7. **Incremental Fetch State** - Watermark-based updates (Section 7.8)
8. **OpenTelemetry Integration** - Distributed tracing
9. **Alerting Integration** - PagerDuty/Slack for failures
10. **Data Catalog UI** - Browse sources, schemas, lineage
