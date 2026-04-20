# Test Service Main Application
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import scripts, tasks, schedules, auth, users
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.database import init_db, close_db

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

# Rate limit middleware
app.add_middleware(RateLimitMiddleware)

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
app.include_router(
    users.router,
    prefix=f"{settings.API_PREFIX}/users",
    tags=["Users"]
)


@app.on_event("startup")
async def startup_event():
    """Initialize database and validate configuration."""
    # Initialize database tables
    await init_db()

    settings.validate_jwt_config()
    settings.validate_api_key_config()

    # Start WebSocket heartbeat and cleanup tasks
    from app.api.tasks import manager
    await manager.start_heartbeat()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    # Stop WebSocket heartbeat and cleanup tasks
    from app.api.tasks import manager
    await manager.stop_heartbeat()

    # Close database connection
    await close_db()


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
