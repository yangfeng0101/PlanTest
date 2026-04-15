# Device Service - Device Models
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    MAINTAINING = "maintaining"
    MAINTENANCE = "maintenance"  # Legacy alias


class Device(BaseModel):
    """Device model"""
    id: str = Field(..., description="Device unique identifier (serial number)")
    name: str = Field(..., description="Device name")
    model: str = Field(..., description="Device model")
    brand: str = Field(..., description="Device brand")
    os: str = Field(default="android", description="Operating system")
    os_version: str = Field(..., description="OS version")
    status: DeviceStatus = Field(default=DeviceStatus.ONLINE, description="Device status")

    # Hardware info
    screen_resolution: str = Field(..., description="Screen resolution (e.g., 1080x1920)")
    screen_size: float = Field(..., description="Screen size in inches")
    cpu: str = Field(..., description="CPU info")
    memory: str = Field(..., description="Memory size")
    storage: str = Field(..., description="Storage size")
    battery_level: int = Field(default=100, description="Battery level (0-100)")

    # Occupation info
    occupied_by: Optional[str] = Field(default=None, description="User who occupied the device")
    occupied_at: Optional[datetime] = Field(default=None, description="Occupation timestamp")

    # Timestamps
    last_active_at: datetime = Field(default_factory=datetime.now, description="Last active time")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Tags
    tags: List[str] = Field(default_factory=list, description="Device tags")

    # Thumbnail
    thumbnail: Optional[str] = Field(default=None, description="Device thumbnail URL")

    class Config:
        use_enum_values = True


class DeviceCreate(BaseModel):
    """Device creation model"""
    name: str
    model: str
    brand: str
    os_version: str
    screen_resolution: str
    screen_size: float
    cpu: str
    memory: str
    storage: str
    tags: List[str] = []


class DeviceUpdate(BaseModel):
    """Device update model"""
    name: Optional[str] = None
    status: Optional[DeviceStatus] = None
    tags: Optional[List[str]] = None


class DeviceOccupyRequest(BaseModel):
    """Device occupy request"""
    user_id: str = Field(..., description="User ID who wants to occupy")
    duration: Optional[int] = Field(default=None, description="Occupation duration in minutes")


class DeviceListResponse(BaseModel):
    """Device list response"""
    devices: List[Device]
    total: int


class DeviceFilter(BaseModel):
    """Device filter parameters"""
    status: Optional[DeviceStatus] = None
    brand: Optional[str] = None
    os_version: Optional[str] = None
    keyword: Optional[str] = None
    tags: Optional[List[str]] = None
