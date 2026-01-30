"""
DK Data Services Package.

Provides services for:
- Data Platform: Medallion architecture pipeline
- External APIs: Third-party data source clients
- Ground Truth: Competitive intelligence services
- Auth: JWT authentication services
"""

from . import data_platform
from . import external_apis
from . import ground_truth
from . import auth

__all__ = [
    "data_platform",
    "external_apis",
    "ground_truth",
    "auth",
]
