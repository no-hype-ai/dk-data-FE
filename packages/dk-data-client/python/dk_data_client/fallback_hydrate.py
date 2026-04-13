"""Hydrate fallback mode — v1.1 stub.

Feature: 002-external-integration-foundation (T145, US-1)

In hydrate mode, when dk-data returns 404 for a call, the client:

  1. Fetches the result from the configured upstream shim (same as
     upstream mode)
  2. Writes the result back to dk-data via an idempotent ingestion
     endpoint (`POST /data-platform/ingest/{resource}`)
  3. Returns the upstream result to the caller
  4. Emits a telemetry event with `outcome=fallthrough_hydrate` so
     operators can see which sources the adapter is self-hydrating

**Gating requirement**: hydrate mode is scheduled for v1.1 because
idempotent ingestion endpoints are not yet present in Phase 4. Writing
back to dk-data without idempotency would produce duplicate silver
rows on every fallthrough — a correctness bug the v0.1 design avoids
by raising NotImplementedError.

When Phase 4 lands:
  1. Add `POST /data-platform/ingest/{resource}` endpoints that are
     idempotent on `(source, upstream_id)` via `ON CONFLICT DO UPDATE`
  2. Bump the client to v1.0 and register the hydrate shim below
  3. Drop the NotImplementedError guard in `fallback.py`
"""

from __future__ import annotations

from typing import Any

import httpx

from dk_data_client.errors import DkDataUpstreamError
from dk_data_client.fallback import FallbackContext, UpstreamShim


class HydrateWriteBackClient:
    """Write-back helper for hydrate mode (not yet active).

    Stubbed so the code path compiles and the v1.1 implementer has
    a clear home. Currently every method raises NotImplementedError;
    importing this module must not fail.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def write_back(
        self,
        ctx: FallbackContext,
        upstream_value: Any,
        http: httpx.AsyncClient,
    ) -> None:
        """Persist the upstream result back to dk-data.

        Implementation notes for v1.1:

          - Pick the right endpoint based on `ctx.method`
          - Send upstream_value as JSON body
          - Require 202 Accepted (ingestion is async) or 201 Created
          - On non-2xx, raise DkDataUpstreamError so the caller can
            tell the difference between "upstream failed" and "dk-data
            refused the write-back"
        """
        raise NotImplementedError(
            "hydrate fallback mode is scheduled for dk-data-client v1.1; "
            "v0.1 raises before reaching write-back. See T145 and Phase 4 "
            "idempotent ingestion endpoints."
        )


def hydrate_fetch_and_write_back(
    shim: UpstreamShim,
    write_back_client: HydrateWriteBackClient,
) -> Any:
    """Placeholder composition helper — activated in v1.1.

    Kept importable so the TS/Py type generator stays symmetric with
    the TypeScript `fallback/hydrate.ts` stub.
    """
    raise NotImplementedError(
        "hydrate fallback mode is scheduled for dk-data-client v1.1"
    )
