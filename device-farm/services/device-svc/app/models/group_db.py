# Device Group Database Model (SQLAlchemy)
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, DateTime, Enum as SQLEnum, Index
from app.database import Base
from enum import Enum
import uuid
import json


class GroupType(str, Enum):
    """Group type enum"""
    CUSTOM = "custom"      # User-created custom group
    SYSTEM = "system"      # System-defined group (e.g., by OS, brand)
    TAG = "tag"            # Auto-generated from device tags


class DeviceGroupDB(Base):
    """Device group database model"""
    __tablename__ = "device_groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    type = Column(
        SQLEnum(GroupType, native_enum=False),
        default=GroupType.CUSTOM,
        nullable=False,
        index=True
    )

    # Device membership stored as JSON array
    # In production, consider using a separate junction table for better querying
    device_ids_json = Column(Text, default="[]", nullable=False)

    # Metadata
    color = Column(String(20), default="#1890ff", nullable=False)
    icon = Column(String(50), nullable=True)

    # Ownership
    created_by = Column(String(100), nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_device_groups_type_created', 'type', 'created_at'),
    )

    @property
    def device_ids(self) -> List[str]:
        """Get device IDs as list"""
        try:
            return json.loads(self.device_ids_json) if self.device_ids_json else []
        except json.JSONDecodeError:
            return []

    @device_ids.setter
    def device_ids(self, value: List[str]):
        """Set device IDs from list"""
        self.device_ids_json = json.dumps(value or [])

    def __repr__(self):
        return f"<DeviceGroupDB(id={self.id}, name={self.name}, type={self.type})>"
