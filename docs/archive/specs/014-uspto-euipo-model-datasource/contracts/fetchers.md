# Contract: Fetchers & Loaders

**Feature**: 014-uspto-euipo-model-datasource
**Date**: 2026-02-16

## USPTOTrademarksFetcher (NEW)

**File**: `src/dk_data/ingestion/fetchers/uspto_trademarks.py`
**Extends**: `BaseFetcher`
**Source Name**: `uspto_trademarks`

### Configuration

| Property | Value |
|----------|-------|
| BASE_URL | `https://tsdrapi.uspto.gov` |
| SOURCE_NAME | `uspto_trademarks` |
| Auth | API key via `USPTO_TSDR_API_KEY` env var |
| Rate limit | 60 req/min standard, 4 req/min for multi-case batch |
| Batch endpoint | `GET /ts/cd/caseMultiStatus/sn?ids={comma-separated-sns}` |
| Single endpoint | `GET /ts/cd/casestatus/sn{serial_number}/info` |

### Methods

```python
from typing import Any, Dict, List, Optional


class USPTOTrademarksFetcher(BaseFetcher):
    SOURCE_NAME = "uspto_trademarks"
    BASE_URL = "https://tsdrapi.uspto.gov"

    # Rate limit: 60 req/min standard, 4 req/min for multi-case batch
    REQUEST_DELAY = 1.0  # seconds between standard requests
    BATCH_REQUEST_DELAY = 15.0  # seconds between batch requests

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the USPTO Trademarks fetcher.

        Reads USPTO_TSDR_API_KEY from the environment.
        """
        super().__init__(data_dir)
        import os
        self.api_key: Optional[str] = os.environ.get("USPTO_TSDR_API_KEY")
        if self.api_key:
            self.session.headers.update({"USPTO-API-KEY": self.api_key})
        else:
            logger.warning("USPTO_TSDR_API_KEY not set; TSDR API calls will fail")

    def get_latest_url(self) -> str:
        """Return the TSDR API base URL."""

    def fetch(self, serial_numbers: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
        """Fetch trademark data for given serial numbers.

        Args:
            serial_numbers: List of 8-digit serial numbers to look up.
                           If None, reads from raw table for weekly refresh.

        Returns:
            Dict[str, Any] with keys: status, records, record_count, hash
        """

    @staticmethod
    def _normalize_trademark(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize TSDR API response to flat record.

        Maps Swagger Trademark object fields to raw table columns:
        - serialNumber -> serial_number
        - markElement -> mark_element
        - status/statusStr -> status
        - statusDate -> status_date
        - filingDate -> filing_date
        - usRegistrationNumber -> registration_number
        - gsList[].internationalClasses -> nice_classes
        - parties.currentOwners[0].name -> owner_name
        """

    @staticmethod
    def _build_batch_params(serial_numbers: List[str]) -> Dict[str, Any]:
        """Build query params for multi-case batch endpoint."""
```

### Acceptance Criteria

- AC-1: Fetcher extends `BaseFetcher` and is importable from `dk_data.ingestion.fetchers`.
- AC-2: API key is read from `USPTO_TSDR_API_KEY` environment variable in `__init__`.
- AC-3: Rate limiting uses `time.sleep()` delays: 1.0s between standard requests (60/min), 15.0s between batch requests (4/min), following EPO OPS `OPS_REQUEST_DELAY` pattern.
- AC-4: Returns `{"status": "success", "records": [...], "hash": "..."}` on success. Optionally includes `record_count` (not all existing fetchers return it — USPTOCIFetcher omits it, EPOOPSFetcher includes it).
- AC-5: Returns `{"status": "success", "records": [], "hash": None}` on empty results.
- AC-6: Returns `{"status": "failed", "records": [], "hash": None, "error": "..."}` on failure.
- AC-7: Handles 401 (bad API key) gracefully with logged error.
- AC-8: Hash computed using `hashlib.md5` (matching `BaseFetcher.calculate_hash` convention).

---

## EUIPOTrademarksFetcher (NEW)

**File**: `src/dk_data/ingestion/fetchers/euipo_trademarks.py`
**Extends**: `BaseFetcher`
**Source Name**: `euipo_trademarks`

### Configuration

| Property | Value |
|----------|-------|
| TMview URL | `https://www.tmdn.org/tmview/api/search` |
| IBM Gateway URL | `https://api.euipo.europa.eu/trademark-search` |
| SOURCE_NAME | `euipo_trademarks` |
| Auth (TMview) | Registration-based, API key if required |
| Auth (IBM) | OAuth2 + IBM Client ID (`EUIPO_API_KEY`, `EUIPO_SECRET_KEY`) |
| Rate limit | 30 req/min |
| Nice Class filter | Class 05 (pharmaceutical) |
| Backend selector | `EUIPO_BACKEND` env var: `tmview` (default) or `ibm_gateway` |

### Methods

```python
from typing import Any, Dict, List, Optional


class EUIPOTrademarksFetcher(BaseFetcher):
    SOURCE_NAME = "euipo_trademarks"

    # Rate limit: 30 req/min
    REQUEST_DELAY = 2.0  # seconds between requests

    def __init__(self, data_dir: Optional[str] = None, backend: Optional[str] = None):
        """Initialize with selectable backend.

        Args:
            data_dir: Directory to store downloaded files.
            backend: 'tmview' or 'ibm_gateway'. Defaults to env EUIPO_BACKEND
                    or 'tmview' if not set.
        """
        super().__init__(data_dir)
        import os
        self.backend = backend or os.environ.get("EUIPO_BACKEND", "tmview")
        self.api_key: Optional[str] = os.environ.get("EUIPO_API_KEY")
        self.secret_key: Optional[str] = os.environ.get("EUIPO_SECRET_KEY")

    def get_latest_url(self) -> str:
        """Return the active backend URL."""

    def fetch(self, nice_classes: Optional[List[str]] = None,
              days_back: int = 7,
              max_records: int = 10000,
              **kwargs) -> Dict[str, Any]:
        """Fetch EUIPO trademark data.

        Args:
            nice_classes: Nice class codes to filter (default: ["05"]).
            days_back: Number of days to look back for filing dates.
            max_records: Maximum records to return (pagination limit).

        Returns:
            Dict[str, Any] with keys: status, records, record_count, hash
        """

    def _fetch_tmview(self, nice_classes, date_from, max_records) -> List[Dict[str, Any]]:
        """Fetch from TMview API.

        POST https://www.tmdn.org/tmview/api/search
        Body: {pageSize, pageIndex, criteria: {niceClasses, tradeMarkOffices, ...}}
        """

    def _fetch_ibm_gateway(self, nice_classes, date_from, max_records) -> List[Dict[str, Any]]:
        """Fetch from IBM API Gateway.

        Uses OAuth2 token from EUIPO CAS server.
        Adds X-IBM-Client-Id header.
        """

    @staticmethod
    def _normalize_trademark(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize TMview/IBM response to flat record.

        Maps response fields to raw table columns:
        - applicationNumber -> application_number
        - tradeMarkName -> mark_name
        - tradeMarkType -> mark_kind
        - status -> status
        - applicationDate -> filing_date
        - registrationDate -> registration_date
        - expiryDate -> expiry_date
        - niceClasses -> nice_classes
        - applicantName -> applicant_name
        """
```

### Acceptance Criteria

- AC-1: Fetcher supports both TMview and IBM Gateway backends.
- AC-2: Backend is selectable via `EUIPO_BACKEND` env var or constructor arg.
- AC-3: TMview is the default if no env var is set.
- AC-4: IBM Gateway uses OAuth2 token exchange + IBM Client ID header.
- AC-5: Rate limiting uses `time.sleep(2.0)` between requests (30 req/min), following EPO OPS `OPS_REQUEST_DELAY` pattern.
- AC-6: Pagination stops at `max_records` limit.
- AC-7: Handles HTTP 500 gracefully without crashing.
- AC-8: Returns dict with `status`, `records`, `hash`, `error` keys. Optionally includes `record_count` (not all existing fetchers return it).
- AC-9: Hash computed using `hashlib.md5` (matching `BaseFetcher.calculate_hash` convention).

---

## USPTO Trademarks Loader (NEW)

**File**: `src/dk_data/ingestion/sources/uspto_trademarks.py`

### Interface

**IMPORTANT**: Must follow existing loader pattern from `sources/epo_ops.py`:
- Uses `get_connection()` internally (NOT a `conn` parameter)
- Accepts `source_hash`, `source_file`, `batch_size` parameters
- Returns `Dict[str, Any]` with `status`, `records_inserted`, `records_failed`, `errors`
- Validates each record via Pydantic before INSERT (separate `except ValidationError` and `except Exception` catches per record)
- Batch commits every `batch_size` records (modulo pattern: `if i % batch_size == 0: conn.commit()`)
- Error list truncated to first 10 entries: `errors[:10]` in return dict
- Status logic: `"success" if records_inserted > 0 or records_failed == 0 else "failed"`
- Log suppression: only log individual record errors if `records_failed <= 5`

```python
import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import USPTOTrademarkRecord

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

def load_uspto_trademarks_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Upsert USPTO trademark records into raw.uspto_trademarks.

    Args:
        records: List of normalized trademark dicts from USPTOTrademarksFetcher.
        source_hash: Optional content hash for lineage tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.

    Upsert: ON CONFLICT (serial_number) DO UPDATE SET
            mark_element, status, status_date, ..., _loaded_at = NOW()
    """
```

### Status History Integration

After upserting each record, compare `status` with the last known status in `raw.trademark_status_history` for that serial_number + source. If different, INSERT a new history row. This runs inside the same `get_connection()` block.

**Error handling**: Wrap the history INSERT in a try/except — if the history write fails, log a warning but do NOT fail the main upsert. The history table is informational; the raw upsert must succeed independently.

---

## EUIPO Trademarks Loader (NEW)

**File**: `src/dk_data/ingestion/sources/euipo_trademarks.py`

### Interface

**IMPORTANT**: Same pattern as USPTO loader above — follows `sources/epo_ops.py` conventions (see detailed notes in USPTO Trademarks Loader section).

```python
import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import EUIPOTrademarkRecord

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

def load_euipo_trademarks_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Upsert EUIPO trademark records into raw.euipo_trademarks.

    Args:
        records: List of normalized trademark dicts from EUIPOTrademarksFetcher.
        source_hash: Optional content hash for lineage tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.

    Upsert: ON CONFLICT (application_number) DO UPDATE SET
            mark_name, status, ..., _loaded_at = NOW()
    """
```

### Status History Integration

Same as USPTO loader — compare status and insert history row if changed. Same error handling: history INSERT failure must not block the main upsert.

---

## Module Registration (MODIFY)

### `fetchers/__init__.py`

**File**: `src/dk_data/ingestion/fetchers/__init__.py`

Add imports and register in `__all__`:

```python
from .uspto_trademarks import USPTOTrademarksFetcher
from .euipo_trademarks import EUIPOTrademarksFetcher

__all__ = [
    ...,
    "USPTOTrademarksFetcher",
    "EUIPOTrademarksFetcher",
]
```

### `sources/__init__.py`

**File**: `src/dk_data/ingestion/sources/__init__.py`

Add module name strings to `__all__` (existing pattern uses bare strings, NOT function imports):

```python
__all__ = [
    ...,
    "uspto_trademarks",
    "euipo_trademarks",
]
```

---

## Fetcher Registration (MODIFY)

**File**: `src/dk_data/ingestion/fetch_data.py`

### Changes

```python
# Add to imports
from dk_data.ingestion.fetchers import (
    ...,
    USPTOTrademarksFetcher,
    EUIPOTrademarksFetcher,
)

# Add to FETCHERS dict
FETCHERS = {
    ...,
    'uspto_trademarks': {
        'class': USPTOTrademarksFetcher,
        'description': 'USPTO TSDR trademark case status data',
        'priority': 3,  # Same tier as epo_ops, drugbank (credential-gated)
    },
    'euipo_trademarks': {
        'class': EUIPOTrademarksFetcher,
        'description': 'EUIPO trademark data via TMview/IBM Gateway',
        'priority': 3,  # Same tier as epo_ops, drugbank (credential-gated)
    },
}
```

---

## Pydantic Validators (MODIFY)

**File**: `src/dk_data/ingestion/utils/validators.py`

### USPTOTrademarkRecord (NEW)

```python
class USPTOTrademarkRecord(BaseModel):
    """Validation model for USPTO TSDR trademark data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    serial_number: str = Field(..., min_length=1)
    mark_element: Optional[str] = None
    mark_type: Optional[str] = None
    status: Optional[str] = None
    status_code: Optional[int] = None
    status_date: Optional[date] = None
    filing_date: Optional[date] = None
    registration_number: Optional[str] = None
    registration_date: Optional[date] = None
    nice_classes: Optional[list[int]] = None
    us_classes: Optional[list[str]] = None
    owner_name: Optional[str] = None
    owner_entity_type: Optional[str] = None
    goods_and_services: Optional[str] = None
    description_of_mark: Optional[str] = None  # Matches migration 071 column
```

### EUIPOTrademarkRecord (NEW)

```python
class EUIPOTrademarkRecord(BaseModel):
    """Validation model for EUIPO trademark data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    application_number: str = Field(..., min_length=1)
    mark_name: Optional[str] = None
    mark_kind: Optional[str] = None
    mark_feature: Optional[str] = None
    mark_basis: Optional[str] = None
    applicant_name: Optional[str] = None
    applicant_country: Optional[str] = Field(None, max_length=10)
    representative_name: Optional[str] = None
    status: Optional[str] = None
    filing_date: Optional[date] = None
    registration_date: Optional[date] = None
    expiry_date: Optional[date] = None
    nice_classes: Optional[list[int]] = None
    goods_and_services: Optional[str] = None
```
