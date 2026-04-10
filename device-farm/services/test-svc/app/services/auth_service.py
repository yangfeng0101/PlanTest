# Auth Service for User Management
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
import uuid

from app.models.user import UserDB, UserRole, UserStatus
from app.services.password_service import password_service
from app.services.jwt_service import jwt_service, TokenResponse


class UserCreate(BaseModel):
    """User registration request"""
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    """User login request"""
    username: str
    password: str


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str


class UserResponse(BaseModel):
    """User response model"""
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


class LoginResponse(BaseModel):
    """Login response with tokens and user info"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class AuthService:
    """Service for user authentication and management"""

    async def create_user(
        self,
        db: AsyncSession,
        user_data: UserCreate,
        role: UserRole = UserRole.USER,
    ) -> UserDB:
        """Create a new user

        Args:
            db: Database session
            user_data: User creation data
            role: User role (default: USER)

        Returns:
            Created user

        Raises:
            ValueError: If username or email already exists
        """
        # Check if username exists
        query = select(UserDB).where(UserDB.username == user_data.username)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValueError(f"Username '{user_data.username}' already exists")

        # Check if email exists
        query = select(UserDB).where(UserDB.email == user_data.email)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise ValueError(f"Email '{user_data.email}' already exists")

        # Hash password
        password_hash = password_service.hash_password(user_data.password)

        # Create user
        user = UserDB(
            id=str(uuid.uuid4()),
            username=user_data.username,
            email=user_data.email,
            password_hash=password_hash,
            role=role,
            status=UserStatus.ACTIVE,
            full_name=user_data.full_name,
        )

        db.add(user)
        await db.flush()
        await db.refresh(user)

        return user

    async def authenticate_user(
        self,
        db: AsyncSession,
        username: str,
        password: str,
    ) -> Optional[UserDB]:
        """Authenticate a user by username and password

        Args:
            db: Database session
            username: Username
            password: Plain text password

        Returns:
            User if authentication successful, None otherwise
        """
        # Find user by username or email
        query = select(UserDB).where(
            (UserDB.username == username) | (UserDB.email == username)
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Check if user is active
        if not user.is_active():
            return None

        # Verify password
        if not password_service.verify_password(password, user.password_hash):
            return None

        # Update last login time
        user.last_login_at = datetime.utcnow()
        await db.flush()

        return user

    async def login(
        self,
        db: AsyncSession,
        username: str,
        password: str,
    ) -> Optional[LoginResponse]:
        """Login a user and return tokens

        Args:
            db: Database session
            username: Username or email
            password: Plain text password

        Returns:
            LoginResponse if successful, None otherwise
        """
        user = await self.authenticate_user(db, username, password)

        if not user:
            return None

        # Generate tokens
        token_response = jwt_service.create_token_pair(
            user_id=user.id,
            username=user.username,
            role=user.role.value,
        )

        return LoginResponse(
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            token_type=token_response.token_type,
            expires_in=token_response.expires_in,
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                role=user.role.value,
                status=user.status.value,
                full_name=user.full_name,
                avatar_url=user.avatar_url,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
            ),
        )

    async def get_user_by_id(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> Optional[UserDB]:
        """Get a user by ID

        Args:
            db: Database session
            user_id: User ID

        Returns:
            User if found, None otherwise
        """
        query = select(UserDB).where(UserDB.id == user_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_username(
        self,
        db: AsyncSession,
        username: str,
    ) -> Optional[UserDB]:
        """Get a user by username

        Args:
            db: Database session
            username: Username

        Returns:
            User if found, None otherwise
        """
        query = select(UserDB).where(UserDB.username == username)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_email(
        self,
        db: AsyncSession,
        email: str,
    ) -> Optional[UserDB]:
        """Get a user by email

        Args:
            db: Database session
            email: Email address

        Returns:
            User if found, None otherwise
        """
        query = select(UserDB).where(UserDB.email == email)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    def refresh_tokens(self, refresh_token: str) -> Optional[TokenResponse]:
        """Refresh access token using refresh token

        Args:
            refresh_token: Valid refresh token

        Returns:
            New TokenResponse if valid, None otherwise
        """
        return jwt_service.refresh_access_token(refresh_token)


# Global instance
auth_service = AuthService()
