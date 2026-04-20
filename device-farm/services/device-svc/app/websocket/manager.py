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
from shared.websocket_manager import BaseConnectionManager

logger = logging.getLogger(__name__)


class ConnectionManager(BaseConnectionManager):
    """WebSocket connection manager with device/metrics subscription support"""

    def __init__(self):
        super().__init__(
            connection_timeout=settings.WS_CONNECTION_TIMEOUT,
            heartbeat_interval=settings.WS_HEARTBEAT_INTERVAL,
            cleanup_interval=settings.WS_CLEANUP_INTERVAL,
        )
        self._device_subscribers: Dict[str, Set[WebSocket]] = {}
        self._metrics_subscribers: Dict[str, Set[WebSocket]] = {}  # device_id -> set of websockets
        self._all_metrics_subscribers: Set[WebSocket] = set()  # subscribers for all devices metrics
        self._device_update_task: Optional[asyncio.Task] = None
        self._metrics_push_task: Optional[asyncio.Task] = None

    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection and cleanup subscriptions"""
        # Remove from all device subscriptions
        for device_id in list(self._device_subscribers.keys()):
            self._device_subscribers[device_id].discard(websocket)

        # Remove from all metrics subscriptions
        for device_id in list(self._metrics_subscribers.keys()):
            self._metrics_subscribers[device_id].discard(websocket)

        # Remove from all-metrics subscribers
        self._all_metrics_subscribers.discard(websocket)

        # Call parent disconnect
        await super().disconnect(websocket)

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

        subscribers = self._device_subscribers.get(device_id, set())
        disconnected = set()

        for connection in subscribers:
            try:
                await self.send_to_connection(connection, message)
            except Exception as e:
                logger.error(f"Error sending device update: {e}")
                disconnected.add(connection)

        for conn in disconnected:
            await self.disconnect(conn)

    def get_connection_stats(self) -> dict:
        """Get connection statistics for monitoring"""
        stats = super().get_connection_stats()
        stats["device_subscribers"] = {
            device_id: len(subs)
            for device_id, subs in self._device_subscribers.items()
        }
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
                    "devices": [d.model_dump(mode='json') for d in devices],
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
                "metrics": {device_id: m.model_dump(mode='json') for device_id, m in all_metrics.items()},
                "timestamp": now.isoformat()
            }

            disconnected = set()
            for conn in self._all_metrics_subscribers:
                try:
                    await self.send_to_connection(conn, message)
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
                "metrics": metrics.model_dump(mode='json'),
                "timestamp": now.isoformat()
            }

            disconnected = set()
            for conn in subscribers:
                try:
                    await self.send_to_connection(conn, message)
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
