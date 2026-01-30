#!/usr/bin/env python3
"""
Configure logging for TAVR Data Infrastructure.

This module provides centralized logging configuration for both development
and production environments.

Usage:
    from scripts.setup_logging import setup_logging

    # Development (console output)
    logger = setup_logging('my_module')

    # Production (file output)
    logger = setup_logging('my_module', production=True)
"""

import os
import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler


# Default log directory
DEFAULT_LOG_DIR = Path(__file__).parent.parent / 'logs'
PRODUCTION_LOG_DIR = Path('/var/log/edwards')


def get_log_dir(production: bool = False) -> Path:
    """Get the appropriate log directory."""
    if production:
        # Check if we can write to /var/log/edwards
        if PRODUCTION_LOG_DIR.exists() and os.access(PRODUCTION_LOG_DIR, os.W_OK):
            return PRODUCTION_LOG_DIR
        # Fall back to home directory
        fallback = Path.home() / '.edwards' / 'logs'
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_LOG_DIR


def setup_logging(
    name: str,
    level: int = logging.INFO,
    production: bool = False,
    log_to_console: bool = True,
    log_to_file: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Set up logging for a module.

    Args:
        name: Module name for the logger
        level: Logging level (default: INFO)
        production: If True, use production log directory
        log_to_console: If True, output to console
        log_to_file: If True, output to file
        max_bytes: Max file size before rotation
        backup_count: Number of backup files to keep

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Format
    if production:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler
    if log_to_file:
        log_dir = get_log_dir(production)
        log_file = log_dir / f'{name}.log'

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Also log errors to a separate file
        error_file = log_dir / f'{name}_error.log'
        error_handler = RotatingFileHandler(
            error_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)

    return logger


def setup_production_logging_directory():
    """
    Set up production logging directory with proper permissions.

    This should be run with sudo on the target system.

    Example:
        sudo python -c "from scripts.setup_logging import setup_production_logging_directory; setup_production_logging_directory()"
    """
    import pwd
    import grp

    log_dir = PRODUCTION_LOG_DIR

    if os.geteuid() != 0:
        print("This function requires root privileges.")
        print("Run with: sudo python -c \"from scripts.setup_logging import setup_production_logging_directory; setup_production_logging_directory()\"")
        return False

    try:
        # Create directory
        log_dir.mkdir(parents=True, exist_ok=True)

        # Set ownership to current user (for cron jobs)
        current_user = os.environ.get('SUDO_USER', 'root')
        try:
            uid = pwd.getpwnam(current_user).pw_uid
            gid = grp.getgrnam(current_user).gr_gid
        except KeyError:
            uid = 0
            gid = 0

        os.chown(log_dir, uid, gid)
        os.chmod(log_dir, 0o755)

        print(f"Created log directory: {log_dir}")
        print(f"Owner: {current_user}")
        return True

    except Exception as e:
        print(f"Failed to create log directory: {e}")
        return False


# Convenience loggers for common modules
def get_ingestion_logger(source_name: str, production: bool = False) -> logging.Logger:
    """Get a logger for ingestion modules."""
    return setup_logging(f'ingestion.{source_name}', production=production)


def get_api_logger(production: bool = False) -> logging.Logger:
    """Get a logger for API modules."""
    return setup_logging('api', production=production)


def get_sqlmesh_logger(production: bool = False) -> logging.Logger:
    """Get a logger for SQLMesh operations."""
    return setup_logging('sqlmesh', production=production)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Configure logging')
    parser.add_argument('--setup-production', action='store_true',
                        help='Set up production log directory (requires sudo)')
    parser.add_argument('--test', action='store_true',
                        help='Test logging configuration')

    args = parser.parse_args()

    if args.setup_production:
        setup_production_logging_directory()
    elif args.test:
        # Test logging
        logger = setup_logging('test', production=False)
        logger.info("Test INFO message")
        logger.warning("Test WARNING message")
        logger.error("Test ERROR message")
        print(f"\nLog files written to: {get_log_dir(False)}")
    else:
        parser.print_help()
