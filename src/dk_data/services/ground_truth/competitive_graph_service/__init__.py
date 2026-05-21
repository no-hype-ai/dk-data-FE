"""Competitive graph service package.

Re-exports the public API so existing imports
(`from ...ground_truth.competitive_graph_service import CompetitiveGraphService`)
keep working after the split into submodules.
"""

from .config import FailedRequest, GraphBuildConfig
from .service import CompetitiveGraphService

__all__ = [
    "CompetitiveGraphService",
    "GraphBuildConfig",
    "FailedRequest",
]
