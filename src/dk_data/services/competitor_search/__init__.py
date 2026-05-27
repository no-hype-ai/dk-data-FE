"""Composed competitor-discovery service.

Powers POST /api/v1/data-tools/competitor-search/invoke. Wraps the existing
CompetitiveGraphService and shapes its output into the dk-data invoke
envelope (`source: "composed"`).
"""

from .service import CompetitorSearchService

__all__ = ["CompetitorSearchService"]
