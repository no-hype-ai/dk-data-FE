"""
Logging configuration for dk-data molecule platform.

This module delegates to dk_data.observability for centralized logging.
Kept for backwards compatibility with existing imports.
"""

# Re-export from observability module
try:
    from dk_data.observability.logging import (
        setup_logging,
        get_logger,
        configure_structlog,
    )
except ImportError:
    # Fallback for when observability is not available
    import logging

    def setup_logging(service_name: str = "dk-data", log_level: str = "INFO") -> None:
        """Configure basic logging when observability module unavailable."""
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    def get_logger(name: str) -> logging.Logger:
        """Get a logger instance."""
        return logging.getLogger(name)

    def configure_structlog() -> None:
        """No-op when observability unavailable."""
        pass


__all__ = ["setup_logging", "get_logger", "configure_structlog"]
