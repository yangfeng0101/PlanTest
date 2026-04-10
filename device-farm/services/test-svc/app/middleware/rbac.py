# Role-Based Access Control (RBAC) Middleware
from typing import Optional, List, Callable
from fastapi import Depends, HTTPException, status
from functools import wraps

from app.models.user import UserDB, UserRole
from app.api.auth import get_current_user


# Permission definitions
PERMISSIONS = {
    # Device management
    "device:read": [UserRole.ADMIN, UserRole.USER, UserRole.VIEWER],
    "device:write": [UserRole.ADMIN, UserRole.USER],
    "device:delete": [UserRole.ADMIN],

    # Script management
    "script:read": [UserRole.ADMIN, UserRole.USER, UserRole.VIEWER],
    "script:write": [UserRole.ADMIN, UserRole.USER],
    "script:execute": [UserRole.ADMIN, UserRole.USER],
    "script:delete": [UserRole.ADMIN],

    # Reservation management
    "reservation:read": [UserRole.ADMIN, UserRole.USER, UserRole.VIEWER],
    "reservation:write": [UserRole.ADMIN, UserRole.USER],
    "reservation:cancel": [UserRole.ADMIN, UserRole.USER],

    # Schedule management
    "schedule:read": [UserRole.ADMIN, UserRole.USER, UserRole.VIEWER],
    "schedule:write": [UserRole.ADMIN, UserRole.USER],
    "schedule:delete": [UserRole.ADMIN],

    # Parallel execution
    "parallel:execute": [UserRole.ADMIN, UserRole.USER],

    # Report management
    "report:read": [UserRole.ADMIN, UserRole.USER, UserRole.VIEWER],
    "report:export": [UserRole.ADMIN, UserRole.USER],

    # User management (admin only)
    "user:read": [UserRole.ADMIN],
    "user:write": [UserRole.ADMIN],
    "user:delete": [UserRole.ADMIN],

    # System configuration (admin only)
    "system:config": [UserRole.ADMIN],
    "system:alerts": [UserRole.ADMIN],
}


def has_permission(user_role: UserRole, permission: str) -> bool:
    """Check if a role has a specific permission

    Args:
        user_role: User's role
        permission: Permission to check (e.g., "device:read")

    Returns:
        True if role has permission, False otherwise
    """
    allowed_roles = PERMISSIONS.get(permission, [])
    return user_role in allowed_roles


def require_permission(permission: str):
    """Decorator/Dependency to require a specific permission

    Args:
        permission: Required permission (e.g., "device:write")

    Returns:
        Dependency function

    Usage:
        @router.post("/devices")
        async def create_device(
            _: UserDB = Depends(require_permission("device:write"))
        ):
            ...
    """
    async def permission_checker(
        current_user: UserDB = Depends(get_current_user),
    ) -> UserDB:
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required: {permission}",
            )
        return current_user

    return permission_checker


def require_role(*roles: UserRole):
    """Decorator/Dependency to require specific roles

    Args:
        roles: Required roles (any of them)

    Returns:
        Dependency function

    Usage:
        @router.get("/admin/users")
        async def list_users(
            _: UserDB = Depends(require_role(UserRole.ADMIN))
        ):
            ...
    """
    async def role_checker(
        current_user: UserDB = Depends(get_current_user),
    ) -> UserDB:
        if current_user.role not in roles:
            role_names = [r.value for r in roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role not authorized. Required roles: {role_names}",
            )
        return current_user

    return role_checker


def require_admin():
    """Dependency that requires admin role"""
    return require_role(UserRole.ADMIN)


def require_user():
    """Dependency that requires user or admin role"""
    return require_role(UserRole.ADMIN, UserRole.USER)


class RBACMiddleware:
    """
    Middleware for checking permissions on routes.

    This can be used to protect entire routers with specific permissions.
    """

    def __init__(
        self,
        required_permission: Optional[str] = None,
        required_roles: Optional[List[UserRole]] = None,
    ):
        self.required_permission = required_permission
        self.required_roles = required_roles or []

    async def __call__(
        self,
        current_user: UserDB = Depends(get_current_user),
    ) -> UserDB:
        # Check role if specified
        if self.required_roles and current_user.role not in self.required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role privileges",
            )

        # Check permission if specified
        if self.required_permission:
            if not has_permission(current_user.role, self.required_permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {self.required_permission}",
                )

        return current_user


# Convenience functions for common permission checks
async def can_create_device(current_user: UserDB = Depends(get_current_user)) -> UserDB:
    """Check if user can create devices"""
    return await require_permission("device:write")(current_user)


async def can_delete_device(current_user: UserDB = Depends(get_current_user)) -> UserDB:
    """Check if user can delete devices"""
    return await require_permission("device:delete")(current_user)


async def can_execute_script(current_user: UserDB = Depends(get_current_user)) -> UserDB:
    """Check if user can execute scripts"""
    return await require_permission("script:execute")(current_user)


async def can_manage_users(current_user: UserDB = Depends(get_current_user)) -> UserDB:
    """Check if user can manage other users"""
    return await require_permission("user:write")(current_user)
