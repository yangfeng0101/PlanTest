# Device Routes
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query, Depends
from typing import Optional, List
import logging
import base64

from app.models import (
    Device, DeviceUpdate, DeviceFilter, DeviceStatus,
    DeviceListResponse, DeviceOccupyRequest
)
from app.services import device_service
from app.websocket import ws_manager

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
async def execute_command(device_id: str, command: str):
    """Execute shell command on device"""
    try:
        result = await device_service.execute_command(device_id, command)
        return {"device_id": device_id, "result": result}
    except ValueError as e:
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
                        "timestamp": logging.datetime.now().isoformat()
                    }))

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
