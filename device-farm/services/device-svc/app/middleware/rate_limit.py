# Rate Limit Middleware for Device Service
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Tuple
import time
import logging
import os

logger = logging.getLogger(__name__)

# Rate limit configuration: {path_pattern: (max_requests, window_seconds)}
RATE_LIMITS: dict[str, Tuple[int, int]] = {
    # Device command execution: 60 requests per minute per client
    "/api/v1/devices/": (60, 60),  # Matches all device command endpoints
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware for device command endpoints.

    Uses in-memory storage for rate limiting (suitable for single instance).
    For distributed deployments, consider using Redis-based rate limiting.
    """

    # In-memory storage: {key: (count, reset_time)}
    _memory_store: dict[str, Tuple[int, float]] = {}

    def _get_client_key(self, request: Request, path: str) -> str:
        """Generate rate limit key for client + path."""
        client_ip = request.client.host if request.client else "unknown"
        return f"rate_limit:{path}:{client_ip}"

    async def _check_rate_limit_memory(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> Tuple[bool, int, int]:
        """Check rate limit using in-memory storage.

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

        # Check if this is a command endpoint (POST to /devices/{id}/command)
        # Only apply rate limiting to command execution
        if request.method == "POST" and "/command" in path:
            max_requests, window_seconds = RATE_LIMITS["/api/v1/devices/"]
            key = self._get_client_key(request, path)

            # Check rate limit
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

        return await call_next(request)
