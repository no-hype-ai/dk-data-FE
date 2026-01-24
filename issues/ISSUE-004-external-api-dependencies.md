# ISSUE-004: Brittle External API Dependencies

**Project**: dk-data-FE
**Category**: Data Quality & Reliability
**Priority**: P2 - Medium
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The data ingestion layer depends on multiple external government APIs (CMS, HRSA, ACC) without adequate resilience patterns. API changes, rate limits, or outages can cause complete ingestion failures with no fallback mechanisms.

---

## Affected Files

| File | Component | Risk |
|------|-----------|------|
| `src/dk_data/ingestion/fetchers/base.py` | Base retry logic | Limited retry strategies |
| `src/dk_data/ingestion/fetchers/cms_inpatient.py` | CMS API | Rate limits, format changes |
| `src/dk_data/ingestion/fetchers/cms_hospital_info.py` | CMS Hospital Compare | Multiple endpoints |
| `src/dk_data/ingestion/fetchers/acc_tvc.py` | ACC API | Scraping fallback (brittle) |
| `src/dk_data/ingestion/fetchers/hrsa.py` | HRSA API | Pagination changes |

---

## Evidence from Codebase

### base.py (lines 36-44) - Limited Retry Configuration

```python
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
self.session.mount("http://", adapter)
self.session.mount("https://", adapter)
```

**Issues**:
- Only 3 retries with 1-second backoff factor
- No maximum backoff ceiling
- No jitter to prevent thundering herd
- Does not handle connection errors explicitly
- No circuit breaker pattern

### ARCHITECTURE.md (lines 83-86) - Documented Strategies

```markdown
| `ACCTVCFetcher` | ACC certifications | API → Scraping → CSV chain |
```

**Risk**: Scraping fallback is inherently brittle and breaks with HTML changes.

---

## External API Risk Assessment

### CMS APIs (Centers for Medicare & Medicaid Services)

| Endpoint | Risk Factor | Failure Mode |
|----------|-------------|--------------|
| data.cms.gov/provider-data | Rate limits | 429 errors |
| Medicare Inpatient DRG | Annual format changes | Parse failures |
| HCRIS Cost Reports | Large ZIP files | Timeout/memory |
| Hospital Compare | Multiple endpoints | Partial failures |

**Historical Issues**:
- CMS API restructuring (2024) broke existing integrations
- Socrata endpoints have 10,000 row limits without pagination
- Annual file format changes require code updates

### ACC TVC (American College of Cardiology)

| Component | Risk Factor | Failure Mode |
|-----------|-------------|--------------|
| Public API | Low availability | Connection errors |
| Web scraping | HTML structure changes | Parse failures |
| CSV fallback | Manual updates | Stale data |

**Critical Risk**: The 3-stage fallback chain (API → Scrape → CSV) indicates known reliability issues.

### HRSA (Health Resources & Services Administration)

| Endpoint | Risk Factor | Failure Mode |
|----------|-------------|--------------|
| data.hrsa.gov API | Pagination changes | Incomplete data |
| HPSA designations | Quarterly updates | Sync timing |

---

## Current Failure Handling

```
┌─────────────────┐
│  External API   │
│    Request      │
└────────┬────────┘
         │
         ▼
   ┌─────────────┐
   │  3 Retries  │──── Retry with 1s, 2s, 4s backoff
   │  (urllib3)  │
   └──────┬──────┘
         │
         ▼
   ┌─────────────┐
   │  Exception  │──── Logged, but not tracked
   │   Raised    │
   └──────┬──────┘
         │
         ▼
   ┌─────────────┐
   │ Job Fails   │──── No fallback to cached data
   │  Silently   │──── No alert notification
   └─────────────┘
```

---

## Recommended Solutions

### Phase 1: Enhanced Retry Configuration

#### 1.1 Configurable Retry per Source

```python
# ingestion/fetchers/base.py
from dataclasses import dataclass
from typing import Tuple

@dataclass
class RetryConfig:
    """Per-source retry configuration."""
    total: int = 5
    backoff_factor: float = 2.0
    backoff_max: float = 300.0  # 5 minutes max
    backoff_jitter: bool = True
    status_forcelist: Tuple[int, ...] = (429, 500, 502, 503, 504)
    allowed_methods: Tuple[str, ...] = ("GET", "HEAD", "OPTIONS")
    raise_on_status: bool = True

class BaseFetcher(ABC):
    RETRY_CONFIG: RetryConfig = RetryConfig()

    def __init__(self, data_dir: Optional[str] = None):
        # ... existing code ...

        # Enhanced retry with jitter
        retry_strategy = Retry(
            total=self.RETRY_CONFIG.total,
            backoff_factor=self.RETRY_CONFIG.backoff_factor,
            backoff_max=self.RETRY_CONFIG.backoff_max,
            backoff_jitter=self.RETRY_CONFIG.backoff_jitter,
            status_forcelist=self.RETRY_CONFIG.status_forcelist,
            allowed_methods=self.RETRY_CONFIG.allowed_methods,
            raise_on_status=self.RETRY_CONFIG.raise_on_status,
        )
```

#### 1.2 Source-Specific Overrides

```python
# ingestion/fetchers/cms_inpatient.py
class CMSInpatientFetcher(BaseFetcher):
    SOURCE_NAME = "cms_inpatient"
    BASE_URL = "https://data.cms.gov"

    # CMS has aggressive rate limits
    RETRY_CONFIG = RetryConfig(
        total=5,
        backoff_factor=10.0,  # Start with 10s backoff
        backoff_max=600.0,    # Max 10 minutes
        status_forcelist=(429, 500, 502, 503, 504),
    )
```

### Phase 2: Circuit Breaker Pattern

#### 2.1 Implement Circuit Breaker

```python
# ingestion/utils/circuit_breaker.py
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, skip requests
    HALF_OPEN = "half_open"  # Testing if recovered

@dataclass
class CircuitBreaker:
    """Circuit breaker for external API resilience."""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2

    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = field(default=0)
    success_count: int = field(default=0)
    last_failure_time: float = field(default=0.0)

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        else:  # HALF_OPEN
            return True

    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.success_count = 0
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

# Global circuit breakers per source
_circuit_breakers: Dict[str, CircuitBreaker] = {}

def get_circuit_breaker(source_name: str) -> CircuitBreaker:
    if source_name not in _circuit_breakers:
        _circuit_breakers[source_name] = CircuitBreaker()
    return _circuit_breakers[source_name]
```

#### 2.2 Integrate with Fetchers

```python
# ingestion/fetchers/base.py
from ..utils.circuit_breaker import get_circuit_breaker, CircuitState

class BaseFetcher(ABC):
    def fetch_with_circuit_breaker(self, **kwargs) -> Dict[str, Any]:
        """Fetch with circuit breaker protection."""
        cb = get_circuit_breaker(self.SOURCE_NAME)

        if not cb.can_execute():
            logger.warning(f"[{self.SOURCE_NAME}] Circuit breaker OPEN, skipping request")
            return {
                'status': 'skipped',
                'reason': 'circuit_breaker_open',
                'retry_after': cb.recovery_timeout - (time.time() - cb.last_failure_time),
            }

        try:
            result = self.fetch(**kwargs)
            if result.get('status') == 'success':
                cb.record_success()
            else:
                cb.record_failure()
            return result
        except Exception as e:
            cb.record_failure()
            raise
```

### Phase 3: Fallback to Cached Data

#### 3.1 Cache Layer

```python
# ingestion/utils/cache.py
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta

class DataCache:
    """File-based cache for API responses."""

    def __init__(self, cache_dir: str = "./data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, source: str, params: dict) -> str:
        param_str = json.dumps(params, sort_keys=True)
        return hashlib.md5(f"{source}:{param_str}".encode()).hexdigest()

    def get(self, source: str, params: dict, max_age: timedelta = timedelta(days=7)) -> Optional[dict]:
        """Get cached data if available and not too old."""
        key = self._cache_key(source, params)
        cache_file = self.cache_dir / f"{source}_{key}.json"

        if not cache_file.exists():
            return None

        # Check age
        mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
        if datetime.now() - mtime > max_age:
            return None

        with open(cache_file) as f:
            return json.load(f)

    def set(self, source: str, params: dict, data: dict):
        """Cache data for later use."""
        key = self._cache_key(source, params)
        cache_file = self.cache_dir / f"{source}_{key}.json"

        with open(cache_file, 'w') as f:
            json.dump(data, f)
```

#### 3.2 Fallback in Fetchers

```python
# ingestion/fetchers/base.py
class BaseFetcher(ABC):
    def fetch_with_fallback(self, **kwargs) -> Dict[str, Any]:
        """Fetch with cache fallback."""
        cache = DataCache()
        cache_params = {'year': kwargs.get('year'), 'version': '1.0'}

        try:
            result = self.fetch_with_circuit_breaker(**kwargs)

            if result.get('status') == 'success':
                # Cache successful response
                cache.set(self.SOURCE_NAME, cache_params, result)
                return result

        except Exception as e:
            logger.error(f"[{self.SOURCE_NAME}] Fetch failed: {e}")

        # Try cache fallback
        cached = cache.get(self.SOURCE_NAME, cache_params, max_age=timedelta(days=30))
        if cached:
            logger.warning(f"[{self.SOURCE_NAME}] Using cached data from fallback")
            cached['from_cache'] = True
            return cached

        return {
            'status': 'failed',
            'error': 'API unavailable and no cached data',
        }
```

### Phase 4: Alerting Integration

#### 4.1 Alert on Failures

```python
# ingestion/utils/alerts.py
import os
import requests

def send_alert(source: str, error: str, severity: str = "warning"):
    """Send alert to Slack/PagerDuty."""
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    if not webhook_url:
        return

    message = {
        "text": f":warning: Data Ingestion Alert",
        "attachments": [{
            "color": "danger" if severity == "critical" else "warning",
            "fields": [
                {"title": "Source", "value": source, "short": True},
                {"title": "Severity", "value": severity, "short": True},
                {"title": "Error", "value": error[:200], "short": False},
            ]
        }]
    }

    try:
        requests.post(webhook_url, json=message, timeout=10)
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
```

---

## Implementation Checklist

- [ ] Add `RetryConfig` dataclass with per-source overrides
- [ ] Implement circuit breaker pattern
- [ ] Add file-based cache layer
- [ ] Implement `fetch_with_fallback()` method
- [ ] Add Slack/PagerDuty alerting
- [ ] Create health dashboard for API status
- [ ] Document expected API behaviors
- [ ] Add monitoring for circuit breaker state
- [ ] Set up synthetic monitoring for external APIs

---

## Monitoring Recommendations

### Metrics to Track

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| `api_request_duration_seconds` | Fetchers | p95 > 30s |
| `api_failure_count` | Circuit breaker | > 3 in 5 min |
| `circuit_breaker_state` | Circuit breaker | state = OPEN |
| `cache_hit_ratio` | Cache layer | < 0.5 (indicates freshness issues) |
| `data_staleness_hours` | meta.data_sources | > 168 (1 week) |

### Dashboard Queries

```sql
-- Sources with failed recent fetches
SELECT
    source_name,
    last_refresh_status,
    last_refresh_attempt,
    NOW() - last_successful_refresh AS staleness
FROM meta.data_sources
WHERE last_refresh_status = 'failed'
   OR last_successful_refresh < NOW() - INTERVAL '7 days';
```

---

## References

- [Microsoft: Circuit Breaker Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
- [urllib3: Retry Configuration](https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html#urllib3.util.Retry)
- [CMS Data API Documentation](https://data.cms.gov/api-docs)
- [HRSA Data API](https://data.hrsa.gov/data/api)
