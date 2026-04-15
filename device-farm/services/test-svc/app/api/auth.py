# Auth API Router
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status, Response, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import (
    auth_service,
    UserCreate,
    UserLogin,
    UserResponse,
    LoginResponse,
    RefreshTokenRequest,
)
from app.services.jwt_service import jwt_service
from app.services.token_blacklist import token_blacklist
from app.models.user import UserRole, UserStatus, UserDB
from app.config import settings


router = APIRouter()
security = HTTPBearer()


def _get_cookie_settings() -> dict:
    """Get cookie settings based on environment"""
    return {
        "httponly": True,
        "secure": settings.COOKIE_SECURE,  # True in production
        "samesite": settings.COOKIE_SAMESITE,  # 'lax' or 'strict'
        "path": "/",
    }


async def validate_csrf_token(
    request: Request,
    x_csrf_token: Optional[str] = Header(None, alias="X-CSRF-Token"),
) -> Optional[str]:
    """Validate CSRF token for state-changing requests

    This is a soft validation - if CSRF token is not provided,
    the request continues (for backward compatibility).
    For strict CSRF protection, use require_csrf_token instead.

    Args:
        request: FastAPI request object
        x_csrf_token: CSRF token from header

    Returns:
        CSRF token if valid, None otherwise
    """
    if not x_csrf_token:
        return None

    access_token = request.cookies.get("access_token")
    if not access_token:
        return None

    if jwt_service.validate_csrf_token(access_token, x_csrf_token):
        return x_csrf_token

    return None


async def require_csrf_token(
    request: Request,
    x_csrf_token: Optional[str] = Header(None, alias="X-CSRF-Token"),
) -> str:
    """Require and validate CSRF token for state-changing requests

    Use this dependency for endpoints that require strict CSRF protection.

    Args:
        request: FastAPI request object
        x_csrf_token: CSRF token from header

    Returns:
        CSRF token if valid

    Raises:
        HTTPException: If CSRF token is missing or invalid
    """
    if not x_csrf_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token is required",
        )

    access_token = request.cookies.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    if not jwt_service.validate_csrf_token(access_token, x_csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        )

    return x_csrf_token


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> UserDB:
    """Get current authenticated user from JWT token

    Args:
        credentials: HTTP Bearer credentials
        db: Database session

    Returns:
        Current user

    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials

    # Check blacklist
    if await token_blacklist.is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate token
    payload = jwt_service.validate_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user
    user = await auth_service.get_user_by_id(db, payload.sub)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_from_cookie(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserDB:
    """Get current user from HTTP-only cookie

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        Current user

    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    # Check blacklist
    if await token_blacklist.is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Validate token
    payload = jwt_service.validate_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Get user
    user = await auth_service.get_user_by_id(db, payload.sub)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
        )

    return user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user

    Args:
        user_data: User registration data
        db: Database session

    Returns:
        Created user

    Raises:
        HTTPException: If username or email already exists
    """
    try:
        user = await auth_service.create_user(db, user_data)
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            status=user.status,
            full_name=user.full_name or user.display_name,
            avatar_url=user.avatar_url,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=LoginResponse)
async def login(
    credentials: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Login and get access tokens

    Args:
        credentials: Login credentials (username/email and password)
        response: FastAPI response object for setting cookies
        db: Database session

    Returns:
        Login response with tokens and user info

    Raises:
        HTTPException: If credentials are invalid
    """
    login_response = await auth_service.login(
        db,
        credentials.username,
        credentials.password,
    )

    if not login_response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Set HTTP-only cookies
    cookie_settings = _get_cookie_settings()

    # Access token cookie (shorter expiry)
    access_token_expire = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    response.set_cookie(
        key="access_token",
        value=login_response.access_token,
        max_age=int(access_token_expire.total_seconds()),
        **cookie_settings,
    )

    # Refresh token cookie (longer expiry)
    refresh_token_expire = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    response.set_cookie(
        key="refresh_token",
        value=login_response.refresh_token,
        max_age=int(refresh_token_expire.total_seconds()),
        **cookie_settings,
    )

    # CSRF token cookie (not HTTP-only, accessible to JS for reading)
    # This is used for CSRF protection in subsequent requests
    csrf_token = jwt_service.generate_csrf_token(login_response.access_token)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=int(access_token_expire.total_seconds()),
        httponly=False,  # Must be readable by JavaScript
        secure=cookie_settings["secure"],
        samesite=cookie_settings["samesite"],
        path="/",
    )

    return login_response


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
):
    """Refresh access token

    Args:
        request: FastAPI request object for reading cookies
        response: FastAPI response object for setting cookies

    Returns:
        New token pair

    Raises:
        HTTPException: If refresh token is invalid
    """
    # Try to get refresh token from cookie first, then from body
    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided",
        )

    # Check blacklist
    if await token_blacklist.is_blacklisted(refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    login_response = auth_service.refresh_tokens(refresh_token)

    if not login_response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Set HTTP-only cookies
    cookie_settings = _get_cookie_settings()

    # Access token cookie
    access_token_expire = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    response.set_cookie(
        key="access_token",
        value=login_response.access_token,
        max_age=int(access_token_expire.total_seconds()),
        **cookie_settings,
    )

    # Refresh token cookie
    refresh_token_expire = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    response.set_cookie(
        key="refresh_token",
        value=login_response.refresh_token,
        max_age=int(refresh_token_expire.total_seconds()),
        **cookie_settings,
    )

    # CSRF token cookie
    csrf_token = jwt_service.generate_csrf_token(login_response.access_token)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=int(access_token_expire.total_seconds()),
        httponly=False,
        secure=cookie_settings["secure"],
        samesite=cookie_settings["samesite"],
        path="/",
    )

    return login_response


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: UserDB = Depends(get_current_user_from_cookie),
):
    """Logout and invalidate tokens

    Args:
        request: FastAPI request object for reading cookies
        response: FastAPI response object for clearing cookies
        current_user: Current authenticated user

    Returns:
        Success message
    """
    # Get token from cookie
    token = request.cookies.get("access_token")

    if token:
        # Add access token to blacklist with TTL matching token expiration
        ttl_seconds = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        await token_blacklist.add_token(token, ttl_seconds)

    # Also blacklist refresh token if present
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        refresh_ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        await token_blacklist.add_token(refresh_token, refresh_ttl)

    # Clear cookies
    cookie_settings = _get_cookie_settings()
    response.delete_cookie(key="access_token", **{k: v for k, v in cookie_settings.items() if k != "max_age"})
    response.delete_cookie(key="refresh_token", **{k: v for k, v in cookie_settings.items() if k != "max_age"})
    response.delete_cookie(key="csrf_token", path="/", secure=cookie_settings["secure"], samesite=cookie_settings["samesite"])

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: UserDB = Depends(get_current_user_from_cookie),
):
    """Get current user information

    Args:
        current_user: Current authenticated user

    Returns:
        Current user info
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        status=current_user.status,
        full_name=current_user.full_name or current_user.display_name,
        avatar_url=current_user.avatar_url,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )
