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
    # Validate device IDs exist using batch query
    if group_data.device_ids:
        devices = await device_service.batch_get_devices(group_data.device_ids)
        missing_ids = set(group_data.device_ids) - set(devices.keys())
        if missing_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Devices not found: {', '.join(missing_ids)}"
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

    # Calculate device statistics using batch query
    device_ids = group_db.device_ids
    device_count = len(device_ids)

    # Batch fetch devices to avoid N+1 query
    devices = await device_service.batch_get_devices(device_ids)
    online_count = sum(1 for d in devices.values() if d.status == "online")

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
    # Validate device IDs if being updated using batch query
    if update.device_ids is not None:
        devices = await device_service.batch_get_devices(update.device_ids)
        missing_ids = set(update.device_ids) - set(devices.keys())
        if missing_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Devices not found: {', '.join(missing_ids)}"
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
    # Validate device IDs using batch query
    devices = await device_service.batch_get_devices(operation.device_ids)
    missing_ids = set(operation.device_ids) - set(devices.keys())
    if missing_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Devices not found: {', '.join(missing_ids)}"
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

    # Batch fetch device details to avoid N+1 query
    devices = await device_service.batch_get_devices(group_db.device_ids)
    device_list = list(devices.values())

    return {
        "group_id": group_id,
        "group_name": group_db.name,
        "devices": device_list,
        "total": len(device_list),
    }
