"""
Table Generator Service

Dynamically creates Bronze tables from detected schema.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from dataclasses import dataclass
import logging

from .schema_detector import SchemaDetector, TableSchema, ColumnSchema, PostgresType

logger = logging.getLogger(__name__)


@dataclass
class TableGenerationResult:
    """Result of table generation."""
    success: bool
    table_name: str
    schema_name: str
    columns_created: int
    sql_executed: str
    error: Optional[str] = None
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class DataSourceRegistration:
    """Registration info for a new data source."""
    id: UUID
    name: str
    api_type: str  # rest, graphql, file
    base_url: str
    auth_type: str  # none, api_key, oauth2, basic
    refresh_schedule: str  # cron expression
    table_name: str
    schema: TableSchema
    created_by: UUID
    created_at: datetime


class TableGenerator:
    """
    Service for dynamically generating Bronze tables.

    Features:
    - Create tables from detected schema
    - Register new data sources
    - Generate SQLMesh models
    - Manage table migrations
    """

    # Standard columns added to all Bronze tables
    STANDARD_COLUMNS = [
        ("id", "UUID PRIMARY KEY DEFAULT gen_random_uuid()"),
        ("raw_json", "JSONB"),
        ("raw_source_id", "UUID"),
        ("source", "TEXT NOT NULL"),
        ("source_updated_at", "TIMESTAMPTZ"),
        ("processed_to_silver", "BOOLEAN DEFAULT FALSE"),
        ("created_at", "TIMESTAMPTZ DEFAULT NOW()"),
    ]

    # Standard indexes
    STANDARD_INDEXES = [
        "source",
        "source_updated_at",
        "processed_to_silver",
        "created_at",
    ]

    def __init__(self, db_pool):
        """
        Initialize table generator.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool
        self.schema_detector = SchemaDetector()

    async def create_bronze_table(
        self,
        table_name: str,
        schema: TableSchema,
        schema_name: str = "bronze",
        if_not_exists: bool = True
    ) -> TableGenerationResult:
        """
        Create a Bronze layer table from detected schema.

        Args:
            table_name: Name for the table
            schema: Detected TableSchema
            schema_name: PostgreSQL schema (default: bronze)
            if_not_exists: Add IF NOT EXISTS clause

        Returns:
            TableGenerationResult with creation status
        """
        try:
            sql = self._generate_create_table_sql(
                table_name, schema, schema_name, if_not_exists
            )

            async with self.db_pool.acquire() as conn:
                await conn.execute(sql)

            logger.info(f"Created table {schema_name}.{table_name}")

            return TableGenerationResult(
                success=True,
                table_name=table_name,
                schema_name=schema_name,
                columns_created=len(schema.columns) + len(self.STANDARD_COLUMNS),
                sql_executed=sql,
            )

        except Exception as e:
            logger.error(f"Failed to create table {table_name}: {e}")
            return TableGenerationResult(
                success=False,
                table_name=table_name,
                schema_name=schema_name,
                columns_created=0,
                sql_executed="",
                error=str(e),
            )

    def _generate_create_table_sql(
        self,
        table_name: str,
        schema: TableSchema,
        schema_name: str,
        if_not_exists: bool
    ) -> str:
        """Generate CREATE TABLE SQL."""
        exists_clause = "IF NOT EXISTS " if if_not_exists else ""

        lines = [f"CREATE TABLE {exists_clause}{schema_name}.{table_name} ("]

        # Add standard ID column
        lines.append("    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),")

        # Add detected columns
        for column in schema.columns:
            null_clause = "" if column.nullable else " NOT NULL"
            lines.append(f"    {column.name} {column.postgres_type.value}{null_clause},")

        # Add standard metadata columns
        lines.append("    raw_json JSONB,")
        lines.append("    raw_source_id UUID,")
        lines.append("    source TEXT NOT NULL,")
        lines.append("    source_updated_at TIMESTAMPTZ,")
        lines.append("    processed_to_silver BOOLEAN DEFAULT FALSE,")
        lines.append("    created_at TIMESTAMPTZ DEFAULT NOW()")
        lines.append(");")

        # Add indexes for detected columns
        for idx_col in schema.indexes:
            lines.append(
                f"\nCREATE INDEX {exists_clause}idx_{table_name}_{idx_col} "
                f"ON {schema_name}.{table_name} ({idx_col});"
            )

        # Add standard indexes
        for idx_col in self.STANDARD_INDEXES:
            lines.append(
                f"\nCREATE INDEX {exists_clause}idx_{table_name}_{idx_col} "
                f"ON {schema_name}.{table_name} ({idx_col});"
            )

        # Add GIN index for raw_json
        lines.append(
            f"\nCREATE INDEX {exists_clause}idx_{table_name}_raw_json "
            f"ON {schema_name}.{table_name} USING GIN (raw_json);"
        )

        return "\n".join(lines)

    async def register_data_source(
        self,
        name: str,
        api_type: str,
        base_url: str,
        auth_type: str,
        refresh_schedule: str,
        sample_responses: List[Dict[str, Any]],
        created_by: UUID
    ) -> DataSourceRegistration:
        """
        Register a new data source with auto-schema detection.

        Args:
            name: Data source name
            api_type: Type of API (rest, graphql, file)
            base_url: Base URL for the API
            auth_type: Authentication type
            refresh_schedule: Cron schedule for refresh
            sample_responses: Sample JSON responses for schema detection
            created_by: User UUID who registered the source

        Returns:
            DataSourceRegistration with detected schema
        """
        # Sanitize table name
        table_name = self._sanitize_table_name(name)

        # Detect schema from samples
        schema = self.schema_detector.detect_schema(
            sample_responses,
            table_name,
            source_api=name
        )

        # Create the Bronze table
        result = await self.create_bronze_table(table_name, schema)

        if not result.success:
            raise RuntimeError(f"Failed to create table: {result.error}")

        # Save registration to database
        registration_id = uuid4()
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO platform.data_source_registrations (
                    id, name, api_type, base_url, auth_type,
                    refresh_schedule, table_name, schema_json,
                    created_by, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
            """,
                registration_id, name, api_type, base_url, auth_type,
                refresh_schedule, table_name, self._schema_to_json(schema),
                created_by
            )

        return DataSourceRegistration(
            id=registration_id,
            name=name,
            api_type=api_type,
            base_url=base_url,
            auth_type=auth_type,
            refresh_schedule=refresh_schedule,
            table_name=table_name,
            schema=schema,
            created_by=created_by,
            created_at=datetime.utcnow(),
        )

    def _sanitize_table_name(self, name: str) -> str:
        """Sanitize name for use as table name."""
        import re
        # Replace spaces and special chars with underscores
        sanitized = re.sub(r'[^a-zA-Z0-9]', '_', name.lower())
        # Remove consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')
        return sanitized or "unnamed_source"

    def _schema_to_json(self, schema: TableSchema) -> Dict[str, Any]:
        """Convert TableSchema to JSON-serializable dict."""
        return {
            "table_name": schema.table_name,
            "columns": [
                {
                    "name": c.name,
                    "type": c.postgres_type.value,
                    "nullable": c.nullable,
                    "is_array": c.is_array,
                    "json_path": c.json_path,
                }
                for c in schema.columns
            ],
            "primary_key": schema.primary_key,
            "unique_columns": schema.unique_columns,
            "indexes": schema.indexes,
            "source_api": schema.source_api,
            "detected_at": schema.detected_at.isoformat(),
        }

    async def generate_sqlmesh_model(
        self,
        table_name: str,
        raw_table: str,
        cron_schedule: str = "@daily"
    ) -> str:
        """
        Generate SQLMesh model for a registered data source.

        Args:
            table_name: Bronze table name
            raw_table: Raw table name
            cron_schedule: SQLMesh cron schedule

        Returns:
            SQLMesh model SQL
        """
        # Get schema from registration
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT schema_json FROM platform.data_source_registrations
                WHERE table_name = $1
            """, table_name)

        if not row:
            raise ValueError(f"No registration found for table: {table_name}")

        schema_dict = row['schema_json']
        schema = self._json_to_schema(schema_dict)

        return self.schema_detector.generate_sqlmesh_model(
            schema, raw_table, cron_schedule
        )

    def _json_to_schema(self, data: Dict[str, Any]) -> TableSchema:
        """Convert JSON dict back to TableSchema."""
        columns = [
            ColumnSchema(
                name=c["name"],
                postgres_type=PostgresType(c["type"]),
                nullable=c.get("nullable", True),
                is_array=c.get("is_array", False),
                json_path=c.get("json_path", ""),
            )
            for c in data.get("columns", [])
        ]

        return TableSchema(
            table_name=data["table_name"],
            columns=columns,
            primary_key=data.get("primary_key"),
            unique_columns=data.get("unique_columns", []),
            indexes=data.get("indexes", []),
            source_api=data.get("source_api", ""),
            detected_at=datetime.fromisoformat(data["detected_at"]) if "detected_at" in data else datetime.utcnow(),
        )

    async def list_registered_sources(self) -> List[Dict[str, Any]]:
        """List all registered data sources."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name, api_type, base_url, auth_type,
                       refresh_schedule, table_name, created_at
                FROM platform.data_source_registrations
                ORDER BY created_at DESC
            """)

        return [dict(r) for r in rows]

    async def get_table_info(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a Bronze table."""
        async with self.db_pool.acquire() as conn:
            # Get column info from PostgreSQL
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'bronze'
                AND table_name = $1
                ORDER BY ordinal_position
            """, table_name)

            if not columns:
                return None

            # Get row count
            count = await conn.fetchval(f"SELECT COUNT(*) FROM mol_bronze.{table_name}")

            # Get registration info
            reg = await conn.fetchrow("""
                SELECT * FROM platform.data_source_registrations
                WHERE table_name = $1
            """, table_name)

        return {
            "table_name": table_name,
            "columns": [dict(c) for c in columns],
            "row_count": count,
            "registration": dict(reg) if reg else None,
        }

    async def alter_table_add_column(
        self,
        table_name: str,
        column: ColumnSchema,
        schema_name: str = "bronze"
    ) -> bool:
        """
        Add a new column to an existing table.

        Args:
            table_name: Table to alter
            column: New column definition
            schema_name: PostgreSQL schema

        Returns:
            True if successful
        """
        try:
            null_clause = "" if column.nullable else " NOT NULL"
            sql = f"""
                ALTER TABLE {schema_name}.{table_name}
                ADD COLUMN IF NOT EXISTS {column.name} {column.postgres_type.value}{null_clause}
            """

            async with self.db_pool.acquire() as conn:
                await conn.execute(sql)

            logger.info(f"Added column {column.name} to {schema_name}.{table_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to add column: {e}")
            return False
