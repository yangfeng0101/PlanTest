# WebSocket Connection Manager
from typing import Dict, Set, Optional, List
from fastapi import WebSocket
import asyncio
import json
import logging
from datetime import datetime

from app.config import settings
from app.services import device_service
from app.services.metrics_service import metrics_collector
from app.models import DeviceStatus, DeviceMetrics

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket connection manager with timeout detection, heartbeat, and cleanup"""

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._device_subscribers: Dict[str, Set[WebSocket]] = {}
        self._metrics_subscribers: Dict[str, Set[WebSocket]] = {}  # device_id -> set of websockets
        self._all_metrics_subscribers: Set[WebSocket] = set()  # subscribers for all devices metrics
        self._connection_times: Dict[WebSocket, datetime] = {}
        self._last_heartbeat: Dict[WebSocket, datetime] = {}
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._device_update_task: Optional[asyncio.Task] = None
        self._metrics_push_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection with timeout tracking"""
        await websocket.accept()
        now = datetime.utcnow()
        self._connections.add(websocket)
        self._connection_times[websocket] = now
        self._last_heartbeat[websocket] = now
        logger.info(f"New WebSocket connection. Total: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection and cleanup"""
        self._connections.discard(websocket)

        # Remove from all device subscriptions
        for device_id in list(self._device_subscribers.keys()):
            self._device_subscribers[device_id].discard(websocket)

        # Remove from all metrics subscriptions
        for device_id in list(self._metrics_subscribers.keys()):
            self._metrics_subscribers[device_id].discard(websocket)

        # Remove from all-metrics subscribers
        self._all_metrics_subscribers.discard(websocket)

        # Clean up tracking data
        self._connection_times.pop(websocket, None)
        self._last_heartbeat.pop(websocket, None)

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
                # Update heartbeat on successful send
                self._last_heartbeat[connection] = datetime.utcnow()
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
            "timestamp": datetime.utcnow().isoformat()
        }
        message_json = json.dumps(message)

        disconnected = set()
        subscribers = self._device_subscribers.get(device_id, set())

        for connection in subscribers:
            try:
                await connection.send_text(message_json)
                # Update heartbeat on successful send
                self._last_heartbeat[connection] = datetime.utcnow()
            except Exception as e:
                logger.error(f"Error sending device update: {e}")
                disconnected.add(connection)

        for conn in disconnected:
            await self.disconnect(conn)

    async def start_heartbeat(self):
        """Start heartbeat and cleanup background tasks"""
        if self._running:
            return

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("WebSocket heartbeat and cleanup tasks started")

    async def stop_heartbeat(self):
        """Stop heartbeat and cleanup tasks"""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._device_update_task:
            self._device_update_task.cancel()
            try:
                await self._device_update_task
            except asyncio.CancelledError:
                pass

        logger.info("WebSocket heartbeat and cleanup tasks stopped")

    async def _heartbeat_loop(self):
        """Heartbeat loop to keep connections alive"""
        while self._running:
            try:
                await self._send_heartbeats()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            await asyncio.sleep(settings.WS_HEARTBEAT_INTERVAL)

    async def _send_heartbeats(self):
        """Send ping to all connections"""
        ping_msg = json.dumps({"type": "ping", "timestamp": datetime.utcnow().isoformat()})
        disconnected = []

        for conn in list(self._connections):
            try:
                await conn.send_text(ping_msg)
            except Exception as e:
                logger.warning(f"Failed to send heartbeat: {e}")
                disconnected.append(conn)

        # Clean up failed connections
        for conn in disconnected:
            await self.disconnect(conn)

    async def _cleanup_loop(self):
        """Periodically clean up stale connections"""
        while self._running:
            try:
                await self._cleanup_stale_connections()
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

            await asyncio.sleep(settings.WS_CLEANUP_INTERVAL)

    async def _cleanup_stale_connections(self):
        """Remove connections that have timed out"""
        now = datetime.utcnow()
        stale_connections = []

        for conn in list(self._connections):
            # Check connection timeout
            conn_time = self._connection_times.get(conn)
            if conn_time:
                age = (now - conn_time).total_seconds()
                if age > settings.WS_CONNECTION_TIMEOUT:
                    logger.warning(f"Connection timed out after {age:.0f}s")
                    stale_connections.append((conn, "timeout"))
                    continue

            # Check heartbeat timeout
            last_heartbeat = self._last_heartbeat.get(conn)
            if last_heartbeat:
                silence = (now - last_heartbeat).total_seconds()
                if silence > settings.WS_CONNECTION_TIMEOUT:
                    logger.warning(f"Connection silent for {silence:.0f}s")
                    stale_connections.append((conn, "silent"))

        # Close and remove stale connections
        for conn, reason in stale_connections:
            try:
                await conn.close(code=1001, reason=f"Connection {reason}")
            except Exception:
                pass
            await self.disconnect(conn)

        if stale_connections:
            logger.info(f"Cleaned up {len(stale_connections)} stale connections")

    def handle_pong(self, websocket: WebSocket):
        """Handle pong response from client"""
        if websocket in self._last_heartbeat:
            self._last_heartbeat[websocket] = datetime.utcnow()

    def get_connection_stats(self) -> dict:
        """Get connection statistics for monitoring"""
        now = datetime.utcnow()

        stats = {
            "total_connections": len(self._connections),
            "device_subscribers": {
                device_id: len(subs)
                for device_id, subs in self._device_subscribers.items()
            },
            "oldest_connection_age": None,
            "avg_connection_age": None,
        }

        if self._connection_times:
            ages = [(now - t).total_seconds() for t in self._connection_times.values()]
            stats["oldest_connection_age"] = max(ages) if ages else None
            stats["avg_connection_age"] = sum(ages) / len(ages) if ages else None

        return stats

    async def start_device_updates(self):
        """Start device status update broadcasts"""
        self._device_update_task = asyncio.create_task(self._device_update_loop())
        logger.info("Device update broadcasts started")

    async def _device_update_loop(self):
        """Periodically broadcast device status updates"""
        while self._running:
            try:
                devices = await device_service.get_devices()
                await self.broadcast({
                    "type": "device_list",
                    "devices": [d.model_dump() for d in devices],
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as e:
                logger.error(f"Device update broadcast error: {e}")

            await asyncio.sleep(settings.DEVICE_SCAN_INTERVAL)

    # ==================== Metrics Subscription Methods ====================

    async def subscribe_metrics(self, websocket: WebSocket, device_ids: Optional[List[str]] = None):
        """
        Subscribe to metrics updates.

        Args:
            websocket: WebSocket connection
            device_ids: List of device IDs to subscribe to. If None, subscribes to all devices.
        """
        if device_ids is None or len(device_ids) == 0:
            # Subscribe to all devices metrics
            self._all_metrics_subscribers.add(websocket)
            logger.info(f"Subscribed to all devices metrics")
        else:
            # Subscribe to specific devices
            for device_id in device_ids:
                if device_id not in self._metrics_subscribers:
                    self._metrics_subscribers[device_id] = set()
                self._metrics_subscribers[device_id].add(websocket)
            logger.info(f"Subscribed to metrics for devices: {device_ids}")

    async def unsubscribe_metrics(self, websocket: WebSocket, device_ids: Optional[List[str]] = None):
        """
        Unsubscribe from metrics updates.

        Args:
            websocket: WebSocket connection
            device_ids: List of device IDs to unsubscribe from. If None, unsubscribes from all.
        """
        if device_ids is None or len(device_ids) == 0:
            # Unsubscribe from all metrics
            self._all_metrics_subscribers.discard(websocket)
            for device_id in list(self._metrics_subscribers.keys()):
                self._metrics_subscribers[device_id].discard(websocket)
            logger.info(f"Unsubscribed from all metrics")
        else:
            # Unsubscribe from specific devices
            for device_id in device_ids:
                if device_id in self._metrics_subscribers:
                    self._metrics_subscribers[device_id].discard(websocket)
            logger.info(f"Unsubscribed from metrics for devices: {device_ids}")

    async def start_metrics_push(self):
        """Start metrics push background task"""
        if self._metrics_push_task:
            return

        self._metrics_push_task = asyncio.create_task(self._metrics_push_loop())
        logger.info("Metrics push task started")

    async def stop_metrics_push(self):
        """Stop metrics push task"""
        if self._metrics_push_task:
            self._metrics_push_task.cancel()
            try:
                await self._metrics_push_task
            except asyncio.CancelledError:
                pass
            self._metrics_push_task = None
            logger.info("Metrics push task stopped")

    async def _metrics_push_loop(self):
        """Periodically push metrics to subscribers"""
        while self._running:
            try:
                await self._push_metrics_updates()
            except Exception as e:
                logger.error(f"Metrics push error: {e}")

            await asyncio.sleep(settings.METRICS_PUSH_INTERVAL)

    async def _push_metrics_updates(self):
        """Push metrics updates to subscribers"""
        now = datetime.utcnow()

        # Get all current metrics
        all_metrics = metrics_collector.get_all_current_metrics()

        if not all_metrics:
            return

        # Push to all-metrics subscribers
        if self._all_metrics_subscribers:
            message = {
                "type": "metrics_update",
                "metrics": {device_id: m.model_dump() for device_id, m in all_metrics.items()},
                "timestamp": now.isoformat()
            }
            message_json = json.dumps(message)

            disconnected = set()
            for conn in self._all_metrics_subscribers:
                try:
                    await conn.send_text(message_json)
                    self._last_heartbeat[conn] = now
                except Exception as e:
                    logger.error(f"Error sending metrics update: {e}")
                    disconnected.add(conn)

            for conn in disconnected:
                await self.disconnect(conn)

        # Push to device-specific subscribers
        for device_id, metrics in all_metrics.items():
            subscribers = self._metrics_subscribers.get(device_id, set())
            if not subscribers:
                continue

            message = {
                "type": "metrics_update",
                "device_id": device_id,
                "metrics": metrics.model_dump(),
                "timestamp": now.isoformat()
            }
            message_json = json.dumps(message)

            disconnected = set()
            for conn in subscribers:
                try:
                    await conn.send_text(message_json)
                    self._last_heartbeat[conn] = now
                except Exception as e:
                    logger.error(f"Error sending device metrics update: {e}")
                    disconnected.add(conn)

            for conn in disconnected:
                await self.disconnect(conn)

    def get_metrics_subscribers_stats(self) -> dict:
        """Get metrics subscription statistics"""
        return {
            "all_metrics_subscribers": len(self._all_metrics_subscribers),
            "device_metrics_subscribers": {
                device_id: len(subs)
                for device_id, subs in self._metrics_subscribers.items()
                if subs
            }
        }


# Global instance
ws_manager = ConnectionManager()
