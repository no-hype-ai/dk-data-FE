"""Persistent fetch checkpoint helpers.

Provides save/load/clear for per-source pagination state stored in
meta.fetch_checkpoints. Used by long-running fetchers (ChEMBL, BindingDB)
so they can resume from the last committed offset after a pod restart,
OOMKill, or timeout.

Usage:
    from dk_data.ingestion.utils.checkpoint import load_checkpoint, save_checkpoint, clear_checkpoint

    # On start: check for a prior checkpoint
    cp = load_checkpoint("chembl_molecules")
    start_offset = cp.get("offset", 0) if cp else 0

    # After each committed batch:
    save_checkpoint("chembl_molecules", {"offset": current_offset, "total": total_count})

    # On successful completion:
    clear_checkpoint("chembl_molecules")
"""

import logging
from typing import Any, Dict, Optional

from .database import get_connection

logger = logging.getLogger(__name__)


def load_checkpoint(source_name: str) -> Optional[Dict[str, Any]]:
    """Return the stored checkpoint for source_name, or None if absent/expired."""
    sql = """
        SELECT checkpoint_data
        FROM meta.fetch_checkpoints
        WHERE source_name = %s
          AND expires_at > NOW()
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (source_name,))
                row = cur.fetchone()
                if row:
                    logger.info(
                        "Checkpoint loaded for %s: %s", source_name, row[0]
                    )
                    return row[0]
    except Exception as exc:
        # Never let checkpoint logic crash the fetcher
        logger.warning("Failed to load checkpoint for %s: %s", source_name, exc)
    return None


def save_checkpoint(source_name: str, data: Dict[str, Any]) -> None:
    """Upsert checkpoint data for source_name, resetting the 7-day expiry."""
    sql = """
        INSERT INTO meta.fetch_checkpoints (source_name, checkpoint_data, updated_at, expires_at)
        VALUES (%s, %s::JSONB, NOW(), NOW() + INTERVAL '7 days')
        ON CONFLICT (source_name)
        DO UPDATE SET
            checkpoint_data = EXCLUDED.checkpoint_data,
            updated_at      = NOW(),
            expires_at      = NOW() + INTERVAL '7 days'
    """
    try:
        import json
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (source_name, json.dumps(data)))
            conn.commit()
    except Exception as exc:
        logger.warning("Failed to save checkpoint for %s: %s", source_name, exc)


def clear_checkpoint(source_name: str) -> None:
    """Delete the checkpoint for source_name after a successful run."""
    sql = "DELETE FROM meta.fetch_checkpoints WHERE source_name = %s"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (source_name,))
            conn.commit()
        logger.info("Checkpoint cleared for %s", source_name)
    except Exception as exc:
        logger.warning("Failed to clear checkpoint for %s: %s", source_name, exc)
