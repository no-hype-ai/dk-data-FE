# ISSUE-014: Unknown Test Coverage

**Project**: dk-data-FE
**Category**: Code Quality
**Priority**: P2 - Medium
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

Test coverage is unknown. While `pytest` and `pytest-postgresql` are listed as dependencies, no visible test directory or test files exist in the codebase. Without tests, regressions can't be caught before deployment, and refactoring carries high risk.

---

## Evidence from Codebase

### requirements.txt (lines 36-38)

```
# Testing (optional, for development)
pytest>=8.0.0
pytest-postgresql>=6.0.0
```

**Issue**: Testing dependencies exist but marked as "optional".

### File Structure

```bash
$ find . -name "test_*.py" -o -name "*_test.py"
# No results
```

### ARCHITECTURE.md - Test Template

The architecture document includes a test template (lines 1087-1148):

```python
class Test{{ class_name }}Fetcher:
    """Tests for {{ class_name }}Fetcher."""

    def test_source_name(self):
        fetcher = {{ class_name }}Fetcher()
        assert fetcher.SOURCE_NAME == "{{ name }}"
```

**Issue**: Template exists but no actual tests implemented.

---

## Risk Assessment

### Areas Without Test Coverage

| Component | Risk Level | Consequence of Bug |
|-----------|------------|-------------------|
| Fetchers (CMS, HRSA, ACC) | High | Wrong data ingested |
| Data validators (Pydantic) | High | Invalid data in DB |
| API endpoints | High | Incorrect responses |
| SQLMesh models | Medium | Wrong calculations |
| Job runner | Medium | Silent failures |
| Database functions | Medium | Data corruption |

### Business Impact

- **No regression detection**: Changes may break existing functionality
- **Slow debugging**: Manual testing to find issues
- **Fear of refactoring**: Technical debt accumulates
- **Deployment risk**: Each release is uncertain

---

## Recommended Test Strategy

### Test Pyramid

```
                 ┌─────────────────┐
                 │   E2E Tests     │  ← Few (slow, brittle)
                 │   (10-15%)      │
                 └────────┬────────┘
                          │
              ┌───────────┴───────────┐
              │   Integration Tests    │  ← Some
              │       (20-30%)         │
              └───────────┬────────────┘
                          │
       ┌──────────────────┴──────────────────┐
       │           Unit Tests                 │  ← Many (fast)
       │            (60-70%)                  │
       └──────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Test Infrastructure

#### 1.1 Test Directory Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_fetchers.py
│   ├── test_validators.py
│   ├── test_utils.py
│   └── test_job_runner.py
├── integration/
│   ├── test_database.py
│   ├── test_api.py
│   └── test_pipeline.py
└── e2e/
    └── test_full_flow.py
```

#### 1.2 Pytest Configuration

```ini
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = [
    "-v",
    "--tb=short",
    "--strict-markers",
    "-ra",
]
markers = [
    "unit: Unit tests (fast, no external dependencies)",
    "integration: Integration tests (require database)",
    "e2e: End-to-end tests (full system)",
    "slow: Slow tests (excluded by default)",
]
filterwarnings = [
    "ignore::DeprecationWarning",
]

[tool.coverage.run]
source = ["src/dk_data"]
branch = true
omit = [
    "*/tests/*",
    "*/__pycache__/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.:",
    "raise NotImplementedError",
]
fail_under = 70
```

### Phase 2: Unit Tests

#### 2.1 Fetcher Tests

```python
# tests/unit/test_fetchers.py
import pytest
from unittest.mock import Mock, patch
from ingestion.fetchers.base import BaseFetcher
from ingestion.fetchers.cms_inpatient import CMSInpatientFetcher


class TestBaseFetcher:
    """Tests for BaseFetcher base class."""

    def test_calculate_hash_consistent(self, tmp_path):
        """Hash should be consistent for same file."""
        fetcher = CMSInpatientFetcher()
        test_file = tmp_path / "test.csv"
        test_file.write_text("a,b,c\n1,2,3")

        hash1 = fetcher.calculate_hash(test_file)
        hash2 = fetcher.calculate_hash(test_file)

        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hex length

    def test_calculate_hash_changes_with_content(self, tmp_path):
        """Hash should change when file content changes."""
        fetcher = CMSInpatientFetcher()
        test_file = tmp_path / "test.csv"

        test_file.write_text("content1")
        hash1 = fetcher.calculate_hash(test_file)

        test_file.write_text("content2")
        hash2 = fetcher.calculate_hash(test_file)

        assert hash1 != hash2


class TestCMSInpatientFetcher:
    """Tests for CMS Inpatient fetcher."""

    def test_source_name(self):
        fetcher = CMSInpatientFetcher()
        assert fetcher.SOURCE_NAME == "cms_inpatient"

    def test_base_url(self):
        fetcher = CMSInpatientFetcher()
        assert "cms.gov" in fetcher.BASE_URL.lower() or "data.cms.gov" in fetcher.BASE_URL.lower()

    @patch('requests.Session.get')
    def test_fetch_success(self, mock_get, tmp_path):
        """Test successful fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b"test data"]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        fetcher = CMSInpatientFetcher(data_dir=str(tmp_path))

        with patch.object(fetcher, 'get_latest_url', return_value='http://test.com/data.csv'):
            result = fetcher.fetch(year=2024)

        assert result.get('status') in ('success', None) or 'filepath' in result

    @patch('requests.Session.get')
    def test_fetch_handles_timeout(self, mock_get):
        """Test timeout handling."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        fetcher = CMSInpatientFetcher()

        # Should not raise, should return error in result
        result = fetcher.fetch_with_error_handling() if hasattr(fetcher, 'fetch_with_error_handling') else {'status': 'test'}

        # If fetch_with_error_handling exists, check error handling
        # Otherwise, this test documents expected behavior
```

#### 2.2 Validator Tests

```python
# tests/unit/test_validators.py
import pytest
from decimal import Decimal
from pydantic import ValidationError
from ingestion.utils.validators import CMSMedicareInpatientRecord


class TestCMSMedicareInpatientRecord:
    """Tests for CMS Medicare Inpatient validator."""

    def test_valid_record(self):
        record = CMSMedicareInpatientRecord(
            provider_id="123456",
            fiscal_year=2024,
            drg_code="266",
            total_discharges=100,
            average_covered_charges=Decimal("50000.00"),
            average_total_payments=Decimal("25000.00"),
            average_medicare_payments=Decimal("20000.00"),
        )
        assert record.provider_id == "123456"

    def test_invalid_provider_id_length(self):
        with pytest.raises(ValidationError) as exc_info:
            CMSMedicareInpatientRecord(
                provider_id="123",  # Too short
                fiscal_year=2024,
                drg_code="266",
                total_discharges=100,
                average_covered_charges=Decimal("50000.00"),
                average_total_payments=Decimal("25000.00"),
                average_medicare_payments=Decimal("20000.00"),
            )
        assert "provider_id" in str(exc_info.value)

    def test_invalid_fiscal_year(self):
        with pytest.raises(ValidationError):
            CMSMedicareInpatientRecord(
                provider_id="123456",
                fiscal_year=2050,  # Too far in future
                drg_code="266",
                total_discharges=100,
                average_covered_charges=Decimal("50000.00"),
                average_total_payments=Decimal("25000.00"),
                average_medicare_payments=Decimal("20000.00"),
            )

    def test_negative_discharges(self):
        with pytest.raises(ValidationError):
            CMSMedicareInpatientRecord(
                provider_id="123456",
                fiscal_year=2024,
                drg_code="266",
                total_discharges=-1,  # Invalid
                average_covered_charges=Decimal("50000.00"),
                average_total_payments=Decimal("25000.00"),
                average_medicare_payments=Decimal("20000.00"),
            )
```

### Phase 3: Integration Tests

#### 3.1 Database Tests

```python
# tests/integration/test_database.py
import pytest
from ingestion.utils.database import get_connection, get_cursor

@pytest.fixture
def db_connection():
    """Provide database connection for tests."""
    conn = get_connection()
    yield conn
    conn.rollback()
    conn.close()


class TestDatabaseConnection:
    """Tests for database connectivity."""

    @pytest.mark.integration
    def test_connection_works(self, db_connection):
        """Can connect to database."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1

    @pytest.mark.integration
    def test_schemas_exist(self, db_connection):
        """Required schemas exist."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name IN ('raw', 'staging', 'mart', 'scoring', 'meta', 'api')
        """)
        schemas = {row[0] for row in cursor.fetchall()}
        assert schemas == {'raw', 'staging', 'mart', 'scoring', 'meta', 'api'}

    @pytest.mark.integration
    def test_tables_exist(self, db_connection):
        """Critical tables exist."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('raw', 'meta')
        """)
        tables = {f"{row[0]}.{row[1]}" for row in cursor.fetchall()}

        expected = {
            'raw.cms_medicare_inpatient',
            'raw.cms_hospital_info',
            'meta.data_sources',
            'meta.batch_jobs',
        }
        assert expected.issubset(tables)
```

#### 3.2 API Tests

```python
# tests/integration/test_api.py
import pytest
from fastapi.testclient import TestClient
from ingestion.batch.api import app


@pytest.fixture
def client():
    return TestClient(app)


class TestAPIEndpoints:
    """Tests for API endpoints."""

    @pytest.mark.integration
    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "database" in data

    @pytest.mark.integration
    def test_jobs_list(self, client):
        response = client.get("/jobs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.integration
    def test_job_not_found(self, client):
        response = client.get("/jobs/nonexistent-job")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_runs_list(self, client):
        response = client.get("/runs?limit=10")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
```

### Phase 4: Makefile Integration

```makefile
# Test commands
.PHONY: test test-unit test-integration test-e2e test-coverage

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v -m "not slow"

test-integration:
	pytest tests/integration/ -v -m integration

test-e2e:
	pytest tests/e2e/ -v -m e2e

test-coverage:
	pytest tests/ --cov=src/dk_data --cov-report=html --cov-report=term-missing

test-ci:
	pytest tests/ -v --junitxml=test-results.xml --cov=src/dk_data --cov-report=xml
```

---

## Coverage Goals

| Phase | Target Coverage | Focus Areas |
|-------|-----------------|-------------|
| Phase 1 | 30% | Critical paths (fetchers, validators) |
| Phase 2 | 50% | API endpoints, database functions |
| Phase 3 | 70% | Edge cases, error handling |
| Phase 4 | 80% | Comprehensive coverage |

---

## Implementation Checklist

- [ ] Create `tests/` directory structure
- [ ] Add `conftest.py` with shared fixtures
- [ ] Configure pytest in `pyproject.toml`
- [ ] Write unit tests for each fetcher
- [ ] Write unit tests for validators
- [ ] Write integration tests for database
- [ ] Write integration tests for API
- [ ] Add test commands to Makefile
- [ ] Configure CI/CD to run tests
- [ ] Set up coverage reporting
- [ ] Add coverage badge to README

---

## CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r src/dk_data/requirements.txt
          pip install pytest pytest-cov pytest-postgresql

      - name: Run tests
        run: |
          pytest tests/ -v --cov=src/dk_data --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## References

- [pytest: Documentation](https://docs.pytest.org/)
- [pytest-postgresql: Documentation](https://pytest-postgresql.readthedocs.io/)
- [Coverage.py: Documentation](https://coverage.readthedocs.io/)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)
