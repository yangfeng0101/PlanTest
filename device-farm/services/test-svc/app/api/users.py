# User Management API Router
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.user import UserDB, UserRole, UserStatus
from app.api.auth import get_current_user, require_csrf_token
from app.services.password_service import password_service


router = APIRouter()


class UserUpdateRequest(BaseModel):
    """User update request"""
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    status: Optional[str] = None


class UserRoleUpdateRequest(BaseModel):
    """User role update request"""
    role: str


class UserPasswordResetRequest(BaseModel):
    """User password reset request"""
    password: str


class UserCreateRequest(BaseModel):
    """User create request (admin only)"""
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    role: str = "user"


class UserListResponse(BaseModel):
    """User list response"""
    id: str
    username: str
    email: str
    role: str
    status: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaginatedUserResponse(BaseModel):
    """Paginated user response"""
    items: List[UserListResponse]
    total: int
    page: int
    page_size: int


def check_admin(current_user: UserDB) -> None:
    """Check if current user is admin"""
    if not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )


@router.get("", response_model=PaginatedUserResponse)
async def list_users(
    page: int = 1,
    page_size: int = 20,
    role: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)

    Args:
        page: Page number
        page_size: Items per page
        role: Filter by role
        status: Filter by status
        keyword: Search keyword
        current_user: Current authenticated user
        db: Database session

    Returns:
        Paginated user list
    """
    check_admin(current_user)

    # Build query
    query = select(UserDB)

    if role:
        try:
            role_enum = UserRole(role)
            query = query.where(UserDB.role == role_enum)
        except ValueError:
            pass

    if status:
        try:
            status_enum = UserStatus(status)
            query = query.where(UserDB.status == status_enum)
        except ValueError:
            pass

    if keyword:
        query = query.where(
            (UserDB.username.ilike(f"%{keyword}%")) |
            (UserDB.email.ilike(f"%{keyword}%")) |
            (UserDB.full_name.ilike(f"%{keyword}%"))
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(UserDB.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    users = list(result.scalars().all())

    return PaginatedUserResponse(
        items=[UserListResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=UserListResponse)
async def get_user(
    user_id: str,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user by ID (admin only)

    Args:
        user_id: User ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        User details
    """
    check_admin(current_user)

    query = select(UserDB).where(UserDB.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserListResponse.model_validate(user)


@router.post("", response_model=UserListResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreateRequest,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user (admin only)

    Args:
        user_data: User creation data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Created user
    """
    check_admin(current_user)

    # Check if username exists
    query = select(UserDB).where(UserDB.username == user_data.username)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    # Check if email exists
    query = select(UserDB).where(UserDB.email == user_data.email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists")

    # Validate role
    try:
        role_enum = UserRole(user_data.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {user_data.role}")

    # Create user
    user = UserDB(
        username=user_data.username,
        email=user_data.email,
        password_hash=password_service.hash_password(user_data.password),
        role=role_enum,
        status=UserStatus.ACTIVE,
        full_name=user_data.full_name,
    )

    db.add(user)
    await db.flush()
    await db.refresh(user)

    return UserListResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserListResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdateRequest,
    current_user: UserDB = Depends(get_current_user),
    _: str = Depends(require_csrf_token),
    db: AsyncSession = Depends(get_db),
):
    """Update user (admin only)

    Args:
        user_id: User ID
        user_data: User update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Updated user
    """
    check_admin(current_user)

    query = select(UserDB).where(UserDB.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update fields
    if user_data.username is not None:
        # Check if username exists
        query = select(UserDB).where(
            UserDB.username == user_data.username,
            UserDB.id != user_id
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Username already exists")
        user.username = user_data.username

    if user_data.email is not None:
        # Check if email exists
        query = select(UserDB).where(
            UserDB.email == user_data.email,
            UserDB.id != user_id
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already exists")
        user.email = user_data.email

    if user_data.full_name is not None:
        user.full_name = user_data.full_name

    if user_data.avatar_url is not None:
        user.avatar_url = user_data.avatar_url

    if user_data.status is not None:
        try:
            user.status = UserStatus(user_data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {user_data.status}")

    await db.flush()
    await db.refresh(user)

    return UserListResponse.model_validate(user)


@router.patch("/{user_id}/role", response_model=UserListResponse)
async def update_user_role(
    user_id: str,
    role_data: UserRoleUpdateRequest,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user role (admin only)

    Args:
        user_id: User ID
        role_data: Role update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Updated user
    """
    check_admin(current_user)

    query = select(UserDB).where(UserDB.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admin from demoting themselves
    if user.id == current_user.id and role_data.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=400, detail="Cannot change your own admin role")

    try:
        user.role = UserRole(role_data.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role_data.role}")

    await db.flush()
    await db.refresh(user)

    return UserListResponse.model_validate(user)


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    password_data: UserPasswordResetRequest,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset user password (admin only)

    Args:
        user_id: User ID
        password_data: Password reset data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message
    """
    check_admin(current_user)

    query = select(UserDB).where(UserDB.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = password_service.hash_password(password_data.password)
    await db.flush()

    return {"message": "Password reset successful"}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete user (admin only)

    Args:
        user_id: User ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message
    """
    check_admin(current_user)

    # Prevent admin from deleting themselves
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    query = select(UserDB).where(UserDB.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.flush()

    return {"message": "User deleted successfully"}
