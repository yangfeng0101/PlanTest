# Device Routes
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query, Depends
from typing import Optional, List
import logging
import base64
from datetime import datetime
from pydantic import BaseModel, Field

from app.models import (
    Device, DeviceUpdate, DeviceFilter, DeviceStatus,
    DeviceListResponse, DeviceOccupyRequest,
    ReservationCreate, ReservationResponse, ReservationStatus
)
from app.services import device_service
from app.services.device_service import IOSAgentRequestError
from app.services.ui_hierarchy_service import UIHierarchyError, ui_hierarchy_service
from app.services.reservation_service import reservation_service
from app.websocket import ws_manager
from app.middleware.auth import get_current_user, get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter()


class IOSDebugTapRequest(BaseModel):
    x: float = Field(..., ge=0)
    y: float = Field(..., ge=0)


class IOSDebugTextRequest(BaseModel):
    text: str = Field(..., min_length=1)


class IOSDebugSwipeRequest(BaseModel):
    startX: float = Field(..., ge=0)
    startY: float = Field(..., ge=0)
    endX: float = Field(..., ge=0)
    endY: float = Field(..., ge=0)
    durationMs: int = Field(500, ge=50, le=5000)


class IOSDebugLongPressRequest(BaseModel):
    x: float = Field(..., ge=0)
    y: float = Field(..., ge=0)
    durationMs: int = Field(800, ge=100, le=5000)


def is_ios_device(device: Device) -> bool:
    return str(device.os).lower() == "ios"


def device_status_value(device: Device) -> str:
    return device.status.value if isinstance(device.status, DeviceStatus) else str(device.status)


def ensure_ios_debug_available(device: Device) -> None:
    if is_ios_device(device) and device_status_value(device) != DeviceStatus.ONLINE.value:
        raise HTTPException(
            status_code=409,
            detail="iOS 静态调试需要独占 Appium/WDA，当前设备正在被占用或不可用",
        )


def ensure_ios_static_operation_available(device: Device) -> None:
    if not is_ios_device(device):
        raise HTTPException(status_code=400, detail="iOS static debug operation is only supported for iOS devices")
    ensure_ios_debug_available(device)
    if not device.capabilities.automation:
        raise HTTPException(status_code=400, detail="iOS automation is not available for this device")


def ios_agent_error_status(error: IOSAgentRequestError) -> int:
    return error.status_code if 400 <= error.status_code < 500 else 502


@router.get("", response_model=DeviceListResponse)
async def list_devices(
    status: Optional[DeviceStatus] = Query(None, description="Filter by status"),
    brand: Optional[str] = Query(None, description="Filter by brand"),
    keyword: Optional[str] = Query(None, description="Search keyword"),
):
    """Get list of all devices"""
    filter = DeviceFilter(
        status=status,
        brand=brand,
        keyword=keyword
    )
    devices = await device_service.get_devices(filter)
    return DeviceListResponse(
        devices=devices,
        total=len(devices)
    )


@router.get("/stats")
async def get_device_stats():
    """Get device statistics"""
    return await device_service.get_device_stats()


@router.get("/scan")
async def scan_devices():
    """Trigger device scan"""
    devices = await device_service.scan_devices()
    return {
        "message": "Device scan completed",
        "count": len(devices)
    }


@router.get("/{device_id}", response_model=Device)
async def get_device(device_id: str):
    """Get device by ID"""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.patch("/{device_id}", response_model=Device)
async def update_device(
    device_id: str,
    update: DeviceUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update device information"""
    device = await device_service.update_device(device_id, update)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.post("/{device_id}/occupy")
async def occupy_device(device_id: str, request: DeviceOccupyRequest):
    """Occupy a device"""
    try:
        device = await device_service.occupy_device(device_id, request.user_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"message": "Device occupied", "device": device}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{device_id}/release")
async def release_device(device_id: str):
    """Release a device"""
    device = await device_service.release_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device released", "device": device}


@router.get("/{device_id}/screenshot")
async def get_screenshot(device_id: str):
    """Get device screenshot"""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.capabilities.screenshot:
        raise HTTPException(status_code=400, detail="Screenshot is not supported by this device connection")
    ensure_ios_debug_available(device)

    try:
        if is_ios_device(device):
            payload = await device_service.get_ios_screenshot_payload(device_id)
            image = payload.get("image")
            if not image:
                raise HTTPException(status_code=404, detail="Device not found or screenshot failed")
            return {
                "device_id": device_id,
                "image": image,
                "format": payload.get("format") or "png",
                "screen": payload.get("screen"),
            }
        screenshot = await device_service.get_screenshot(device_id)
    except IOSAgentRequestError as e:
        raise HTTPException(status_code=ios_agent_error_status(e), detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not screenshot:
        raise HTTPException(status_code=404, detail="Device not found or screenshot failed")

    # Return base64 encoded image
    return {
        "device_id": device_id,
        "image": base64.b64encode(screenshot).decode('utf-8'),
        "format": "png"
    }


@router.get("/{device_id}/ui-hierarchy")
async def get_ui_hierarchy(device_id: str):
    """Get current Android UI hierarchy for automation locator generation"""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if not device.capabilities.ui_hierarchy:
        raise HTTPException(
            status_code=400,
            detail="UI hierarchy is not supported by this device connection",
        )
    ensure_ios_debug_available(device)

    try:
        if is_ios_device(device):
            source = await device_service.get_ios_ui_source(device_id)
            return ui_hierarchy_service.parse_ios_hierarchy(
                xml_text=source,
                device_id=device_id,
            )
        return await ui_hierarchy_service.get_ui_hierarchy(
            device_id=device_id,
            screen_resolution=device.screen_resolution,
        )
    except UIHierarchyError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except IOSAgentRequestError as e:
        raise HTTPException(status_code=ios_agent_error_status(e), detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get UI hierarchy for {device_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get UI hierarchy")


@router.delete("/{device_id}/debug-session")
async def release_debug_session(device_id: str):
    """Release an iOS static debug Appium session if one exists."""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not is_ios_device(device):
        return {"device_id": device_id, "released": False}

    try:
        released = await device_service.release_ios_debug_session(device_id)
    except IOSAgentRequestError as e:
        raise HTTPException(status_code=ios_agent_error_status(e), detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"device_id": device_id, "released": released}


@router.post("/{device_id}/debug/tap")
async def tap_ios_static_debug(device_id: str, request: IOSDebugTapRequest):
    """Perform a one-shot iOS static debug tap using Appium/WDA."""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    ensure_ios_static_operation_available(device)

    try:
        return await device_service.tap_ios_debug(device_id, request.x, request.y)
    except IOSAgentRequestError as e:
        raise HTTPException(status_code=ios_agent_error_status(e), detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/{device_id}/debug/text")
async def input_ios_static_debug_text(device_id: str, request: IOSDebugTextRequest):
    """Input text into the currently focused iOS element using Appium/WDA."""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    ensure_ios_static_operation_available(device)

    try:
        return await device_service.input_ios_debug_text(device_id, request.text)
    except IOSAgentRequestError as e:
        raise HTTPException(status_code=ios_agent_error_status(e), detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/{device_id}/debug/swipe")
async def swipe_ios_static_debug(device_id: str, request: IOSDebugSwipeRequest):
    """Perform a one-shot iOS static debug swipe using Appium/WDA."""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    ensure_ios_static_operation_available(device)

    try:
        return await device_service.swipe_ios_debug(
            device_id,
            request.startX,
            request.startY,
            request.endX,
            request.endY,
            request.durationMs,
        )
    except IOSAgentRequestError as e:
        raise HTTPException(status_code=ios_agent_error_status(e), detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/{device_id}/debug/long-press")
async def long_press_ios_static_debug(device_id: str, request: IOSDebugLongPressRequest):
    """Perform a one-shot iOS static debug long press using Appium/WDA."""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    ensure_ios_static_operation_available(device)

    try:
        return await device_service.long_press_ios_debug(device_id, request.x, request.y, request.durationMs)
    except IOSAgentRequestError as e:
        raise HTTPException(status_code=ios_agent_error_status(e), detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/{device_id}/debug/clear-text")
async def clear_ios_static_debug_text(device_id: str):
    """Clear the currently focused iOS input element using Appium/WDA."""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    ensure_ios_static_operation_available(device)

    try:
        return await device_service.clear_ios_debug_text(device_id)
    except IOSAgentRequestError as e:
        raise HTTPException(status_code=ios_agent_error_status(e), detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/{device_id}/command")
async def execute_command(
    device_id: str,
    command: str,
    current_user: dict = Depends(get_current_user),
):
    """Execute shell command on device (admin only)"""
    # Check admin role
    user_role = current_user.get("role", "")
    if user_role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only admin users can execute commands on devices"
        )

    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.connection_type != "adb":
        raise HTTPException(status_code=400, detail="Shell command is only supported for ADB-connected devices")

    user_id = current_user.get("id", "unknown")

    # Log the operation
    logger.info(
        f"Command execution - User: {user_id}, Device: {device_id}, Command: {command}"
    )

    try:
        result = await device_service.execute_command(device_id, command)

        # Log success
        logger.info(
            f"Command success - User: {user_id}, Device: {device_id}, Command: {command}"
        )

        return {"device_id": device_id, "result": result}
    except ValueError as e:
        # Log failure
        logger.warning(
            f"Command failed - User: {user_id}, Device: {device_id}, Command: {command}, Error: {e}"
        )
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{device_id}/logs")
async def get_device_logs(device_id: str, lines: int = 100):
    """Get device logcat"""
    device = await device_service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.connection_type != "adb":
        raise HTTPException(status_code=400, detail="Logcat is only supported for ADB-connected devices")

    from app.services.adb_service import adb_service
    try:
        logs = await adb_service.get_device_logs(device_id, lines)
        return {"device_id": device_id, "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{device_id}/reserve", response_model=ReservationResponse, status_code=201)
async def reserve_device(
    device_id: str,
    reservation: ReservationCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a reservation for a specific device.

    The reservation will be checked for conflicts with existing reservations.
    User ID is automatically set from the authenticated user.
    """
    current_user_id = current_user.get("id", "")

    # Override device_id with path parameter and user_id from auth
    reservation.device_id = device_id
    reservation.user_id = current_user_id

    try:
        result = await reservation_service.create_reservation(reservation)
        return ReservationResponse(
            id=result.id,
            device_id=result.device_id,
            user_id=result.user_id,
            start_time=result.start_time,
            end_time=result.end_time,
            status=ReservationStatus(result.status.value),
            purpose=result.purpose,
            created_at=result.created_at,
            updated_at=result.updated_at
        )
    except ValueError as e:
        if "conflicts" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{device_id}/reserve")
async def cancel_device_reservation(
    device_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Cancel reservation for a specific device.

    Cancels the active or pending reservation for the device.
    Non-admin users can only cancel their own reservations.
    """
    current_user_id = current_user.get("id", "")
    user_role = current_user.get("role", "")

    # Get active reservation for device
    reservations = await reservation_service.get_reservations(
        device_id=device_id,
        status=ReservationStatus.ACTIVE
    )

    if not reservations:
        # Check for pending reservations
        reservations = await reservation_service.get_reservations(
            device_id=device_id,
            status=ReservationStatus.PENDING
        )

    if not reservations:
        raise HTTPException(
            status_code=404,
            detail="No active or pending reservation found for device"
        )

    # Non-admin users can only cancel their own reservations
    if user_role != "admin":
        reservations = [r for r in reservations if r.user_id == current_user_id]
        if not reservations:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to cancel this reservation"
            )

    # Cancel the first matching reservation
    try:
        reservation = await reservation_service.cancel_reservation(
            reservations[0].id,
            user_id=None if user_role == "admin" else current_user_id
        )
        return {"message": "Reservation cancelled", "reservation_id": reservation.id}
    except ValueError as e:
        if "not authorized" in str(e).lower():
            raise HTTPException(status_code=403, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ws/stats")
async def get_websocket_stats():
    """Get WebSocket connection statistics

    Returns information about active WebSocket connections including:
    - Total number of connections
    - Connections per device subscription
    - Connection ages

    Returns:
        Connection statistics
    """
    return ws_manager.get_connection_stats()
