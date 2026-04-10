# Rate Limit Middleware
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Optional, Tuple
import time
import redis
import logging
import os

logger = logging.getLogger(__name__)

# Redis connection for rate limiting
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def get_redis_client() -> redis.Redis:
    """Get Redis client for rate limiting."""
    try:
        client = redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except redis.ConnectionError:
        logger.warning("Redis unavailable for rate limiting, using in-memory fallback")
        return None


# Rate limit configuration: (max_requests, window_seconds)
RATE_LIMITS: dict[str, Tuple[int, int]] = {
    "/api/v1/auth/login": (5, 60),      # 5 requests per minute
    "/api/v1/auth/register": (3, 60),   # 3 requests per minute
    "/api/v1/auth/refresh": (10, 60),   # 10 requests per minute
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware for authentication endpoints.

    Uses Redis for distributed rate limiting with in-memory fallback.
    Rate limits are configured per endpoint in RATE_LIMITS dict.
    """

    # In-memory fallback storage: {key: (count, reset_time)}
    _memory_store: dict[str, Tuple[int, float]] = {}

    def __init__(self, app):
        super().__init__(app)
        self.redis = get_redis_client()

    def _get_client_key(self, request: Request, path: str) -> str:
        """Generate rate limit key for client + path."""
        client_ip = request.client.host if request.client else "unknown"
        return f"rate_limit:{path}:{client_ip}"

    async def _check_rate_limit_redis(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> Tuple[bool, int, int]:
        """Check rate limit using Redis.

        Returns:
            (allowed, remaining, retry_after)
        """
        try:
            now = time.time()
            window_start = now - window_seconds

            pipe = self.redis.pipeline()
            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)
            # Count current entries
            pipe.zcard(key)
            # Add new entry
            pipe.zadd(key, {str(now): now})
            # Set expiry
            pipe.expire(key, window_seconds)

            results = pipe.execute()
            count = results[1]

            if count >= max_requests:
                # Calculate retry after
                oldest = self.redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    retry_after = int(oldest[0][1] + window_seconds - now) + 1
                else:
                    retry_after = window_seconds
                return False, 0, retry_after

            remaining = max_requests - count - 1
            return True, remaining, 0

        except redis.RedisError as e:
            logger.warning(f"Redis rate limit error: {e}, falling back to memory")
            return await self._check_rate_limit_memory(key, max_requests, window_seconds)

    async def _check_rate_limit_memory(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> Tuple[bool, int, int]:
        """Check rate limit using in-memory storage (fallback).

        Returns:
            (allowed, remaining, retry_after)
        """
        now = time.time()

        if key in self._memory_store:
            count, reset_time = self._memory_store[key]

            if now > reset_time:
                # Window expired, reset
                self._memory_store[key] = (1, now + window_seconds)
                return True, max_requests - 1, 0

            if count >= max_requests:
                retry_after = int(reset_time - now) + 1
                return False, 0, retry_after

            # Increment count
            self._memory_store[key] = (count + 1, reset_time)
            return True, max_requests - count - 1, 0

        # First request
        self._memory_store[key] = (1, now + window_seconds)
        return True, max_requests - 1, 0

    async def dispatch(self, request: Request, call_next):
        # Check if path has rate limit
        path = request.url.path

        # Find matching rate limit config
        rate_limit = None
        for pattern, config in RATE_LIMITS.items():
            if path.startswith(pattern):
                rate_limit = config
                break

        if not rate_limit:
            return await call_next(request)

        max_requests, window_seconds = rate_limit
        key = self._get_client_key(request, path)

        # Check rate limit
        if self.redis:
            allowed, remaining, retry_after = await self._check_rate_limit_redis(
                key, max_requests, window_seconds
            )
        else:
            allowed, remaining, retry_after = await self._check_rate_limit_memory(
                key, max_requests, window_seconds
            )

        if not allowed:
            logger.warning(
                f"Rate limit exceeded for {path} from "
                f"{request.client.host if request.client else 'unknown'}"
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Too many requests. Please try again later.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response


def rate_limit(max_requests: int, window_seconds: int = 60):
    """
    Dependency for rate limiting in route handlers.

    Usage:
        @router.post("/login")
        async def login(_: None = Depends(rate_limit(5, 60))):
            ...

    Args:
        max_requests: Maximum requests allowed in window
        window_seconds: Window duration in seconds

    Returns:
        None if allowed

    Raises:
        HTTPException: If rate limit exceeded
    """
    # This is a placeholder for route-level rate limiting
    # The middleware handles rate limiting globally
    return None
