# Device Threshold Config Database Model (SQLAlchemy)
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Float, Index
from app.database import Base
import uuid


class DeviceThresholdDB(Base):
    """Device threshold configuration database model"""
    __tablename__ = "device_thresholds"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(100), unique=True, nullable=False, index=True)
    cpu_warning = Column(Float, default=80.0, nullable=False)
    cpu_critical = Column(Float, default=95.0, nullable=False)
    memory_warning = Column(Float, default=80.0, nullable=False)
    memory_critical = Column(Float, default=95.0, nullable=False)
    battery_warning = Column(Float, default=20.0, nullable=False)
    battery_critical = Column(Float, default=10.0, nullable=False)
    temperature_warning = Column(Float, default=45.0, nullable=False)
    temperature_critical = Column(Float, default=55.0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_device_thresholds_device_id', 'device_id'),
    )

    def __repr__(self):
        return f"<DeviceThreshold(device_id={self.device_id})>"
