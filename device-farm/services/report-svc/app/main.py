# Report Service Main Application
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import reports, statistics, alerts, export

# Create FastAPI application
app = FastAPI(
    title="Report Service",
    description="Device Farm Report Generation and Storage Service",
    version=settings.SERVICE_VERSION,
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(
    reports.router,
    prefix=f"{settings.API_PREFIX}/reports",
    tags=["Reports"]
)
app.include_router(
    statistics.router,
    prefix=f"{settings.API_PREFIX}/statistics",
    tags=["Statistics"]
)
app.include_router(
    alerts.router,
    prefix=f"{settings.API_PREFIX}/alerts",
    tags=["Alerts"]
)
app.include_router(
    export.router,
    prefix=f"{settings.API_PREFIX}/export",
    tags=["Export"]
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
