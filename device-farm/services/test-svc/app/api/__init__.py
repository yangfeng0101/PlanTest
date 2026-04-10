# API Package
from app.api.scripts import router as scripts_router
from app.api.tasks import router as tasks_router
from app.api.schedules import router as schedules_router
from app.api.auth import router as auth_router

__all__ = ["scripts_router", "tasks_router", "schedules_router", "auth_router"]
