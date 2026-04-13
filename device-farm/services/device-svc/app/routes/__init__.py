# Routes package
from app.routes.devices import router as devices_router
from app.routes.reservations import router as reservations_router
from app.routes.groups import router as groups_router
from app.routes.metrics import router as metrics_router

__all__ = [
    "devices_router",
    "reservations_router",
    "groups_router",
    "metrics_router",
]
