# Device Group Routes
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
import logging

from app.database import get_db
from app.models.group import (
    DeviceGroup,
    GroupType,
    GroupCreate,
    GroupUpdate,
    GroupDeviceOperation,
    GroupListResponse,
    GroupDetail,
)
from app.models.group_db import DeviceGroupDB
from app.services.group_service import group_service
from app.services import device_service
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=GroupListResponse)
async def list_groups(
    type: Optional[GroupType] = Query(None, description="Filter by group type"),
    keyword: Optional[str] = Query(None, description="Search by name"),
    db: AsyncSession = Depends(get_db),
):
    """Get list of all device groups"""
    groups = await group_service.list_groups(db, type=type, keyword=keyword)

    return GroupListResponse(
        groups=groups,
        total=len(groups)
    )


@router.post("", response_model=DeviceGroup, status_code=201)
async def create_group(
    group_data: GroupCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new device group"""
    # Validate device IDs exist
    if group_data.device_ids:
        for device_id in group_data.device_ids:
            device = await device_service.get_device(device_id)
            if not device:
                raise HTTPException(
                    status_code=400,
                    detail=f"Device not found: {device_id}"
                )

    try:
        group = await group_service.create_group(db, group_data)
        logger.info(f"Created group: {group.name} ({group.id})")
        return group
    except Exception as e:
        if "unique constraint" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=400, detail="Group with this name already exists")
        raise


@router.get("/{group_id}", response_model=GroupDetail)
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get group by ID with device statistics"""
    group_db = await group_service.get_group(db, group_id)
    if not group_db:
        raise HTTPException(status_code=404, detail="Group not found")

    # Calculate device statistics
    device_ids = group_db.device_ids
    device_count = len(device_ids)
    online_count = 0

    for device_id in device_ids:
        device = await device_service.get_device(device_id)
        if device and device.status == "online":
            online_count += 1

    group_pydantic = group_service._to_pydantic(group_db)

    return GroupDetail(
        **group_pydantic.model_dump(),
        device_count=device_count,
        online_count=online_count,
    )


@router.put("/{group_id}", response_model=DeviceGroup)
async def update_group(
    group_id: str,
    update: GroupUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update group information"""
    # Validate device IDs if being updated
    if update.device_ids is not None:
        for device_id in update.device_ids:
            device = await device_service.get_device(device_id)
            if not device:
                raise HTTPException(
                    status_code=400,
                    detail=f"Device not found: {device_id}"
                )

    try:
        group = await group_service.update_group(db, group_id, update)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

        logger.info(f"Updated group: {group.name} ({group_id})")
        return group
    except Exception as e:
        if "unique constraint" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=400, detail="Group with this name already exists")
        raise


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a group"""
    try:
        deleted = await group_service.delete_group(db, group_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Group not found")

        logger.info(f"Deleted group: {group_id}")
        return {"message": "Group deleted", "id": group_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{group_id}/devices", response_model=DeviceGroup)
async def add_devices(
    group_id: str,
    operation: GroupDeviceOperation,
    db: AsyncSession = Depends(get_db),
):
    """Add devices to a group"""
    # Validate device IDs
    for device_id in operation.device_ids:
        device = await device_service.get_device(device_id)
        if not device:
            raise HTTPException(
                status_code=400,
                detail=f"Device not found: {device_id}"
            )

    group = await group_service.add_devices(db, group_id, operation.device_ids)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    logger.info(f"Added devices to group {group.name}")
    return group


@router.delete("/{group_id}/devices", response_model=DeviceGroup)
async def remove_devices(
    group_id: str,
    operation: GroupDeviceOperation,
    db: AsyncSession = Depends(get_db),
):
    """Remove devices from a group"""
    group = await group_service.remove_devices(db, group_id, operation.device_ids)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    logger.info(f"Removed devices from group {group.name}")
    return group


@router.get("/{group_id}/devices")
async def get_group_devices(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all devices in a group"""
    group_db = await group_service.get_group(db, group_id)
    if not group_db:
        raise HTTPException(status_code=404, detail="Group not found")

    # Fetch device details
    devices = []
    for device_id in group_db.device_ids:
        device = await device_service.get_device(device_id)
        if device:
            devices.append(device)

    return {
        "group_id": group_id,
        "group_name": group_db.name,
        "devices": devices,
        "total": len(devices),
    }
