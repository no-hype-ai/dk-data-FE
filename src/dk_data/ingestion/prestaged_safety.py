"""View-safety pre-flight for the 005-prestaged-hydration feature (FR-015).

Prevents ``pg_restore`` from blasting over SQLMesh-managed views. Same
``relkind='r'`` pattern that migration 227 had to adopt after the
``mol_silver.publications`` / ``mol_silver.bioactivity`` incident.

Active tag: ``[VIEWSAFE]``.
"""

from __future__ import annotations

from typing import Any


def is_restorable_target(conn: Any, schema: str, table: str) -> bool:
    """True iff restoring into ``schema.table`` is safe.

    Safe means one of:
      - the relation exists and ``pg_class.relkind = 'r'`` (a real table);
      - the relation does not exist yet — the first chunk of a multi-chunk
        restore will create it.

    Unsafe means the relation exists but is a view, materialized view,
    foreign table, or any other relkind — a ``pg_restore`` against one
    of those is exactly the failure migration 227 hit. We refuse.

    The caller is expected to record ``status='skipped_view'`` in
    ``meta.transform_runs`` for the LoadStep when this returns False.

    Args:
        conn: a live psycopg2 connection. Caller owns transaction state.
        schema: target schema name.
        table: target relation name.

    Returns:
        True when safe to restore; False when the relation exists and
        is not a plain table.
    """
    sql = """
        SELECT c.relkind
          FROM pg_class c
          JOIN pg_namespace n ON c.relnamespace = n.oid
         WHERE n.nspname = %s
           AND c.relname = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (schema, table))
        row = cur.fetchone()
    if row is None:
        # Relation doesn't exist — first chunk will create it. Safe.
        return True
    relkind = row[0]
    return relkind == "r"
