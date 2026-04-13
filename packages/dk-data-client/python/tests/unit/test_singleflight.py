"""Tests for the single-flight coalescing primitive."""

from __future__ import annotations

import asyncio

import pytest

from dk_data_client.singleflight import SingleFlight


class TestSingleFlight:
    @pytest.mark.asyncio
    async def test_first_call_runs_fn_and_returns_result(self):
        sf = SingleFlight()
        called = 0

        async def fn() -> str:
            nonlocal called
            called += 1
            return "v1"

        result = await sf.do("k", fn)
        assert result == "v1"
        assert called == 1

    @pytest.mark.asyncio
    async def test_concurrent_calls_coalesce_into_one_invocation(self):
        """Ten concurrent callers with the same key → fn() runs exactly once."""
        sf = SingleFlight()
        invocations = 0
        gate = asyncio.Event()

        async def fn() -> str:
            nonlocal invocations
            invocations += 1
            await gate.wait()
            return "shared-result"

        tasks = [asyncio.create_task(sf.do("k", fn)) for _ in range(10)]
        # Let all tasks arrive at the single-flight before releasing fn.
        await asyncio.sleep(0.01)
        gate.set()
        results = await asyncio.gather(*tasks)
        assert invocations == 1
        assert all(r == "shared-result" for r in results)

    @pytest.mark.asyncio
    async def test_different_keys_do_not_coalesce(self):
        sf = SingleFlight()
        invocations = 0

        async def fn() -> str:
            nonlocal invocations
            invocations += 1
            return "x"

        await asyncio.gather(
            sf.do("k1", fn),
            sf.do("k2", fn),
            sf.do("k3", fn),
        )
        assert invocations == 3

    @pytest.mark.asyncio
    async def test_exception_propagates_to_all_waiters(self):
        sf = SingleFlight()
        invocations = 0
        gate = asyncio.Event()

        class MyError(Exception):
            pass

        async def fn() -> str:
            nonlocal invocations
            invocations += 1
            await gate.wait()
            raise MyError("boom")

        tasks = [
            asyncio.create_task(sf.do("k", fn))
            for _ in range(5)
        ]
        await asyncio.sleep(0.01)
        gate.set()
        # All 5 callers should see MyError
        for task in tasks:
            with pytest.raises(MyError):
                await task
        # fn was invoked exactly once despite 5 callers
        assert invocations == 1

    @pytest.mark.asyncio
    async def test_cleanup_after_completion_allows_new_call(self):
        sf = SingleFlight()
        invocations = 0

        async def fn() -> str:
            nonlocal invocations
            invocations += 1
            return "v"

        await sf.do("k", fn)
        await sf.do("k", fn)
        await sf.do("k", fn)
        # Three sequential calls (not concurrent) → three invocations
        assert invocations == 3
        assert sf.active_count() == 0

    @pytest.mark.asyncio
    async def test_active_count_reflects_in_flight(self):
        sf = SingleFlight()
        gate = asyncio.Event()

        async def fn() -> str:
            await gate.wait()
            return "v"

        task = asyncio.create_task(sf.do("k", fn))
        await asyncio.sleep(0.01)
        assert sf.active_count() == 1
        gate.set()
        await task
        assert sf.active_count() == 0
