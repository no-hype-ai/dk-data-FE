"""
Centralized Error Handling with Source Attribution.

Implements T337: Comprehensive error messages with data source attribution.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from loguru import logger


class DataSource(str, Enum):
    """Data sources used by Ground Truth Service."""
    OPENFDA = "openfda"
    CLINICALTRIALS = "clinicaltrials.gov"
    RXNORM = "rxnorm"
    UMLS = "umls"
    DRUGBANK = "drugbank"
    DAILYMED = "dailymed"
    PUBMED = "pubmed"
    EMA = "ema"
    HEALTH_CANADA = "health_canada"
    ORANGE_BOOK = "orange_book"
    FAERS = "faers"
    NEO4J = "neo4j"
    INTERNAL = "internal"


class ErrorCode(str, Enum):
    """Standardized error codes."""
    # Client errors (4xx)
    INVALID_REQUEST = "INVALID_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    MOLECULE_NOT_FOUND = "MOLECULE_NOT_FOUND"
    INDICATION_NOT_FOUND = "INDICATION_NOT_FOUND"
    TRIAL_NOT_FOUND = "TRIAL_NOT_FOUND"
    EXPORT_NOT_FOUND = "EXPORT_NOT_FOUND"
    EXPORT_EXPIRED = "EXPORT_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    UNAUTHORIZED = "UNAUTHORIZED"

    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATA_SOURCE_ERROR = "DATA_SOURCE_ERROR"
    GRAPH_BUILD_ERROR = "GRAPH_BUILD_ERROR"
    EXPORT_ERROR = "EXPORT_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class ErrorDetail(BaseModel):
    """Detailed error information."""
    code: str
    message: str
    source: Optional[str] = None
    source_url: Optional[str] = None
    timestamp: str
    request_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    suggestions: Optional[List[str]] = None


class GroundTruthError(Exception):
    """Base exception for Ground Truth Service errors."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 500,
        source: Optional[DataSource] = None,
        details: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.source = source
        self.details = details or {}
        self.suggestions = suggestions or []
        super().__init__(message)

    def to_response(self, request_id: Optional[str] = None) -> ErrorDetail:
        """Convert to error response."""
        source_urls = {
            DataSource.OPENFDA: "https://open.fda.gov/",
            DataSource.CLINICALTRIALS: "https://clinicaltrials.gov/",
            DataSource.RXNORM: "https://mor.nlm.nih.gov/RxNav/",
            DataSource.UMLS: "https://www.nlm.nih.gov/research/umls/",
            DataSource.DRUGBANK: "https://go.drugbank.com/",
            DataSource.DAILYMED: "https://dailymed.nlm.nih.gov/",
            DataSource.PUBMED: "https://pubmed.ncbi.nlm.nih.gov/",
            DataSource.EMA: "https://www.ema.europa.eu/",
            DataSource.HEALTH_CANADA: "https://health-products.canada.ca/",
            DataSource.ORANGE_BOOK: "https://www.fda.gov/drugs/drug-approvals-and-databases/approved-drug-products-therapeutic-equivalence-evaluations-orange-book",
            DataSource.FAERS: "https://www.fda.gov/drugs/surveillance/fda-adverse-event-reporting-system-faers",
        }

        return ErrorDetail(
            code=self.code.value,
            message=self.message,
            source=self.source.value if self.source else None,
            source_url=source_urls.get(self.source) if self.source else None,
            timestamp=datetime.utcnow().isoformat() + "Z",
            request_id=request_id,
            details=self.details if self.details else None,
            suggestions=self.suggestions if self.suggestions else None,
        )


# Specific error classes
class MoleculeNotFoundError(GroundTruthError):
    """Raised when a molecule cannot be found."""

    def __init__(
        self,
        molecule_id: str,
        source: Optional[DataSource] = None,
        searched_sources: Optional[List[str]] = None,
    ):
        details = {"molecule_id": molecule_id}
        if searched_sources:
            details["searched_sources"] = searched_sources

        suggestions = [
            "Verify the molecule ID or name is spelled correctly",
            "Try searching with alternative names (INN, brand name, UNII)",
            "Check if the molecule is in development vs. approved status",
        ]

        super().__init__(
            code=ErrorCode.MOLECULE_NOT_FOUND,
            message=f"Molecule '{molecule_id}' not found in available data sources",
            status_code=404,
            source=source,
            details=details,
            suggestions=suggestions,
        )


class DataSourceError(GroundTruthError):
    """Raised when an external data source fails."""

    def __init__(
        self,
        source: DataSource,
        operation: str,
        original_error: Optional[str] = None,
    ):
        details = {"operation": operation}
        if original_error:
            details["original_error"] = original_error

        suggestions = [
            f"The {source.value} service may be temporarily unavailable",
            "Try again in a few minutes",
            "Check https://status.nlm.nih.gov/ for NLM service status" if source in [DataSource.RXNORM, DataSource.UMLS, DataSource.PUBMED] else None,
        ]
        suggestions = [s for s in suggestions if s]

        super().__init__(
            code=ErrorCode.DATA_SOURCE_ERROR,
            message=f"Error accessing {source.value}: {operation}",
            status_code=503,
            source=source,
            details=details,
            suggestions=suggestions,
        )


class GraphBuildError(GroundTruthError):
    """Raised when graph building fails."""

    def __init__(
        self,
        molecule_id: str,
        reason: str,
        partial_results: Optional[Dict[str, int]] = None,
    ):
        details = {"molecule_id": molecule_id, "reason": reason}
        if partial_results:
            details["partial_results"] = partial_results

        suggestions = [
            "Check if the molecule has known indications, MOA, or targets",
            "Try with a lower depth (depth=1 instead of depth=2)",
            "Verify the molecule name is the INN or common name",
        ]

        super().__init__(
            code=ErrorCode.GRAPH_BUILD_ERROR,
            message=f"Failed to build competitive graph for '{molecule_id}': {reason}",
            status_code=500,
            source=DataSource.INTERNAL,
            details=details,
            suggestions=suggestions,
        )


class ExportError(GroundTruthError):
    """Raised when export fails."""

    def __init__(
        self,
        export_type: str,
        reason: str,
        job_id: Optional[str] = None,
    ):
        details = {"export_type": export_type, "reason": reason}
        if job_id:
            details["job_id"] = job_id

        suggestions = [
            "Try a different export format",
            "For large datasets, try exporting smaller sections",
            "Check if the export job is still processing",
        ]

        super().__init__(
            code=ErrorCode.EXPORT_ERROR,
            message=f"Export failed: {reason}",
            status_code=500,
            source=DataSource.INTERNAL,
            details=details,
            suggestions=suggestions,
        )


class ValidationError(GroundTruthError):
    """Raised for request validation errors."""

    def __init__(
        self,
        field: str,
        reason: str,
        allowed_values: Optional[List[str]] = None,
    ):
        details = {"field": field, "reason": reason}
        if allowed_values:
            details["allowed_values"] = allowed_values

        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Validation error for '{field}': {reason}",
            status_code=400,
            details=details,
        )


class RateLimitError(GroundTruthError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        source: DataSource,
        retry_after: Optional[int] = None,
    ):
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after

        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message=f"Rate limit exceeded for {source.value}",
            status_code=429,
            source=source,
            details=details,
            suggestions=[f"Wait {retry_after} seconds before retrying" if retry_after else "Wait before retrying"],
        )


# Exception handler for FastAPI
async def ground_truth_error_handler(request: Request, exc: GroundTruthError) -> JSONResponse:
    """Handle GroundTruthError exceptions."""
    request_id = request.headers.get("X-Request-ID")
    error_response = exc.to_response(request_id)

    logger.error(
        f"GroundTruthError: {exc.code.value} - {exc.message}",
        extra={
            "code": exc.code.value,
            "source": exc.source.value if exc.source else None,
            "request_id": request_id,
            "details": exc.details,
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_response.model_dump(exclude_none=True)},
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    request_id = request.headers.get("X-Request-ID")

    logger.exception(f"Unexpected error: {exc}", extra={"request_id": request_id})

    error = ErrorDetail(
        code=ErrorCode.INTERNAL_ERROR.value,
        message="An unexpected error occurred. Please try again or contact support.",
        timestamp=datetime.utcnow().isoformat() + "Z",
        request_id=request_id,
    )

    return JSONResponse(
        status_code=500,
        content={"error": error.model_dump(exclude_none=True)},
    )


def raise_for_source_error(
    source: DataSource,
    response: Any,
    operation: str,
) -> None:
    """
    Raise appropriate error based on data source response.

    Use in API clients to convert failures to proper errors.
    """
    if hasattr(response, 'success') and not response.success:
        error_msg = getattr(response, 'error', 'Unknown error')
        raise DataSourceError(source, operation, error_msg)


def create_error_response(
    code: ErrorCode,
    message: str,
    status_code: int = 500,
    source: Optional[DataSource] = None,
    details: Optional[Dict[str, Any]] = None,
) -> HTTPException:
    """
    Create an HTTPException with standardized error format.

    Use for simple error cases where a full exception class isn't needed.
    """
    error = GroundTruthError(
        code=code,
        message=message,
        status_code=status_code,
        source=source,
        details=details,
    )

    return HTTPException(
        status_code=status_code,
        detail=error.to_response().model_dump(exclude_none=True),
    )
