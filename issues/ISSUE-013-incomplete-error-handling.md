# ISSUE-013: Incomplete Error Handling in Fetchers

**Project**: dk-data-FE
**Category**: Code Quality
**Priority**: P2 - Medium
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The fetcher error handling catches broad `Exception` classes, loses stack trace context, doesn't classify errors (retryable vs fatal), and doesn't propagate errors to job status appropriately. This makes debugging difficult and prevents automated recovery.

---

## Affected Files

| File | Issue |
|------|-------|
| `src/dk_data/ingestion/fetchers/base.py` | Broad exception catching |
| `src/dk_data/ingestion/batch/api.py` | Generic 500 responses |
| All fetcher implementations | Inconsistent error patterns |

---

## Evidence from Codebase

### base.py (lines 119-129)

```python
def log_fetch_result(self, result: Dict[str, Any]) -> None:
    """Log fetch result for monitoring."""
    timestamp = datetime.now().isoformat()
    status = result.get('status', 'unknown')
    records = result.get('records', 0)

    if status == 'success':
        logger.info(f"[{self.SOURCE_NAME}] Fetch successful: {records} records at {timestamp}")
    else:
        error = result.get('error', 'Unknown error')
        logger.error(f"[{self.SOURCE_NAME}] Fetch failed: {error} at {timestamp}")
```

**Issues**:
- Error stored as string, stack trace lost
- No error classification
- No structured error logging

### api.py (lines 161-163, 251-254)

```python
except Exception as e:
    logger.error(f"Error listing jobs: {e}")
    raise HTTPException(status_code=500, detail=str(e))
```

**Issues**:
- All exceptions return 500
- `str(e)` loses traceback
- No differentiation between client errors (400) and server errors (500)

---

## Error Handling Anti-Patterns Found

### 1. Broad Exception Catching

```python
# Bad: Catches everything
try:
    result = self.fetch()
except Exception as e:
    result['error'] = str(e)  # Lost: traceback, exception type
```

### 2. Silent Exception Swallowing

```python
# Bad: Logs but doesn't propagate
except Exception as e:
    logger.error(f"Failed: {e}")
    # Execution continues, caller doesn't know about failure
```

### 3. Loss of Exception Context

```python
# Bad: Original exception is replaced
except SomeSpecificError as e:
    raise HTTPException(status_code=500, detail="Something went wrong")
    # Lost: what specifically went wrong
```

### 4. No Retry Classification

```python
# Bad: All failures treated the same
except Exception as e:
    return {'status': 'failed'}
    # No distinction between:
    # - Network timeout (retryable)
    # - Invalid data format (not retryable)
    # - Authentication failure (needs intervention)
```

---

## Recommended Solutions

### Phase 1: Custom Exception Hierarchy

```python
# ingestion/utils/exceptions.py
"""Custom exception hierarchy for data ingestion."""

class IngestionError(Exception):
    """Base exception for all ingestion errors."""

    def __init__(self, message: str, source: str = None, retryable: bool = False):
        self.message = message
        self.source = source
        self.retryable = retryable
        super().__init__(self.message)


class FetchError(IngestionError):
    """Error during data fetching."""

    def __init__(self, message: str, source: str, url: str = None, status_code: int = None, retryable: bool = True):
        super().__init__(message, source, retryable)
        self.url = url
        self.status_code = status_code


class NetworkError(FetchError):
    """Network-related fetch error (connection, timeout)."""
    retryable = True


class RateLimitError(FetchError):
    """Rate limit exceeded."""
    retryable = True

    def __init__(self, message: str, source: str, retry_after: int = None, **kwargs):
        super().__init__(message, source, **kwargs)
        self.retry_after = retry_after


class AuthenticationError(FetchError):
    """Authentication/authorization failure."""
    retryable = False


class DataFormatError(IngestionError):
    """Data parsing or validation error."""
    retryable = False

    def __init__(self, message: str, source: str, row_number: int = None, column: str = None, **kwargs):
        super().__init__(message, source, retryable=False, **kwargs)
        self.row_number = row_number
        self.column = column


class SchemaError(IngestionError):
    """Schema mismatch or database error."""
    retryable = False
```

### Phase 2: Enhanced Error Handling in Fetchers

```python
# ingestion/fetchers/base.py
import traceback
from ..utils.exceptions import (
    FetchError, NetworkError, RateLimitError,
    AuthenticationError, DataFormatError
)

class BaseFetcher(ABC):

    def fetch_with_error_handling(self, **kwargs) -> Dict[str, Any]:
        """Fetch with comprehensive error handling."""
        result = {
            'source': self.SOURCE_NAME,
            'status': 'unknown',
            'error': None,
            'error_type': None,
            'retryable': False,
            'traceback': None,
        }

        try:
            fetch_result = self.fetch(**kwargs)
            result.update(fetch_result)
            result['status'] = 'success'

        except requests.exceptions.Timeout as e:
            result.update(self._handle_network_error(e, "Request timed out"))

        except requests.exceptions.ConnectionError as e:
            result.update(self._handle_network_error(e, "Connection failed"))

        except requests.exceptions.HTTPError as e:
            result.update(self._handle_http_error(e))

        except json.JSONDecodeError as e:
            result.update({
                'status': 'failed',
                'error': f"Invalid JSON response: {e}",
                'error_type': 'DataFormatError',
                'retryable': False,
            })

        except Exception as e:
            # Catch-all for unexpected errors
            result.update({
                'status': 'failed',
                'error': str(e),
                'error_type': type(e).__name__,
                'retryable': False,
                'traceback': traceback.format_exc(),
            })
            logger.exception(f"[{self.SOURCE_NAME}] Unexpected error during fetch")

        self.log_fetch_result(result)
        return result

    def _handle_network_error(self, exc: Exception, message: str) -> dict:
        return {
            'status': 'failed',
            'error': f"{message}: {exc}",
            'error_type': 'NetworkError',
            'retryable': True,
            'traceback': traceback.format_exc(),
        }

    def _handle_http_error(self, exc: requests.exceptions.HTTPError) -> dict:
        status_code = exc.response.status_code if exc.response else None

        if status_code == 429:
            retry_after = exc.response.headers.get('Retry-After', 60)
            return {
                'status': 'failed',
                'error': f"Rate limited (429). Retry after {retry_after}s",
                'error_type': 'RateLimitError',
                'retryable': True,
                'retry_after': int(retry_after),
            }
        elif status_code in (401, 403):
            return {
                'status': 'failed',
                'error': f"Authentication failed ({status_code})",
                'error_type': 'AuthenticationError',
                'retryable': False,
            }
        elif status_code >= 500:
            return {
                'status': 'failed',
                'error': f"Server error ({status_code})",
                'error_type': 'ServerError',
                'retryable': True,
            }
        else:
            return {
                'status': 'failed',
                'error': f"HTTP error ({status_code}): {exc}",
                'error_type': 'HTTPError',
                'retryable': False,
            }
```

### Phase 3: API Error Responses

```python
# ingestion/batch/api.py
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

# Custom exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    logger.exception(f"Unhandled exception: {exc}")

    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": str(exc),
            "path": str(request.url.path),
            "request_id": request.state.request_id if hasattr(request.state, 'request_id') else None,
        }
    )

# Specific error responses
class APIError(HTTPException):
    """Base API error with structured response."""

    def __init__(self, status_code: int, error_code: str, message: str, details: dict = None):
        self.error_code = error_code
        self.details = details
        super().__init__(
            status_code=status_code,
            detail={
                "error": error_code,
                "message": message,
                "details": details,
            }
        )

class NotFoundError(APIError):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            status_code=404,
            error_code="ResourceNotFound",
            message=f"{resource} not found: {identifier}",
            details={"resource": resource, "identifier": identifier}
        )

class ValidationError(APIError):
    def __init__(self, message: str, field: str = None):
        super().__init__(
            status_code=400,
            error_code="ValidationError",
            message=message,
            details={"field": field}
        )

# Usage
@app.get("/jobs/{job_name}")
async def get_job(job_name: str):
    try:
        job = db.get_job(job_name)
        if not job:
            raise NotFoundError("Job", job_name)
        return job
    except NotFoundError:
        raise  # Re-raise our custom errors
    except psycopg2.Error as e:
        logger.exception(f"Database error: {e}")
        raise APIError(503, "DatabaseError", "Database temporarily unavailable")
```

### Phase 4: Error Tracking in Database

```sql
-- meta.error_log table
CREATE TABLE IF NOT EXISTS meta.error_log (
    error_id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source VARCHAR(100) NOT NULL,
    error_type VARCHAR(100) NOT NULL,
    error_message TEXT NOT NULL,
    retryable BOOLEAN NOT NULL DEFAULT FALSE,
    stack_trace TEXT,
    context JSONB,
    job_run_id INTEGER REFERENCES meta.batch_job_runs(run_id),
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT
);

CREATE INDEX idx_error_log_source_time ON meta.error_log(source, timestamp DESC);
CREATE INDEX idx_error_log_unresolved ON meta.error_log(resolved_at) WHERE resolved_at IS NULL;
```

```python
# Log error to database
def log_error_to_db(
    source: str,
    error_type: str,
    message: str,
    retryable: bool = False,
    stack_trace: str = None,
    context: dict = None,
    job_run_id: int = None
):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO meta.error_log
            (source, error_type, error_message, retryable, stack_trace, context, job_run_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING error_id
        """, (source, error_type, message, retryable, stack_trace,
              json.dumps(context) if context else None, job_run_id))
        return cur.fetchone()[0]
```

---

## Error Classification Guidelines

| Error Type | Retryable | Action |
|------------|-----------|--------|
| `NetworkError` | Yes | Retry with backoff |
| `RateLimitError` | Yes | Wait for Retry-After |
| `ServerError` (5xx) | Yes | Retry with backoff |
| `AuthenticationError` | No | Alert, manual intervention |
| `DataFormatError` | No | Log, skip record |
| `SchemaError` | No | Alert, code fix needed |
| `ValidationError` | No | Log, skip record |

---

## Implementation Checklist

- [ ] Create `ingestion/utils/exceptions.py` with hierarchy
- [ ] Update `BaseFetcher` with `fetch_with_error_handling()`
- [ ] Add specific exception handlers to each fetcher
- [ ] Create `APIError` class hierarchy for FastAPI
- [ ] Add global exception handler to FastAPI app
- [ ] Create `meta.error_log` table
- [ ] Implement `log_error_to_db()` function
- [ ] Update job runner to use new error patterns
- [ ] Add error metrics (Prometheus counters)
- [ ] Document error handling patterns in CONTRIBUTING.md

---

## References

- [Python: Exception Handling Best Practices](https://docs.python.org/3/tutorial/errors.html)
- [FastAPI: Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- [Structured Error Handling in Python](https://www.structlog.org/en/stable/recipes.html)
