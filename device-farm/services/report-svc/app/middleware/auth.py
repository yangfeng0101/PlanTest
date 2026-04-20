# Authentication middleware for Report Service
import os
from fastapi import Depends, HTTPException, Request, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import httpx

# JWT validation is done by calling test-svc auth API
# This allows report-svc to validate tokens without duplicating JWT logic
TEST_SVC_URL = os.getenv("TEST_SVC_URL", "http://localhost:8003")
security = HTTPBearer(auto_error=False)


async def require_csrf_token(
    request: Request,
    x_csrf_token: Optional[str] = Header(None, alias="X-CSRF-Token"),
) -> str:
    if not x_csrf_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token is required",
        )
    
    # Simple Double Submit Cookie check
    csrf_cookie = request.cookies.get("csrf_token")
    if csrf_cookie and x_csrf_token != csrf_cookie:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        )
        
    return x_csrf_token


async def verify_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Verify JWT token by calling test-svc auth API.

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        User info from token

    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials if credentials else request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        async with httpx.AsyncClient() as client:
            request_kwargs = {"timeout": 10.0}
            if credentials:
                request_kwargs["headers"] = {"Authorization": f"Bearer {token}"}
            else:
                request_kwargs["cookies"] = {"access_token": token}

            response = await client.get(
                f"{TEST_SVC_URL}/api/v1/auth/me",
                **request_kwargs,
            )

        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except httpx.RequestError:
        # If test-svc is unavailable, deny access
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )


async def get_current_user(
    user: dict = Depends(verify_token),
) -> dict:
    """Get current authenticated user.

    Args:
        user: User info from token

    Returns:
        User dict with id, username, role, etc.
    """
    return user


async def get_current_user_id(
    user: dict = Depends(get_current_user),
) -> str:
    """Get current user ID.

    Args:
        user: User info

    Returns:
        User ID string
    """
    return user.get("id", "")


def require_role(*allowed_roles: str):
    """Dependency that requires user to have one of the specified roles.

    Args:
        *allowed_roles: Roles that are allowed to access (e.g., "admin", "user", "viewer")

    Returns:
        Dependency function
    """
    async def role_checker(
        user: dict = Depends(get_current_user),
    ) -> dict:
        user_role = user.get("role", "")
        # Case-insensitive role comparison
        user_role_lower = user_role.lower()
        allowed_roles_lower = [r.lower() for r in allowed_roles]
        if user_role_lower not in allowed_roles_lower:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' not authorized. Required: {allowed_roles}",
            )
        return user

    return role_checker
