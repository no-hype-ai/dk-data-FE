"""Startup secret validation for dk-data platform.

Feature: 012-platform-hardening (US5)

Validates that required environment variables / secrets are present
and logs clear errors for any that are missing or empty.
"""

import logging
import os
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# Required secrets — platform will not function without these
REQUIRED_SECRETS = [
    ("POSTGRES_HOST", "PostgreSQL server hostname"),
    ("POSTGRES_PORT", "PostgreSQL server port"),
    ("POSTGRES_USER", "PostgreSQL username"),
    ("POSTGRES_PASSWORD", "PostgreSQL password"),
    ("POSTGRES_DB", "PostgreSQL database name"),
]

# Credential-gated secrets — specific data sources need these
OPTIONAL_SECRETS = [
    ("JWT_SECRET", "PostgREST JWT signing secret"),
    ("NCBI_API_KEY", "NCBI E-utilities API key"),
    ("DRUGBANK_API_KEY", "DrugBank API access key"),
    ("EPO_CONSUMER_KEY", "EPO OPS OAuth2 client key"),
    ("EPO_CONSUMER_SECRET", "EPO OPS OAuth2 client secret"),
    ("USPTO_API_KEY", "USPTO PatentSearch API key"),
    ("USPTO_TSDR_API_KEY", "USPTO TSDR trademark case status API key"),
    ("EUIPO_API_KEY", "EUIPO eSearch/TMview API key"),
    ("EUIPO_SECRET_KEY", "EUIPO eSearch/TMview API secret"),
    ("SEC_EDGAR_USER_AGENT", "SEC EDGAR User-Agent header"),
    ("ANTHROPIC_API_KEY", "Claude SDK API key"),
    ("OTEL_EXPORTER_OTLP_ENDPOINT", "OpenTelemetry collector endpoint"),
]


def validate_secrets(
    required: List[Tuple[str, str]] = None,
    optional: List[Tuple[str, str]] = None,
) -> Dict[str, any]:
    """Validate that required secrets are present in the environment.

    Args:
        required: List of (name, description) tuples for required secrets.
        optional: List of (name, description) tuples for optional secrets.

    Returns:
        Dict with keys: valid (bool), missing_required, missing_optional, present.
    """
    required = required or REQUIRED_SECRETS
    optional = optional or OPTIONAL_SECRETS

    missing_required = []
    missing_optional = []
    present = []

    for name, description in required:
        value = os.environ.get(name)
        if not value or not value.strip():
            missing_required.append(name)
            logger.error(f"MISSING REQUIRED SECRET: {name} — {description}")
        else:
            present.append(name)

    for name, description in optional:
        value = os.environ.get(name)
        if not value or not value.strip():
            missing_optional.append(name)
            logger.warning(f"Missing optional secret: {name} — {description}")
        else:
            present.append(name)

    is_valid = len(missing_required) == 0

    if is_valid:
        logger.info(
            f"Secret validation passed: {len(present)} secrets present, "
            f"{len(missing_optional)} optional secrets missing"
        )
    else:
        logger.error(
            f"Secret validation FAILED: {len(missing_required)} required secrets missing: "
            f"{', '.join(missing_required)}"
        )

    return {
        "valid": is_valid,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "present": present,
    }
