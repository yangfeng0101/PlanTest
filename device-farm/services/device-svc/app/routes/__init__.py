# Routes package
from app.routes.devices import router as devices_router
from app.routes.reservations import router as reservations_router

__all__ = [
    "devices_router",
    "reservations_router",
]
