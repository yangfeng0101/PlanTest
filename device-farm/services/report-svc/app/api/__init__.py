# API Package
from app.api.reports import router as reports_router
from app.api.statistics import router as statistics_router
from app.api.alerts import router as alerts_router

__all__ = ["reports_router", "statistics_router", "alerts_router"]
