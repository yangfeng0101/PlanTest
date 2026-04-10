# Reservation Pydantic Schemas
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from enum import Enum


class ReservationStatus(str, Enum):
    """Reservation status enum"""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReservationCreate(BaseModel):
    """Schema for creating a reservation"""
    device_id: str = Field(..., description="Device ID to reserve")
    user_id: str = Field(..., description="User ID making the reservation")
    start_time: datetime = Field(..., description="Reservation start time")
    end_time: datetime = Field(..., description="Reservation end time")
    purpose: Optional[str] = Field(None, description="Purpose of reservation")

    @validator('end_time')
    def end_time_after_start_time(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('end_time must be after start_time')
        return v


class ReservationUpdate(BaseModel):
    """Schema for updating a reservation"""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    purpose: Optional[str] = None

    @validator('end_time')
    def end_time_after_start_time(cls, v, values):
        if v and 'start_time' in values and values['start_time'] and v <= values['start_time']:
            raise ValueError('end_time must be after start_time')
        return v


class ReservationResponse(BaseModel):
    """Schema for reservation response"""
    id: str
    device_id: str
    user_id: str
    start_time: datetime
    end_time: datetime
    status: ReservationStatus
    purpose: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReservationListResponse(BaseModel):
    """Schema for list of reservations"""
    reservations: List[ReservationResponse]
    total: int


class ConflictDetail(BaseModel):
    """Schema for reservation conflict details"""
    conflicting_reservation_id: str
    start_time: datetime
    end_time: datetime
    user_id: str


class ReservationConflictError(BaseModel):
    """Schema for reservation conflict error"""
    detail: str
    conflicts: List[ConflictDetail]


class ReservationRenewRequest(BaseModel):
    """Schema for renewing a reservation"""
    extension_minutes: int = Field(
        default=60,
        ge=1,
        le=60,
        description="Extension duration in minutes (1-60, default 60)"
    )


class QueuePositionResponse(BaseModel):
    """Schema for queue position response"""
    reservation_id: str
    device_id: str
    position: int = Field(..., description="Queue position (1-based), 0 if not in queue")
    total_in_queue: int = Field(..., description="Total reservations in queue")
