# Authentication Middleware
from fastapi import Request, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Optional
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# API Key authentication
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# Bearer token authentication
BEARER_SECURITY = HTTPBearer(auto_error=False)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware that supports both API Key and Bearer token authentication.

    API Key: X-API-Key header
    Bearer Token: Authorization: Bearer <token>

    For JWT-based auth, Bearer tokens are validated as JWT access tokens.
    """

    # Paths that don't require authentication (exact matches)
    PUBLIC_PATHS = {
        "/",
        "/health",
        "/api/v1/docs",
        "/api/v1/redoc",
        "/openapi.json",
    }

    # Path prefixes that don't require authentication
    PUBLIC_PREFIXES = [
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
    ]

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public paths
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Skip auth for public prefixes
        for prefix in self.PUBLIC_PREFIXES:
            if request.url.path.startswith(prefix):
                return await call_next(request)

        # Skip auth if disabled
        if not settings.API_KEY_ENABLED:
            return await call_next(request)

        # Check for API key in header
        api_key = request.headers.get("X-API-Key")

        # Check for Bearer token
        auth_header = request.headers.get("Authorization", "")
        bearer_token = None
        if auth_header.startswith("Bearer "):
            bearer_token = auth_header[7:]

        # Check for access_token in cookie (for browser-based auth)
        cookie_token = request.cookies.get("access_token")

        # At least one auth method must be provided
        if not api_key and not bearer_token and not cookie_token:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "detail": "Authentication required. Provide X-API-Key header or Authorization: Bearer token."
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate API key if provided
        if api_key:
            if api_key != settings.API_KEY:
                logger.warning(f"Invalid API key attempt from {request.client.host if request.client else 'unknown'}")
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Invalid API key"},
                )

        # Validate Bearer token or cookie token if provided (JWT validation)
        elif bearer_token or cookie_token:
            token = bearer_token or cookie_token
            # Try to validate as JWT token
            try:
                from app.services.jwt_service import jwt_service
                from app.services.token_blacklist import token_blacklist

                # Check if token is blacklisted
                import asyncio
                if asyncio.get_event_loop().is_running():
                    # We're in an async context, but can't await here
                    # Skip blacklist check in middleware (handled in route)
                    pass

                payload = jwt_service.validate_access_token(token)
                if not payload:
                    logger.warning(f"Invalid JWT token attempt from {request.client.host if request.client else 'unknown'}")
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Invalid or expired Bearer token"},
                    )
                # Token is valid, proceed with request
            except Exception as e:
                logger.warning(f"JWT validation error: {e}")
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Invalid Bearer token"},
                )

        # Auth successful, proceed with request
        return await call_next(request)


async def verify_api_key(api_key: Optional[str] = None) -> str:
    """
    Dependency for verifying API key in route handlers.

    Usage:
        @router.get("/protected")
        async def protected_route(_: str = Depends(verify_api_key)):
            ...

    Args:
        api_key: The API key from X-API-Key header

    Returns:
        The API key if valid

    Raises:
        HTTPException: If authentication fails
    """
    if not settings.API_KEY_ENABLED:
        return ""

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Please provide X-API-Key header.",
        )

    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    return api_key


async def verify_bearer_token(credentials: Optional[HTTPAuthorizationCredentials] = None) -> dict:
    """
    Dependency for verifying Bearer token in route handlers.

    Usage:
        @router.get("/protected")
        async def protected_route(user: dict = Depends(verify_bearer_token)):
            ...

    Args:
        credentials: The Bearer credentials from Authorization header

    Returns:
        The decoded token payload (user info)

    Raises:
        HTTPException: If authentication fails
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Please provide Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Validate JWT token
    try:
        from app.services.jwt_service import jwt_service
        payload = jwt_service.validate_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired Bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {
            "sub": payload.sub,
            "username": payload.username,
            "role": payload.role,
        }
    except Exception as e:
        logger.warning(f"JWT validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
