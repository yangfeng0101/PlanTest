# Base WebSocket Connection Manager
# Shared utilities for WebSocket connection management
from typing import Dict, Set, Optional, List
from fastapi import WebSocket
import asyncio
import json
import logging
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseConnectionManager(ABC):
    """
    Base WebSocket connection manager with timeout detection, heartbeat, and cleanup.

    This class provides common WebSocket management functionality that can be extended
    by service-specific implementations.

    Features:
    - Connection tracking with timestamps
    - Heartbeat/ping-pong mechanism
    - Automatic cleanup of stale connections
    - Connection statistics

    Usage:
        class MyConnectionManager(BaseConnectionManager):
            async def subscribe(self, websocket: WebSocket, channel: str):
                # Service-specific subscription logic
                pass

            async def unsubscribe(self, websocket: WebSocket, channel: str):
                # Service-specific unsubscription logic
                pass
    """

    def __init__(
        self,
        connection_timeout: int = 300,
        heartbeat_interval: int = 30,
        cleanup_interval: int = 60,
    ):
        """
        Initialize the connection manager.

        Args:
            connection_timeout: Max connection age in seconds (default 5 minutes)
            heartbeat_interval: Seconds between heartbeats (default 30 seconds)
            cleanup_interval: Seconds between cleanup runs (default 60 seconds)
        """
        self._connections: Set[WebSocket] = set()
        self._connection_times: Dict[WebSocket, datetime] = {}
        self._last_heartbeat: Dict[WebSocket, datetime] = {}
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Configuration
        self._connection_timeout = connection_timeout
        self._heartbeat_interval = heartbeat_interval
        self._cleanup_interval = cleanup_interval

    async def connect(self, websocket: WebSocket):
        """
        Accept new WebSocket connection with timeout tracking.

        Args:
            websocket: WebSocket connection to accept
        """
        await websocket.accept()
        now = datetime.utcnow()
        self._connections.add(websocket)
        self._connection_times[websocket] = now
        self._last_heartbeat[websocket] = now
        logger.info(f"New WebSocket connection. Total: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket):
        """
        Handle WebSocket disconnection and cleanup.

        Args:
            websocket: WebSocket connection to disconnect
        """
        self._connections.discard(websocket)
        self._connection_times.pop(websocket, None)
        self._last_heartbeat.pop(websocket, None)
        logger.info(f"WebSocket disconnected. Total: {len(self._connections)}")

    async def broadcast(self, message: dict):
        """
        Broadcast message to all connections.

        Args:
            message: Message dict to broadcast (will be JSON encoded)
        """
        if not self._connections:
            return

        message_json = json.dumps(message)
        disconnected = set()

        for connection in self._connections:
            try:
                await connection.send_text(message_json)
                self._last_heartbeat[connection] = datetime.utcnow()
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                disconnected.add(connection)

        for conn in disconnected:
            await self.disconnect(conn)

    async def send_to_connection(self, websocket: WebSocket, message: dict):
        """
        Send message to a specific connection.

        Args:
            websocket: Target WebSocket connection
            message: Message dict to send

        Raises:
            Exception: If send fails (caller should handle disconnection)
        """
        message_json = json.dumps(message)
        await websocket.send_text(message_json)
        self._last_heartbeat[websocket] = datetime.utcnow()

    async def start_heartbeat(self):
        """Start heartbeat and cleanup background tasks."""
        if self._running:
            return

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("WebSocket heartbeat and cleanup tasks started")

    async def stop_heartbeat(self):
        """Stop heartbeat and cleanup tasks."""
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

        logger.info("WebSocket heartbeat and cleanup tasks stopped")

    async def _heartbeat_loop(self):
        """Heartbeat loop to keep connections alive."""
        while self._running:
            try:
                await self._send_heartbeats()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            await asyncio.sleep(self._heartbeat_interval)

    async def _send_heartbeats(self):
        """Send ping to all connections."""
        ping_msg = json.dumps({"type": "ping", "timestamp": datetime.utcnow().isoformat()})
        disconnected = []

        for conn in list(self._connections):
            try:
                await conn.send_text(ping_msg)
            except Exception as e:
                logger.warning(f"Failed to send heartbeat: {e}")
                disconnected.append(conn)

        for conn in disconnected:
            await self.disconnect(conn)

    async def _cleanup_loop(self):
        """Periodically clean up stale connections."""
        while self._running:
            try:
                await self._cleanup_stale_connections()
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

            await asyncio.sleep(self._cleanup_interval)

    async def _cleanup_stale_connections(self):
        """Remove connections that have timed out."""
        now = datetime.utcnow()
        stale_connections = []

        for conn in list(self._connections):
            # Check connection timeout
            conn_time = self._connection_times.get(conn)
            if conn_time:
                age = (now - conn_time).total_seconds()
                if age > self._connection_timeout:
                    logger.warning(f"Connection timed out after {age:.0f}s")
                    stale_connections.append((conn, "timeout"))
                    continue

            # Check heartbeat timeout
            last_heartbeat = self._last_heartbeat.get(conn)
            if last_heartbeat:
                silence = (now - last_heartbeat).total_seconds()
                if silence > self._connection_timeout:
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
        """
        Handle pong response from client.

        Args:
            websocket: WebSocket that sent the pong
        """
        if websocket in self._last_heartbeat:
            self._last_heartbeat[websocket] = datetime.utcnow()

    def get_connection_stats(self) -> dict:
        """
        Get connection statistics for monitoring.

        Returns:
            Dict with connection stats including total, oldest age, avg age
        """
        now = datetime.utcnow()

        stats = {
            "total_connections": len(self._connections),
            "oldest_connection_age": None,
            "avg_connection_age": None,
        }

        if self._connection_times:
            ages = [(now - t).total_seconds() for t in self._connection_times.values()]
            stats["oldest_connection_age"] = max(ages) if ages else None
            stats["avg_connection_age"] = sum(ages) / len(ages) if ages else None

        return stats

    @property
    def total_connections(self) -> int:
        """Get total number of active connections."""
        return len(self._connections)

    @property
    def connections(self) -> Set[WebSocket]:
        """Get set of all active connections (read-only)."""
        return self._connections.copy()
