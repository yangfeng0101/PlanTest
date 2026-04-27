# Device Service - Business Logic
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import asyncio
import json

from app.config import settings
from app.models import Device, DeviceStatus, DeviceCreate, DeviceUpdate, DeviceFilter
from app.models.device_db import DeviceStatusDB
from app.models.device_model_map import get_market_name, should_refresh_device_name
from app.services.adb_service import adb_service
from app.services.device_db_service import device_db_service

logger = logging.getLogger(__name__)


class DeviceService:
    """Device management service with database persistence"""

    def __init__(self):
        self._devices: Dict[str, Device] = {}  # In-memory cache
        self._redis = None  # Will be set when Redis is available
        self._running = False

    async def start_scanning(self):
        """Start device scanning background task"""
        if self._running:
            return

        # Load devices from database first
        await self._load_from_database()

        self._running = True
        asyncio.create_task(self._scan_loop())
        logger.info("Device scanning started")

    async def stop_scanning(self):
        """Stop device scanning"""
        self._running = False
        logger.info("Device scanning stopped")

    async def _load_from_database(self):
        """Load existing devices from database into memory"""
        try:
            devices = await device_db_service.get_all_devices()
            for device in devices:
                await self._refresh_existing_device_metadata(device)
                self._devices[device.id] = device
            logger.info(f"Loaded {len(devices)} devices from database")
        except Exception as e:
            logger.error(f"Error loading devices from database: {e}")

    async def _refresh_generated_device_name(self, device: Device) -> None:
        """Refresh old generated names after the model-name mapping improves."""
        market_name = get_market_name(device.model)
        if market_name == device.model:
            return

        if not should_refresh_device_name(device.name, device.model, device.id):
            return

        device.name = market_name
        device.updated_at = datetime.now()
        await device_db_service.update_device_info(device.id, name=market_name)

    async def _refresh_existing_device_metadata(self, device: Device) -> None:
        """Refresh metadata that used to be inferred too coarsely."""
        await self._refresh_generated_device_name(device)

        brand = (device.brand or "").upper()
        should_probe_harmony = brand == "HUAWEI" and str(device.os).lower() != "harmony"
        if device.status != DeviceStatus.ONLINE or not should_probe_harmony:
            return

        try:
            info = await adb_service.get_device_info(device.id)
        except Exception as e:
            logger.warning(f"Unable to refresh device metadata for {device.id}: {e}")
            return

        new_os = info.get("os")
        new_os_version = info.get("os_version")
        new_name = info.get("name")

        changed = False
        name_for_update: Optional[str] = None

        if new_name and should_refresh_device_name(device.name, device.model, device.id):
            device.name = new_name
            name_for_update = new_name
            changed = True
        if new_os and device.os != new_os:
            device.os = new_os
            changed = True
        if new_os_version and device.os_version != new_os_version:
            device.os_version = new_os_version
            changed = True

        if changed:
            device.updated_at = datetime.now()
            await device_db_service.update_device_info(
                device.id,
                name=name_for_update,
                os=device.os,
                os_version=device.os_version,
            )

    async def _scan_loop(self):
        """Background device scanning loop"""
        while self._running:
            try:
                await self.scan_devices()
            except Exception as e:
                logger.error(f"Error scanning devices: {e}")

            await asyncio.sleep(settings.DEVICE_SCAN_INTERVAL)

    async def scan_devices(self) -> List[Device]:
        """Scan and update device list"""
        device_list = await adb_service.list_devices()
        current_ids = set()

        for device_info in device_list:
            device_id = device_info["id"]
            current_ids.add(device_id)

            if device_id in self._devices:
                # Update existing device status
                self._devices[device_id].status = device_info["status"]
                self._devices[device_id].last_active_at = datetime.now()
                await self._refresh_existing_device_metadata(self._devices[device_id])
                # Persist status update to database
                await device_db_service.update_device_status(
                    device_id,
                    DeviceStatus(device_info["status"])
                )
            else:
                # New device - get full info
                try:
                    info = await adb_service.get_device_info(device_id)
                    device = Device(
                        id=device_id,
                        name=info.get("name", device_id),
                        model=info.get("model", "Unknown"),
                        brand=info.get("brand", "Unknown"),
                        os_version=info.get("os_version", "Unknown"),
                        status=device_info["status"],
                        screen_resolution=info.get("screen_resolution", "Unknown"),
                        screen_size=info.get("screen_size", 5.5),
                        cpu=info.get("cpu", "Unknown"),
                        memory=info.get("memory", "Unknown"),
                        storage=info.get("storage", "Unknown"),
                        battery_level=info.get("battery_level", 100),
                        last_active_at=datetime.now(),
                    )
                    self._devices[device_id] = device
                    # Persist to database
                    await device_db_service.upsert_device(device)
                    logger.info(f"New device discovered and saved: {device_id}")
                except Exception as e:
                    logger.error(f"Error getting info for device {device_id}: {e}")

        # Mark offline for devices not in current list
        offline_ids = [did for did in self._devices if did not in current_ids]
        for device_id in offline_ids:
            self._devices[device_id].status = DeviceStatus.OFFLINE

        # Batch update offline status in database
        if offline_ids:
            await device_db_service.set_devices_offline(offline_ids)

        return list(self._devices.values())

    async def get_devices(self, filter: Optional[DeviceFilter] = None) -> List[Device]:
        """Get device list with optional filtering"""
        devices = list(self._devices.values())

        if filter:
            if filter.status:
                devices = [d for d in devices if d.status == filter.status]
            if filter.brand:
                devices = [d for d in devices if d.brand == filter.brand]
            if filter.os_version:
                devices = [d for d in devices if d.os_version == filter.os_version]
            if filter.keyword:
                keyword = filter.keyword.lower()
                devices = [
                    d for d in devices
                    if keyword in d.name.lower()
                    or keyword in d.model.lower()
                    or keyword in d.id.lower()
                ]
            if filter.tags:
                devices = [
                    d for d in devices
                    if any(tag in d.tags for tag in filter.tags)
                ]

        return devices

    async def get_device(self, device_id: str) -> Optional[Device]:
        """Get single device by ID"""
        return self._devices.get(device_id)

    async def batch_get_devices(self, device_ids: List[str]) -> Dict[str, Device]:
        """
        Get multiple devices by IDs in a single call.

        This is more efficient than calling get_device() in a loop.

        Args:
            device_ids: List of device IDs to fetch

        Returns:
            Dict mapping device_id to Device for found devices
        """
        return {
            device_id: self._devices[device_id]
            for device_id in device_ids
            if device_id in self._devices
        }

    async def occupy_device(self, device_id: str, user_id: str) -> Optional[Device]:
        """Occupy a device"""
        device = self._devices.get(device_id)
        if not device:
            return None

        if device.status != DeviceStatus.ONLINE:
            raise ValueError(f"Device is not available (status: {device.status})")

        device.status = DeviceStatus.BUSY
        device.occupied_by = user_id
        device.occupied_at = datetime.now()
        device.updated_at = datetime.now()

        # Persist to database
        await device_db_service.update_device_status(
            device_id,
            DeviceStatus.BUSY,
            user_id,
            device.occupied_at
        )

        logger.info(f"Device {device_id} occupied by {user_id}")
        return device

    async def release_device(self, device_id: str) -> Optional[Device]:
        """Release a device"""
        device = self._devices.get(device_id)
        if not device:
            return None

        device.status = DeviceStatus.ONLINE
        device.occupied_by = None
        device.occupied_at = None
        device.updated_at = datetime.now()

        # Persist to database
        await device_db_service.update_device_status(
            device_id,
            DeviceStatus.ONLINE
        )

        logger.info(f"Device {device_id} released")
        return device

    async def update_device(self, device_id: str, update: DeviceUpdate) -> Optional[Device]:
        """Update device information"""
        device = self._devices.get(device_id)
        if not device:
            return None

        if update.name is not None:
            device.name = update.name
        if update.status is not None:
            device.status = update.status
        if update.tags is not None:
            device.tags = update.tags

        device.updated_at = datetime.now()

        # Persist to database
        await device_db_service.update_device_info(
            device_id,
            name=update.name,
            tags=update.tags,
            status=update.status
        )

        return device

    async def update_device_battery_level(self, device_id: str, battery_level: int) -> Optional[Device]:
        """Sync the latest collected battery level into device inventory data."""
        device = self._devices.get(device_id)
        if not device:
            return None

        normalized_level = max(0, min(100, int(battery_level)))
        if device.battery_level == normalized_level:
            return device

        device.battery_level = normalized_level
        device.updated_at = datetime.now()

        await device_db_service.update_device_info(
            device_id,
            battery_level=normalized_level,
        )

        return device

    async def get_screenshot(self, device_id: str) -> Optional[bytes]:
        """Get device screenshot"""
        if device_id not in self._devices:
            return None

        return await adb_service.get_screenshot(device_id)

    async def execute_command(self, device_id: str, command: str) -> str:
        """Execute shell command on device"""
        if device_id not in self._devices:
            raise ValueError("Device not found")

        return await adb_service.execute_adb("shell", command, device_id=device_id)

    async def get_device_stats(self) -> Dict[str, Any]:
        """Get device statistics"""
        devices = list(self._devices.values())
        stats = {
            "total": len(devices),
            "online": sum(1 for d in devices if d.status == DeviceStatus.ONLINE),
            "offline": sum(1 for d in devices if d.status == DeviceStatus.OFFLINE),
            "busy": sum(1 for d in devices if d.status == DeviceStatus.BUSY),
            "maintaining": sum(1 for d in devices if d.status == DeviceStatus.MAINTAINING),
            "brands": {},
            "models": {},
        }

        for device in devices:
            stats["brands"][device.brand] = stats["brands"].get(device.brand, 0) + 1
            stats["models"][device.model] = stats["models"].get(device.model, 0) + 1

        return stats


# Global instance
device_service = DeviceService()
