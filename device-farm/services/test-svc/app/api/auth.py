# Auth API Router
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import (
    auth_service,
    UserCreate,
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
            role=user.role.value,
            status=user.status.value,
            full_name=user.full_name,
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
    credentials: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Login and get access tokens

    Args:
        credentials: Login credentials (username/email and password)
        db: Database session

    Returns:
        Login response with tokens and user info

    Raises:
        HTTPException: If credentials are invalid
    """
    response = await auth_service.login(
        db,
        credentials.username,
        credentials.password,
    )

    if not response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return response


@router.post("/refresh")
async def refresh_token(
    request: RefreshTokenRequest,
):
    """Refresh access token

    Args:
        request: Refresh token request body

    Returns:
        New token pair

    Raises:
        HTTPException: If refresh token is invalid
    """
    # Check blacklist
    if await token_blacklist.is_blacklisted(request.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    response = auth_service.refresh_tokens(request.refresh_token)

    if not response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    return response


@router.post("/logout")
async def logout(
    current_user: UserDB = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Logout and invalidate tokens

    Args:
        current_user: Current authenticated user
        credentials: HTTP Bearer credentials

    Returns:
        Success message
    """
    # Add access token to blacklist with TTL matching token expiration
    token = credentials.credentials
    ttl_seconds = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    await token_blacklist.add_token(token, ttl_seconds)

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: UserDB = Depends(get_current_user),
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
        role=current_user.role.value,
        status=current_user.status.value,
        full_name=current_user.full_name,
        avatar_url=current_user.avatar_url,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )
