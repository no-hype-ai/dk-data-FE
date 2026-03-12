"""Local data checker — queries gold/silver/raw tables before external fetch.

Implements the local-first lookup strategy:
1. Check gold table (fully aggregated, highest quality)
2. Check silver table (enriched, deduplicated)
3. Return None if no local data found → caller triggers external fetch
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger


# Strict identifier pattern: only lowercase letters, digits, underscores
_SAFE_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _quote_ident(name: str) -> str:
    """Validate and double-quote a SQL identifier to prevent injection.

    Only allows simple postgres identifiers (lowercase, digits, underscores).
    Raises ValueError for anything else.
    """
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return f'"{name}"'


@dataclass
class LocalCheckConfig:
    """Configuration for local data lookup."""
    gold_schema: str          # e.g., "gold"
    gold_table: str           # e.g., "cms_provider_360"
    gold_key_column: str      # e.g., "npi"
    silver_schema: Optional[str] = None   # e.g., "silver"
    silver_table: Optional[str] = None    # e.g., "cms_pecos_providers"
    silver_key_column: Optional[str] = None
    raw_schema: Optional[str] = None      # e.g., "raw"
    raw_table: Optional[str] = None
    raw_key_column: Optional[str] = None


@dataclass
class LocalCheckResult:
    """Result from local data lookup."""
    found: bool
    data_origin: str          # "gold", "silver", "raw", or "none"
    data: List[Dict[str, Any]]
    record_count: int
    checked_at: str
    freshness_hours: Optional[float] = None  # hours since last update


class LocalDataChecker:
    """Checks local gold/silver/raw tables for existing data."""

    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def check(
        self,
        config: LocalCheckConfig,
        query_key: str,
        query_value: str,
        limit: int = 100,
    ) -> LocalCheckResult:
        """Check local tables for existing data matching the query.

        Args:
            config: Table/column configuration for this source.
            query_key: The query parameter name (must match a key_column).
            query_value: The value to search for.
            limit: Max rows to return.

        Returns:
            LocalCheckResult with data if found, or empty result.
        """
        if self.db_pool is None:
            return self._empty_result()

        # 1. Check gold table
        result = await self._query_table(
            config.gold_schema, config.gold_table,
            config.gold_key_column, query_value, limit,
        )
        if result:
            return LocalCheckResult(
                found=True,
                data_origin="gold",
                data=result,
                record_count=len(result),
                checked_at=datetime.now(timezone.utc).isoformat(),
            )

        # 2. Check silver table
        if config.silver_schema and config.silver_table and config.silver_key_column:
            result = await self._query_table(
                config.silver_schema, config.silver_table,
                config.silver_key_column, query_value, limit,
            )
            if result:
                return LocalCheckResult(
                    found=True,
                    data_origin="silver",
                    data=result,
                    record_count=len(result),
                    checked_at=datetime.now(timezone.utc).isoformat(),
                )

        # 3. Check raw table
        if config.raw_schema and config.raw_table and config.raw_key_column:
            result = await self._query_raw_table(
                config.raw_schema, config.raw_table,
                config.raw_key_column, query_value, limit,
            )
            if result:
                return LocalCheckResult(
                    found=True,
                    data_origin="raw",
                    data=result,
                    record_count=len(result),
                    checked_at=datetime.now(timezone.utc).isoformat(),
                )

        return self._empty_result()

    async def get_freshness(
        self,
        schema: str,
        table: str,
    ) -> Optional[Dict[str, Any]]:
        """Get freshness metadata for a table.

        Returns:
            Dict with last_updated, row_count, or None if table doesn't exist.
        """
        if self.db_pool is None:
            return None

        try:
            async with self.db_pool.acquire() as conn:
                # Check if table exists
                exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = $1 AND table_name = $2
                    )
                """, schema, table)

                if not exists:
                    return None

                s, t = _quote_ident(schema), _quote_ident(table)

                # Detect which timestamp column exists in this table/view.
                # Gold views from 092 use last_refreshed; silver tables use
                # profile_built_at; raw tables use _loaded_at or ingested_at.
                ts_col = await conn.fetchval("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = $1 AND table_name = $2
                      AND column_name IN (
                          'last_refreshed', 'profile_built_at', 'gold_built_at',
                          'updated_at', 'ingested_at', '_loaded_at', 'created_at'
                      )
                    ORDER BY CASE column_name
                        WHEN 'last_refreshed' THEN 1
                        WHEN 'gold_built_at' THEN 2
                        WHEN 'profile_built_at' THEN 3
                        WHEN 'updated_at' THEN 4
                        WHEN '_loaded_at' THEN 5
                        WHEN 'ingested_at' THEN 6
                        WHEN 'created_at' THEN 7
                    END
                    LIMIT 1
                """, schema, table)

                if ts_col:
                    tc = _quote_ident(ts_col)
                    row = await conn.fetchrow(f"""
                        SELECT COUNT(*) as row_count, MAX({tc}) as last_updated
                        FROM {s}.{t}
                    """)
                else:
                    row = await conn.fetchrow(f"""
                        SELECT COUNT(*) as row_count, NULL::timestamptz as last_updated
                        FROM {s}.{t}
                    """)

                if row:
                    last_updated = row["last_updated"]
                    freshness_hours = None
                    if last_updated:
                        delta = datetime.now(timezone.utc) - last_updated.replace(tzinfo=timezone.utc)
                        freshness_hours = delta.total_seconds() / 3600

                    return {
                        "schema": schema,
                        "table": table,
                        "row_count": row["row_count"],
                        "last_updated": last_updated.isoformat() if last_updated else None,
                        "freshness_hours": round(freshness_hours, 2) if freshness_hours else None,
                    }
        except Exception as e:
            logger.debug(f"Freshness check failed for {schema}.{table}: {e}")
            return None

    async def _query_table(
        self,
        schema: str,
        table: str,
        key_column: str,
        value: str,
        limit: int,
    ) -> Optional[List[Dict[str, Any]]]:
        """Query a structured table (gold/silver) by key column."""
        try:
            s, t, col = _quote_ident(schema), _quote_ident(table), _quote_ident(key_column)

            async with self.db_pool.acquire() as conn:
                # Verify table exists before querying
                exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = $1 AND table_name = $2
                    )
                """, schema, table)

                if not exists:
                    logger.debug(f"Table {schema}.{table} does not exist")
                    return None

                rows = await conn.fetch(
                    f"SELECT * FROM {s}.{t} WHERE {col} = $1 LIMIT $2",
                    value, limit,
                )

                if rows:
                    return [dict(r) for r in rows]
                return None

        except Exception as e:
            logger.debug(f"Local check failed for {schema}.{table}: {e}")
            return None

    async def _query_raw_table(
        self,
        schema: str,
        table: str,
        key_column: str,
        value: str,
        limit: int,
    ) -> Optional[List[Dict[str, Any]]]:
        """Query a raw table — searches request_params JSONB for the key."""
        try:
            s, t = _quote_ident(schema), _quote_ident(table)
            # key_column is used as a JSONB text key (not a SQL identifier),
            # so we validate it but pass as a parameter to the ->> operator.
            if not _SAFE_IDENT.match(key_column):
                raise ValueError(f"Unsafe JSONB key: {key_column!r}")

            async with self.db_pool.acquire() as conn:
                exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = $1 AND table_name = $2
                    )
                """, schema, table)

                if not exists:
                    return None

                rows = await conn.fetch(f"""
                    SELECT response_body, request_params, ingested_at
                    FROM {s}.{t}
                    WHERE request_params->>$1 = $2
                    ORDER BY ingested_at DESC
                    LIMIT $3
                """, key_column, value, limit)

                if rows:
                    return [dict(r) for r in rows]
                return None

        except Exception as e:
            logger.debug(f"Raw table check failed for {schema}.{table}: {e}")
            return None

    @staticmethod
    def _empty_result() -> LocalCheckResult:
        return LocalCheckResult(
            found=False,
            data_origin="none",
            data=[],
            record_count=0,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
