"""
Data Platform Error Handlers

Centralized error handling for the DK Molecule Data Platform API.
Provides consistent error responses and logging across all endpoints.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from typing import Optional, Dict, Any, List
from uuid import UUID
import logging
import traceback

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


# ==========================================
# Error Response Models
# ==========================================

class ErrorDetail(BaseModel):
    """Detailed error information."""
    field: Optional[str] = None
    message: str
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response format."""
    success: bool = False
    error: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        code: str,
        message: str,
        details: Optional[List[ErrorDetail]] = None,
        request_id: Optional[str] = None,
        **extra
    ) -> "ErrorResponse":
        error_dict = {
            "code": code,
            "message": message,
        }
        if details:
            error_dict["details"] = [d.model_dump() for d in details]
        if request_id:
            error_dict["request_id"] = request_id
        error_dict.update(extra)

        return cls(success=False, error=error_dict)


# ==========================================
# Base Exception Classes
# ==========================================

class DataPlatformError(Exception):
    """Base exception for all Data Platform errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: Optional[str] = None,
        details: Optional[List[ErrorDetail]] = None,
        **extra
    ):
        self.message = message or self.message
        self.details = details or []
        self.extra = extra
        super().__init__(self.message)

    def to_response(self, request_id: Optional[str] = None) -> ErrorResponse:
        return ErrorResponse.create(
            code=self.error_code,
            message=self.message,
            details=self.details,
            request_id=request_id,
            **self.extra
        )


class ValidationError(DataPlatformError):
    """Raised when request validation fails."""
    status_code = 400
    error_code = "VALIDATION_ERROR"
    message = "Request validation failed"


class NotFoundError(DataPlatformError):
    """Raised when a requested resource is not found."""
    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found"

    def __init__(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        **extra
    ):
        message = f"{resource_type} not found"
        if resource_id:
            message = f"{resource_type} with ID '{resource_id}' not found"
        super().__init__(message=message, resource_type=resource_type, **extra)


class ConflictError(DataPlatformError):
    """Raised when there's a resource conflict."""
    status_code = 409
    error_code = "CONFLICT"
    message = "Resource conflict"


class AuthenticationError(DataPlatformError):
    """Raised when authentication fails."""
    status_code = 401
    error_code = "AUTHENTICATION_ERROR"
    message = "Authentication required"


class AuthorizationError(DataPlatformError):
    """Raised when user lacks required permissions."""
    status_code = 403
    error_code = "AUTHORIZATION_ERROR"
    message = "Insufficient permissions"

    def __init__(
        self,
        required_role: Optional[str] = None,
        required_permission: Optional[str] = None,
        **extra
    ):
        if required_role:
            message = f"Requires {required_role} role or higher"
        elif required_permission:
            message = f"Missing permission: {required_permission}"
        else:
            message = "Insufficient permissions"
        super().__init__(message=message, **extra)


class RateLimitError(DataPlatformError):
    """Raised when rate limit is exceeded."""
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"
    message = "Rate limit exceeded"

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        retry_after: Optional[int] = None,
        **extra
    ):
        message = f"Rate limit of {limit} requests per {window_seconds}s exceeded"
        super().__init__(
            message=message,
            limit=limit,
            window_seconds=window_seconds,
            retry_after=retry_after,
            **extra
        )


class ServiceUnavailableError(DataPlatformError):
    """Raised when an external service is unavailable."""
    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"
    message = "Service temporarily unavailable"


# ==========================================
# Domain-Specific Exceptions
# ==========================================

class EntityResolutionError(DataPlatformError):
    """Raised when entity resolution fails."""
    status_code = 422
    error_code = "ENTITY_RESOLUTION_ERROR"
    message = "Failed to resolve entity"

    def __init__(
        self,
        identifier: str,
        identifier_type: Optional[str] = None,
        reason: Optional[str] = None,
        **extra
    ):
        message = f"Failed to resolve identifier '{identifier}'"
        if identifier_type:
            message = f"Failed to resolve {identifier_type} '{identifier}'"
        if reason:
            message += f": {reason}"
        super().__init__(
            message=message,
            identifier=identifier,
            identifier_type=identifier_type,
            **extra
        )


class QuarantineError(DataPlatformError):
    """Raised for quarantine workflow errors."""
    status_code = 422
    error_code = "QUARANTINE_ERROR"
    message = "Quarantine workflow error"

    def __init__(
        self,
        record_id: Optional[UUID] = None,
        action: Optional[str] = None,
        reason: Optional[str] = None,
        **extra
    ):
        message = "Quarantine workflow error"
        if action:
            message = f"Failed to {action} quarantined record"
        if record_id:
            message += f" (ID: {record_id})"
        if reason:
            message += f": {reason}"
        super().__init__(message=message, record_id=str(record_id) if record_id else None, **extra)


class PipelineError(DataPlatformError):
    """Raised for pipeline execution errors."""
    status_code = 500
    error_code = "PIPELINE_ERROR"
    message = "Pipeline execution failed"

    def __init__(
        self,
        pipeline_name: str,
        stage: Optional[str] = None,
        reason: Optional[str] = None,
        **extra
    ):
        message = f"Pipeline '{pipeline_name}' failed"
        if stage:
            message += f" at stage '{stage}'"
        if reason:
            message += f": {reason}"
        super().__init__(message=message, pipeline_name=pipeline_name, stage=stage, **extra)


class IngestionError(DataPlatformError):
    """Raised when data ingestion fails."""
    status_code = 500
    error_code = "INGESTION_ERROR"
    message = "Data ingestion failed"

    def __init__(
        self,
        source: str,
        layer: str = "raw",
        reason: Optional[str] = None,
        records_processed: int = 0,
        records_failed: int = 0,
        **extra
    ):
        message = f"Ingestion from '{source}' to {layer} layer failed"
        if reason:
            message += f": {reason}"
        super().__init__(
            message=message,
            source=source,
            layer=layer,
            records_processed=records_processed,
            records_failed=records_failed,
            **extra
        )


class TransformationError(DataPlatformError):
    """Raised when data transformation fails."""
    status_code = 500
    error_code = "TRANSFORMATION_ERROR"
    message = "Data transformation failed"

    def __init__(
        self,
        source_layer: str,
        target_layer: str,
        reason: Optional[str] = None,
        **extra
    ):
        message = f"Transformation from {source_layer} to {target_layer} failed"
        if reason:
            message += f": {reason}"
        super().__init__(
            message=message,
            source_layer=source_layer,
            target_layer=target_layer,
            **extra
        )


class DataSourceError(DataPlatformError):
    """Raised for data source configuration errors."""
    status_code = 400
    error_code = "DATA_SOURCE_ERROR"
    message = "Data source error"

    def __init__(
        self,
        source_name: str,
        action: Optional[str] = None,
        reason: Optional[str] = None,
        **extra
    ):
        message = f"Data source '{source_name}' error"
        if action:
            message = f"Failed to {action} data source '{source_name}'"
        if reason:
            message += f": {reason}"
        super().__init__(message=message, source_name=source_name, **extra)


class LifecycleError(DataPlatformError):
    """Raised for lifecycle detection/validation errors."""
    status_code = 422
    error_code = "LIFECYCLE_ERROR"
    message = "Lifecycle operation failed"

    def __init__(
        self,
        molecule_id: Optional[UUID] = None,
        operation: Optional[str] = None,
        reason: Optional[str] = None,
        **extra
    ):
        message = "Lifecycle operation failed"
        if operation:
            message = f"Lifecycle {operation} failed"
        if molecule_id:
            message += f" for molecule {molecule_id}"
        if reason:
            message += f": {reason}"
        super().__init__(
            message=message,
            molecule_id=str(molecule_id) if molecule_id else None,
            **extra
        )


class OnboardingError(DataPlatformError):
    """Raised for molecule onboarding errors."""
    status_code = 422
    error_code = "ONBOARDING_ERROR"
    message = "Molecule onboarding failed"

    def __init__(
        self,
        molecule_name: Optional[str] = None,
        step: Optional[int] = None,
        reason: Optional[str] = None,
        **extra
    ):
        message = "Molecule onboarding failed"
        if molecule_name:
            message = f"Onboarding failed for '{molecule_name}'"
        if step:
            message += f" at step {step}"
        if reason:
            message += f": {reason}"
        super().__init__(message=message, molecule_name=molecule_name, step=step, **extra)


# ==========================================
# Error Handlers
# ==========================================

def register_error_handlers(app: FastAPI) -> None:
    """Register all error handlers with the FastAPI application."""

    @app.exception_handler(DataPlatformError)
    async def data_platform_error_handler(
        request: Request,
        exc: DataPlatformError
    ) -> JSONResponse:
        """Handle all DataPlatformError subclasses."""
        request_id = getattr(request.state, "request_id", None)

        # Log error
        logger.error(
            f"DataPlatformError: {exc.error_code} - {exc.message}",
            extra={
                "error_code": exc.error_code,
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
            }
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response(request_id).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors."""
        request_id = getattr(request.state, "request_id", None)

        details = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            details.append(ErrorDetail(
                field=field,
                message=error["msg"],
                code=error["type"]
            ))

        response = ErrorResponse.create(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details=details,
            request_id=request_id,
        )

        return JSONResponse(
            status_code=400,
            content=response.model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException
    ) -> JSONResponse:
        """Handle FastAPI HTTPExceptions."""
        request_id = getattr(request.state, "request_id", None)

        # Map status codes to error codes
        error_codes = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            422: "UNPROCESSABLE_ENTITY",
            429: "RATE_LIMIT_EXCEEDED",
            500: "INTERNAL_ERROR",
            503: "SERVICE_UNAVAILABLE",
        }

        error_code = error_codes.get(exc.status_code, "ERROR")

        response = ErrorResponse.create(
            code=error_code,
            message=str(exc.detail),
            request_id=request_id,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(),
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(
        request: Request,
        exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle Starlette HTTPExceptions."""
        return await http_exception_handler(request, HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception
    ) -> JSONResponse:
        """Handle any unhandled exceptions."""
        request_id = getattr(request.state, "request_id", None)

        # Log full traceback for debugging
        logger.error(
            f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "traceback": traceback.format_exc(),
            }
        )

        # Don't expose internal error details in production
        response = ErrorResponse.create(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            request_id=request_id,
        )

        return JSONResponse(
            status_code=500,
            content=response.model_dump(),
        )


# ==========================================
# Utility Functions
# ==========================================

def raise_not_found(
    resource_type: str,
    resource_id: Optional[str] = None
) -> None:
    """Convenience function to raise NotFoundError."""
    raise NotFoundError(resource_type, resource_id)


def raise_validation_error(
    message: str,
    field: Optional[str] = None
) -> None:
    """Convenience function to raise ValidationError."""
    details = [ErrorDetail(field=field, message=message)] if field else None
    raise ValidationError(message=message, details=details)


def raise_authorization_error(
    required_role: Optional[str] = None,
    required_permission: Optional[str] = None
) -> None:
    """Convenience function to raise AuthorizationError."""
    raise AuthorizationError(
        required_role=required_role,
        required_permission=required_permission
    )
