# Device Reservation Model (SQLAlchemy)
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Enum as SQLEnum, Index, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from enum import Enum
import uuid


class ReservationStatus(str, Enum):
    """Reservation status enum"""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeviceReservation(Base):
    """Device reservation database model"""
    __tablename__ = "device_reservations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False, index=True)
    status = Column(
        SQLEnum(ReservationStatus),
        default=ReservationStatus.PENDING,
        nullable=False,
        index=True
    )
    purpose = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('ix_device_reservations_device_time', 'device_id', 'start_time', 'end_time'),
        Index('ix_device_reservations_user_status', 'user_id', 'status'),
    )

    def __repr__(self):
        return f"<DeviceReservation(id={self.id}, device_id={self.device_id}, status={self.status})>"

    def is_active(self) -> bool:
        """Check if reservation is currently active"""
        now = datetime.utcnow()
        return (
            self.status == ReservationStatus.ACTIVE
            and self.start_time <= now < self.end_time
        )

    def is_pending(self) -> bool:
        """Check if reservation is pending"""
        return self.status == ReservationStatus.PENDING

    def is_completed(self) -> bool:
        """Check if reservation is completed"""
        return self.status == ReservationStatus.COMPLETED

    def is_cancelled(self) -> bool:
        """Check if reservation is cancelled"""
        return self.status == ReservationStatus.CANCELLED

    def overlaps(self, other: 'DeviceReservation') -> bool:
        """Check if this reservation overlaps with another"""
        if self.device_id != other.device_id:
            return False
        if self.status == ReservationStatus.CANCELLED or other.status == ReservationStatus.CANCELLED:
            return False
        return self.start_time < other.end_time and other.start_time < self.end_time
