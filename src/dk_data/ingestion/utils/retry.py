"""Exponential backoff retry utilities."""

import time
import logging
from functools import wraps
from typing import Callable, TypeVar, Any, Optional
import os

from dotenv import load_dotenv

load_dotenv('.env.local')
load_dotenv('.env', override=True)

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Default retry configuration from environment
DEFAULT_MAX_ATTEMPTS = int(os.getenv('MAX_RETRY_ATTEMPTS', '3'))
DEFAULT_INITIAL_DELAY = int(os.getenv('INITIAL_RETRY_DELAY_SECONDS', '60'))


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, message: str, last_exception: Optional[Exception] = None):
        super().__init__(message)
        self.last_exception = last_exception


def retry_with_backoff(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    max_delay: float = 900.0,  # 15 minutes max
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[Exception, int, float], None]] = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for exponential backoff retry logic.

    Per clarification: max 3 attempts over ~15 minutes total.
    Default: 60s -> 120s -> 240s = 7 minutes wait time + execution time

    Args:
        max_attempts: Maximum number of retry attempts (default: 3).
        initial_delay: Initial delay in seconds before first retry (default: 60).
        max_delay: Maximum delay cap in seconds (default: 900 = 15 minutes).
        backoff_factor: Multiplier for delay after each retry (default: 2.0).
        exceptions: Tuple of exception types to catch and retry.
        on_retry: Optional callback function called on each retry with
                  (exception, attempt_number, next_delay).

    Returns:
        Decorated function with retry logic.

    Example:
        @retry_with_backoff(max_attempts=3, initial_delay=60)
        def fetch_hrsa_data(api_url: str):
            response = requests.get(api_url, timeout=30)
            response.raise_for_status()
            return response.json()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts. "
                            f"Last error: {e}"
                        )
                        raise RetryExhaustedError(
                            f"All {max_attempts} retry attempts exhausted for {func.__name__}",
                            last_exception=e
                        ) from e

                    # Calculate next delay with cap
                    next_delay = min(delay, max_delay)

                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {next_delay:.1f}s..."
                    )

                    # Call optional retry callback
                    if on_retry:
                        on_retry(e, attempt, next_delay)

                    time.sleep(next_delay)
                    delay *= backoff_factor

            # Should not reach here, but just in case
            raise RetryExhaustedError(
                f"Unexpected state in retry logic for {func.__name__}",
                last_exception=last_exception
            )

        return wrapper
    return decorator


def retry_on_connection_error(func: Callable[..., T]) -> Callable[..., T]:
    """
    Shortcut decorator for retrying on common connection/network errors.

    Uses default retry settings: 3 attempts, 60s initial delay.
    """
    import requests
    import urllib.error
    import socket

    connection_errors = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.HTTPError,
        urllib.error.URLError,
        socket.timeout,
        ConnectionError,
        TimeoutError,
    )

    return retry_with_backoff(exceptions=connection_errors)(func)


class RetryContext:
    """
    Context manager for retry logic without decorator.

    Example:
        with RetryContext(max_attempts=3) as retry:
            while retry.should_continue():
                try:
                    result = fetch_data()
                    break
                except Exception as e:
                    retry.handle_exception(e)
    """

    def __init__(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = 900.0,
        backoff_factor: float = 2.0,
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.attempt = 0
        self.delay = initial_delay
        self.last_exception: Optional[Exception] = None

    def __enter__(self) -> 'RetryContext':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False  # Don't suppress exceptions

    def should_continue(self) -> bool:
        """Check if more attempts are available."""
        return self.attempt < self.max_attempts

    def handle_exception(self, exception: Exception) -> None:
        """Handle an exception and wait before next attempt."""
        self.last_exception = exception
        self.attempt += 1

        if self.attempt >= self.max_attempts:
            raise RetryExhaustedError(
                f"All {self.max_attempts} retry attempts exhausted",
                last_exception=exception
            ) from exception

        wait_time = min(self.delay, self.max_delay)
        logger.warning(
            f"Attempt {self.attempt}/{self.max_attempts} failed: {exception}. "
            f"Retrying in {wait_time:.1f}s..."
        )

        time.sleep(wait_time)
        self.delay *= self.backoff_factor
