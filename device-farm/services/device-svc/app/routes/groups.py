# Device Group Routes
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import logging
import uuid
from datetime import datetime

from app.models.group import (
    DeviceGroup,
    GroupType,
    GroupCreate,
    GroupUpdate,
    GroupDeviceOperation,
    GroupListResponse,
    GroupDetail,
)
from app.services import device_service

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory storage for groups (in production, use database)
_groups: dict[str, DeviceGroup] = {}


@router.get("", response_model=GroupListResponse)
async def list_groups(
    type: Optional[GroupType] = Query(None, description="Filter by group type"),
    keyword: Optional[str] = Query(None, description="Search by name"),
):
    """Get list of all device groups"""
    groups = list(_groups.values())

    # Filter by type
    if type:
        groups = [g for g in groups if g.type == type]

    # Filter by keyword
    if keyword:
        keyword_lower = keyword.lower()
        groups = [
            g for g in groups
            if keyword_lower in g.name.lower() or
               (g.description and keyword_lower in g.description.lower())
        ]

    return GroupListResponse(
        groups=groups,
        total=len(groups)
    )


@router.post("", response_model=DeviceGroup, status_code=201)
async def create_group(group_data: GroupCreate):
    """Create a new device group"""
    # Check for duplicate name
    for existing in _groups.values():
        if existing.name == group_data.name:
            raise HTTPException(status_code=400, detail="Group with this name already exists")

    # Validate device IDs exist
    if group_data.device_ids:
        for device_id in group_data.device_ids:
            device = await device_service.get_device(device_id)
            if not device:
                raise HTTPException(
                    status_code=400,
                    detail=f"Device not found: {device_id}"
                )

    # Create group
    group_id = str(uuid.uuid4())
    now = datetime.now()

    group = DeviceGroup(
        id=group_id,
        name=group_data.name,
        description=group_data.description,
        type=group_data.type,
        device_ids=group_data.device_ids,
        color=group_data.color or "#1890ff",
        icon=group_data.icon,
        created_at=now,
        updated_at=now,
    )

    _groups[group_id] = group
    logger.info(f"Created group: {group.name} ({group_id})")

    return group


@router.get("/{group_id}", response_model=GroupDetail)
async def get_group(group_id: str):
    """Get group by ID with device statistics"""
    group = _groups.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Calculate device statistics
    device_count = len(group.device_ids)
    online_count = 0

    for device_id in group.device_ids:
        device = await device_service.get_device(device_id)
        if device and device.status == "online":
            online_count += 1

    return GroupDetail(
        **group.model_dump(),
        device_count=device_count,
        online_count=online_count,
    )


@router.put("/{group_id}", response_model=DeviceGroup)
async def update_group(group_id: str, update: GroupUpdate):
    """Update group information"""
    group = _groups.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Check for duplicate name if name is being changed
    if update.name and update.name != group.name:
        for existing in _groups.values():
            if existing.id != group_id and existing.name == update.name:
                raise HTTPException(status_code=400, detail="Group with this name already exists")

    # Validate device IDs if being updated
    if update.device_ids is not None:
        for device_id in update.device_ids:
            device = await device_service.get_device(device_id)
            if not device:
                raise HTTPException(
                    status_code=400,
                    detail=f"Device not found: {device_id}"
                )

    # Update fields
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)

    group.updated_at = datetime.now()
    _groups[group_id] = group

    logger.info(f"Updated group: {group.name} ({group_id})")
    return group


@router.delete("/{group_id}")
async def delete_group(group_id: str):
    """Delete a group"""
    group = _groups.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Prevent deleting system groups
    if group.type == GroupType.SYSTEM:
        raise HTTPException(status_code=400, detail="Cannot delete system groups")

    del _groups[group_id]
    logger.info(f"Deleted group: {group.name} ({group_id})")

    return {"message": "Group deleted", "id": group_id}


@router.post("/{group_id}/devices", response_model=DeviceGroup)
async def add_devices(group_id: str, operation: GroupDeviceOperation):
    """Add devices to a group"""
    group = _groups.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Validate device IDs
    for device_id in operation.device_ids:
        device = await device_service.get_device(device_id)
        if not device:
            raise HTTPException(
                status_code=400,
                detail=f"Device not found: {device_id}"
            )

    # Add devices (avoid duplicates)
    current_ids = set(group.device_ids)
    new_ids = set(operation.device_ids)
    group.device_ids = list(current_ids | new_ids)
    group.updated_at = datetime.now()

    _groups[group_id] = group
    logger.info(f"Added {len(new_ids - current_ids)} devices to group {group.name}")

    return group


@router.delete("/{group_id}/devices", response_model=DeviceGroup)
async def remove_devices(group_id: str, operation: GroupDeviceOperation):
    """Remove devices from a group"""
    group = _groups.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Remove devices
    current_ids = set(group.device_ids)
    remove_ids = set(operation.device_ids)
    group.device_ids = list(current_ids - remove_ids)
    group.updated_at = datetime.now()

    _groups[group_id] = group
    logger.info(f"Removed {len(remove_ids & current_ids)} devices from group {group.name}")

    return group


@router.get("/{group_id}/devices")
async def get_group_devices(group_id: str):
    """Get all devices in a group"""
    group = _groups.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Fetch device details
    devices = []
    for device_id in group.device_ids:
        device = await device_service.get_device(device_id)
        if device:
            devices.append(device)

    return {
        "group_id": group_id,
        "group_name": group.name,
        "devices": devices,
        "total": len(devices),
    }
