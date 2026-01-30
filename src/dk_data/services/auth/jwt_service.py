"""
JWT Authentication Service

Implements JWT-based authentication for the DK Molecule Data Platform.
Supports role-based access control (viewer, analyst, data_ops, admin).

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import logging

import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """User roles with increasing privilege levels."""
    VIEWER = "viewer"           # Read-only Gold layer access
    ANALYST = "analyst"         # Read Silver + Gold, fuzzy search
    DATA_OPS = "data_ops"       # All above + resolution queue, pipeline triggers
    ADMIN = "admin"             # Full access including user management


# Role hierarchy (higher roles inherit lower role permissions)
ROLE_HIERARCHY = {
    UserRole.VIEWER: [],
    UserRole.ANALYST: [UserRole.VIEWER],
    UserRole.DATA_OPS: [UserRole.ANALYST, UserRole.VIEWER],
    UserRole.ADMIN: [UserRole.DATA_OPS, UserRole.ANALYST, UserRole.VIEWER],
}


@dataclass
class TokenPayload:
    """JWT token payload structure."""
    sub: str                    # User ID
    email: str
    role: UserRole
    iat: datetime
    exp: datetime
    aud: str = "dk-data-platform"
    permissions: List[str] = None


@dataclass
class AuthenticatedUser:
    """Authenticated user context."""
    user_id: str
    email: str
    role: UserRole
    permissions: List[str]
    token_exp: datetime


class JWTService:
    """
    JWT authentication service.

    Handles:
    - Token generation and validation
    - Role-based access control
    - Token refresh
    """

    DEFAULT_EXPIRY_HOURS = 24
    REFRESH_EXPIRY_DAYS = 7

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        issuer: str = "dk-data-platform"
    ):
        """
        Initialize the JWT service.

        Args:
            secret_key: JWT signing secret (uses env var if not provided)
            algorithm: JWT algorithm (default HS256)
            issuer: Token issuer claim
        """
        self.secret_key = secret_key or os.getenv("JWT_SECRET_KEY")
        if not self.secret_key:
            logger.warning("JWT_SECRET_KEY not set, generating random key (not suitable for production)")
            self.secret_key = secrets.token_hex(32)

        self.algorithm = algorithm
        self.issuer = issuer

    def create_access_token(
        self,
        user_id: str,
        email: str,
        role: UserRole,
        expires_delta: Optional[timedelta] = None,
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new access token.

        Args:
            user_id: User identifier
            email: User email
            role: User role
            expires_delta: Custom expiry time
            additional_claims: Extra claims to include

        Returns:
            Encoded JWT token
        """
        now = datetime.utcnow()
        expires = now + (expires_delta or timedelta(hours=self.DEFAULT_EXPIRY_HOURS))

        # Build permissions from role hierarchy
        permissions = self._get_role_permissions(role)

        payload = {
            "sub": user_id,
            "email": email,
            "role": role.value,
            "permissions": permissions,
            "iat": now,
            "exp": expires,
            "iss": self.issuer,
            "aud": "dk-data-platform",
        }

        if additional_claims:
            payload.update(additional_claims)

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: str) -> str:
        """
        Create a refresh token.

        Args:
            user_id: User identifier

        Returns:
            Encoded refresh token
        """
        now = datetime.utcnow()
        expires = now + timedelta(days=self.REFRESH_EXPIRY_DAYS)

        payload = {
            "sub": user_id,
            "type": "refresh",
            "iat": now,
            "exp": expires,
            "iss": self.issuer,
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[AuthenticatedUser]:
        """
        Verify and decode a JWT token.

        Args:
            token: JWT token string

        Returns:
            AuthenticatedUser if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience="dk-data-platform",
                issuer=self.issuer
            )

            role = UserRole(payload.get("role", "viewer"))

            return AuthenticatedUser(
                user_id=payload["sub"],
                email=payload.get("email", ""),
                role=role,
                permissions=payload.get("permissions", []),
                token_exp=datetime.fromtimestamp(payload["exp"])
            )

        except ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None

    def verify_refresh_token(self, token: str) -> Optional[str]:
        """
        Verify a refresh token.

        Args:
            token: Refresh token string

        Returns:
            User ID if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                issuer=self.issuer
            )

            if payload.get("type") != "refresh":
                return None

            return payload["sub"]

        except (ExpiredSignatureError, InvalidTokenError):
            return None

    def refresh_access_token(
        self,
        refresh_token: str,
        get_user_func
    ) -> Optional[tuple]:
        """
        Refresh an access token using a refresh token.

        Args:
            refresh_token: Valid refresh token
            get_user_func: Function to fetch user data (user_id) -> (email, role)

        Returns:
            Tuple of (access_token, refresh_token) or None
        """
        user_id = self.verify_refresh_token(refresh_token)
        if not user_id:
            return None

        # Fetch current user data
        user_data = get_user_func(user_id)
        if not user_data:
            return None

        email, role = user_data

        # Generate new tokens
        access_token = self.create_access_token(user_id, email, role)
        new_refresh_token = self.create_refresh_token(user_id)

        return access_token, new_refresh_token

    def _get_role_permissions(self, role: UserRole) -> List[str]:
        """Get all permissions for a role including inherited ones."""
        permissions = set()

        # Add role-specific permissions
        permissions.add(f"role:{role.value}")

        # Add inherited role permissions
        for inherited_role in ROLE_HIERARCHY.get(role, []):
            permissions.add(f"role:{inherited_role.value}")

        # Add feature permissions based on role
        if role in [UserRole.VIEWER, UserRole.ANALYST, UserRole.DATA_OPS, UserRole.ADMIN]:
            permissions.add("gold:read")

        if role in [UserRole.ANALYST, UserRole.DATA_OPS, UserRole.ADMIN]:
            permissions.add("silver:read")
            permissions.add("search:fuzzy")

        if role in [UserRole.DATA_OPS, UserRole.ADMIN]:
            permissions.add("resolution_queue:read")
            permissions.add("resolution_queue:write")
            permissions.add("pipeline:trigger")
            permissions.add("bronze:read")

        if role == UserRole.ADMIN:
            permissions.add("users:manage")
            permissions.add("raw:read")
            permissions.add("config:write")

        return sorted(list(permissions))

    @staticmethod
    def check_permission(user: AuthenticatedUser, required_permission: str) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user: Authenticated user
            required_permission: Permission to check

        Returns:
            True if user has permission
        """
        return required_permission in user.permissions

    @staticmethod
    def check_role(user: AuthenticatedUser, minimum_role: UserRole) -> bool:
        """
        Check if user has at least the minimum required role.

        Args:
            user: Authenticated user
            minimum_role: Minimum required role

        Returns:
            True if user role is sufficient
        """
        role_order = [UserRole.VIEWER, UserRole.ANALYST, UserRole.DATA_OPS, UserRole.ADMIN]
        user_level = role_order.index(user.role)
        required_level = role_order.index(minimum_role)
        return user_level >= required_level
