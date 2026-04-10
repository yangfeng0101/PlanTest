# Models package
from app.models.device import (
    Device,
    DeviceStatus,
    DeviceCreate,
    DeviceUpdate,
    DeviceOccupyRequest,
    DeviceListResponse,
    DeviceFilter,
)
from app.models.reservation import (
    DeviceReservation,
    ReservationStatus as ModelReservationStatus,
)
from app.models.reservation_schemas import (
    ReservationStatus,
    ReservationCreate,
    ReservationUpdate,
    ReservationResponse,
    ReservationListResponse,
    ReservationConflictError,
    ConflictDetail,
)
from app.models.group import (
    DeviceGroup,
    GroupType,
    GroupCreate,
    GroupUpdate,
    GroupDeviceOperation,
    GroupListResponse,
    GroupDetail,
)

__all__ = [
    "Device",
    "DeviceStatus",
    "DeviceCreate",
    "DeviceUpdate",
    "DeviceOccupyRequest",
    "DeviceListResponse",
    "DeviceFilter",
    "DeviceReservation",
    "ModelReservationStatus",
    "ReservationStatus",
    "ReservationCreate",
    "ReservationUpdate",
    "ReservationResponse",
    "ReservationListResponse",
    "ReservationConflictError",
    "ConflictDetail",
    "DeviceGroup",
    "GroupType",
    "GroupCreate",
    "GroupUpdate",
    "GroupDeviceOperation",
    "GroupListResponse",
    "GroupDetail",
]
