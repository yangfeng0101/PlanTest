# JWT Service for Token Generation and Validation
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from pydantic import BaseModel

from app.config import settings


class TokenPayload(BaseModel):
    """Token payload model"""
    sub: str  # User ID
    username: str
    role: str
    exp: datetime
    iat: datetime
    type: str  # "access" or "refresh"


class TokenResponse(BaseModel):
    """Token response model"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class JWTService:
    """Service for JWT token generation and validation"""

    def __init__(
        self,
        secret_key: str = settings.JWT_SECRET_KEY,
        algorithm: str = settings.JWT_ALGORITHM,
        access_token_expire_minutes: int = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        refresh_token_expire_days: int = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days

    def create_access_token(
        self,
        user_id: str,
        username: str,
        role: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create an access token

        Args:
            user_id: User ID
            username: Username
            role: User role
            expires_delta: Optional custom expiration time

        Returns:
            Encoded JWT access token
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)

        now = datetime.utcnow()

        payload = {
            "sub": user_id,
            "username": username,
            "role": role,
            "exp": expire,
            "iat": now,
            "type": "access",
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(
        self,
        user_id: str,
        username: str,
        role: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a refresh token

        Args:
            user_id: User ID
            username: Username
            role: User role
            expires_delta: Optional custom expiration time

        Returns:
            Encoded JWT refresh token
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)

        now = datetime.utcnow()

        payload = {
            "sub": user_id,
            "username": username,
            "role": role,
            "exp": expire,
            "iat": now,
            "type": "refresh",
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_token_pair(
        self,
        user_id: str,
        username: str,
        role: str,
    ) -> TokenResponse:
        """Create both access and refresh tokens

        Args:
            user_id: User ID
            username: Username
            role: User role

        Returns:
            TokenResponse with both tokens
        """
        access_token = self.create_access_token(user_id, username, role)
        refresh_token = self.create_refresh_token(user_id, username, role)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self.access_token_expire_minutes * 60,
        )

    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and validate a JWT token

        Args:
            token: JWT token to decode

        Returns:
            Decoded payload or None if invalid
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def validate_token(self, token: str, token_type: str = "access") -> Optional[TokenPayload]:
        """Validate a JWT token and return its payload

        Args:
            token: JWT token to validate
            token_type: Expected token type ("access" or "refresh")

        Returns:
            TokenPayload if valid, None otherwise
        """
        payload = self.decode_token(token)

        if not payload:
            return None

        if payload.get("type") != token_type:
            return None

        try:
            return TokenPayload(
                sub=payload["sub"],
                username=payload["username"],
                role=payload["role"],
                exp=datetime.fromtimestamp(payload["exp"]),
                iat=datetime.fromtimestamp(payload["iat"]),
                type=payload["type"],
            )
        except (KeyError, TypeError):
            return None

    def validate_access_token(self, token: str) -> Optional[TokenPayload]:
        """Validate an access token

        Args:
            token: Access token to validate

        Returns:
            TokenPayload if valid, None otherwise
        """
        return self.validate_token(token, "access")

    def validate_refresh_token(self, token: str) -> Optional[TokenPayload]:
        """Validate a refresh token

        Args:
            token: Refresh token to validate

        Returns:
            TokenPayload if valid, None otherwise
        """
        return self.validate_token(token, "refresh")

    def refresh_access_token(self, refresh_token: str) -> Optional[TokenResponse]:
        """Refresh an access token using a valid refresh token

        Args:
            refresh_token: Valid refresh token

        Returns:
            New TokenResponse if refresh token is valid, None otherwise
        """
        payload = self.validate_refresh_token(refresh_token)

        if not payload:
            return None

        return self.create_token_pair(
            user_id=payload.sub,
            username=payload.username,
            role=payload.role,
        )


# Global instance
jwt_service = JWTService()
