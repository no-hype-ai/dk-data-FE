"""Download integrity pipeline — meta.artifact_provenance writer.

Feature: Horizon 2 / plan §C.4.

What this module does
---------------------
Every artifact downloaded by an ingestion fetcher should, after its sha256
has been computed, call:

    writer = ArtifactProvenanceWriter()  # or reuse a long-lived one
    writer.record(
        source_name="cms_part_d_spending",
        source_url=url,
        local_path=str(cache_path),
        headers_dict=response.headers,           # requests.Response.headers or similar
        bytes_written=written,
        sha256=sha256_hex,
    )

The writer inserts a row into ``meta.artifact_provenance`` capturing the
HTTP headers that govern change-detection (``Content-Length``, ``ETag``,
``Last-Modified``), the computed sha256, and whether the bytes on disk
match the header-advertised size.

For every call it also:
  * Looks up the most-recent prior row for the same ``(source_name,
    source_url)``. If present and sha256 differs, the new row is linked
    via ``prior_provenance_id`` and ``changed_from_prior`` is set to
    ``True``; ``dk_artifact_changed_total{source}`` is incremented.
  * Returns the inserted row as a dict so the caller can log the
    ``provenance_id`` alongside its own structured output.

Size-match rule
---------------
``size_match = (Content-Length IS NULL) OR (Content-Length == bytes_written)``

A ``None`` Content-Length is NOT a failure — not all upstreams set it
(chunked transfer, dynamic content). The column exists so ``size_match``
is recomputable server-side without re-reading the header.

FR-030 compliance
-----------------
The connection is obtained via the sanctioned pool helpers in
``dk_data.ingestion.utils.database`` (``get_connection_pool`` and
``init_connection_pool``). Callers may also inject a pre-built
connection at construction time (useful for tests and for orchestrators
that already own a handle). Raw connection construction outside
``database.py`` is a CI failure (T003 grep gate).

Failure handling
----------------
Per plan §C.4: a provenance-write failure MUST NOT fail the download.
Callers should use :meth:`record_swallow` (or catch exceptions from
:meth:`record`). The swallower emits
``dk_artifact_provenance_write_errors_total{source}`` so drift is
visible even when writes silently miss.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

import psycopg2
import psycopg2.extras

from dk_data.ingestion.utils.database import (
    get_connection_pool,
    init_connection_pool,
)
from dk_data.observability.metrics import (
    DK_ARTIFACT_CHANGED_TOTAL,
    DK_ARTIFACT_PROVENANCE_WRITE_ERRORS_TOTAL,
)

logger = logging.getLogger(__name__)

# Keys we care about from an HTTP response's headers dict. Headers are
# case-insensitive on the wire but dict access is case-sensitive in Python;
# _get_header normalises via lower-case lookup of the whole mapping.
_HEADER_CONTENT_LENGTH = "content-length"
_HEADER_ETAG = "etag"
_HEADER_LAST_MODIFIED = "last-modified"


def _get_header(headers: Mapping[str, Any], name: str) -> Optional[str]:
    """Case-insensitive header lookup that handles both dict + HTTPHeaderDict.

    ``requests.Response.headers`` is ``CaseInsensitiveDict`` so direct
    ``headers.get("Content-Length")`` works; plain ``dict`` inputs from
    tests / alternate HTTP libs need a scan. We don't want ``record()``
    to be fragile about which flavour the caller passes.
    """
    if headers is None:
        return None
    # Fast path for CaseInsensitiveDict / any mapping with case-insensitive get.
    try:
        v = headers.get(name)  # type: ignore[attr-defined]
        if v is not None:
            return str(v)
    except Exception:
        pass
    # Fallback: linear scan for a case-insensitive match.
    target = name.lower()
    for key in headers:
        if str(key).lower() == target:
            val = headers[key]
            return None if val is None else str(val)
    return None


def _parse_content_length(raw: Optional[str]) -> Optional[int]:
    """Parse the Content-Length header to an int, returning None on any oddity."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or not s.isdigit():
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


class ArtifactProvenanceWriter:
    """Records artifact download provenance into ``meta.artifact_provenance``.

    Holds a single psycopg2 connection obtained from ``build_dsn()`` (FR-030).
    Callers can either share one writer across a batch of downloads, or
    construct a new one per-download — the table-level indexes make either
    usage pattern fine at today's volumes.

    Example
    -------
    .. code-block:: python

        writer = ArtifactProvenanceWriter()
        try:
            row = writer.record(
                source_name="cms_part_d_spending",
                source_url=url,
                local_path=str(path),
                headers_dict=resp.headers,
                bytes_written=written,
                sha256=sha256_hex,
            )
            logger.info("provenance_id=%d changed=%s", row["provenance_id"], row["changed_from_prior"])
        finally:
            writer.close()
    """

    def __init__(self, conn: Optional[psycopg2.extensions.connection] = None) -> None:
        """Initialise the writer.

        Args:
            conn: Optional pre-built connection (useful for tests that inject
                a mock, or orchestrators that already own a handle). When
                ``None`` (the production path), a connection is leased from
                the shared pool via ``get_connection_pool()``. The pool is
                lazy-initialised on first use if needed.
        """
        self._owns_conn = False
        if conn is None:
            try:
                pool = get_connection_pool()
            except RuntimeError:
                init_connection_pool()
                pool = get_connection_pool()
            conn = pool.getconn()
            conn.autocommit = True  # one INSERT per row, no txn management needed
            self._owns_conn = True
        self._conn = conn

    @property
    def conn(self) -> psycopg2.extensions.connection:
        return self._conn

    def close(self) -> None:
        """Release the underlying connection.

        If the writer leased the connection from the pool (production path),
        it is returned to the pool. If the connection was injected by the
        caller, it is left alone — the caller owns that lifecycle.
        """
        if not self._owns_conn:
            return
        try:
            pool = get_connection_pool()
            pool.putconn(self._conn)
        except Exception:  # pragma: no cover — defensive
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def record(
        self,
        *,
        source_name: str,
        source_url: str,
        local_path: str,
        headers_dict: Mapping[str, Any],
        bytes_written: int,
        sha256: str,
    ) -> Dict[str, Any]:
        """Insert a provenance row and return it as a dict.

        Raises on DB errors; callers that must never fail the download should
        use :meth:`record_swallow` instead.
        """
        content_length = _parse_content_length(
            _get_header(headers_dict, _HEADER_CONTENT_LENGTH)
        )
        etag = _get_header(headers_dict, _HEADER_ETAG)
        last_modified = _get_header(headers_dict, _HEADER_LAST_MODIFIED)

        # None CL is not a failure — chunked transfer / dynamic content
        # legitimately have no Content-Length. Per plan §C.4.
        size_match = (content_length is None) or (content_length == bytes_written)

        prior_id, prior_sha = self._find_prior(source_name, source_url)
        changed_from_prior = bool(prior_sha is not None and prior_sha != sha256)

        row = self._insert_row(
            source_name=source_name,
            source_url=source_url,
            local_path=local_path,
            content_length=content_length,
            etag=etag,
            last_modified=last_modified,
            sha256=sha256,
            bytes_written=bytes_written,
            size_match=size_match,
            prior_provenance_id=prior_id,
            changed_from_prior=changed_from_prior,
        )

        if changed_from_prior:
            DK_ARTIFACT_CHANGED_TOTAL.labels(source=source_name).inc()
            logger.info(
                "Artifact changed: source=%s url=%s prior_id=%s new_sha256=%s…",
                source_name,
                source_url,
                prior_id,
                sha256[:12],
            )

        return row

    def record_swallow(
        self,
        *,
        source_name: str,
        source_url: str,
        local_path: str,
        headers_dict: Mapping[str, Any],
        bytes_written: int,
        sha256: str,
    ) -> Optional[Dict[str, Any]]:
        """Provenance write that MUST NOT fail the caller.

        Per plan §C.4: any exception is logged + counted via
        ``dk_artifact_provenance_write_errors_total{source}`` and the
        method returns ``None``. Ingestion proceeds.
        """
        try:
            return self.record(
                source_name=source_name,
                source_url=source_url,
                local_path=local_path,
                headers_dict=headers_dict,
                bytes_written=bytes_written,
                sha256=sha256,
            )
        except Exception as exc:  # noqa: BLE001 — intentional broad catch
            DK_ARTIFACT_PROVENANCE_WRITE_ERRORS_TOTAL.labels(source=source_name).inc()
            logger.warning(
                "Provenance write failed for source=%s url=%s: %s (download continues)",
                source_name,
                source_url,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _find_prior(
        self, source_name: str, source_url: str
    ) -> tuple[Optional[int], Optional[str]]:
        """Return (provenance_id, sha256) of the most recent prior row, or (None, None)."""
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT provenance_id, sha256
                FROM meta.artifact_provenance
                WHERE source_name = %s AND source_url = %s
                ORDER BY downloaded_at DESC
                LIMIT 1
                """,
                (source_name, source_url),
            )
            row = cur.fetchone()
            if row is None:
                return None, None
            return int(row[0]), str(row[1])

    def _insert_row(
        self,
        *,
        source_name: str,
        source_url: str,
        local_path: str,
        content_length: Optional[int],
        etag: Optional[str],
        last_modified: Optional[str],
        sha256: str,
        bytes_written: int,
        size_match: bool,
        prior_provenance_id: Optional[int],
        changed_from_prior: bool,
    ) -> Dict[str, Any]:
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO meta.artifact_provenance (
                    source_name, source_url, local_path,
                    content_length, etag, last_modified,
                    sha256, bytes_written, size_match,
                    prior_provenance_id, changed_from_prior
                )
                VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
                RETURNING
                    provenance_id, source_name, source_url, local_path,
                    content_length, etag, last_modified, sha256,
                    bytes_written, size_match, downloaded_at,
                    prior_provenance_id, changed_from_prior
                """,
                (
                    source_name,
                    source_url,
                    local_path,
                    content_length,
                    etag,
                    last_modified,
                    sha256,
                    bytes_written,
                    size_match,
                    prior_provenance_id,
                    changed_from_prior,
                ),
            )
            row = cur.fetchone()
        # RealDictCursor returns a dict-like; normalise to plain dict for callers.
        return dict(row) if row is not None else {}


__all__ = ["ArtifactProvenanceWriter"]
