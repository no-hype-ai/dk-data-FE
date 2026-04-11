"""Transform Run Prometheus Exporter.

Feature: 001-silver-medallion-rebuild
Task: T097 — Prometheus exporter for meta.transform_runs WAL and row metrics

Queries meta.transform_runs and exposes Prometheus gauges:
  - dk_data_transform_chunk_wal_bytes  (by procedure_name, chunk_position)
  - dk_data_transform_chunk_rows       (by procedure_name, chunk_position)

Run as a long-lived process on any pod with DB access.
"""

import logging
import os
import time

from prometheus_client import Gauge, start_http_server

from dk_data.ingestion.utils.database import get_connection

logger = logging.getLogger(__name__)

# Prometheus metrics
CHUNK_WAL_BYTES = Gauge(
    "dk_data_transform_chunk_wal_bytes",
    "WAL bytes consumed by a transform procedure chunk",
    ["procedure_name", "chunk_position"],
)

CHUNK_ROWS = Gauge(
    "dk_data_transform_chunk_rows",
    "Rows processed by a transform procedure chunk",
    ["procedure_name", "chunk_position"],
)

SCRAPE_ERRORS = Gauge(
    "dk_data_transform_metrics_scrape_errors_total",
    "Number of scrape errors when querying meta.transform_runs",
)


def collect_transform_metrics() -> None:
    """Query meta.transform_runs and update Prometheus gauges."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        procedure_name,
                        chunk_position,
                        wal_bytes,
                        rows_processed
                    FROM meta.transform_runs
                    WHERE started_at > NOW() - INTERVAL '24 hours'
                    ORDER BY procedure_name, chunk_position
                    """
                )
                rows = cur.fetchall()

        for procedure_name, chunk_position, wal_bytes, rows_processed in rows:
            labels = {
                "procedure_name": str(procedure_name or "unknown"),
                "chunk_position": str(chunk_position or 0),
            }
            CHUNK_WAL_BYTES.labels(**labels).set(wal_bytes or 0)
            CHUNK_ROWS.labels(**labels).set(rows_processed or 0)

        logger.debug("Collected metrics for %d transform run chunks", len(rows))
        SCRAPE_ERRORS.set(0)

    except Exception as e:
        logger.error("Failed to collect transform run metrics: %s", e)
        SCRAPE_ERRORS.inc()


def main() -> None:
    """Start the Prometheus exporter and collect metrics on an interval."""
    port = int(os.getenv("METRICS_PORT", "9090"))
    interval = int(os.getenv("SCRAPE_INTERVAL_SECONDS", "30"))

    logging.basicConfig(level=logging.INFO)
    logger.info("Starting transform run metrics exporter on port %d", port)

    start_http_server(port)

    while True:
        collect_transform_metrics()
        time.sleep(interval)


if __name__ == "__main__":
    main()
