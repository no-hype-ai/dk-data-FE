"""
RBAC Middleware

Role-Based Access Control middleware for FastAPI.
Implements viewer, analyst, data_ops, admin roles.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from functools import wraps
from typing import Optional, List, Callable
import logging

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ...services.auth.jwt_service import (
    JWTService,
    UserRole,
    AuthenticatedUser,
)

logger = logging.getLogger(__name__)

# Global JWT service instance
_jwt_service: Optional[JWTService] = None


def get_jwt_service() -> JWTService:
    """Get or create JWT service instance."""
    global _jwt_service
    if _jwt_service is None:
        _jwt_service = JWTService()
    return _jwt_service


# Security scheme for Swagger docs
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    jwt_service: JWTService = Depends(get_jwt_service)
) -> Optional[AuthenticatedUser]:
    """
    Extract and validate the current user from JWT token.

    Returns None for unauthenticated requests (use require_auth for protected routes).
    """
    if not credentials:
        return None

    token = credentials.credentials
    user = jwt_service.verify_token(token)

    if not user:
        return None

    return user


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    jwt_service: JWTService = Depends(get_jwt_service)
) -> AuthenticatedUser:
    """
    Require authentication. Raises 401 if not authenticated.
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    user = jwt_service.verify_token(token)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return user


class RoleChecker:
    """
    Dependency for checking user roles.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: AuthenticatedUser = Depends(RoleChecker(UserRole.ADMIN))):
            ...
    """

    def __init__(self, minimum_role: UserRole):
        self.minimum_role = minimum_role

    async def __call__(
        self,
        user: AuthenticatedUser = Depends(require_auth)
    ) -> AuthenticatedUser:
        if not JWTService.check_role(user, self.minimum_role):
            raise HTTPException(
                status_code=403,
                detail=f"Requires {self.minimum_role.value} role or higher"
            )
        return user


class PermissionChecker:
    """
    Dependency for checking specific permissions.

    Usage:
        @router.post("/trigger-pipeline")
        async def trigger(user: AuthenticatedUser = Depends(PermissionChecker("pipeline:trigger"))):
            ...
    """

    def __init__(self, *required_permissions: str, require_all: bool = True):
        self.required_permissions = required_permissions
        self.require_all = require_all

    async def __call__(
        self,
        user: AuthenticatedUser = Depends(require_auth)
    ) -> AuthenticatedUser:
        if self.require_all:
            missing = [p for p in self.required_permissions if p not in user.permissions]
            if missing:
                raise HTTPException(
                    status_code=403,
                    detail=f"Missing permissions: {', '.join(missing)}"
                )
        else:
            has_any = any(p in user.permissions for p in self.required_permissions)
            if not has_any:
                raise HTTPException(
                    status_code=403,
                    detail=f"Requires one of: {', '.join(self.required_permissions)}"
                )

        return user


# Pre-configured role dependencies for common use cases
require_viewer = RoleChecker(UserRole.VIEWER)
require_analyst = RoleChecker(UserRole.ANALYST)
require_data_ops = RoleChecker(UserRole.DATA_OPS)
require_admin = RoleChecker(UserRole.ADMIN)

# Pre-configured permission dependencies
can_read_gold = PermissionChecker("gold:read")
can_read_silver = PermissionChecker("silver:read")
can_manage_queue = PermissionChecker("resolution_queue:read", "resolution_queue:write")
can_trigger_pipeline = PermissionChecker("pipeline:trigger")
can_manage_users = PermissionChecker("users:manage")


def role_required(minimum_role: UserRole):
    """
    Decorator for role-based access control.

    Usage:
        @router.get("/data-ops-only")
        @role_required(UserRole.DATA_OPS)
        async def data_ops_endpoint(request: Request):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find the user in kwargs (injected by Depends)
            user = kwargs.get('current_user') or kwargs.get('user')
            if not user:
                raise HTTPException(status_code=401, detail="Authentication required")

            if not JWTService.check_role(user, minimum_role):
                raise HTTPException(
                    status_code=403,
                    detail=f"Requires {minimum_role.value} role or higher"
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


def permission_required(*permissions: str, require_all: bool = True):
    """
    Decorator for permission-based access control.

    Usage:
        @router.post("/resolve")
        @permission_required("resolution_queue:write")
        async def resolve_endpoint(request: Request):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get('current_user') or kwargs.get('user')
            if not user:
                raise HTTPException(status_code=401, detail="Authentication required")

            if require_all:
                missing = [p for p in permissions if p not in user.permissions]
                if missing:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Missing permissions: {', '.join(missing)}"
                    )
            else:
                has_any = any(p in user.permissions for p in permissions)
                if not has_any:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Requires one of: {', '.join(permissions)}"
                    )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


# Layer-specific access control
class LayerAccess:
    """Access control for data platform layers."""

    @staticmethod
    def gold_read() -> PermissionChecker:
        """Read access to Gold layer (all authenticated users)."""
        return PermissionChecker("gold:read")

    @staticmethod
    def silver_read() -> PermissionChecker:
        """Read access to Silver layer (analyst+)."""
        return PermissionChecker("silver:read")

    @staticmethod
    def bronze_read() -> PermissionChecker:
        """Read access to Bronze layer (data_ops+)."""
        return PermissionChecker("bronze:read")

    @staticmethod
    def raw_read() -> PermissionChecker:
        """Read access to Raw layer (admin only)."""
        return PermissionChecker("raw:read")

    @staticmethod
    def resolution_queue() -> PermissionChecker:
        """Access to resolution queue (data_ops+)."""
        return PermissionChecker("resolution_queue:read", "resolution_queue:write")
