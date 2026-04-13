# Authentication middleware for AI Service
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import httpx
import logging

logger = logging.getLogger(__name__)

# JWT validation is done by calling test-svc auth API
TEST_SVC_URL = os.getenv("TEST_SVC_URL", "http://localhost:8003")
security = HTTPBearer()


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Verify JWT token by calling test-svc auth API.

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        User info from token

    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TEST_SVC_URL}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0
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
