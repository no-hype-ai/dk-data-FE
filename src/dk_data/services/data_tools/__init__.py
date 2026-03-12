"""Unified External Data Tools Gateway.

All reads go through PostgREST (unified JWT auth model). The gateway adds
cold-start backfill: if PostgREST returns empty → external fetch → raw insert
→ transform → re-query PostgREST.

Endpoints: /api/v1/data-tools/{source}/query
- 26 molecule/IP tools (from services.pipeline)
- 20 CMS queryable sources (real-time API fallback)
- 8 CMS bulk-only sources (local DB only)
"""

from .tool_registry import TOOL_REGISTRY, DataToolDefinition
from .base_tool import BaseDataTool
from .postgrest_client import PostgRESTClient

__all__ = [
    "TOOL_REGISTRY",
    "DataToolDefinition",
    "BaseDataTool",
    "PostgRESTClient",
]
