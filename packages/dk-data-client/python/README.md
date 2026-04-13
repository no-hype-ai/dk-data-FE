# dk-data-client (Python)

First-party async Python client for the dk-data platform. See the
[monorepo root README](../README.md) for the full contract.

## Install

```bash
pip install dk-data-client            # core
pip install 'dk-data-client[redis]'   # with Redis L2 cache
```

## Usage

```python
import asyncio
from dk_data_client import DkDataClient

async def main():
    async with DkDataClient(
        metering_proxy_url="https://data.behaviorlabs.ai",
        api_key="dk_data_...",
    ) as client:
        profile = await client.molecules.get_profile("CHEMBL25")
        print(profile)

asyncio.run(main())
```

### Sync facade

For scripts, notebooks, or sync-only consumers:

```python
from dk_data_client.sync import DkDataClient

with DkDataClient(
    metering_proxy_url="https://data.behaviorlabs.ai",
    api_key="dk_data_...",
) as client:
    profile = client.molecules.get_profile("CHEMBL25")
```

## Error handling

Every HTTP failure surfaces as a typed exception:

```python
from dk_data_client import (
    DkDataError,            # base class — catch for "anything went wrong"
    DkDataAuthError,        # 401
    DkDataForbiddenError,   # 403
    DkDataNotFoundError,    # 404
    DkDataStaleError,       # 410 (has .last_refreshed_at)
    DkDataRateLimitError,   # 429 (has .retry_after)
    DkDataServerError,      # 5xx (has .status_code)
    DkDataUpstreamError,    # fallback to upstream failed
)

try:
    trial = await client.molecules.get_clinical_trials("CHEMBL25")
except DkDataStaleError as e:
    print(f"stale since {e.last_refreshed_at}")
except DkDataRateLimitError as e:
    await asyncio.sleep(e.retry_after)
    trial = await client.molecules.get_clinical_trials("CHEMBL25")
```

## Fallback modes

| Mode | Behavior on dk-data miss |
|---|---|
| `strict` | Raise `DkDataNotFoundError` immediately |
| `upstream` (default) | Try the canonical upstream API (PubChem, CT.gov, etc.), return the transformed response, no write-back |
| `hydrate` | v1.1 — same as upstream + write-back |

```python
client = DkDataClient(
    metering_proxy_url="https://data.behaviorlabs.ai",
    api_key="dk_data_...",
    fallback_mode="strict",  # or "upstream"
)
```

## Cache backends

```python
# No cache (fine for tests)
DkDataClient(..., cache_backend="none")

# SQLite (dev / single-process)
DkDataClient(..., cache_backend="sqlite", cache_sqlite_path="/tmp/dk-cache.sqlite")

# Redis (production)
DkDataClient(..., cache_backend="redis", cache_redis_url="redis://localhost:6379")
```

L2 TTLs per method match the gold-table refresh cadence — see
`cache.py:_L2_TTL_SECONDS` or the [TTL table in the contract
doc](../../../.dk/specs/002-external-integration-foundation/contracts/client-package-api.md#l2-cache-ttl-table-corrected-per-drift-audit-f-d019).

## Telemetry

Every call produces one structured event emitted to Loki:

```json
{
  "method": "molecules.getProfile",
  "args_hash": "sha256:...",
  "outcome": "hit|miss|stale|fallthrough_upstream|error",
  "latency_ms": 124,
  "cache_tier": "l1|l2|none",
  "client": "behavior-labs-ai",
  "client_version": "0.1.0"
}
```

Opt out for tests:

```python
client.set_telemetry_enabled(False)
```

## Development

```bash
pip install -e '.[dev]'
pytest tests/unit/ -q
mypy dk_data_client
ruff check dk_data_client
```

See the [monorepo README](../README.md) for integration-test setup.
