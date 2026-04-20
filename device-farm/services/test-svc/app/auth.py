# API Authentication Middleware
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import APIKeyHeader
from app.config import settings
from app.services.jwt_service import jwt_service
from typing import Optional

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Depends(API_KEY_HEADER)
) -> str:
    """
    Verify API key if provided.
    Falls back to session auth if no API key is provided or API_KEY_ENABLED is false.
    """
    if api_key and settings.API_KEY_ENABLED:
        if api_key == settings.API_KEY:
            return "api-key-user"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    # Check session auth
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key or authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = jwt_service.validate_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload.sub
