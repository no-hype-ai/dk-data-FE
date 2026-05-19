"""Tests for EMA Labels adapter — Task 1.5 (H2/H3: cache integrity).

TDD: RED first (no _is_valid_extraction, H3 raises, no TTL), then GREEN.
No pytest-asyncio: coroutines driven with asyncio.run() in plain sync tests.
No respx: DB is faked with hand-rolled async context manager helpers.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# Fake asyncpg pool helpers (matching test_adapter_ema.py style)
# ---------------------------------------------------------------------------


class _FakeRow(dict):
    """dict subclass so row['col'] works like asyncpg Records."""
    pass


class _FakeConn:
    """Minimal fake asyncpg connection for _check_cache (fetch) usage."""

    def __init__(self, rows):
        self._rows = rows
        self.execute_calls = []  # records (query, *args) tuples

    async def fetch(self, query, *args):
        return self._rows

    async def fetchrow(self, query, *args):
        return self._rows[0] if self._rows else None

    async def execute(self, query, *args):
        self.execute_calls.append((query,) + args)


class _FakePool:
    """Minimal fake asyncpg pool whose .acquire() is an async context manager."""

    def __init__(self, rows):
        self._conn = _FakeConn(rows)

    @property
    def conn(self):
        return self._conn

    def acquire(self):
        return self

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc_info):
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_good_row(
    medicine_name="Testivir",
    active_substance="testamine",
    smpc_pdf_url="https://example.com/test.pdf",
    extracted_text=None,
    ingested_at=None,
):
    """Return a _FakeRow for ema_label_cache with valid, fresh data."""
    if extracted_text is None:
        extracted_text = json.dumps({"page_count": 3, "full_text": "some real text", "pages": ["p1", "p2", "p3"]})
    if ingested_at is None:
        ingested_at = datetime.now(timezone.utc) - timedelta(hours=1)
    return _FakeRow({
        "medicine_name": medicine_name,
        "active_substance": active_substance,
        "smpc_pdf_url": smpc_pdf_url,
        "extracted_text": extracted_text,
        "ingested_at": ingested_at,
    })


# ---------------------------------------------------------------------------
# Tests: _derive_smpc_url — pure function
# ---------------------------------------------------------------------------

class TestDeriveSmpcUrlValid:
    """Valid EMA URLs with /EPAR/<slug> → correct PDF URL."""

    @pytest.mark.parametrize("medicine_url,expected_slug", [
        (
            "https://www.ema.europa.eu/en/medicines/human/EPAR/keytruda",
            "keytruda",
        ),
        (
            "https://www.ema.europa.eu/en/medicines/human/EPAR/some-long-slug-name",
            "some-long-slug-name",
        ),
        (
            "https://www.ema.europa.eu/EPAR/UPPERCASE-SLUG",
            "uppercase-slug",
        ),
    ])
    def test_derive_smpc_url_valid(self, medicine_url, expected_slug):
        from dk_data.services.mcp.adapters.ema_labels import _derive_smpc_url

        result = _derive_smpc_url(medicine_url)
        assert result is not None
        assert result == (
            f"https://www.ema.europa.eu/en/documents/product-information/"
            f"{expected_slug}-epar-product-information_en.pdf"
        )


class TestDeriveSmpcUrlInvalid:
    """URLs without a /EPAR/<slug> tail → None."""

    @pytest.mark.parametrize("bad_url", [
        "",
        "https://www.ema.europa.eu/en/medicines/human/",
        "https://unrelated.example.com/page",
        "https://www.ema.europa.eu/EPAR/",  # trailing slash, no slug
    ])
    def test_derive_smpc_url_invalid(self, bad_url):
        from dk_data.services.mcp.adapters.ema_labels import _derive_smpc_url

        assert _derive_smpc_url(bad_url) is None


# ---------------------------------------------------------------------------
# Tests: _is_valid_extraction — truth table
# ---------------------------------------------------------------------------

class TestIsValidExtraction:
    """_is_valid_extraction truth table."""

    @pytest.mark.parametrize("extracted,expected", [
        # valid
        ({"page_count": 3, "full_text": "some text"}, True),
        ({"page_count": 1, "full_text": "x", "pages": ["x"]}, True),
        # zero page_count
        ({"page_count": 0, "full_text": ""}, False),
        # whitespace-only full_text
        ({"page_count": 2, "full_text": "   "}, False),
        # empty full_text
        ({"page_count": 1, "full_text": ""}, False),
        # None / wrong types
        (None, False),
        ([], False),
        ("str", False),
        ({}, False),
        ({"page_count": 3}, False),   # missing full_text key → falsy
    ])
    def test_is_valid_extraction(self, extracted, expected):
        from dk_data.services.mcp.adapters.ema_labels import _is_valid_extraction

        assert _is_valid_extraction(extracted) == expected


# ---------------------------------------------------------------------------
# Tests: H2 — _save_cache refuses garbage (no INSERT)
# ---------------------------------------------------------------------------

class TestSaveCacheRefusesGarbage:
    """H2: _save_cache must NOT call execute() for empty/garbage extraction."""

    def test_save_cache_refuses_garbage(self):
        from dk_data.services.mcp.adapters.ema_labels import Adapter

        adapter = Adapter()
        fake_pool = _FakePool([])

        # Garbage extraction: page_count=0, full_text=""
        asyncio.run(adapter._save_cache(
            medicine_name="X",
            active_substance=None,
            smpc_url="https://example.com/x.pdf",
            extracted={"page_count": 0, "full_text": ""},
            db_pool=fake_pool,
        ))

        # execute must NOT have been called
        assert fake_pool.conn.execute_calls == [], (
            "INSERT must not be executed for garbage extraction"
        )

    def test_save_cache_allows_valid(self):
        """Positive control: valid extraction → execute IS called once."""
        from dk_data.services.mcp.adapters.ema_labels import Adapter

        adapter = Adapter()
        fake_pool = _FakePool([])

        asyncio.run(adapter._save_cache(
            medicine_name="Testivir",
            active_substance="testamine",
            smpc_url="https://example.com/test.pdf",
            extracted={"page_count": 3, "full_text": "real content here", "pages": []},
            db_pool=fake_pool,
        ))

        assert len(fake_pool.conn.execute_calls) == 1, (
            "INSERT must be executed for valid extraction"
        )


# ---------------------------------------------------------------------------
# Tests: H2 — db_query end-to-end: garbage not returned or cached
# ---------------------------------------------------------------------------

class TestDbQueryDoesNotReturnOrCacheGarbage:
    """H2 end-to-end: garbage extraction → return None, _save_cache not called."""

    def test_db_query_garbage_not_returned_or_cached(self, monkeypatch):
        from dk_data.services.mcp.adapters.ema_labels import Adapter

        adapter = Adapter()
        fake_pool = _FakePool([])

        # Stub _check_cache → miss (receives self, drug, pool)
        async def _no_cache(_self, _drug, _pool):
            return None

        # Stub _get_ema_record → valid record
        async def _good_record(_self, _drug, _pool):
            return {
                "medicine_url": "https://www.ema.europa.eu/EPAR/foo",
                "medicine_name": "Foo",
                "active_substance": "foo",
            }

        # Stub _download_and_extract → garbage (page_count=0)
        async def _garbage_extract(_self, _url):
            return {"page_count": 0, "full_text": "", "pages": []}

        # _save_cache must NOT be called
        async def _must_not_cache(_self, **kwargs):
            raise AssertionError("must not cache garbage")

        monkeypatch.setattr(Adapter, "_check_cache", _no_cache)
        monkeypatch.setattr(Adapter, "_get_ema_record", _good_record)
        monkeypatch.setattr(Adapter, "_download_and_extract", _garbage_extract)
        monkeypatch.setattr(Adapter, "_save_cache", _must_not_cache)

        result = asyncio.run(adapter.db_query("foo", fake_pool))

        assert result is None, "db_query must return None for garbage extraction"


# ---------------------------------------------------------------------------
# Tests: H3 — corrupt cached rows skipped+logged, no 500
# ---------------------------------------------------------------------------

class TestCheckCacheSkipsCorruptJson:
    """H3: corrupt extracted_text rows are skipped, not an exception."""

    def _make_rows(self):
        now = datetime.now(timezone.utc) - timedelta(hours=1)
        row_a = _FakeRow({
            "medicine_name": "GoodDrug",
            "active_substance": "goodstuff",
            "smpc_pdf_url": "https://example.com/good.pdf",
            "extracted_text": '{"page_count": 2, "full_text": "text here"}',
            "ingested_at": now,
        })
        row_b = _FakeRow({
            "medicine_name": "BadJsonDrug",
            "active_substance": "badjson",
            "smpc_pdf_url": "https://example.com/badjson.pdf",
            "extracted_text": '{not json',  # json.loads raises
            "ingested_at": now,
        })
        row_c = _FakeRow({
            "medicine_name": "ListDrug",
            "active_substance": "listsubstance",
            "smpc_pdf_url": "https://example.com/list.pdf",
            "extracted_text": '[1, 2]',  # decodes to list, not dict
            "ingested_at": now,
        })
        return [row_a, row_b, row_c]

    def test_check_cache_skips_corrupt_returns_valid_only(self):
        """Only row A (valid JSON dict) is returned; no exception raised."""
        from dk_data.services.mcp.adapters.ema_labels import Adapter

        adapter = Adapter()
        rows = self._make_rows()
        fake_pool = _FakePool(rows)

        result = asyncio.run(adapter._check_cache("gooddrug", fake_pool))

        assert result is not None, "Should return the valid row"
        assert len(result) == 1, f"Expected 1 valid row, got {len(result)}"
        assert result[0]["medicine_name"] == "GoodDrug"
        assert result[0]["page_count"] == 2

    def test_check_cache_all_corrupt_returns_none(self):
        """When all rows are corrupt → returns None (cache miss)."""
        from dk_data.services.mcp.adapters.ema_labels import Adapter

        adapter = Adapter()
        now = datetime.now(timezone.utc) - timedelta(hours=1)
        bad_rows = [
            _FakeRow({
                "medicine_name": "BadJsonDrug",
                "active_substance": "badjson",
                "smpc_pdf_url": "https://example.com/bad1.pdf",
                "extracted_text": '{not json',
                "ingested_at": now,
            }),
            _FakeRow({
                "medicine_name": "ListDrug",
                "active_substance": "list",
                "smpc_pdf_url": "https://example.com/bad2.pdf",
                "extracted_text": '[1, 2]',
                "ingested_at": now,
            }),
        ]
        fake_pool = _FakePool(bad_rows)

        result = asyncio.run(adapter._check_cache("baddrug", fake_pool))

        assert result is None, "All-corrupt result must be treated as cache miss (None)"


# ---------------------------------------------------------------------------
# Tests: TTL — stale cached rows ignored → re-extract path
# ---------------------------------------------------------------------------

class TestCheckCacheTtlStaleIgnored:
    """Stale rows (age > 30d) are skipped; fresh rows are returned."""

    def _make_row(self, ingested_at, url="https://example.com/stale.pdf"):
        return _FakeRow({
            "medicine_name": "StaleDrug",
            "active_substance": "stalesubstance",
            "smpc_pdf_url": url,
            "extracted_text": json.dumps({"page_count": 1, "full_text": "some text"}),
            "ingested_at": ingested_at,
        })

    def test_stale_row_returns_none(self):
        """Row with ingested_at 31 days ago → stale → returns None."""
        from dk_data.services.mcp.adapters.ema_labels import Adapter

        adapter = Adapter()
        stale_ingested_at = datetime.now(timezone.utc) - timedelta(days=31)
        fake_pool = _FakePool([self._make_row(stale_ingested_at)])

        result = asyncio.run(adapter._check_cache("StaleDrug", fake_pool))

        assert result is None, "Stale row (31d) must be treated as cache miss"

    def test_fresh_row_is_returned(self):
        """Row with ingested_at 1 day ago → fresh → row IS returned."""
        from dk_data.services.mcp.adapters.ema_labels import Adapter

        adapter = Adapter()
        fresh_ingested_at = datetime.now(timezone.utc) - timedelta(days=1)
        fake_pool = _FakePool([self._make_row(fresh_ingested_at)])

        result = asyncio.run(adapter._check_cache("StaleDrug", fake_pool))

        assert result is not None, "Fresh row (1d) must be returned"
        assert len(result) == 1

    def test_naive_datetime_treated_as_utc(self):
        """ingested_at with tzinfo=None (naive) is treated as UTC → fresh row returned."""
        from dk_data.services.mcp.adapters.ema_labels import Adapter

        adapter = Adapter()
        # Recent but naive datetime (no tzinfo)
        naive_recent = datetime.now() - timedelta(hours=2)
        assert naive_recent.tzinfo is None, "Precondition: must be naive"
        fake_pool = _FakePool([self._make_row(naive_recent)])

        result = asyncio.run(adapter._check_cache("StaleDrug", fake_pool))

        assert result is not None, "Naive-but-recent ingested_at must be treated as UTC and returned"
        assert len(result) == 1

    def test_ingested_at_none_row_still_appended(self):
        """When ingested_at is None (unexpected), staleness check is skipped and row is returned."""
        from dk_data.services.mcp.adapters.ema_labels import Adapter

        adapter = Adapter()
        row = self._make_row(None)  # ingested_at=None
        fake_pool = _FakePool([row])

        result = asyncio.run(adapter._check_cache("StaleDrug", fake_pool))

        # ingested_at=None → skip TTL check → row is returned (no crash)
        assert result is not None, "Row with ingested_at=None should not crash and should be returned"
