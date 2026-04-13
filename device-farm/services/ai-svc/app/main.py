# AI Service Main Application
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import httpx
import os
import logging

from app.config import settings
from app.api.ocr import router as ocr_router
from app.api.locate import router as locate_router
from app.api.generate import router as generate_router

logger = logging.getLogger(__name__)

# Test service URL for token validation
TEST_SVC_URL = os.getenv("TEST_SVC_URL", "http://localhost:8003")


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for AI Service.
    Validates JWT tokens by calling test-svc auth API.
    """

    # Paths that don't require authentication
    PUBLIC_PATHS = {
        "/",
        "/health",
        "/api/v1/docs",
        "/api/v1/redoc",
        "/openapi.json",
    }

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public paths
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Get Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required. Provide Authorization: Bearer token."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]

        # Validate token with test-svc
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{TEST_SVC_URL}/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0
                )

            if response.status_code != 200:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid or expired token"},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Token is valid, proceed
            return await call_next(request)

        except httpx.RequestError:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Authentication service unavailable"},
            )


# Create FastAPI application
app = FastAPI(
    title="AI Service",
    description="Device Farm AI Service - OCR, Element Location, Test Generation",
    version=settings.SERVICE_VERSION,
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
)

# Add authentication middleware
app.add_middleware(AuthMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(
    ocr_router,
    prefix=f"{settings.API_PREFIX}/ocr",
    tags=["OCR"]
)
app.include_router(
    locate_router,
    prefix=f"{settings.API_PREFIX}/locate",
    tags=["Element Location"]
)
app.include_router(
    generate_router,
    prefix=f"{settings.API_PREFIX}/generate",
    tags=["Test Generation"]
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "docs": f"{settings.API_PREFIX}/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
