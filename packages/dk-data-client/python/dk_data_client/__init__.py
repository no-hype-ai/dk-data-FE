"""dk-data-client — first-party client for the dk-data platform.

Provides authenticated, cached, telemetry-instrumented access to
dk-data's PostgREST and FastAPI data-platform endpoints. Handles:

- API key auth through the metering proxy (https://data.behaviorlabs.ai)
- Two-tier caching (L1 in-process LRU, L2 Redis or SQLite)
- Typed errors matching server-side status codes
- Fallback modes: strict (fail fast), upstream (call source on miss)
- Structured telemetry events emitted to Loki

The high-level API mirrors the TypeScript package exactly — see
`.dk/specs/002-external-integration-foundation/contracts/client-package-api.md`
for the canonical contract.

Example:
    >>> from dk_data_client import DkDataClient
    >>> client = DkDataClient(
    ...     metering_proxy_url="https://data.behaviorlabs.ai",
    ...     api_key="dk_data_...",
    ... )
    >>> profile = await client.molecules.get_profile("CHEMBL25")
"""

from dk_data_client.client import DkDataClient
from dk_data_client.errors import (
    DkDataAuthError,
    DkDataError,
    DkDataForbiddenError,
    DkDataNotFoundError,
    DkDataRateLimitError,
    DkDataServerError,
    DkDataStaleError,
    DkDataUpstreamError,
)

__version__ = "0.1.0"

__all__ = [
    "DkDataClient",
    "DkDataError",
    "DkDataAuthError",
    "DkDataForbiddenError",
    "DkDataNotFoundError",
    "DkDataStaleError",
    "DkDataUpstreamError",
    "DkDataRateLimitError",
    "DkDataServerError",
    "__version__",
]
