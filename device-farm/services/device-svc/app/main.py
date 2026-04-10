# Device Service Main Application
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.routes import devices_router, reservations_router
from app.services import device_service
from app.websocket import ws_manager
from app.tasks import reservation_tasks

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Device Service...")

    # Start device scanning
    await device_service.start_scanning()
    logger.info("Device scanning started")

    # Start WebSocket heartbeat
    await ws_manager.start_heartbeat()
    await ws_manager.start_device_updates()
    logger.info("WebSocket services started")

    # Start reservation background tasks
    await reservation_tasks.start()
    logger.info("Reservation background tasks started")

    # Initial device scan
    await device_service.scan_devices()

    yield

    # Shutdown
    logger.info("Shutting down Device Service...")
    await device_service.stop_scanning()
    await ws_manager.stop_heartbeat()
    await reservation_tasks.stop()


# Create FastAPI application
app = FastAPI(
    title="Device Service",
    description="Device Farm Device Management Service - Manage Android devices via ADB",
    version=settings.SERVICE_VERSION,
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
    lifespan=lifespan
)

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
    devices_router,
    prefix=f"{settings.API_PREFIX}/devices",
    tags=["Devices"]
)
app.include_router(
    reservations_router,
    prefix=f"{settings.API_PREFIX}/reservations",
    tags=["Reservations"]
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
