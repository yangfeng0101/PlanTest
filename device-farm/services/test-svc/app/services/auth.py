# Authentication Service
import hashlib
import secrets
import time
from typing import Optional, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class APIKeyInfo:
    """Information about an API key"""
    key_hash: str
    name: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool = True


class AuthService:
    """
    Authentication service for API key management.

    Supports:
    - API key validation
    - Key expiration
    - Key usage tracking
    """

    def __init__(self):
        # In production, this would be backed by a database
        self._keys: Dict[str, APIKeyInfo] = {}
        self._key_expiry_hours: int = 24 * 365  # 1 year default

    def hash_key(self, key: str) -> str:
        """Hash an API key for secure storage"""
        return hashlib.sha256(key.encode()).hexdigest()

    def generate_key(self, name: str, expires_in_hours: Optional[int] = None) -> str:
        """
        Generate a new API key.

        Args:
            name: Human-readable name for the key
            expires_in_hours: Optional expiration time in hours

        Returns:
            The generated API key (shown once)
        """
        # Generate a secure random key
        key = f"df_{secrets.token_hex(32)}"
        key_hash = self.hash_key(key)

        expires_at = None
        if expires_in_hours:
            expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
        elif self._key_expiry_hours:
            expires_at = datetime.utcnow() + timedelta(hours=self._key_expiry_hours)

        key_info = APIKeyInfo(
            key_hash=key_hash,
            name=name,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
        )

        self._keys[key_hash] = key_info
        logger.info(f"Generated API key: {name}")

        return key

    def validate_key(self, key: str) -> tuple[bool, Optional[str]]:
        """
        Validate an API key.

        Args:
            key: The API key to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not key:
            return False, "API key is required"

        key_hash = self.hash_key(key)

        # Check if key exists
        if key_hash not in self._keys:
            return False, "Invalid API key"

        key_info = self._keys[key_hash]

        # Check if key is active
        if not key_info.is_active:
            return False, "API key is disabled"

        # Check expiration
        if key_info.expires_at and datetime.utcnow() > key_info.expires_at:
            return False, "API key has expired"

        # Update last used timestamp
        key_info.last_used_at = datetime.utcnow()

        return True, None

    def revoke_key(self, key_hash: str) -> bool:
        """Revoke an API key by its hash"""
        if key_hash in self._keys:
            self._keys[key_hash].is_active = False
            logger.info(f"Revoked API key: {self._keys[key_hash].name}")
            return True
        return False

    def list_keys(self) -> list[Dict]:
        """List all API keys (without revealing the actual keys)"""
        return [
            {
                "name": info.name,
                "created_at": info.created_at.isoformat(),
                "expires_at": info.expires_at.isoformat() if info.expires_at else None,
                "last_used_at": info.last_used_at.isoformat() if info.last_used_at else None,
                "is_active": info.is_active,
            }
            for info in self._keys.values()
        ]


# Global auth service instance
auth_service = AuthService()
