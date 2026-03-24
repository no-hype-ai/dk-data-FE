#!/usr/bin/env python3
"""SQLMesh scheduler loop with advisory lock.

Replaces the bare `sqlmesh run` daemon. Runs one SQLMesh pass every
INTERVAL_SECONDS, skipping the pass if the job-trigger pipeline is
currently holding the advisory lock (key 42424242).

This prevents the deadlock pattern where:
  - scheduler and job-trigger both run `sqlmesh run / run --select-model`
    on the same physical tables simultaneously
  - multiple DELETE WHERE TRUE + MERGE operations pile up and lock each other
"""
import asyncio
import os
import subprocess
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sqlmesh-scheduler")

LOCK_KEY       = 42424242
INTERVAL       = int(os.getenv("SQLMESH_INTERVAL_SECONDS", "900"))   # 15 min default
SQLMESH_PATHS  = os.getenv("SQLMESH_PATHS", "/app/sqlmesh")
GATEWAY        = os.getenv("SQLMESH_GATEWAY", "local")


def get_dsn() -> str:
    host     = os.getenv("POSTGRES_HOST", "postgres")
    port     = os.getenv("POSTGRES_PORT", "5432")
    db       = os.getenv("POSTGRES_DB", "dk_data")
    user     = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


async def try_run_once() -> None:
    import asyncpg
    dsn = get_dsn()
    conn = await asyncpg.connect(dsn)
    try:
        acquired = await conn.fetchval("SELECT pg_try_advisory_lock($1)", LOCK_KEY)
        if not acquired:
            log.info("Advisory lock held by job-trigger — skipping this cycle.")
            return

        log.info("Lock acquired — running sqlmesh …")
        result = subprocess.run(
            ["sqlmesh", "--paths", SQLMESH_PATHS, "--gateway", GATEWAY,
             "run", "--ignore-cron"],
            capture_output=True, text=True, timeout=3600,
            env={**os.environ, "OTEL_SDK_DISABLED": "true"},
        )
        if result.returncode == 0:
            log.info("sqlmesh run completed successfully.")
        else:
            log.warning(f"sqlmesh run exited {result.returncode}:\n{result.stderr[-500:]}")
    finally:
        try:
            await conn.execute("SELECT pg_advisory_unlock($1)", LOCK_KEY)
        except Exception:
            pass
        await conn.close()


async def main() -> None:
    log.info(f"SQLMesh scheduler loop starting (interval={INTERVAL}s, lock_key={LOCK_KEY})")
    while True:
        try:
            await try_run_once()
        except Exception as exc:
            log.error(f"Scheduler cycle error: {exc}")
        log.info(f"Sleeping {INTERVAL}s until next cycle …")
        await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
