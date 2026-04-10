# Test Service Main Application
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import scripts, tasks, schedules, auth
from app.middleware.auth import AuthMiddleware

# Create FastAPI application
app = FastAPI(
    title="Test Service",
    description="Device Farm Test Scheduling and Execution Service",
    version=settings.SERVICE_VERSION,
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware (applies to all routes)
app.add_middleware(AuthMiddleware)

# Include routers
app.include_router(
    scripts.router,
    prefix=f"{settings.API_PREFIX}/scripts",
    tags=["Scripts"]
)
app.include_router(
    tasks.router,
    prefix=f"{settings.API_PREFIX}/tasks",
    tags=["Tasks"]
)
app.include_router(
    schedules.router,
    prefix=f"{settings.API_PREFIX}/schedules",
    tags=["Schedules"]
)
app.include_router(
    auth.router,
    prefix=f"{settings.API_PREFIX}/auth",
    tags=["Auth"]
)


@app.on_event("startup")
async def validate_config():
    """Validate configuration at startup."""
    settings.validate_jwt_config()


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
