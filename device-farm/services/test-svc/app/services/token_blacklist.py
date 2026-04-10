# Token Blacklist Service using Redis
import json
from datetime import datetime, timedelta
from typing import Optional
import redis.asyncio as redis
from app.config import settings


class TokenBlacklistService:
    """Redis-based token blacklist for JWT revocation."""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._prefix = "token_blacklist:"

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
        return self._redis

    async def add_token(self, token: str, expires_in_seconds: int) -> bool:
        """Add a token to the blacklist.

        Args:
            token: The JWT token to blacklist
            expires_in_seconds: TTL in seconds (should match token expiration)

        Returns:
            True if successful
        """
        try:
            r = await self._get_redis()
            key = f"{self._prefix}{token}"
            # Store with TTL so expired tokens are automatically removed
            await r.setex(key, expires_in_seconds, json.dumps({
                "revoked_at": datetime.utcnow().isoformat(),
                "reason": "logout"
            }))
            return True
        except Exception as e:
            # Fallback to in-memory if Redis fails
            print(f"Redis error, falling back to in-memory: {e}")
            return False

    async def is_blacklisted(self, token: str) -> bool:
        """Check if a token is blacklisted.

        Args:
            token: The JWT token to check

        Returns:
            True if token is blacklisted
        """
        try:
            r = await self._get_redis()
            key = f"{self._prefix}{token}"
            return await r.exists(key) > 0
        except Exception as e:
            # If Redis fails, deny access for safety
            print(f"Redis error in is_blacklisted: {e}")
            return False

    async def remove_token(self, token: str) -> bool:
        """Remove a token from the blacklist (for testing).

        Args:
            token: The JWT token to remove

        Returns:
            True if token was removed
        """
        try:
            r = await self._get_redis()
            key = f"{self._prefix}{token}"
            await r.delete(key)
            return True
        except Exception as e:
            print(f"Redis error in remove_token: {e}")
            return False

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# Global instance
token_blacklist = TokenBlacklistService()
