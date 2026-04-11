"""Job Trigger Handlers — meta.job_runs integration.

Feature: 001-silver-medallion-rebuild
Task: T192 — INSERT INTO meta.job_runs on every fetcher/transform invocation

Wraps job execution with lifecycle tracking in meta.job_runs.
Call record_job_start() before invoking the fetcher/transform and
record_job_end() after it completes (or fails).
"""

import logging
import os
import socket
from contextlib import contextmanager
from typing import Generator, Optional

from dk_data.ingestion.utils.database import get_connection

logger = logging.getLogger(__name__)

_POD_NAME = os.getenv("HOSTNAME", socket.gethostname())


def record_job_start(job_name: str) -> Optional[int]:
    """Insert a running row in meta.job_runs and return the run_id.

    Args:
        job_name: Name of the job/fetcher being invoked.

    Returns:
        run_id from meta.job_runs, or None if the insert fails.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meta.job_runs (job_name, status, pod_name)
                    VALUES (%s, 'running', %s)
                    RETURNING run_id
                    """,
                    (job_name, _POD_NAME),
                )
                run_id = cur.fetchone()[0]
            conn.commit()
        logger.debug("Started job run %d for %s", run_id, job_name)
        return run_id
    except Exception as e:
        logger.warning("Failed to record job start for %s: %s", job_name, e)
        return None


def record_job_end(
    run_id: Optional[int],
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """Update meta.job_runs with final status and ended_at timestamp.

    Args:
        run_id: The run_id returned by record_job_start(). If None, no-ops.
        status: Final status: 'completed', 'failed', or 'killed'.
        error_message: Optional error description on failure.
    """
    if run_id is None:
        return

    if status not in ("completed", "failed", "killed"):
        status = "failed"

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE meta.job_runs
                    SET status = %s,
                        ended_at = NOW(),
                        error_message = %s
                    WHERE run_id = %s
                    """,
                    (status, error_message, run_id),
                )
            conn.commit()
        logger.debug("Completed job run %d with status %s", run_id, status)
    except Exception as e:
        logger.warning("Failed to record job end for run_id=%s: %s", run_id, e)


@contextmanager
def track_job_run(job_name: str) -> Generator[None, None, None]:
    """Context manager that wraps a job invocation with meta.job_runs tracking.

    Usage:
        with track_job_run("uspto_patents"):
            fetcher.fetch()

    On success: status set to 'completed'.
    On exception: status set to 'failed' with error_message.
    """
    run_id = record_job_start(job_name)
    try:
        yield
        record_job_end(run_id, "completed")
    except Exception as exc:
        record_job_end(run_id, "failed", error_message=str(exc)[:2000])
        raise
