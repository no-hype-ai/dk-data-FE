"""Unit tests for the typed error hierarchy."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

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


class TestHierarchy:
    @pytest.mark.parametrize(
        "cls",
        [
            DkDataAuthError,
            DkDataForbiddenError,
            DkDataNotFoundError,
            DkDataUpstreamError,
            DkDataRateLimitError,
            DkDataServerError,
            DkDataStaleError,
        ],
    )
    def test_every_class_inherits_from_base(self, cls):
        assert issubclass(cls, DkDataError)
        assert issubclass(cls, Exception)

    def test_base_is_exception(self):
        assert issubclass(DkDataError, Exception)


class TestRichErrors:
    def test_stale_error_carries_timestamp(self):
        ts = datetime(2026, 4, 13, tzinfo=timezone.utc)
        err = DkDataStaleError("gold stale", last_refreshed_at=ts)
        assert err.last_refreshed_at == ts
        assert str(err) == "gold stale"

    def test_upstream_error_carries_source_name(self):
        err = DkDataUpstreamError("pubchem down", upstream="pubchem")
        assert err.upstream == "pubchem"

    def test_rate_limit_error_carries_retry_after(self):
        err = DkDataRateLimitError("slow down", retry_after=12.5)
        assert err.retry_after == 12.5

    def test_server_error_carries_status_code(self):
        err = DkDataServerError("boom", status_code=503)
        assert err.status_code == 503

    def test_details_default_to_empty_dict(self):
        err = DkDataError("no details")
        assert err.details == {}

    def test_details_passthrough(self):
        err = DkDataNotFoundError("nope", details={"query": "X"})
        assert err.details["query"] == "X"


class TestCatchability:
    def test_catch_base_catches_all(self):
        for cls_args in [
            (DkDataAuthError("x"),),
            (DkDataForbiddenError("x"),),
            (DkDataNotFoundError("x"),),
            (DkDataServerError("x", status_code=500),),
            (DkDataRateLimitError("x", retry_after=1.0),),
            (DkDataUpstreamError("x", upstream="y"),),
            (
                DkDataStaleError(
                    "x", last_refreshed_at=datetime.now(timezone.utc)
                ),
            ),
        ]:
            with pytest.raises(DkDataError):
                raise cls_args[0]
