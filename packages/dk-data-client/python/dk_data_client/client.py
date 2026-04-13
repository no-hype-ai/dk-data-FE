"""Core `DkDataClient` — ties transport, cache, fallback, and telemetry
together and exposes per-domain modules (`molecules`, `companies`, …).

The design goal is that every call through the client produces exactly
one telemetry event with a well-defined `outcome`, regardless of whether
the result came from L1, L2, the server, or an upstream fallback. This
makes the Adapter Hydration Heat Map dashboard actionable — you can see
at a glance which methods are missing their cache, stalling on the
server, or falling through to an upstream source.
"""

from __future__ import annotations

import time
from typing import Any, Literal

import httpx

from dk_data_client.cache import TwoTierCache, build_cache
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
from dk_data_client.fallback import FallbackMode, fallback_to_upstream
from dk_data_client.telemetry import TelemetryEmitter


class DkDataClient:
    """Async client for the dk-data platform.

    Construct once per process; module accessors are cheap (`client.molecules`,
    `client.companies`, ...). Close via `await client.aclose()` to flush
    pending telemetry and release the HTTP connection pool.
    """

    def __init__(
        self,
        *,
        metering_proxy_url: str,
        api_key: str,
        fallback_mode: Literal["strict", "upstream", "hydrate"] = "upstream",
        cache_backend: Literal["redis", "sqlite", "none"] | None = "redis",
        cache_redis_url: str | None = None,
        cache_sqlite_path: str | None = None,
        timeout: float = 10.0,
        client_name: str = "unknown",
        client_version: str = "0.1.0",
        loki_push_url: str | None = None,
    ) -> None:
        if not metering_proxy_url:
            raise ValueError("metering_proxy_url is required")
        if not api_key:
            raise ValueError("api_key is required")
        self._base_url = metering_proxy_url.rstrip("/")
        self._api_key = api_key
        self._fallback_mode = FallbackMode(fallback_mode)
        self._timeout = timeout

        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": f"dk-data-client/{client_version} (python)",
            },
            timeout=timeout,
        )
        # Upstream fallback uses a separate client with no auth header.
        self._upstream_http = httpx.AsyncClient(timeout=timeout)

        self._cache: TwoTierCache = build_cache(
            cache_backend,
            redis_url=cache_redis_url,
            sqlite_path=cache_sqlite_path,
        )

        self._telemetry = TelemetryEmitter(
            client_name=client_name,
            client_version=client_version,
            loki_push_url=loki_push_url,
        )

        # Lazy-initialized module accessors — see __getattr__ below.
        self._modules: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public module accessors
    # ------------------------------------------------------------------

    @property
    def molecules(self) -> Any:
        return self._module("molecules")

    @property
    def companies(self) -> Any:
        return self._module("companies")

    @property
    def conditions(self) -> Any:
        return self._module("conditions")

    @property
    def publications(self) -> Any:
        return self._module("publications")

    @property
    def patents(self) -> Any:
        return self._module("patents")

    @property
    def providers(self) -> Any:
        return self._module("providers")

    def _module(self, name: str) -> Any:
        if name in self._modules:
            return self._modules[name]
        from dk_data_client.modules import (
            companies,
            conditions,
            molecules,
            patents,
            providers,
            publications,
        )

        registry = {
            "molecules": molecules.MoleculesModule,
            "companies": companies.CompaniesModule,
            "conditions": conditions.ConditionsModule,
            "publications": publications.PublicationsModule,
            "patents": patents.PatentsModule,
            "providers": providers.ProvidersModule,
        }
        instance = registry[name](self)
        self._modules[name] = instance
        return instance

    # ------------------------------------------------------------------
    # Catalog / health (lightweight, uncached)
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        return await self._raw_get("/health", method="health")

    async def catalog(self) -> dict[str, Any]:
        return await self._raw_get("/catalog", method="catalog")

    async def data_sources(self) -> list[dict[str, Any]]:
        data = await self._raw_get("/data_sources", method="dataSources")
        return data if isinstance(data, list) else data.get("data_sources", [])

    async def server_info(self) -> dict[str, Any]:
        """Fetch dk-data version + schema fingerprint.

        Used by `serverInfo()` schema fingerprint check. On mismatch
        between client and server fingerprints the client emits a
        structured warning but does NOT throw (see docs/consumer-
        onboarding.md "v0.1 → v0.2 transition window").
        """
        info = await self._raw_get("/rpc/server_info", method="serverInfo")
        if isinstance(info, dict):
            self._telemetry.set_dk_data_version(info.get("version", ""))
        return info if isinstance(info, dict) else {"version": "", "schema_fingerprint": ""}

    # Public helpers invoked by modules. Kept at client level so every
    # module uses the same transport, cache, and telemetry path.

    async def call(
        self,
        *,
        method: str,
        path: str,
        args: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        http_method: str = "GET",
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Single entry point every module uses.

        Semantics:
          1. Look up L1 → L2
          2. If miss, call the server
          3. If server returns 404 and we have a fallback shim, fall
             through to upstream
          4. Emit one telemetry event with the appropriate outcome
        """
        args = args or {}
        started = time.perf_counter()

        # Cache lookup
        cache_hit = await self._cache.get(method, args)
        if cache_hit is not None:
            self._emit(
                method=method,
                args=args,
                outcome="hit",
                started=started,
                cache_tier=cache_hit.tier,
            )
            return cache_hit.value

        # Server call
        try:
            value = await self._http_call(
                path=path, params=params, http_method=http_method, json_body=json_body
            )
            await self._cache.set(method, args, value)
            self._emit(
                method=method,
                args=args,
                outcome="miss",
                started=started,
                cache_tier="none",
            )
            return value
        except DkDataStaleError:
            self._emit(
                method=method,
                args=args,
                outcome="stale",
                started=started,
                error_type="DkDataStaleError",
            )
            raise
        except DkDataNotFoundError:
            # Fallback path — only if not strict
            if self._fallback_mode is FallbackMode.STRICT:
                self._emit(
                    method=method,
                    args=args,
                    outcome="error",
                    started=started,
                    error_type="DkDataNotFoundError",
                )
                raise
            try:
                value, upstream_name = await fallback_to_upstream(
                    method, args, mode=self._fallback_mode, http=self._upstream_http
                )
            except DkDataUpstreamError:
                self._emit(
                    method=method,
                    args=args,
                    outcome="error",
                    started=started,
                    error_type="DkDataUpstreamError",
                )
                raise
            except DkDataNotFoundError:
                self._emit(
                    method=method,
                    args=args,
                    outcome="error",
                    started=started,
                    error_type="DkDataNotFoundError",
                )
                raise
            self._emit(
                method=method,
                args=args,
                outcome="fallthrough_upstream",
                started=started,
                extra={"upstream": upstream_name},
            )
            return value
        except DkDataError as e:
            self._emit(
                method=method,
                args=args,
                outcome="error",
                started=started,
                error_type=type(e).__name__,
            )
            raise

    async def _raw_get(self, path: str, *, method: str) -> Any:
        """Uncached, telemetry-only GET for catalog/health."""
        started = time.perf_counter()
        try:
            value = await self._http_call(path=path, http_method="GET")
            self._emit(method=method, args={}, outcome="miss", started=started)
            return value
        except DkDataError as e:
            self._emit(
                method=method,
                args={},
                outcome="error",
                started=started,
                error_type=type(e).__name__,
            )
            raise

    async def _http_call(
        self,
        *,
        path: str,
        params: dict[str, Any] | None = None,
        http_method: str = "GET",
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = await self._http.request(
                http_method,
                path,
                params=params,
                json=json_body,
            )
        except httpx.HTTPError as e:
            raise DkDataServerError(
                f"transport error calling {path}: {e}", status_code=0
            ) from e

        return self._raise_for_status(response, path=path)

    def _raise_for_status(self, response: httpx.Response, *, path: str) -> Any:
        sc = response.status_code
        if 200 <= sc < 300:
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            return response.text
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text

        if sc == 401:
            raise DkDataAuthError(f"401 from {path}", details={"body": body})
        if sc == 403:
            raise DkDataForbiddenError(f"403 from {path}", details={"body": body})
        if sc == 404:
            raise DkDataNotFoundError(f"404 from {path}", details={"body": body})
        if sc == 410:
            last = response.headers.get("X-Last-Refreshed-At") or ""
            from datetime import datetime, timezone
            try:
                last_ts = datetime.fromisoformat(last.replace("Z", "+00:00"))
            except ValueError:
                last_ts = datetime.now(timezone.utc)
            raise DkDataStaleError(
                f"410 from {path}",
                last_refreshed_at=last_ts,
                details={"body": body},
            )
        if sc == 429:
            retry_after = float(response.headers.get("Retry-After", 1.0))
            raise DkDataRateLimitError(
                f"429 from {path}",
                retry_after=retry_after,
                details={"body": body},
            )
        if sc >= 500:
            raise DkDataServerError(
                f"{sc} from {path}", status_code=sc, details={"body": body}
            )
        raise DkDataError(f"unexpected status {sc} from {path}", details={"body": body})

    def _emit(
        self,
        *,
        method: str,
        args: dict[str, Any],
        outcome: Any,
        started: float,
        cache_tier: Any = "none",
        error_type: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        latency_ms = int((time.perf_counter() - started) * 1000)
        self._telemetry.emit(
            method=method,
            args=args,
            outcome=outcome,
            latency_ms=latency_ms,
            cache_tier=cache_tier,
            error_type=error_type,
            extra=extra,
        )

    def set_telemetry_enabled(self, enabled: bool) -> None:
        """Opt-out hook for tests and privacy-sensitive consumers."""
        self._telemetry.set_enabled(enabled)

    async def aclose(self) -> None:
        """Flush telemetry and close transport clients."""
        await self._telemetry.aclose()
        await self._http.aclose()
        await self._upstream_http.aclose()
        await self._cache.close()

    async def __aenter__(self) -> DkDataClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
