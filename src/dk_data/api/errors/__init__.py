"""
API Error Handlers

Centralized error handling for the DK Molecule Data Platform and Ground Truth Service.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

# Import from the parent errors.py module (Ground Truth errors)
import os
# We need to import from the sibling errors.py file which is now shadowed
# Load it directly
import importlib.util
_errors_py_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'errors.py')
if os.path.exists(_errors_py_path):
    _spec = importlib.util.spec_from_file_location("_ground_truth_errors", _errors_py_path)
    _gt_errors = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_gt_errors)

    # Re-export Ground Truth errors
    GroundTruthError = _gt_errors.GroundTruthError
    ground_truth_error_handler = _gt_errors.ground_truth_error_handler
    generic_error_handler = _gt_errors.generic_error_handler
    MoleculeNotFoundError = _gt_errors.MoleculeNotFoundError
    GraphBuildError = _gt_errors.GraphBuildError
    ExportError = _gt_errors.ExportError
    DataSource = _gt_errors.DataSource
    ErrorCode = _gt_errors.ErrorCode

from .data_platform_errors import (  # noqa: E402
    # Base exceptions
    DataPlatformError,
    NotFoundError,
    ConflictError,
    AuthenticationError,
    AuthorizationError,
    ServiceUnavailableError,

    # Domain-specific exceptions
    EntityResolutionError,
    QuarantineError,
    PipelineError,
    IngestionError,
    TransformationError,
    LifecycleError,
    OnboardingError,

    # Error handlers
    register_error_handlers,

    # Error response model
    ErrorResponse,
    ErrorDetail,
)

# Import validation/rate limit errors from data platform (renamed to avoid conflict)
from .data_platform_errors import (  # noqa: E402
    ValidationError as DataPlatformValidationError,
    RateLimitError as DataPlatformRateLimitError,
    DataSourceError as DataPlatformDataSourceError,
)

__all__ = [
    # Ground Truth errors (for backward compatibility)
    'GroundTruthError',
    'ground_truth_error_handler',
    'generic_error_handler',
    'MoleculeNotFoundError',
    'GraphBuildError',
    'ExportError',
    'DataSource',
    'ErrorCode',

    # Data Platform base exceptions
    'DataPlatformError',
    'DataPlatformValidationError',
    'NotFoundError',
    'ConflictError',
    'AuthenticationError',
    'AuthorizationError',
    'DataPlatformRateLimitError',
    'ServiceUnavailableError',

    # Data Platform domain-specific exceptions
    'EntityResolutionError',
    'QuarantineError',
    'PipelineError',
    'IngestionError',
    'TransformationError',
    'DataPlatformDataSourceError',
    'LifecycleError',
    'OnboardingError',

    # Error handlers
    'register_error_handlers',

    # Error response model
    'ErrorResponse',
    'ErrorDetail',
]
