# User Database Model (SQLAlchemy)
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase
from enum import Enum
import uuid

from app.models.database import Base


class UserRole(str, Enum):
    """User role enum"""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    """User status enum"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class UserDB(Base):
    """User database model"""
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False, index=True)
    display_name = Column(String(128), nullable=True)
    role = Column(String(16), default="user", nullable=False)
    password_hash = Column(String(255), nullable=True)
    status = Column(String(20), default="active", nullable=True)
    full_name = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"

    def is_active(self) -> bool:
        """Check if user is active"""
        return self.status == UserStatus.ACTIVE.value

    def is_admin(self) -> bool:
        """Check if user is admin"""
        return self.role == UserRole.ADMIN.value
