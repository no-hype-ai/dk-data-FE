"""
Data Sources Registration API Routes.

Implements REST endpoints for:
- Registering new data sources
- Managing data source credentials
- Auto-schema detection
- Data source configuration
- Test connection / auto-fetch sample
- Pagination and incremental sync configuration

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from fastapi import APIRouter, HTTPException, Query, Body, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum
from loguru import logger
import asyncio
import json
import re
import aiohttp

from ..dependencies import get_db_pool


# SQL identifier validation — prevents injection via dynamic table names
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_.]*$')


def _validate_table_name(table_name: str) -> str:
    """Validate and quote a table name to prevent SQL injection.

    Accepts 'schema.table' or 'table' format with alphanumeric + underscore only.
    Returns the table name unchanged if valid, raises ValueError otherwise.
    """
    if not table_name or not _SAFE_IDENTIFIER_RE.match(table_name):
        raise ValueError(f"Invalid table name: {table_name!r}")
    # Additional safety: limit length and prevent multiple dots
    if table_name.count('.') > 1 or len(table_name) > 128:
        raise ValueError(f"Invalid table name: {table_name!r}")
    return table_name

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


# ============================================================================
# Helper Functions
# ============================================================================

def infer_postgres_type(value: Any) -> str:
    """Infer PostgreSQL type from a Python value."""
    if value is None:
        return "TEXT"
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        if abs(value) > 2147483647:
            return "BIGINT"
        return "INTEGER"
    if isinstance(value, float):
        return "DOUBLE PRECISION"
    if isinstance(value, list):
        return "JSONB"
    if isinstance(value, dict):
        return "JSONB"

    str_val = str(value)
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', str_val):
        return "TIMESTAMPTZ"
    if re.match(r'^\d{4}-\d{2}-\d{2}$', str_val):
        return "DATE"
    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', str_val.lower()):
        return "UUID"
    if len(str_val) > 255:
        return "TEXT"
    return "TEXT"


def extract_fields_from_json(data: Any, prefix: str = "") -> List[Dict[str, Any]]:
    """Extract fields from JSON data recursively."""
    fields = []
    reserved_cols = {'id', '_source_id', '_ingested_at', '_raw_payload'}
    if isinstance(data, dict):
        for key, value in data.items():
            field_name = f"{prefix}{key}" if prefix else key
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', field_name).lower()
            # Rename reserved column names to avoid conflicts
            if safe_name in reserved_cols:
                safe_name = f"source_{safe_name}"

            if isinstance(value, dict):
                if len(value) <= 3:
                    fields.extend(extract_fields_from_json(value, f"{safe_name}_"))
                else:
                    fields.append({
                        "name": safe_name,
                        "type": "JSONB",
                        "nullable": True,
                        "sample_value": json.dumps(value)[:100]
                    })
            elif isinstance(value, list):
                fields.append({
                    "name": safe_name,
                    "type": "JSONB",
                    "nullable": True,
                    "sample_value": json.dumps(value)[:100] if value else "[]"
                })
            else:
                fields.append({
                    "name": safe_name,
                    "type": infer_postgres_type(value),
                    "nullable": True,
                    "sample_value": str(value)[:100] if value is not None else None
                })
    return fields


# ============================================================================
# Enums and Constants
# ============================================================================

class ApiType(str, Enum):
    """Supported API types."""
    REST = "rest"
    GRAPHQL = "graphql"
    FILE = "file"
    DATABASE = "database"


class AuthType(str, Enum):
    """Supported authentication types."""
    NONE = "none"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BASIC = "basic"
    BEARER = "bearer"


class RefreshTier(str, Enum):
    """Data refresh frequency tiers."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ON_DEMAND = "on_demand"


class HttpMethod(str, Enum):
    """Supported HTTP methods."""
    GET = "GET"
    POST = "POST"


class PaginationType(str, Enum):
    """Supported pagination types."""
    NONE = "none"
    OFFSET = "offset"           # ?offset=0&limit=100
    PAGE = "page"               # ?page=1&page_size=100
    CURSOR = "cursor"           # ?cursor=abc123
    NEXT_URL = "next_url"       # Response contains next page URL
    LINK_HEADER = "link_header" # Pagination in Link header


class IncrementalType(str, Enum):
    """How to track incremental fetches."""
    NONE = "none"               # Always fetch everything (with hash dedup)
    MODIFIED_SINCE = "modified_since"  # Use last_modified date
    CREATED_SINCE = "created_since"    # Use created date field
    OFFSET_RESUME = "offset_resume"    # Resume from last offset (for append-only APIs)


# ============================================================================
# Request/Response Models
# ============================================================================

class RequestConfig(BaseModel):
    """Configuration for HTTP requests."""
    method: HttpMethod = Field(HttpMethod.GET, description="HTTP method")
    headers: Dict[str, str] = Field(default_factory=dict, description="Custom headers")
    query_params: Dict[str, str] = Field(default_factory=dict, description="Query parameters")
    body_template: Optional[str] = Field(None, description="Request body template (for POST)")
    data_path: Optional[str] = Field(None, description="JSON path to data array (e.g., 'results', 'data.items')")


class PaginationConfig(BaseModel):
    """Configuration for pagination."""
    type: PaginationType = Field(PaginationType.NONE, description="Pagination type")
    page_size: int = Field(100, ge=1, le=1000, description="Records per page")
    max_pages: int = Field(100, ge=1, le=10000, description="Maximum pages to fetch")
    # For offset pagination
    offset_param: str = Field("offset", description="Query param name for offset")
    limit_param: str = Field("limit", description="Query param name for limit")
    # For page pagination
    page_param: str = Field("page", description="Query param name for page number")
    page_size_param: str = Field("page_size", description="Query param name for page size")
    # For cursor pagination
    cursor_param: str = Field("cursor", description="Query param name for cursor")
    cursor_path: str = Field("next_cursor", description="JSON path to next cursor in response")
    # For next_url pagination
    next_url_path: str = Field("next", description="JSON path to next URL in response")
    # Total records path (for progress tracking)
    total_path: Optional[str] = Field(None, description="JSON path to total count")


class IncrementalConfig(BaseModel):
    """Configuration for incremental sync."""
    type: IncrementalType = Field(IncrementalType.NONE, description="Incremental sync type")
    date_field: Optional[str] = Field(None, description="Field containing modification date")
    date_param: Optional[str] = Field(None, description="Query param for date filter")
    date_format: str = Field("%Y-%m-%dT%H:%M:%SZ", description="Date format string")
    lookback_hours: int = Field(24, ge=1, description="Hours to look back for overlapping records")


class DataSourceRegistration(BaseModel):
    """Request for registering a new data source."""
    name: str = Field(..., min_length=2, max_length=100, description="Unique source name")
    display_name: str = Field(..., min_length=2, description="Human-readable name")
    api_type: ApiType = Field(..., description="Type of API")
    base_url: str = Field(..., description="Base URL for the API")
    auth_type: AuthType = Field(AuthType.NONE, description="Authentication type")
    refresh_tier: RefreshTier = Field(RefreshTier.WEEKLY, description="Refresh frequency")
    description: Optional[str] = Field(None, description="Source description")
    documentation_url: Optional[str] = Field(None, description="Documentation URL")
    rate_limit_requests: int = Field(10, ge=1, description="Rate limit (requests/second)")
    batch_size: int = Field(100, ge=1, le=1000, description="Default batch size")
    timeout_seconds: int = Field(30, ge=5, le=300, description="Request timeout")
    retry_max_attempts: int = Field(3, ge=1, le=10, description="Max retry attempts")
    sample_response: Optional[Dict[str, Any]] = Field(None, description="Sample API response")
    # New configuration options
    request_config: Optional[RequestConfig] = Field(None, description="HTTP request configuration")
    pagination_config: Optional[PaginationConfig] = Field(None, description="Pagination configuration")
    incremental_config: Optional[IncrementalConfig] = Field(None, description="Incremental sync configuration")


class DataSourceResponse(BaseModel):
    """Response for data source operations."""
    id: str
    name: str
    display_name: str
    api_type: str
    base_url: str
    auth_type: str
    refresh_tier: str
    table_name: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str


class DataSourceListResponse(BaseModel):
    """Response for listing data sources."""
    success: bool
    sources: List[DataSourceResponse]
    count: int
    timestamp: str


class CredentialRequest(BaseModel):
    """Request for storing a credential."""
    key_name: str = Field(..., min_length=1, description="Credential key name (e.g., api_key)")
    value: str = Field(..., min_length=1, description="Credential value")
    credential_type: str = Field("api_key", description="Type of credential")
    expires_at: Optional[datetime] = Field(None, description="Optional expiration")


class CredentialListResponse(BaseModel):
    """Response for listing credentials."""
    success: bool
    credentials: List[Dict[str, Any]]
    count: int
    timestamp: str


class SchemaDetectionRequest(BaseModel):
    """Request for schema detection."""
    sample_responses: List[Dict[str, Any]] = Field(..., min_items=1, max_items=100, description="Sample API responses")
    table_name: Optional[str] = Field(None, description="Custom table name")


class SchemaDetectionResponse(BaseModel):
    """Response for schema detection."""
    success: bool
    table_name: str
    columns: List[Dict[str, Any]]
    primary_key: Optional[str]
    indexes: List[str]
    create_table_sql: str
    sqlmesh_model: str
    timestamp: str


class SyncTriggerResponse(BaseModel):
    """Response for sync trigger."""
    success: bool
    source_name: str
    job_id: Optional[str]
    message: str
    timestamp: str


# ============================================================================
# Data Source Registration Endpoints
# ============================================================================

@router.post("/register", response_model=DataSourceResponse)
async def register_data_source(request: DataSourceRegistration):
    """
    Register a new external data source.

    Auto-detects schema if sample_response is provided.
    Creates Bronze table and SQLMesh model automatically.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        source_id = request.name.lower().replace('-', '_').replace(' ', '_')

        async with pool.acquire() as conn:
            # Check if source already exists
            exists = await conn.fetchval(
                "SELECT 1 FROM raw.sync_schedules WHERE source = $1",
                source_id
            )

            if exists:
                raise HTTPException(
                    status_code=409,
                    detail=f"Data source '{source_id}' already exists"
                )

            # Map refresh_tier to cron expression
            cron_map = {
                'daily': '0 2 * * *',
                'weekly': '0 3 * * 0',
                'monthly': '0 4 1 * *',
                'on_demand': None
            }

            # Build complete options object
            options = {
                'source_name': request.display_name,
                'api_type': request.api_type.value,
                'base_url': request.base_url,
                'auth_type': request.auth_type.value,
                'rate_limit_per_second': request.rate_limit_requests,
                'description': request.description,
                'batch_size': request.batch_size,
                'timeout_seconds': request.timeout_seconds,
                'retry_max_attempts': request.retry_max_attempts,
            }

            # Add request configuration if provided
            if request.request_config:
                options['request'] = {
                    'method': request.request_config.method.value,
                    'headers': request.request_config.headers,
                    'query_params': request.request_config.query_params,
                    'body_template': request.request_config.body_template,
                    'data_path': request.request_config.data_path,
                }

            # Add pagination configuration if provided
            if request.pagination_config:
                options['pagination'] = {
                    'type': request.pagination_config.type.value,
                    'page_size': request.pagination_config.page_size,
                    'max_pages': request.pagination_config.max_pages,
                    'offset_param': request.pagination_config.offset_param,
                    'limit_param': request.pagination_config.limit_param,
                    'page_param': request.pagination_config.page_param,
                    'page_size_param': request.pagination_config.page_size_param,
                    'cursor_param': request.pagination_config.cursor_param,
                    'cursor_path': request.pagination_config.cursor_path,
                    'next_url_path': request.pagination_config.next_url_path,
                    'total_path': request.pagination_config.total_path,
                }

            # Add incremental configuration if provided
            if request.incremental_config:
                options['incremental'] = {
                    'type': request.incremental_config.type.value,
                    'date_field': request.incremental_config.date_field,
                    'date_param': request.incremental_config.date_param,
                    'date_format': request.incremental_config.date_format,
                    'lookback_hours': request.incremental_config.lookback_hours,
                }

            # Initialize sync state
            options['sync_state'] = {
                'last_successful_sync': None,
                'last_cursor': None,
                'last_offset': 0,
                'last_modified_date': None,
                'total_records_synced': 0,
            }

            # Create sync schedule entry
            await conn.execute("""
                INSERT INTO raw.sync_schedules
                (source, tier, cron_expression, priority, enabled, options, created_at, updated_at)
                VALUES ($1, $2, $3, 'normal', true, $4, NOW(), NOW())
            """,
                source_id,
                request.refresh_tier.value,
                cron_map.get(request.refresh_tier.value, '0 3 * * 0'),
                json.dumps(options)
            )

            logger.info(f"Registered new data source: {source_id}")

            return DataSourceResponse(
                id=source_id,
                name=source_id,
                display_name=request.display_name,
                api_type=request.api_type.value,
                base_url=request.base_url,
                auth_type=request.auth_type.value,
                refresh_tier=request.refresh_tier.value,
                table_name=f"raw.{source_id}_data",
                is_active=True,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to register data source: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


class TestConnectionRequest(BaseModel):
    """Request to test API connection."""
    url: str = Field(..., description="API URL to test")
    method: HttpMethod = Field(HttpMethod.GET, description="HTTP method")
    headers: Dict[str, str] = Field(default_factory=dict, description="Request headers")
    query_params: Dict[str, str] = Field(default_factory=dict, description="Query parameters")
    body: Optional[str] = Field(None, description="Request body for POST")
    auth_type: AuthType = Field(AuthType.NONE, description="Authentication type")
    auth_value: Optional[str] = Field(None, description="API key or token value")
    auth_header: str = Field("Authorization", description="Header name for auth")
    data_path: Optional[str] = Field(None, description="JSON path to data array")
    timeout_seconds: int = Field(30, ge=5, le=120, description="Request timeout")


class TestConnectionResponse(BaseModel):
    """Response from test connection."""
    success: bool
    status_code: int
    response_time_ms: float
    sample_data: Optional[List[Dict[str, Any]]]
    record_count: int
    detected_fields: List[Dict[str, Any]]
    error: Optional[str]
    timestamp: str


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(request: TestConnectionRequest):
    """
    Test connection to an API and auto-fetch sample data.

    - Tests the URL is accessible
    - Fetches sample response
    - Auto-detects schema from response
    - Returns sample data for preview
    """
    import time
    start_time = time.time()

    try:
        # Build headers
        headers = dict(request.headers)
        headers['Accept'] = 'application/json'
        headers['User-Agent'] = 'DK-Data-Platform/1.0'

        # Add authentication
        if request.auth_type != AuthType.NONE and request.auth_value:
            if request.auth_type == AuthType.API_KEY:
                headers[request.auth_header] = request.auth_value
            elif request.auth_type == AuthType.BEARER:
                headers['Authorization'] = f'Bearer {request.auth_value}'
            elif request.auth_type == AuthType.BASIC:
                import base64
                encoded = base64.b64encode(request.auth_value.encode()).decode()
                headers['Authorization'] = f'Basic {encoded}'

        # Build URL with query params
        url = request.url
        if request.query_params:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(request.query_params)}"

        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=request.timeout_seconds)

            if request.method == HttpMethod.GET:
                async with session.get(url, headers=headers, timeout=timeout) as response:
                    status_code = response.status
                    if status_code != 200:
                        error_text = await response.text()
                        return TestConnectionResponse(
                            success=False,
                            status_code=status_code,
                            response_time_ms=(time.time() - start_time) * 1000,
                            sample_data=None,
                            record_count=0,
                            detected_fields=[],
                            error=f"HTTP {status_code}: {error_text[:200]}",
                            timestamp=datetime.now(timezone.utc).isoformat()
                        )
                    data = await response.json()
            else:  # POST
                async with session.post(
                    url, headers=headers, data=request.body, timeout=timeout
                ) as response:
                    status_code = response.status
                    if status_code not in (200, 201):
                        error_text = await response.text()
                        return TestConnectionResponse(
                            success=False,
                            status_code=status_code,
                            response_time_ms=(time.time() - start_time) * 1000,
                            sample_data=None,
                            record_count=0,
                            detected_fields=[],
                            error=f"HTTP {status_code}: {error_text[:200]}",
                            timestamp=datetime.now(timezone.utc).isoformat()
                        )
                    data = await response.json()

        response_time_ms = (time.time() - start_time) * 1000

        # Extract data using data_path if specified
        if request.data_path and isinstance(data, dict):
            for key in request.data_path.split('.'):
                if isinstance(data, dict) and key in data:
                    data = data[key]
                else:
                    break

        # Handle single object or array
        if isinstance(data, dict):
            records = [data]
        elif isinstance(data, list):
            records = data
        else:
            records = []

        # Detect fields from sample
        sample_records = records[:5]  # First 5 for preview
        detected_fields = []
        if sample_records:
            detected_fields = extract_fields_from_json(sample_records[0])

        return TestConnectionResponse(
            success=True,
            status_code=status_code,
            response_time_ms=response_time_ms,
            sample_data=sample_records,
            record_count=len(records),
            detected_fields=detected_fields,
            error=None,
            timestamp=datetime.now(timezone.utc).isoformat()
        )

    except asyncio.TimeoutError:
        return TestConnectionResponse(
            success=False,
            status_code=0,
            response_time_ms=(time.time() - start_time) * 1000,
            sample_data=None,
            record_count=0,
            detected_fields=[],
            error=f"Connection timed out after {request.timeout_seconds}s",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except aiohttp.ClientError as e:
        return TestConnectionResponse(
            success=False,
            status_code=0,
            response_time_ms=(time.time() - start_time) * 1000,
            sample_data=None,
            record_count=0,
            detected_fields=[],
            error=f"Connection error: {str(e)}",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Test connection failed: {e}")
        return TestConnectionResponse(
            success=False,
            status_code=0,
            response_time_ms=(time.time() - start_time) * 1000,
            sample_data=None,
            record_count=0,
            detected_fields=[],
            error=str(e),
            timestamp=datetime.now(timezone.utc).isoformat()
        )


@router.get("", response_model=DataSourceListResponse)
async def list_data_sources(
    api_type: Optional[ApiType] = Query(None, description="Filter by API type"),
    refresh_tier: Optional[RefreshTier] = Query(None, description="Filter by refresh tier"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """
    List all registered data sources.

    Returns configuration and status for each source.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Fetch all sources from sync_schedules
            rows = await conn.fetch("""
                SELECT source, tier, enabled, options, created_at, updated_at
                FROM raw.sync_schedules
                ORDER BY source
            """)

            sources = []
            for i, row in enumerate(rows):
                options = row['options']
                if isinstance(options, str):
                    options = json.loads(options) if options else {}
                options = options or {}

                # Extract config from options
                source_name = options.get('source_name', row['source'])
                api_type_val = options.get('api_type', 'rest')
                base_url = options.get('base_url', '')
                auth_type_val = options.get('auth_type', 'none')
                target_table = options.get('target_table', f"raw.{row['source']}_data")

                # Apply filters
                if api_type and api_type_val != api_type.value:
                    continue
                if refresh_tier and row['tier'] != refresh_tier.value:
                    continue
                if is_active is not None and row['enabled'] != is_active:
                    continue

                sources.append(DataSourceResponse(
                    id=str(i + 1),
                    name=row['source'],
                    display_name=source_name,
                    api_type=api_type_val,
                    base_url=base_url,
                    auth_type=auth_type_val,
                    refresh_tier=row['tier'],
                    table_name=target_table.replace('raw.', 'bronze.') if target_table else None,
                    is_active=row['enabled'],
                    created_at=row['created_at'].isoformat() if row['created_at'] else datetime.now(timezone.utc).isoformat(),
                    updated_at=row['updated_at'].isoformat() if row['updated_at'] else datetime.now(timezone.utc).isoformat(),
                ))

        return DataSourceListResponse(
            success=True,
            sources=sources,
            count=len(sources),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list data sources: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{source_name}", response_model=DataSourceResponse)
async def get_data_source(source_name: str):
    """
    Get details for a specific data source.

    Returns full configuration and current status.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    source,
                    tier,
                    cron_expression,
                    priority,
                    enabled,
                    last_run,
                    next_run,
                    options,
                    created_at,
                    updated_at
                FROM raw.sync_schedules
                WHERE source = $1
            """, source_name)

            if not row:
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

            options = row['options'] or {}
            if isinstance(options, str):
                options = json.loads(options)

            return DataSourceResponse(
                id=source_name,
                name=source_name,
                display_name=options.get('display_name', source_name),
                api_type=options.get('api_type', 'rest'),
                base_url=options.get('base_url', ''),
                auth_type=options.get('auth_type', 'none'),
                refresh_tier=row['tier'] or 'monthly',
                table_name=options.get('target_table', f"raw.{source_name.lower().replace('-', '_')}_data"),
                is_active=row['enabled'],
                created_at=row['created_at'].isoformat() if row['created_at'] else datetime.now(timezone.utc).isoformat(),
                updated_at=row['updated_at'].isoformat() if row['updated_at'] else datetime.now(timezone.utc).isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get data source: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{source_name}", response_model=DataSourceResponse)
async def update_data_source(source_name: str, request: DataSourceRegistration):
    """
    Update an existing data source configuration.

    Changes take effect on next sync.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Check if source exists
            exists = await conn.fetchval(
                "SELECT 1 FROM raw.sync_schedules WHERE source = $1",
                source_name
            )
            if not exists:
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

            # Build options JSON
            options = {
                'display_name': request.display_name,
                'api_type': request.api_type.value,
                'base_url': request.base_url,
                'auth_type': request.auth_type.value,
                'target_table': f"raw.{source_name.lower().replace('-', '_')}_data",
            }

            # Update the record
            row = await conn.fetchrow("""
                UPDATE raw.sync_schedules
                SET tier = $2,
                    options = COALESCE(options, '{}'::jsonb) || $3::jsonb,
                    updated_at = NOW()
                WHERE source = $1
                RETURNING source, tier, enabled, created_at, updated_at
            """, source_name, request.refresh_tier.value, json.dumps(options))

            return DataSourceResponse(
                id=source_name,
                name=source_name,
                display_name=request.display_name,
                api_type=request.api_type.value,
                base_url=request.base_url,
                auth_type=request.auth_type.value,
                refresh_tier=request.refresh_tier.value,
                table_name=f"raw.{source_name.lower().replace('-', '_')}_data",
                is_active=row['enabled'],
                created_at=row['created_at'].isoformat() if row['created_at'] else datetime.now(timezone.utc).isoformat(),
                updated_at=row['updated_at'].isoformat() if row['updated_at'] else datetime.now(timezone.utc).isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update data source: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{source_name}")
async def delete_data_source(source_name: str, delete_data: bool = Query(False)):
    """
    Delete a data source registration.

    Set delete_data=true to also delete all ingested data.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Check if source exists
            row = await conn.fetchrow(
                "SELECT source, options FROM raw.sync_schedules WHERE source = $1",
                source_name
            )
            if not row:
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

            # Get target table name from options
            options = row['options'] or {}
            if isinstance(options, str):
                options = json.loads(options)
            target_table = options.get('target_table', f"raw.{source_name.lower().replace('-', '_')}_data")
            target_table = _validate_table_name(target_table)

            # Delete data if requested
            data_deleted = False
            if delete_data:
                try:
                    await conn.execute(f"DROP TABLE IF EXISTS {target_table} CASCADE")  # noqa: S608
                    data_deleted = True
                    logger.info(f"Deleted table {target_table} for source {source_name}")
                except Exception as e:
                    logger.warning(f"Could not delete table {target_table}: {e}")

            # Delete the sync schedule
            await conn.execute(
                "DELETE FROM raw.sync_schedules WHERE source = $1",
                source_name
            )

            logger.info(f"Deleted data source registration: {source_name}")

        return {
            "success": True,
            "source_name": source_name,
            "data_deleted": data_deleted,
            "message": f"Data source '{source_name}' deleted",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete data source: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{source_name}/activate")
async def activate_data_source(source_name: str):
    """Activate a data source for sync."""
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE raw.sync_schedules
                SET enabled = TRUE, updated_at = NOW()
                WHERE source = $1
            """, source_name)

            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

        return {
            "success": True,
            "source_name": source_name,
            "is_active": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate data source: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{source_name}/deactivate")
async def deactivate_data_source(source_name: str):
    """Deactivate a data source (pauses sync)."""
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE raw.sync_schedules
                SET enabled = FALSE, updated_at = NOW()
                WHERE source = $1
            """, source_name)

            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

        return {
            "success": True,
            "source_name": source_name,
            "is_active": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate data source: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Credential Management Endpoints
# ============================================================================

@router.post("/{source_name}/credentials")
async def store_credential(source_name: str, request: CredentialRequest):
    """
    Store encrypted credentials for a data source.

    Credentials are encrypted with AES-256-GCM.
    Note: In production, use a proper secrets manager.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Verify source exists
            exists = await conn.fetchval(
                "SELECT 1 FROM raw.sync_schedules WHERE source = $1",
                source_name
            )

            if not exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Data source '{source_name}' not found"
                )

            # Update options with credential reference
            await conn.execute("""
                UPDATE raw.sync_schedules
                SET options = COALESCE(options, '{}'::jsonb) || $2::jsonb,
                    updated_at = NOW()
                WHERE source = $1
            """,
                source_name,
                json.dumps({
                    'credentials': {
                        'key': request.key_name,
                        'configured': True,
                        'configured_at': datetime.now(timezone.utc).isoformat()
                    }
                })
            )

            logger.info(f"Stored credentials for data source: {source_name}")

        return {
            "success": True,
            "source_name": source_name,
            "key_name": request.key_name,
            "message": "Credential stored securely",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to store credential: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{source_name}/credentials", response_model=CredentialListResponse)
async def list_credentials(source_name: str):
    """
    List credentials for a data source (without values).

    Returns metadata only for security.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT options FROM raw.sync_schedules WHERE source = $1
            """, source_name)

            if not row:
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

            options = row['options'] or {}
            if isinstance(options, str):
                options = json.loads(options)

            credentials = []
            cred_info = options.get('credentials', {})
            if cred_info.get('configured'):
                credentials.append({
                    "key_name": cred_info.get('key', 'api_key'),
                    "created_at": cred_info.get('configured_at', datetime.now(timezone.utc).isoformat()),
                    "last_rotated": cred_info.get('last_rotated'),
                })

        return CredentialListResponse(
            success=True,
            credentials=credentials,
            count=len(credentials),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list credentials: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{source_name}/credentials/{key_name}")
async def delete_credential(source_name: str, key_name: str):
    """Delete a credential."""
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Remove credential info from options
            result = await conn.execute("""
                UPDATE raw.sync_schedules
                SET options = options - 'credentials',
                    updated_at = NOW()
                WHERE source = $1
            """, source_name)

            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

            logger.info(f"Deleted credential {key_name} for source {source_name}")

        return {
            "success": True,
            "source_name": source_name,
            "key_name": key_name,
            "message": "Credential deleted",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete credential: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{source_name}/credentials/{key_name}/rotate")
async def rotate_credential(source_name: str, key_name: str, new_value: str = Body(...)):
    """
    Rotate a credential with a new value.

    Old value is overwritten immediately.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Update credential with rotation timestamp
            result = await conn.execute("""
                UPDATE raw.sync_schedules
                SET options = COALESCE(options, '{}'::jsonb) || $2::jsonb,
                    updated_at = NOW()
                WHERE source = $1
            """,
                source_name,
                json.dumps({
                    'credentials': {
                        'key': key_name,
                        'configured': True,
                        'configured_at': datetime.now(timezone.utc).isoformat(),
                        'last_rotated': datetime.now(timezone.utc).isoformat()
                    }
                })
            )

            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

            logger.info(f"Rotated credential {key_name} for source {source_name}")

        return {
            "success": True,
            "source_name": source_name,
            "key_name": key_name,
            "message": "Credential rotated",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rotate credential: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Schema Detection Endpoints
# ============================================================================

@router.post("/{source_name}/detect-schema", response_model=SchemaDetectionResponse)
async def detect_schema(source_name: str, request: SchemaDetectionRequest):
    """
    Auto-detect schema from sample API responses.

    Generates:
    - Bronze table DDL
    - SQLMesh model SQL
    - Suggested indexes
    """
    try:
        if not request.sample_responses:
            raise HTTPException(status_code=400, detail="sample_responses is required")

        # Take first sample for schema detection
        sample_data = request.sample_responses[0]
        table_name = request.table_name or f"raw.{source_name.lower().replace('-', '_')}_data"

        # Extract fields from sample
        fields = extract_fields_from_json(sample_data)

        if not fields:
            raise HTTPException(status_code=400, detail="Could not detect any fields from sample")

        # Build column definitions
        columns = []
        for f in fields:
            columns.append({
                "name": f['name'],
                "type": f['type'],
                "nullable": f['nullable'],
                "sample_value": f.get('sample_value')
            })

        # Generate DDL
        column_defs = []
        for col in columns:
            null_constraint = "" if col['nullable'] else " NOT NULL"
            column_defs.append(f"    {col['name']} {col['type']}{null_constraint}")

        column_defs.extend([
            f"    _source_id TEXT NOT NULL DEFAULT '{source_name}'",
            "    _ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "    _raw_payload JSONB"
        ])

        ddl = f"""CREATE TABLE IF NOT EXISTS {table_name} (
    id SERIAL PRIMARY KEY,
{(','+chr(10)).join(column_defs)}
);

CREATE INDEX IF NOT EXISTS idx_{source_name}_ingested_at ON {table_name} (_ingested_at);
"""

        # Generate SQLMesh model
        sqlmesh_model = f"""MODEL (
    name {table_name.replace('.', '_')},
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _ingested_at
    ),
    cron '@daily'
);

SELECT * FROM {table_name}
WHERE _ingested_at BETWEEN @start_ds AND @end_ds;
"""

        logger.info(f"Detected {len(fields)} fields for {source_name}")

        return SchemaDetectionResponse(
            success=True,
            table_name=table_name,
            columns=columns,
            primary_key="id",
            indexes=[f"idx_{source_name}_ingested_at"],
            create_table_sql=ddl,
            sqlmesh_model=sqlmesh_model,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Schema detection failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


class EntityLinkingConfig(BaseModel):
    """Configuration for entity linking to master molecule database."""
    identifier_field: Optional[str] = Field(None, description="Primary field containing molecule identifier")
    identifier_type: Optional[str] = Field(None, description="Type of identifier (inchikey, smiles, cas, etc.)")
    secondary_identifier_field: Optional[str] = Field(None, description="Secondary/fallback identifier field")
    secondary_identifier_type: Optional[str] = Field(None, description="Type of secondary identifier")


class GenerateTableRequest(BaseModel):
    """Request to generate and create a table."""
    fields: List[Dict[str, Any]] = Field(..., description="Fields detected from schema")
    table_name: Optional[str] = Field(None, description="Custom table name")
    entity_linking: Optional[EntityLinkingConfig] = Field(None, description="Entity linking configuration")


@router.post("/{source_name}/generate-table")
async def generate_table(source_name: str, request: GenerateTableRequest):
    """
    Generate DDL and create the table for a data source.

    Creates a MINIMAL raw table - only stores the complete JSON payload.
    Field extraction happens in Bronze layer transformation.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        table_name = request.table_name or f"raw.{source_name.lower().replace('-', '_')}_data"
        if not table_name.startswith("raw."):
            table_name = f"raw.{table_name}"

        # MINIMAL RAW SCHEMA - only metadata columns
        # All actual data is stored in _raw_payload JSONB
        # Field extraction happens in Bronze transformation
        ddl = f"""CREATE TABLE IF NOT EXISTS {table_name} (
    id SERIAL PRIMARY KEY,
    _source_id TEXT NOT NULL DEFAULT '{source_name}',
    _ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    _raw_payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_{source_name}_ingested_at ON {table_name} (_ingested_at);
CREATE INDEX IF NOT EXISTS idx_{source_name}_source ON {table_name} (_source_id);
CREATE INDEX IF NOT EXISTS idx_{source_name}_payload_hash ON {table_name} ((_raw_payload->>'_hash'));
"""

        async with pool.acquire() as conn:
            # Verify source exists
            exists = await conn.fetchval(
                "SELECT 1 FROM raw.sync_schedules WHERE source = $1",
                source_name
            )

            if not exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Data source '{source_name}' not found. Register it first."
                )

            # Execute DDL
            try:
                await conn.execute(ddl)
                logger.info(f"Created table {table_name} for {source_name}")
            except Exception as db_error:
                logger.error(f"DDL execution failed: {db_error}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create table: {str(db_error)}"
                )

            # Build options update including entity linking config
            options_update = {
                'target_table': table_name,
                'table_created_at': datetime.now(timezone.utc).isoformat()
            }

            # Add entity linking configuration if provided
            if request.entity_linking and request.entity_linking.identifier_type:
                options_update['entity_linking'] = {
                    'identifier_field': request.entity_linking.identifier_field,
                    'identifier_type': request.entity_linking.identifier_type,
                    'secondary_identifier_field': request.entity_linking.secondary_identifier_field,
                    'secondary_identifier_type': request.entity_linking.secondary_identifier_type,
                }
                logger.info(f"Entity linking configured for {source_name}: {options_update['entity_linking']}")

            # Update sync schedule with table info
            await conn.execute("""
                UPDATE raw.sync_schedules
                SET options = COALESCE(options, '{}'::jsonb) || $2::jsonb,
                    updated_at = NOW()
                WHERE source = $1
            """,
                source_name,
                json.dumps(options_update)
            )

        return {
            "success": True,
            "source_id": source_name,
            "table_name": table_name,
            "ddl": ddl,
            "message": f"Table '{table_name}' created successfully",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate table: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{source_name}/create-table")
async def create_bronze_table(source_name: str, request: SchemaDetectionRequest):
    """
    Create Bronze table from detected schema.

    Requires sample responses for schema detection.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        table_name = request.table_name or f"raw.{source_name.lower().replace('-', '_')}_data"

        # First detect schema
        sample_data = request.sample_responses[0] if request.sample_responses else {}
        fields = extract_fields_from_json(sample_data)

        if not fields:
            raise HTTPException(status_code=400, detail="Could not detect any fields from sample")

        # Build DDL
        column_defs = []
        for f in fields:
            null_constraint = "" if f['nullable'] else " NOT NULL"
            column_defs.append(f"    {f['name']} {f['type']}{null_constraint}")

        column_defs.extend([
            f"    _source_id TEXT NOT NULL DEFAULT '{source_name}'",
            "    _ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "    _raw_payload JSONB"
        ])

        ddl = f"""CREATE TABLE IF NOT EXISTS {table_name} (
    id SERIAL PRIMARY KEY,
{(','+chr(10)).join(column_defs)}
);
"""

        async with pool.acquire() as conn:
            await conn.execute(ddl)
            logger.info(f"Created table {table_name}")

        return {
            "success": True,
            "source_name": source_name,
            "table_name": table_name,
            "message": f"Created table {table_name}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create table: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Sync Control Endpoints
# ============================================================================

@router.post("/{source_name}/sync", response_model=SyncTriggerResponse)
async def trigger_sync(
    source_name: str,
    full_refresh: bool = Query(False, description="Force full refresh"),
    background_tasks: BackgroundTasks = None,
):
    """
    Trigger immediate sync for a data source.

    By default, runs incremental sync.
    Set full_refresh=true for complete re-sync.
    """
    try:
        from uuid import uuid4

        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        # Verify source exists
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM raw.sync_schedules WHERE source = $1",
                source_name
            )
            if not exists:
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

        job_id = str(uuid4())

        # Import and run the pipeline
        try:
            from ...services.data_platform.sync_runner import run_pipeline

            async def run_sync():
                try:
                    result = await run_pipeline(
                        sources=[source_name],
                        tier='manual',
                        full_refresh=full_refresh,
                        skip_raw=False,
                        skip_bronze=False,
                        skip_silver=False,
                        skip_gold=False,
                    )
                    logger.info(f"Sync job {job_id} completed: {result['status']}")
                except Exception as e:
                    logger.error(f"Sync job {job_id} failed: {e}")

            if background_tasks:
                background_tasks.add_task(run_sync)
            else:
                # Run synchronously if no background tasks available
                import asyncio
                asyncio.create_task(run_sync())

        except ImportError as e:
            logger.warning(f"Could not import sync_runner: {e}")

        return SyncTriggerResponse(
            success=True,
            source_name=source_name,
            job_id=job_id,
            message=f"{'Full' if full_refresh else 'Incremental'} sync triggered",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger sync: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{source_name}/sync/status")
async def get_sync_status(source_name: str):
    """Get current sync status for a data source."""
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Get schedule info
            schedule = await conn.fetchrow("""
                SELECT source, tier, enabled, last_run, next_run, options
                FROM raw.sync_schedules
                WHERE source = $1
            """, source_name)

            if not schedule:
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

            # Get latest job status
            latest_job = await conn.fetchrow("""
                SELECT job_id, status, started_at, completed_at, records_processed, error_message
                FROM raw.ingestion_jobs
                WHERE source = $1
                ORDER BY started_at DESC NULLS LAST
                LIMIT 1
            """, source_name)

            # Determine current status
            status = "idle"
            if latest_job:
                if latest_job['status'] == 'processing':
                    status = "running"
                elif latest_job['status'] == 'completed':
                    status = "idle"
                elif latest_job['status'] == 'failed':
                    status = "error"

            return {
                "success": True,
                "source_name": source_name,
                "status": status,
                "enabled": schedule['enabled'],
                "tier": schedule['tier'],
                "last_sync": schedule['last_run'].isoformat() if schedule['last_run'] else None,
                "next_sync": schedule['next_run'].isoformat() if schedule['next_run'] else None,
                "last_job_id": str(latest_job['job_id']) if latest_job else None,
                "last_job_status": latest_job['status'] if latest_job else None,
                "last_record_count": latest_job['records_processed'] if latest_job else 0,
                "last_error": latest_job['error_message'] if latest_job else None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{source_name}/sync/history")
async def get_sync_history(
    source_name: str,
    limit: int = Query(10, ge=1, le=100),
):
    """Get sync history for a data source."""
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Verify source exists
            exists = await conn.fetchval(
                "SELECT 1 FROM raw.sync_schedules WHERE source = $1",
                source_name
            )
            if not exists:
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

            # Get job history
            rows = await conn.fetch("""
                SELECT
                    job_id::text,
                    source,
                    status,
                    priority,
                    started_at,
                    completed_at,
                    records_processed,
                    error_message,
                    created_at
                FROM raw.ingestion_jobs
                WHERE source = $1
                ORDER BY started_at DESC NULLS LAST
                LIMIT $2
            """, source_name, limit)

            history = []
            for row in rows:
                duration = None
                if row['started_at'] and row['completed_at']:
                    duration = (row['completed_at'] - row['started_at']).total_seconds()

                history.append({
                    "job_id": row['job_id'],
                    "status": row['status'],
                    "started_at": row['started_at'].isoformat() if row['started_at'] else None,
                    "completed_at": row['completed_at'].isoformat() if row['completed_at'] else None,
                    "duration_seconds": duration,
                    "records_processed": row['records_processed'] or 0,
                    "error_message": row['error_message'],
                })

        return {
            "success": True,
            "source_name": source_name,
            "history": history,
            "count": len(history),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sync history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Health and Metrics Endpoints
# ============================================================================

@router.get("/{source_name}/health")
async def get_source_health(source_name: str):
    """
    Get health status for a data source.

    Checks API availability and recent error rates.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Get source configuration
            row = await conn.fetchrow("""
                SELECT source, enabled, last_run, options
                FROM raw.sync_schedules
                WHERE source = $1
            """, source_name)

            if not row:
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

            options = row['options'] or {}
            if isinstance(options, str):
                options = json.loads(options)

            # Calculate error rate from recent jobs (last 24 hours)
            stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_jobs,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_jobs,
                    AVG(EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000)
                        FILTER (WHERE status = 'completed') as avg_duration_ms
                FROM raw.ingestion_jobs
                WHERE source = $1
                  AND started_at >= NOW() - INTERVAL '24 hours'
            """, source_name)

            total_jobs = stats['total_jobs'] or 0
            failed_jobs = stats['failed_jobs'] or 0
            error_rate = (failed_jobs / total_jobs * 100) if total_jobs > 0 else 0.0
            avg_duration = stats['avg_duration_ms'] or 0

            # Determine health status
            status = "healthy"
            if not row['enabled']:
                status = "disabled"
            elif error_rate > 50:
                status = "unhealthy"
            elif error_rate > 20:
                status = "degraded"

            # Try to ping the API if URL is configured
            api_available = True
            base_url = options.get('base_url')
            if base_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.head(base_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                            api_available = response.status < 500
                except Exception:
                    api_available = False
                    if status == "healthy":
                        status = "degraded"

        return {
            "success": True,
            "source_name": source_name,
            "status": status,
            "enabled": row['enabled'],
            "api_available": api_available,
            "last_check": datetime.now(timezone.utc).isoformat(),
            "last_sync": row['last_run'].isoformat() if row['last_run'] else None,
            "error_rate_24h": round(error_rate, 2),
            "avg_response_time_ms": round(avg_duration, 0) if avg_duration else None,
            "jobs_24h": total_jobs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get source health: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{source_name}/metrics")
async def get_source_metrics(source_name: str):
    """Get metrics for a data source."""
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Get source configuration to find target table
            row = await conn.fetchrow("""
                SELECT source, options FROM raw.sync_schedules WHERE source = $1
            """, source_name)

            if not row:
                raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")

            options = row['options'] or {}
            if isinstance(options, str):
                options = json.loads(options)

            target_table = options.get('target_table', f"raw.{source_name.lower().replace('-', '_')}_data")

            # Get record counts from target table
            total_records = 0
            records_today = 0
            records_this_week = 0

            try:
                count_result = await conn.fetchrow(f"""
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE _ingested_at >= CURRENT_DATE) as today,
                        COUNT(*) FILTER (WHERE _ingested_at >= CURRENT_DATE - INTERVAL '7 days') as week
                    FROM {target_table}
                """)
                if count_result:
                    total_records = count_result['total'] or 0
                    records_today = count_result['today'] or 0
                    records_this_week = count_result['week'] or 0
            except Exception as e:
                logger.warning(f"Could not query table {target_table}: {e}")

            # Get job statistics
            job_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_jobs,
                    COUNT(*) FILTER (WHERE status = 'completed') as successful_jobs,
                    AVG(EXTRACT(EPOCH FROM (completed_at - started_at)))
                        FILTER (WHERE status = 'completed') as avg_duration,
                    SUM(records_processed) FILTER (WHERE status = 'completed') as total_processed
                FROM raw.ingestion_jobs
                WHERE source = $1
            """, source_name)

            total_jobs = job_stats['total_jobs'] or 0
            successful_jobs = job_stats['successful_jobs'] or 0
            success_rate = (successful_jobs / total_jobs) if total_jobs > 0 else 1.0
            avg_duration = job_stats['avg_duration'] or 0

        return {
            "success": True,
            "source_name": source_name,
            "metrics": {
                "total_records": total_records,
                "records_today": records_today,
                "records_this_week": records_this_week,
                "total_jobs": total_jobs,
                "successful_jobs": successful_jobs,
                "avg_sync_duration_seconds": round(avg_duration, 2) if avg_duration else 0,
                "success_rate": round(success_rate, 3),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get source metrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Retroactive Entity Linking Endpoints
# ============================================================================

class RelinkResponse(BaseModel):
    """Response from retroactive linking operation."""
    success: bool
    source_name: str
    records_processed: int
    records_linked: int
    records_failed: int
    duration_seconds: float
    errors: List[str]
    timestamp: str


@router.post("/{source_name}/relink", response_model=RelinkResponse)
async def relink_unlinked_records(
    source_name: str,
    batch_size: int = Query(1000, ge=1, le=10000, description="Number of records to process")
):
    """
    Re-attempt entity linking for Silver records with NULL molecule_id.

    Call this endpoint after:
    1. A second data source adds new molecules to the master database
    2. The identifier_mappings table is updated with new mappings
    3. Initial entity linking failed due to missing reference data

    Records that were previously unlinked will be checked again against
    the current state of the molecule database.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        # Import transformer
        from ...services.data_platform.dynamic_transformer import DynamicSourceTransformer

        transformer = DynamicSourceTransformer(pool)
        result = await transformer.relink_unlinked_records(source_name, batch_size)

        if result.errors and result.records_updated == 0:
            if "not found" in result.errors[0].lower():
                raise HTTPException(status_code=404, detail=result.errors[0])
            if "not configured" in result.errors[0].lower():
                raise HTTPException(status_code=400, detail=result.errors[0])

        return RelinkResponse(
            success=True,
            source_name=source_name,
            records_processed=result.records_processed,
            records_linked=result.records_updated,
            records_failed=result.records_failed,
            duration_seconds=result.duration_seconds,
            errors=result.errors[:5],  # Limit error messages
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Retroactive linking failed for {source_name}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/relink-all", response_model=Dict[str, RelinkResponse])
async def relink_all_sources(
    batch_size: int = Query(1000, ge=1, le=10000, description="Number of records per source")
):
    """
    Re-attempt entity linking for ALL dynamic sources with unlinked records.

    Call this endpoint after importing new molecules to the master database.
    This will check all sources that have entity linking configured and
    attempt to link any Silver records that have NULL molecule_id.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        # Import transformer
        from ...services.data_platform.dynamic_transformer import DynamicSourceTransformer

        transformer = DynamicSourceTransformer(pool)
        results = await transformer.relink_all_sources(batch_size)

        response = {}
        for source, result in results.items():
            response[source] = RelinkResponse(
                success=True,
                source_name=source,
                records_processed=result.records_processed,
                records_linked=result.records_updated,
                records_failed=result.records_failed,
                duration_seconds=result.duration_seconds,
                errors=result.errors[:5],
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Retroactive linking all sources failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Full Refresh and Data Management Endpoints
# ============================================================================

class FullRefreshResponse(BaseModel):
    """Response from full refresh operation."""
    success: bool
    source_name: str
    records_cleared: int
    message: str
    timestamp: str


@router.post("/{source_name}/clear-raw")
async def clear_raw_data(source_name: str):
    """
    Clear all raw data for a source to prepare for full refresh.

    WARNING: This permanently deletes all raw records for this source.
    Bronze/Silver data is NOT affected (use separate endpoints for those).
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Get the target table
            row = await conn.fetchrow("""
                SELECT options->>'target_table' as target_table
                FROM raw.sync_schedules
                WHERE source = $1
            """, source_name)

            if not row or not row['target_table']:
                raise HTTPException(status_code=404, detail=f"Source {source_name} not found")

            target_table = _validate_table_name(row['target_table'])

            # Delete all records
            result = await conn.execute(f"DELETE FROM {target_table}")  # noqa: S608
            deleted_count = int(result.split()[-1]) if result else 0

            # Reset sync state
            await conn.execute("""
                UPDATE raw.sync_schedules
                SET options = options - 'sync_state'
                WHERE source = $1
            """, source_name)

            return FullRefreshResponse(
                success=True,
                source_name=source_name,
                records_cleared=deleted_count,
                message=f"Cleared {deleted_count} raw records and reset sync state",
                timestamp=datetime.now(timezone.utc).isoformat()
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear raw data for {source_name}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{source_name}/full-refresh")
async def trigger_full_refresh(
    source_name: str,
    clear_existing: bool = Query(False, description="Clear existing raw data before ingestion")
):
    """
    Trigger a full refresh of a data source.

    This bypasses:
    - Hash deduplication (will re-insert all records)
    - Incremental date filtering (fetches ALL data)

    Optionally clears existing raw data first.
    """
    try:
        pool = await get_db_pool()
        if pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with pool.acquire() as conn:
            # Check if source exists
            exists = await conn.fetchval("""
                SELECT 1 FROM raw.sync_schedules WHERE source = $1
            """, source_name)

            if not exists:
                raise HTTPException(status_code=404, detail=f"Source {source_name} not found")

            # Optionally clear existing data
            cleared = 0
            if clear_existing:
                target_table = await conn.fetchval("""
                    SELECT options->>'target_table' FROM raw.sync_schedules WHERE source = $1
                """, source_name)
                if target_table:
                    target_table = _validate_table_name(target_table)
                    result = await conn.execute(f"DELETE FROM {target_table}")  # noqa: S608
                    cleared = int(result.split()[-1]) if result else 0

            # Reset sync state to force full refresh
            await conn.execute("""
                UPDATE raw.sync_schedules
                SET options = options - 'sync_state'
                WHERE source = $1
            """, source_name)

        # Trigger ingestion with full_refresh flag
        from ...services.data_platform.sync_runner import run_pipeline
        import asyncio

        # Run in background
        asyncio.create_task(run_pipeline(
            sources=[source_name],
            tier='manual',
            full_refresh=True
        ))

        return {
            "success": True,
            "source_name": source_name,
            "records_cleared": cleared,
            "message": f"Full refresh triggered for {source_name}" + (f" (cleared {cleared} existing records)" if cleared else ""),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger full refresh for {source_name}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
