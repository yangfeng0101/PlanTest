# Device Routes
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query, Depends
from typing import Optional, List
import logging
import base64
from datetime import datetime

from app.models import (
    Device, DeviceUpdate, DeviceFilter, DeviceStatus,
    DeviceListResponse, DeviceOccupyRequest,
    ReservationCreate, ReservationResponse, ReservationStatus
)
from app.services import device_service
from app.services.reservation_service import reservation_service
from app.websocket import ws_manager
from app.middleware.auth import get_current_user, get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter()


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
async def update_device(device_id: str, update: DeviceUpdate):
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
    screenshot = await device_service.get_screenshot(device_id)
    if not screenshot:
        raise HTTPException(status_code=404, detail="Device not found or screenshot failed")

    # Return base64 encoded image
    return {
        "device_id": device_id,
        "image": base64.b64encode(screenshot).decode('utf-8'),
        "format": "png"
    }


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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time device updates"""
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()

            # Parse message
            try:
                import json
                message = json.loads(data)
                msg_type = message.get("type")

                if msg_type == "subscribe":
                    device_id = message.get("device_id")
                    if device_id:
                        await ws_manager.subscribe_device(websocket, device_id)
                        await websocket.send_text(json.dumps({
                            "type": "subscribed",
                            "device_id": device_id
                        }))

                elif msg_type == "unsubscribe":
                    device_id = message.get("device_id")
                    if device_id:
                        await ws_manager.unsubscribe_device(websocket, device_id)
                        await websocket.send_text(json.dumps({
                            "type": "unsubscribed",
                            "device_id": device_id
                        }))

                elif msg_type == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    }))

                elif msg_type == "pong":
                    # Client responds to our ping, update heartbeat
                    ws_manager.handle_pong(websocket)

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


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
