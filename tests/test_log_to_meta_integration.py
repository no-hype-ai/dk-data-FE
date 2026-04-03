"""Integration tests for meta logging against real PostgreSQL schema."""

from datetime import datetime

import pytest

from dk_data.ingestion.main import get_last_successful_refresh, log_to_meta
from dk_data.ingestion.utils import database as db_utils


pytestmark = pytest.mark.integration

TEST_SOURCE = "_test_source_ltm"


@pytest.fixture
def ingestion_connection_pool(monkeypatch):
    """Initialize the shared ingestion DB pool for tests."""
    monkeypatch.setattr(db_utils, "_check_required_secrets", lambda: None)
    db_utils.close_connection_pool()
    try:
        db_utils.init_connection_pool(minconn=1, maxconn=2)
        yield
    finally:
        db_utils.close_connection_pool()


def test_log_to_meta_success(postgres_connection, db_cursor, ingestion_connection_pool):
    """log_to_meta should write refresh_log and update source status."""
    db_cursor.execute(
        """
        INSERT INTO meta.data_sources
            (source_name, source_type, description, is_active, refresh_frequency)
        VALUES (%s, 'api', 'Integration test source', true, 'daily')
        ON CONFLICT (source_name) DO NOTHING
        """,
        (TEST_SOURCE,),
    )
    postgres_connection.commit()

    try:
        log_to_meta(
            TEST_SOURCE,
            {"status": "success", "records_fetched": 42, "records_inserted": 42},
        )

        db_cursor.execute(
            """
            SELECT rl.status, rl.records_fetched
            FROM meta.refresh_log rl
            JOIN meta.data_sources ds ON ds.source_id = rl.source_id
            WHERE ds.source_name = %s
            ORDER BY rl.log_id DESC
            LIMIT 1
            """,
            (TEST_SOURCE,),
        )
        row = db_cursor.fetchone()
        assert row is not None
        assert row[0] == "success"
        assert row[1] == 42

        db_cursor.execute(
            """
            SELECT last_refresh_status
            FROM meta.data_sources
            WHERE source_name = %s
            """,
            (TEST_SOURCE,),
        )
        source_row = db_cursor.fetchone()
        assert source_row is not None
        assert source_row[0] == "success"
    finally:
        db_cursor.execute(
            """
            DELETE FROM meta.refresh_log
            WHERE source_id = (
                SELECT source_id FROM meta.data_sources WHERE source_name = %s
            )
            """,
            (TEST_SOURCE,),
        )
        db_cursor.execute("DELETE FROM meta.data_sources WHERE source_name = %s", (TEST_SOURCE,))
        postgres_connection.commit()


def test_log_to_meta_missing_source(postgres_connection, db_cursor, ingestion_connection_pool):
    """log_to_meta should return safely when source does not exist."""
    missing_source = "_test_nonexistent_xyz"

    log_to_meta(missing_source, {"status": "success", "records_fetched": 0})

    db_cursor.execute(
        "SELECT COUNT(*) FROM meta.refresh_log WHERE source_name = %s",
        (missing_source,),
    )
    count = db_cursor.fetchone()[0]
    assert count == 0
    postgres_connection.rollback()


def test_log_to_meta_refresh_log_schema(db_cursor):
    """Document expected refresh_log schema contract."""
    db_cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'meta' AND table_name = 'refresh_log'
        """
    )
    columns = {row[0] for row in db_cursor.fetchall()}
    assert "source_id" in columns
    assert "source_name" in columns
    assert "status" in columns
    assert "records_fetched" in columns


def test_get_last_successful_refresh(postgres_connection, db_cursor, ingestion_connection_pool):
    """get_last_successful_refresh should return a datetime when present."""
    db_cursor.execute(
        """
        INSERT INTO meta.data_sources
            (source_name, source_type, description, is_active, refresh_frequency)
        VALUES (%s, 'api', 'Integration test source', true, 'daily')
        ON CONFLICT (source_name) DO NOTHING
        """,
        (TEST_SOURCE,),
    )
    db_cursor.execute(
        "SELECT source_id FROM meta.data_sources WHERE source_name = %s",
        (TEST_SOURCE,),
    )
    source_id = db_cursor.fetchone()[0]
    db_cursor.execute(
        """
        INSERT INTO meta.refresh_log (
            source_id, source_name, refresh_started_at, refresh_completed_at,
            status, records_fetched, records_inserted, records_updated
        ) VALUES (%s, %s, NOW(), NOW(), 'success', 1, 1, 0)
        """,
        (source_id, TEST_SOURCE),
    )
    db_cursor.execute(
        """
        UPDATE meta.data_sources
        SET last_successful_refresh = NOW(),
            last_refresh_status = 'success'
        WHERE source_id = %s
        """,
        (source_id,),
    )
    postgres_connection.commit()

    try:
        value = get_last_successful_refresh(TEST_SOURCE)
        assert value is not None
        assert isinstance(value, datetime)
    finally:
        db_cursor.execute(
            "DELETE FROM meta.refresh_log WHERE source_id = %s",
            (source_id,),
        )
        db_cursor.execute("DELETE FROM meta.data_sources WHERE source_id = %s", (source_id,))
        postgres_connection.commit()


def test_get_last_successful_refresh_missing_source(ingestion_connection_pool):
    """Missing source should return None."""
    assert get_last_successful_refresh("_nonexistent_xyz") is None
