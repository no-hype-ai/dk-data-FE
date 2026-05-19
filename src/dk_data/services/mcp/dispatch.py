"""Registry-driven DB-first dispatch for MCP tool invocations.

Wires the two registries together:
  - router.TOOL_REGISTRY  → slug → BaseMCPTool (HTTP-first, 9 entries)
  - tool_registry.TOOL_REGISTRY → slug → ToolDefinition (lazy Adapter import)

Dispatch order per slug:
  1. If a ToolDefinition exists AND its adapter_module exports an
     ``Adapter(BaseAdapter)`` AND a db_pool is available:
       - db_query() returns dict  → return it (no HTTP).
       - db_query() returns None  → fall through to HTTP.
       - db_query() RAISES        → surface as 502 {"stage": "db_query"}.
         DO NOT fall through to HTTP (a DB outage ≠ a cache miss).
  2. HTTP fallthrough via http_tool.invoke() if available.
  3. Neither available → 404.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from fastapi import HTTPException

from .adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


def _load_db_adapter(adapter_module: str) -> "BaseAdapter | None":
    """Lazily import *adapter_module* and return an ``Adapter`` instance.

    Returns ``None`` when:
    - the module cannot be imported (not built yet), OR
    - the module has no ``Adapter`` attribute, OR
    - ``Adapter`` is not a ``BaseAdapter`` subclass.

    Never raises — absent adapters are expected during Phase 2+ build-out.
    """
    try:
        mod = importlib.import_module(adapter_module)
    except ImportError:
        logger.debug("Adapter module not yet available: %s", adapter_module)
        return None

    adapter_cls = getattr(mod, "Adapter", None)
    if adapter_cls is None:
        logger.debug("Module %s has no Adapter class — skipping DB path", adapter_module)
        return None

    if not (isinstance(adapter_cls, type) and issubclass(adapter_cls, BaseAdapter)):
        logger.debug(
            "Module %s.Adapter is not a BaseAdapter subclass — skipping DB path",
            adapter_module,
        )
        return None

    return adapter_cls()


async def dispatch_invoke(
    slug: str,
    drug_name: str,
    db_pool: Any,
    http_tool_registry: "dict[str, Any]",
    tool_definition_registry: "dict[str, Any]",
) -> dict:
    """Resolve slug → DB-first dispatch → HTTP fallthrough → structured error.

    Returns a dict suitable for constructing an ``InvokeResponse``::

        {"tool": slug, "data": ..., "error": ..., "status_code": ...}

    Raises ``HTTPException`` for 404 (slug not found) and 502 (db error).
    """
    http_tool = http_tool_registry.get(slug)
    tdef = tool_definition_registry.get(slug)

    if http_tool is None and tdef is None:
        all_slugs = sorted(set(http_tool_registry) | set(tool_definition_registry))
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Tool '{slug}' not found.",
                "available_tools": all_slugs,
            },
        )

    # ------------------------------------------------------------------
    # DB-first path
    # ------------------------------------------------------------------
    if tdef is not None and db_pool is not None:
        db_adapter = _load_db_adapter(tdef.adapter_module)
        if db_adapter is not None:
            try:
                db_result = await db_adapter.db_query(drug_name, db_pool)
            except HTTPException:
                raise  # adapter raised a structured HTTP error — pass through unchanged
            except Exception as exc:
                # A real DB error — surface it, do NOT fall through to HTTP.
                logger.error(
                    "db_query raised for slug=%s drug=%s: %s",
                    slug,
                    drug_name,
                    exc,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": str(exc),
                        "tool": slug,
                        "stage": "db_query",
                    },
                ) from exc

            if db_result is not None:
                # DB hit — return without any HTTP call.
                return {
                    "tool": slug,
                    "data": db_result,
                    "error": None,
                    "status_code": 200,
                }
            # db_result is None → cache miss, fall through to HTTP.

    # ------------------------------------------------------------------
    # HTTP fallthrough
    # ------------------------------------------------------------------
    if http_tool is not None:
        import httpx  # local import to keep module-level deps minimal

        try:
            result = await http_tool.invoke(drug_name)
            return {
                "tool": slug,
                "data": result.get("data"),
                "error": result.get("error"),
                "status_code": result.get("status_code"),
            }
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": f"Upstream API returned {exc.response.status_code}",
                    "tool": slug,
                },
            ) from exc
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail={"error": "Upstream API timed out", "tool": slug},
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail={"error": str(exc), "tool": slug},
            ) from exc

    # Slug is in tool_definition_registry only, Adapter returned None (miss),
    # and there is no HTTP tool to fall back to.
    raise HTTPException(
        status_code=404,
        detail={
            "error": (
                f"No local DB match and no HTTP fallback configured for '{slug}'."
            ),
            "tool": slug,
        },
    )
