"""
CronJob Completion Reporting Utility

Feature: 013-dk-data-observability (T017)

Async function that POSTs a JobCompletionReport to the job-trigger service.
Used by CronJob entrypoints to report metrics after execution.
"""

import os
import logging

logger = logging.getLogger(__name__)


async def report_completion(
    job_name: str,
    status: str,
    duration_seconds: float,
    records_processed: int = 0,
    source_name: str = None,
    error_message: str = None,
) -> None:
    """
    Report CronJob completion to the job-trigger metrics endpoint.

    Args:
        job_name: Name of the CronJob (matches K8s CronJob metadata.name)
        status: Job outcome ("success" or "failure")
        duration_seconds: Total job execution time in seconds
        records_processed: Number of records ingested/transformed
        source_name: Human-readable data source name (for data_source metrics)
        error_message: Error details if status is failure

    Note:
        Catches and logs connection errors without raising, so CronJob
        completion is never blocked by reporting failures.
    """
    import httpx

    namespace = os.environ.get("K8S_NAMESPACE", "dk-data-prod")
    trigger_url = f"http://job-trigger.{namespace}.svc.cluster.local:8000"

    payload = {
        "job_name": job_name,
        "status": status,
        "duration_seconds": duration_seconds,
        "records_processed": records_processed,
    }
    if source_name:
        payload["source_name"] = source_name
    if error_message:
        payload["error_message"] = error_message

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{trigger_url}/api/v1/monitoring/job-complete",
                json=payload,
            )
            resp.raise_for_status()
            logger.info(f"Reported completion for {job_name}: {status}")
    except Exception as e:
        logger.warning(f"Failed to report completion for {job_name}: {e}")
