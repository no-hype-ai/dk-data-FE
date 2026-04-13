"""Synchronous facade over the async `DkDataClient`.

Use this from scripts, Jupyter notebooks, or sync-only consumers. It
spins up a background asyncio event loop per client and dispatches
calls to the underlying async client via `asyncio.run_coroutine_threadsafe`.

Caveat: if you're already in an async context, use the async
`DkDataClient` directly. Importing this sync facade inside an async
context and calling it will deadlock the event loop. The module raises
a clear error in that case.

Example:
    >>> from dk_data_client.sync import DkDataClient
    >>> client = DkDataClient(metering_proxy_url="...", api_key="dk_data_...")
    >>> profile = client.molecules.get_profile("CHEMBL25")
    >>> client.close()
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any

from dk_data_client.client import DkDataClient as AsyncDkDataClient


class _LoopThread(threading.Thread):
    """Dedicated asyncio loop running on its own thread."""

    def __init__(self) -> None:
        super().__init__(daemon=True, name="dk-data-client-sync")
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()

    def run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        self.loop.run_forever()

    def wait_ready(self) -> None:
        self._ready.wait()

    def stop(self) -> None:
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.join(timeout=2.0)


class _SyncModule:
    """Wraps an async module so every coroutine method becomes sync."""

    def __init__(self, async_module: Any, loop: asyncio.AbstractEventLoop) -> None:
        self._async = async_module
        self._loop = loop

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._async, name)
        if not callable(attr):
            return attr

        def _sync_call(*args: Any, **kwargs: Any) -> Any:
            coro = attr(*args, **kwargs)
            if not asyncio.iscoroutine(coro):
                return coro
            future: Future[Any] = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result()

        return _sync_call


class DkDataClient:
    """Sync facade. Mirrors the async API — every `await` drops."""

    def __init__(self, **kwargs: Any) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "dk_data_client.sync.DkDataClient cannot be used inside a "
                "running asyncio event loop. Use the async DkDataClient "
                "from dk_data_client.client directly."
            )
        self._thread = _LoopThread()
        self._thread.start()
        self._thread.wait_ready()
        # Construct the underlying async client on the loop thread so
        # its internal httpx client is bound to the correct loop.
        ctor_future: Future[AsyncDkDataClient] = asyncio.run_coroutine_threadsafe(
            self._build(kwargs), self._thread.loop
        )
        self._async: AsyncDkDataClient = ctor_future.result()

    async def _build(self, kwargs: dict[str, Any]) -> AsyncDkDataClient:
        return AsyncDkDataClient(**kwargs)

    @property
    def molecules(self) -> _SyncModule:
        return _SyncModule(self._async.molecules, self._thread.loop)

    @property
    def companies(self) -> _SyncModule:
        return _SyncModule(self._async.companies, self._thread.loop)

    @property
    def conditions(self) -> _SyncModule:
        return _SyncModule(self._async.conditions, self._thread.loop)

    @property
    def publications(self) -> _SyncModule:
        return _SyncModule(self._async.publications, self._thread.loop)

    @property
    def patents(self) -> _SyncModule:
        return _SyncModule(self._async.patents, self._thread.loop)

    @property
    def providers(self) -> _SyncModule:
        return _SyncModule(self._async.providers, self._thread.loop)

    def health(self) -> Any:
        fut: Future[Any] = asyncio.run_coroutine_threadsafe(
            self._async.health(), self._thread.loop
        )
        return fut.result()

    def catalog(self) -> Any:
        fut: Future[Any] = asyncio.run_coroutine_threadsafe(
            self._async.catalog(), self._thread.loop
        )
        return fut.result()

    def server_info(self) -> Any:
        fut: Future[Any] = asyncio.run_coroutine_threadsafe(
            self._async.server_info(), self._thread.loop
        )
        return fut.result()

    def close(self) -> None:
        try:
            fut: Future[None] = asyncio.run_coroutine_threadsafe(
                self._async.aclose(), self._thread.loop
            )
            fut.result(timeout=2.0)
        finally:
            self._thread.stop()

    def __enter__(self) -> DkDataClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
