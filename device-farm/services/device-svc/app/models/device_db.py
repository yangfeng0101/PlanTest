# Device Database Model (SQLAlchemy)
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, DateTime, Integer, Float, Enum as SQLEnum, Index
from app.database import Base
from enum import Enum
import json


class DeviceStatusDB(str, Enum):
    """Device status enum for database"""
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    MAINTAINING = "maintaining"


class DeviceDB(Base):
    """Device database model for persistence"""
    __tablename__ = "devices"

    id = Column(String(100), primary_key=True)  # Device serial number
    name = Column(String(200), nullable=False)
    model = Column(String(100), nullable=False, index=True)
    brand = Column(String(100), nullable=False, index=True)
    os = Column(String(20), default="android", nullable=False)
    os_version = Column(String(50), nullable=False)
    status = Column(
        SQLEnum(DeviceStatusDB),
        default=DeviceStatusDB.ONLINE,
        nullable=False,
        index=True
    )

    # Hardware info
    screen_resolution = Column(String(50), nullable=False)
    screen_size = Column(Float, nullable=False)
    cpu = Column(String(200), nullable=False)
    memory = Column(String(50), nullable=False)
    storage = Column(String(50), nullable=False)
    battery_level = Column(Integer, default=100, nullable=False)

    # Occupation info
    occupied_by = Column(String(100), nullable=True, index=True)
    occupied_at = Column(DateTime, nullable=True)

    # Timestamps
    last_active_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Tags stored as JSON
    tags_json = Column(Text, default="[]", nullable=False)

    # Thumbnail
    thumbnail = Column(Text, nullable=True)

    __table_args__ = (
        Index('ix_devices_status_brand', 'status', 'brand'),
        Index('ix_devices_occupied_by', 'occupied_by'),
    )

    @property
    def tags(self) -> List[str]:
        """Get tags as list"""
        try:
            return json.loads(self.tags_json) if self.tags_json else []
        except json.JSONDecodeError:
            return []

    @tags.setter
    def tags(self, value: List[str]):
        """Set tags from list"""
        self.tags_json = json.dumps(value or [])

    def __repr__(self):
        return f"<DeviceDB(id={self.id}, name={self.name}, status={self.status})>"
