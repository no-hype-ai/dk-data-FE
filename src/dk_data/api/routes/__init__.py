"""
API Routes Package.

Exposes all API routers for the DK Data Platform.
"""

from .data_platform import router as data_platform_router
from .alerts import router as alerts_router
from .monitoring import router as monitoring_router
from .onboarding import router as onboarding_router
from .coverage import router as coverage_router
from .feedback import router as feedback_router
from .graph import router as graph_router
from .kols import router as kols_router
from .visualize import router as visualize_router
from .data_sources import router as data_sources_router

__all__ = [
    "data_platform_router",
    "alerts_router",
    "monitoring_router",
    "onboarding_router",
    "coverage_router",
    "feedback_router",
    "graph_router",
    "kols_router",
    "visualize_router",
    "data_sources_router",
]
