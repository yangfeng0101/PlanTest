# Device Group Model
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class GroupType(str, Enum):
    """Group type enum"""
    CUSTOM = "custom"      # User-created custom group
    SYSTEM = "system"      # System-defined group (e.g., by OS, brand)
    TAG = "tag"            # Auto-generated from device tags


class DeviceGroup(BaseModel):
    """Device group model"""
    id: str = Field(..., description="Group unique identifier")
    name: str = Field(..., description="Group name")
    description: Optional[str] = Field(default=None, description="Group description")
    type: GroupType = Field(default=GroupType.CUSTOM, description="Group type")

    # Device membership
    device_ids: List[str] = Field(default_factory=list, description="List of device IDs in this group")

    # Metadata
    color: Optional[str] = Field(default="#1890ff", description="Group color for UI")
    icon: Optional[str] = Field(default=None, description="Group icon name")

    # Ownership
    created_by: Optional[str] = Field(default=None, description="User ID who created the group")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


class GroupCreate(BaseModel):
    """Group creation model"""
    name: str = Field(..., min_length=1, max_length=100, description="Group name")
    description: Optional[str] = Field(default=None, max_length=500, description="Group description")
    type: GroupType = Field(default=GroupType.CUSTOM, description="Group type")
    device_ids: List[str] = Field(default_factory=list, description="Initial device IDs")
    color: Optional[str] = Field(default="#1890ff", description="Group color")
    icon: Optional[str] = Field(default=None, description="Group icon name")


class GroupUpdate(BaseModel):
    """Group update model"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="Group name")
    description: Optional[str] = Field(default=None, max_length=500, description="Group description")
    device_ids: Optional[List[str]] = Field(default=None, description="Device IDs list")
    color: Optional[str] = Field(default=None, description="Group color")
    icon: Optional[str] = Field(default=None, description="Group icon name")


class GroupDeviceOperation(BaseModel):
    """Model for adding/removing devices from a group"""
    device_ids: List[str] = Field(..., min_items=1, description="Device IDs to add/remove")


class GroupListResponse(BaseModel):
    """Group list response"""
    groups: List[DeviceGroup]
    total: int


class GroupDetail(DeviceGroup):
    """Group detail with device count"""
    device_count: int = Field(default=0, description="Number of devices in group")
    online_count: int = Field(default=0, description="Number of online devices in group")
