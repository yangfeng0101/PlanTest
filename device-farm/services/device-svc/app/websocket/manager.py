# WebSocket Connection Manager
from typing import Dict, Set
from fastapi import WebSocket
import asyncio
import json
import logging
from datetime import datetime

from app.config import settings
from app.services import device_service
from app.models import DeviceStatus

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket connection manager for real-time updates"""

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._device_subscribers: Dict[str, Set[WebSocket]] = {}
        self._running = False

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self._connections.add(websocket)
        logger.info(f"New WebSocket connection. Total: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection"""
        self._connections.discard(websocket)

        # Remove from all device subscriptions
        for device_id in list(self._device_subscribers.keys()):
            self._device_subscribers[device_id].discard(websocket)

        logger.info(f"WebSocket disconnected. Total: {len(self._connections)}")

    async def subscribe_device(self, websocket: WebSocket, device_id: str):
        """Subscribe to device updates"""
        if device_id not in self._device_subscribers:
            self._device_subscribers[device_id] = set()
        self._device_subscribers[device_id].add(websocket)
        logger.info(f"Subscribed to device {device_id}")

    async def unsubscribe_device(self, websocket: WebSocket, device_id: str):
        """Unsubscribe from device updates"""
        if device_id in self._device_subscribers:
            self._device_subscribers[device_id].discard(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connections"""
        if not self._connections:
            return

        message_json = json.dumps(message)
        disconnected = set()

        for connection in self._connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                disconnected.add(connection)

        # Clean up disconnected
        for conn in disconnected:
            await self.disconnect(conn)

    async def broadcast_device_update(self, device_id: str, data: dict):
        """Broadcast device update to subscribers"""
        if device_id not in self._device_subscribers:
            return

        message = {
            "type": "device_update",
            "device_id": device_id,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        message_json = json.dumps(message)

        disconnected = set()
        subscribers = self._device_subscribers.get(device_id, set())

        for connection in subscribers:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error(f"Error sending device update: {e}")
                disconnected.add(connection)

        for conn in disconnected:
            await self.disconnect(conn)

    async def start_heartbeat(self):
        """Start heartbeat background task"""
        if self._running:
            return

        self._running = True
        asyncio.create_task(self._heartbeat_loop())
        logger.info("WebSocket heartbeat started")

    async def stop_heartbeat(self):
        """Stop heartbeat"""
        self._running = False
        logger.info("WebSocket heartbeat stopped")

    async def _heartbeat_loop(self):
        """Heartbeat loop to keep connections alive"""
        while self._running:
            try:
                await self.broadcast({
                    "type": "heartbeat",
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            await asyncio.sleep(settings.WS_HEARTBEAT_INTERVAL)

    async def start_device_updates(self):
        """Start device status update broadcasts"""
        asyncio.create_task(self._device_update_loop())
        logger.info("Device update broadcasts started")

    async def _device_update_loop(self):
        """Periodically broadcast device status updates"""
        while self._running:
            try:
                devices = await device_service.get_devices()
                await self.broadcast({
                    "type": "device_list",
                    "devices": [d.model_dump() for d in devices],
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"Device update broadcast error: {e}")

            await asyncio.sleep(settings.DEVICE_SCAN_INTERVAL)


# Global instance
ws_manager = ConnectionManager()
