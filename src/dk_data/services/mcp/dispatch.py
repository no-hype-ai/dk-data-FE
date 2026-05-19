"""Registry-driven, gated, parallel DB-first dispatch — WS4 SP1 (feature 211).

ADDITIVE: ``router.invoke_tool`` consults :func:`try_db_first` *before* its
existing httpx path. This module never replaces that path — when DB-first is
off / unavailable / a miss it returns ``None`` and the router runs its
unchanged feature-015 behaviour.

Decision table — specs/211-ws4-staging-main-reconcile/contracts/
dispatch-decision-table.md:

* gate off / no ToolDefinition / no ``Adapter`` / adapter does not override
  ``db_query`` / no DB pool        -> ``None``  (outcome=disabled)
* ``db_query`` returns ``None``/empty -> ``None`` (outcome=fallthrough)
* ``db_query`` returns non-empty dict -> served, no HTTP (outcome=served)
* ``db_query`` raises               -> HTTPException 502 {"stage":"db_query"},
                                       NEVER fall through (outcome=error, H1)
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Optional

from fastapi import HTTPException

from dk_data.observability import metrics

from .adapters.base import BaseAdapter
from .dbfirst_gate import gate_on
from .tool_registry import TOOL_REGISTRY

logger = logging.getLogger(__name__)


def _emit(slug: str, outcome: str) -> None:
    metrics.MCP_DBFIRST_OUTCOME_TOTAL.labels(source=slug, outcome=outcome).inc()


async def get_db_pool() -> Any:
    """Lazy seam over the app's existing asyncpg pool (R1, ``[DSN]``).

    Imported lazily so this module stays import-light; a stable
    module-level name so tests can monkeypatch it.
    """
    from dk_data.api.dependencies import get_db_pool as _get_pool

    return await _get_pool()


def _load_db_adapter(adapter_module: str) -> Optional[BaseAdapter]:
    """Lazily import *adapter_module* and return an ``Adapter()`` instance,
    or ``None`` when absent / not a ``BaseAdapter`` subclass. Never raises —
    an absent adapter is an expected "no DB path", not an error.
    """
    try:
        mod = importlib.import_module(adapter_module)
    except ImportError:
        logger.debug("adapter module unavailable: %s", adapter_module)
        return None
    cls = getattr(mod, "Adapter", None)
    if not (isinstance(cls, type) and issubclass(cls, BaseAdapter)):
        logger.debug("%s has no Adapter(BaseAdapter) — no DB path", adapter_module)
        return None
    return cls()


async def try_db_first(slug: str, drug_name: str) -> Optional[dict]:
    """Return an InvokeResponse-shaped dict on a warehouse hit, else
    ``None`` (router runs its unchanged path). Raises ``HTTPException``
    502 ``{"stage": "db_query"}`` on a genuine DB error — never falls
    through (a DB outage is not a cache miss; FR-004 / H1)."""
    if not gate_on(slug):
        _emit(slug, "disabled")
        return None

    tdef = TOOL_REGISTRY.get(slug)
    if tdef is None:
        _emit(slug, "disabled")
        return None

    adapter = _load_db_adapter(tdef.adapter_module)
    if adapter is None or type(adapter).db_query is BaseAdapter.db_query:
        # No adapter, or it does not override db_query → no DB path.
        _emit(slug, "disabled")
        return None

    pool = await get_db_pool()
    if pool is None:
        _emit(slug, "disabled")
        return None

    try:
        result = await adapter.db_query(drug_name, pool)
    except HTTPException:
        raise  # adapter raised a structured HTTP error — pass through
    except Exception as exc:
        _emit(slug, "error")
        logger.error(
            "db_query raised slug=%s drug=%s: %s", slug, drug_name, exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": str(exc), "tool": slug, "stage": "db_query"},
        ) from exc

    if result:
        _emit(slug, "served")
        return {"tool": slug, "data": result, "error": None, "status_code": 200}

    # None or empty/zero-row → a miss, NOT a served-empty (R4).
    _emit(slug, "fallthrough")
    return None
