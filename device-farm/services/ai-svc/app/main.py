# AI Service Main Application
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.ocr import router as ocr_router
from app.api.locate import router as locate_router
from app.api.generate import router as generate_router

# Create FastAPI application
app = FastAPI(
    title="AI Service",
    description="Device Farm AI Service - OCR, Element Location, Test Generation",
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
