"""Structured JSON logging configuration for the drug enrichment service."""

import json
import logging
import sys
import time
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from loguru import logger


# Context variables for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
operation_var: ContextVar[str] = ContextVar("operation", default="")


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add context from context variables
        if request_id := request_id_var.get():
            log_data["request_id"] = request_id
        if user_id := user_id_var.get():
            log_data["user_id"] = user_id
        if operation := operation_var.get():
            log_data["operation"] = operation

        # Add extra fields from record
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def configure_logging(
    level: str = "INFO",
    json_output: bool = True,
    include_timestamp: bool = True,
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output logs as JSON
        include_timestamp: If True, include timestamps in non-JSON output
    """
    # Remove default loguru handler
    logger.remove()

    if json_output:
        # JSON format for production
        logger.add(
            sys.stdout,
            format=_json_formatter,
            level=level,
            serialize=False,
        )
    else:
        # Human-readable format for development
        format_str = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | " if include_timestamp else ""
        format_str += (
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{extra[request_id]} | "
            "<level>{message}</level>"
        )
        logger.add(
            sys.stdout,
            format=format_str,
            level=level,
            colorize=True,
        )


def _json_formatter(record: dict) -> str:
    """Format log record as JSON for loguru."""
    log_data = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "message": record["message"],
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
    }

    # Add context from context variables
    if request_id := request_id_var.get():
        log_data["request_id"] = request_id
    if user_id := user_id_var.get():
        log_data["user_id"] = user_id
    if operation := operation_var.get():
        log_data["operation"] = operation

    # Add extra fields
    if record.get("extra"):
        for key, value in record["extra"].items():
            if key not in ["request_id", "user_id", "operation"]:
                log_data[key] = value

    # Add exception info
    if record.get("exception"):
        log_data["exception"] = {
            "type": record["exception"].type.__name__ if record["exception"].type else None,
            "value": str(record["exception"].value) if record["exception"].value else None,
            "traceback": record["exception"].traceback if record["exception"].traceback else None,
        }

    return json.dumps(log_data) + "\n"


def get_request_id() -> str:
    """Get or generate a request ID."""
    request_id = request_id_var.get()
    if not request_id:
        request_id = str(uuid4())[:8]
        request_id_var.set(request_id)
    return request_id


def set_request_context(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    operation: Optional[str] = None,
) -> None:
    """Set request context for logging."""
    if request_id:
        request_id_var.set(request_id)
    if user_id:
        user_id_var.set(user_id)
    if operation:
        operation_var.set(operation)


def clear_request_context() -> None:
    """Clear request context after request completes."""
    request_id_var.set("")
    user_id_var.set("")
    operation_var.set("")


def log_with_context(
    level: str = "info",
    message: str = "",
    **extra: Any,
) -> None:
    """
    Log a message with context and extra fields.

    Args:
        level: Log level
        message: Log message
        **extra: Additional fields to include in log
    """
    log_method = getattr(logger, level.lower())
    log_method(message, request_id=get_request_id(), **extra)


def log_operation(
    operation_name: str,
    log_args: bool = True,
    log_result: bool = False,
) -> Callable:
    """
    Decorator to log operation start, duration, and completion.

    Args:
        operation_name: Name of the operation
        log_args: If True, log function arguments
        log_result: If True, log return value
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            operation_var.set(operation_name)

            extra: Dict[str, Any] = {"operation": operation_name}
            if log_args and kwargs:
                extra["args"] = {k: str(v)[:100] for k, v in kwargs.items()}

            logger.info(f"Starting {operation_name}", **extra)

            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                log_extra = {
                    "operation": operation_name,
                    "duration_ms": round(duration_ms, 2),
                    "status": "success",
                }
                if log_result and result:
                    log_extra["result_type"] = type(result).__name__

                logger.info(f"Completed {operation_name}", **log_extra)
                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"Failed {operation_name}",
                    operation=operation_name,
                    duration_ms=round(duration_ms, 2),
                    status="error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            operation_var.set(operation_name)

            extra: Dict[str, Any] = {"operation": operation_name}
            if log_args and kwargs:
                extra["args"] = {k: str(v)[:100] for k, v in kwargs.items()}

            logger.info(f"Starting {operation_name}", **extra)

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                log_extra = {
                    "operation": operation_name,
                    "duration_ms": round(duration_ms, 2),
                    "status": "success",
                }
                if log_result and result:
                    log_extra["result_type"] = type(result).__name__

                logger.info(f"Completed {operation_name}", **log_extra)
                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"Failed {operation_name}",
                    operation=operation_name,
                    duration_ms=round(duration_ms, 2),
                    status="error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class EnrichmentLogger:
    """Specialized logger for drug enrichment operations."""

    def __init__(self, name: str = "drug_enrichment"):
        """Initialize enrichment logger."""
        self.name = name
        self._logger = logger.bind(service=name)

    def log_lookup(
        self,
        identifier: str,
        identifier_type: str,
        resolved: bool,
        duration_ms: float,
        sources_queried: list,
        cache_hit: bool = False,
    ) -> None:
        """Log a drug lookup operation."""
        self._logger.info(
            "Drug lookup completed",
            operation="lookup",
            identifier=identifier,
            identifier_type=identifier_type,
            resolved=resolved,
            duration_ms=round(duration_ms, 2),
            sources_queried=sources_queried,
            cache_hit=cache_hit,
        )

    def log_batch_start(
        self,
        job_id: str,
        total_items: int,
        sources: list,
    ) -> None:
        """Log batch job start."""
        self._logger.info(
            "Batch job started",
            operation="batch_start",
            job_id=job_id,
            total_items=total_items,
            sources=sources,
        )

    def log_batch_progress(
        self,
        job_id: str,
        processed: int,
        total: int,
        failed: int,
    ) -> None:
        """Log batch job progress."""
        self._logger.info(
            "Batch job progress",
            operation="batch_progress",
            job_id=job_id,
            processed=processed,
            total=total,
            failed=failed,
            progress_pct=round((processed / total) * 100, 1) if total > 0 else 0,
        )

    def log_batch_complete(
        self,
        job_id: str,
        total_items: int,
        resolved: int,
        failed: int,
        duration_ms: float,
    ) -> None:
        """Log batch job completion."""
        self._logger.info(
            "Batch job completed",
            operation="batch_complete",
            job_id=job_id,
            total_items=total_items,
            resolved=resolved,
            failed=failed,
            duration_ms=round(duration_ms, 2),
            success_rate=round((resolved / total_items) * 100, 1) if total_items > 0 else 0,
        )

    def log_source_query(
        self,
        source: str,
        inchi_key: str,
        success: bool,
        duration_ms: float,
        cached: bool = False,
    ) -> None:
        """Log a source query."""
        level = "info" if success else "warning"
        getattr(self._logger, level)(
            f"Source query: {source}",
            operation="source_query",
            source=source,
            inchi_key=inchi_key[:10] + "...",  # Truncate for log readability
            success=success,
            duration_ms=round(duration_ms, 2),
            cached=cached,
        )

    def log_cache_operation(
        self,
        operation: str,
        key: str,
        hit: bool,
        cache_type: str = "redis",
    ) -> None:
        """Log a cache operation."""
        self._logger.debug(
            f"Cache {operation}",
            operation=f"cache_{operation}",
            cache_key=key[:20] + "..." if len(key) > 20 else key,
            cache_hit=hit,
            cache_type=cache_type,
        )

    def log_rate_limit(
        self,
        api_key: str,
        limit: int,
        remaining: int,
        reset_seconds: int,
    ) -> None:
        """Log rate limit status."""
        self._logger.info(
            "Rate limit check",
            operation="rate_limit",
            api_key_prefix=api_key[:8] + "..." if api_key else "none",
            limit=limit,
            remaining=remaining,
            reset_seconds=reset_seconds,
        )


# Global logger instance
enrichment_logger = EnrichmentLogger()


# Initialize default configuration
def init_logging(json_output: bool = True, level: str = "INFO") -> None:
    """Initialize logging with default configuration."""
    configure_logging(level=level, json_output=json_output)
