"""
API Middleware

Middleware components for request processing.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import os
import importlib.util

# Import from parent middleware.py file (setup_middleware, etc.)
_middleware_py_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'middleware.py')
if os.path.exists(_middleware_py_path):
    _spec = importlib.util.spec_from_file_location("_base_middleware", _middleware_py_path)
    _base_middleware = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_base_middleware)

    # Re-export base middleware
    setup_middleware = _base_middleware.setup_middleware
    CacheControlMiddleware = _base_middleware.CacheControlMiddleware
    RequestTrackingMiddleware = _base_middleware.RequestTrackingMiddleware
    CORSHeadersMiddleware = _base_middleware.CORSHeadersMiddleware
    SecurityHeadersMiddleware = _base_middleware.SecurityHeadersMiddleware

from .rbac import (
    get_current_user,
    require_auth,
    RoleChecker,
    PermissionChecker,
    require_viewer,
    require_analyst,
    require_data_ops,
    require_admin,
    can_read_gold,
    can_read_silver,
    can_manage_queue,
    can_trigger_pipeline,
    can_manage_users,
    role_required,
    permission_required,
    LayerAccess,
)

__all__ = [
    # Base middleware (from middleware.py)
    'setup_middleware',
    'CacheControlMiddleware',
    'RequestTrackingMiddleware',
    'CORSHeadersMiddleware',
    'SecurityHeadersMiddleware',

    # RBAC middleware
    'get_current_user',
    'require_auth',
    'RoleChecker',
    'PermissionChecker',
    'require_viewer',
    'require_analyst',
    'require_data_ops',
    'require_admin',
    'can_read_gold',
    'can_read_silver',
    'can_manage_queue',
    'can_trigger_pipeline',
    'can_manage_users',
    'role_required',
    'permission_required',
    'LayerAccess',
]
