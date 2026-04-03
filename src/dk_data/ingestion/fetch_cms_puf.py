#!/usr/bin/env python3
"""Fetch and load CMS PUF datasets discovered via CMS DCAT catalog.

Usage:
    python -m dk_data.ingestion.fetch_cms_puf --all
    python -m dk_data.ingestion.fetch_cms_puf --source cms_physician_puf --year 2024
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
import zipfile
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import sql

from dk_data.ingestion.downloaders.cms_downloader import (
    CMS_DATASET_REGISTRY,
    download_cms_file,
)

logger = logging.getLogger(__name__)

HASH_STATE_PATH = Path(os.getenv("CMS_DOWNLOAD_DIR", "/tmp/cms_downloads")) / "_cms_puf_load_state.json"
CHUNK_SIZE = 10_000


def _db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        dbname=os.getenv("POSTGRES_DB"),
    )


def _slug_identifier(name: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z_]+", "_", name.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "column"
    if cleaned[0].isdigit():
        cleaned = f"c_{cleaned}"
    return cleaned[:63]


def _normalize_headers(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    normalized: list[str] = []
    for idx, col in enumerate(columns):
        base = _slug_identifier(str(col) if col is not None else f"column_{idx + 1}")
        count = seen.get(base, 0) + 1
        seen[base] = count
        normalized.append(base if count == 1 else f"{base}_{count}")
    return normalized


def _compute_file_hash(filepath: Path) -> str:
    digest = hashlib.md5()
    with filepath.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _state_key(source_key: str, year: int | None) -> str:
    return f"{source_key}:{year if year is not None else 'latest'}"


def _load_hash_state() -> dict[str, str]:
    if not HASH_STATE_PATH.exists():
        return {}
    try:
        return json.loads(HASH_STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_hash_state(state: dict[str, str]) -> None:
    HASH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    HASH_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def _table_has_rows(cur, source_key: str) -> bool:
    cur.execute(
        sql.SQL("SELECT EXISTS (SELECT 1 FROM {}.{} LIMIT 1)").format(
            sql.Identifier("hcs_raw"),
            sql.Identifier(source_key),
        )
    )
    return bool(cur.fetchone()[0])


def _refresh_log_exists(cur) -> bool:
    cur.execute("SELECT to_regclass('meta.refresh_log')")
    return cur.fetchone()[0] is not None


def _log_refresh(conn, source_key: str, status: str, records_fetched: int, error_message: str | None = None) -> None:
    try:
        with conn.cursor() as cur:
            if not _refresh_log_exists(cur):
                return

            cur.execute(
                """
                SELECT source_id
                FROM meta.data_sources
                WHERE source_name = %s
                """,
                (source_key,),
            )
            row = cur.fetchone()
            if not row:
                logger.warning("meta.data_sources missing source '%s'; skipping refresh log", source_key)
                return

            source_id = row[0]
            cur.execute(
                """
                INSERT INTO meta.refresh_log (
                    source_id,
                    refresh_started_at,
                    refresh_completed_at,
                    status,
                    records_fetched,
                    records_inserted,
                    records_updated,
                    error_message
                ) VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s)
                """,
                (
                    source_id,
                    datetime.utcnow(),
                    status,
                    records_fetched,
                    records_fetched if status == "success" else 0,
                    0,
                    error_message,
                ),
            )

            cur.execute(
                """
                UPDATE meta.data_sources
                SET last_refresh_attempt = NOW(),
                    last_refresh_status = %s,
                    last_successful_refresh = CASE
                        WHEN %s IN ('success', 'partial') THEN NOW()
                        ELSE last_successful_refresh
                    END,
                    record_count = CASE
                        WHEN %s = 'success' THEN COALESCE(record_count, 0) + %s
                        ELSE record_count
                    END
                WHERE source_id = %s
                """,
                (status, status, status, records_fetched, source_id),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.warning("Failed to write meta.refresh_log for %s: %s", source_key, exc)


def _resolve_csv_path(filepath: Path) -> Path:
    if filepath.suffix.lower() == ".csv":
        return filepath

    if filepath.suffix.lower() != ".zip":
        return filepath

    extract_dir = filepath.parent / f"{filepath.stem}_extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(filepath, "r") as zip_file:
        csv_members = [m for m in zip_file.infolist() if m.filename.lower().endswith(".csv")]
        if not csv_members:
            raise ValueError(f"ZIP has no CSV members: {filepath}")
        largest = max(csv_members, key=lambda m: m.file_size)
        zip_file.extract(largest, extract_dir)
        return extract_dir / largest.filename


def _create_table_if_needed(cur, source_key: str, csv_columns: list[str]) -> None:
    column_defs = [sql.SQL("{} TEXT").format(sql.Identifier(col)) for col in csv_columns]
    column_defs.extend(
        [
            sql.SQL("{} BIGSERIAL PRIMARY KEY").format(sql.Identifier("id")),
            sql.SQL("{} INT").format(sql.Identifier("_source_year")),
            sql.SQL("{} TEXT").format(sql.Identifier("_source_hash")),
            sql.SQL("{} TEXT").format(sql.Identifier("_source_file")),
            sql.SQL("{} TIMESTAMPTZ NOT NULL DEFAULT NOW()").format(sql.Identifier("_loaded_at")),
        ]
    )

    cur.execute(
        sql.SQL("CREATE SCHEMA IF NOT EXISTS {};").format(sql.Identifier("hcs_raw"))
    )

    cur.execute(
        sql.SQL("CREATE TABLE IF NOT EXISTS {}.{} ({})").format(
            sql.Identifier("hcs_raw"),
            sql.Identifier(source_key),
            sql.SQL(", ").join(column_defs),
        )
    )


def _table_has_non_pk_unique_index(cur, source_key: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_index i
            JOIN pg_class t ON t.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'hcs_raw'
              AND t.relname = %s
              AND i.indisunique = TRUE
              AND i.indisprimary = FALSE
        )
        """,
        (source_key,),
    )
    return bool(cur.fetchone()[0])


def _bulk_load_csv(conn, source_key: str, csv_path: Path, source_year: int | None) -> int:
    headers_df = pd.read_csv(csv_path, nrows=0)
    csv_columns = _normalize_headers([str(c) for c in headers_df.columns])

    with conn.cursor() as cur:
        _create_table_if_needed(cur, source_key, csv_columns)
        temp_name = f"tmp_{source_key[:40]}"
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {};").format(sql.Identifier(temp_name)))
        cur.execute(
            sql.SQL("CREATE TEMP TABLE {} (LIKE {}.{} INCLUDING DEFAULTS)").format(
                sql.Identifier(temp_name),
                sql.Identifier("hcs_raw"),
                sql.Identifier(source_key),
            )
        )
        conn.commit()

    file_hash = _compute_file_hash(csv_path)
    load_columns = csv_columns + ["_source_year", "_source_hash", "_source_file"]
    copy_stmt = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"
    ).format(
        sql.Identifier(temp_name),
        sql.SQL(", ").join(sql.Identifier(c) for c in load_columns),
    )

    inserted_rows = 0
    chunks = pd.read_csv(csv_path, dtype=str, chunksize=CHUNK_SIZE)

    with conn.cursor() as cur:
        for chunk in chunks:
            chunk.columns = csv_columns
            chunk = chunk.fillna("")
            chunk["_source_year"] = source_year
            chunk["_source_hash"] = file_hash
            chunk["_source_file"] = csv_path.name

            buf = StringIO()
            chunk[load_columns].to_csv(
                buf,
                index=False,
                header=False,
                quoting=csv.QUOTE_MINIMAL,
                lineterminator="\n",
            )
            buf.seek(0)
            cur.copy_expert(copy_stmt.as_string(cur), buf)

        conflict_clause = sql.SQL(" ON CONFLICT DO NOTHING") if _table_has_non_pk_unique_index(cur, source_key) else sql.SQL("")
        insert_stmt = sql.SQL(
            "INSERT INTO {}.{} ({}) "
            "SELECT {} FROM {}{}"
        ).format(
            sql.Identifier("hcs_raw"),
            sql.Identifier(source_key),
            sql.SQL(", ").join(sql.Identifier(c) for c in load_columns),
            sql.SQL(", ").join(sql.Identifier(c) for c in load_columns),
            sql.Identifier(temp_name),
            conflict_clause,
        )
        cur.execute(insert_stmt)
        inserted_rows = cur.rowcount

    conn.commit()
    return inserted_rows


def process_source(source_key: str, year: int | None = None) -> dict:
    if source_key not in CMS_DATASET_REGISTRY:
        raise ValueError(f"Unknown source: {source_key}")

    source_cfg = CMS_DATASET_REGISTRY[source_key]
    if source_cfg.get("not_available"):
        print(f"[{source_key}] skipped (not available)")
        return {"source": source_key, "status": "skipped", "records_fetched": 0, "reason": "not_available"}

    filepath_str, _ = download_cms_file(source_key, year=year)
    if not filepath_str:
        print(f"[{source_key}] warning: download failed, skipping")
        return {"source": source_key, "status": "failed", "records_fetched": 0, "error": "download_failed"}

    filepath = Path(filepath_str)
    csv_path = _resolve_csv_path(filepath)
    file_hash = _compute_file_hash(csv_path)
    state = _load_hash_state()
    key = _state_key(source_key, year)

    conn = _db_connection()
    try:
        with conn.cursor() as cur:
            _create_table_if_needed(cur, source_key, _normalize_headers(list(pd.read_csv(csv_path, nrows=0).columns)))
            has_data = _table_has_rows(cur, source_key)
            conn.commit()

        if has_data and state.get(key) == file_hash:
            print(f"[{source_key}] no new data")
            _log_refresh(conn, source_key, "success", 0)
            return {"source": source_key, "status": "success", "records_fetched": 0, "skipped": "no_new_data"}

        rows = _bulk_load_csv(conn, source_key, csv_path, year)
        state[key] = file_hash
        _save_hash_state(state)

        _log_refresh(conn, source_key, "success", rows)
        print(f"[{source_key}] {rows} rows loaded → hcs_raw.{source_key}")
        return {"source": source_key, "status": "success", "records_fetched": rows}
    except pd.errors.ParserError as exc:
        conn.rollback()
        _log_refresh(conn, source_key, "failed", 0, str(exc))
        print(f"[{source_key}] error parsing CSV: {exc}")
        return {"source": source_key, "status": "failed", "records_fetched": 0, "error": str(exc)}
    except Exception as exc:
        conn.rollback()
        _log_refresh(conn, source_key, "failed", 0, str(exc))
        print(f"[{source_key}] error: {exc}")
        return {"source": source_key, "status": "failed", "records_fetched": 0, "error": str(exc)}
    finally:
        conn.close()


def run_sources(source_keys: list[str], year: int | None = None, continue_on_error: bool = True) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for source_key in source_keys:
        try:
            results[source_key] = process_source(source_key, year=year)
        except Exception as exc:
            results[source_key] = {
                "source": source_key,
                "status": "failed",
                "records_fetched": 0,
                "error": str(exc),
            }
            print(f"[{source_key}] error: {exc}")
            if not continue_on_error:
                raise
    return results


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and load CMS PUF datasets into hcs_raw")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source", help="Specific source key from CMS_DATASET_REGISTRY")
    group.add_argument("--all", action="store_true", help="Process all CMS PUF sources")
    parser.add_argument("--year", type=int, help="Optional service year for CMS downloader")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logs")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if args.source:
        if args.source not in CMS_DATASET_REGISTRY:
            print(f"Error: unknown source '{args.source}'")
            return 1
        result = process_source(args.source, year=args.year)
        return 0 if result.get("status") in {"success", "skipped"} else 1

    source_keys = list(CMS_DATASET_REGISTRY.keys())
    results = run_sources(source_keys, year=args.year, continue_on_error=True)
    failed = [k for k, v in results.items() if v.get("status") == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
