# Device Service - Business Logic
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import asyncio
import base64
import json
import httpx

from app.config import settings
from app.models import Device, DeviceStatus, DeviceCreate, DeviceUpdate, DeviceFilter, DeviceDrivers, DeviceCapabilities
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
        device.refresh_runtime_fields()

    async def _scan_loop(self):
        """Background device scanning loop"""
        while self._running:
            try:
                await self.scan_devices()
            except Exception as e:
                logger.error(f"Error scanning devices: {e}")

            await asyncio.sleep(settings.DEVICE_SCAN_INTERVAL)

    async def _fetch_ios_agent_devices(self) -> List[Dict[str, Any]]:
        """Fetch iOS devices from the optional Mac host-side iOS Agent."""
        if not settings.IOS_AGENT_URL:
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{settings.IOS_AGENT_URL.rstrip('/')}/devices")
            response.raise_for_status()
            payload = response.json()
        except Exception as e:
            logger.warning(f"Unable to fetch iOS devices from agent: {e}")
            return []

        devices = payload.get("devices", []) if isinstance(payload, dict) else []
        if not isinstance(devices, list):
            logger.warning("iOS Agent returned invalid devices payload")
            return []
        return [device for device in devices if isinstance(device, dict)]

    def _apply_ios_automation_capability(self, device: Device, automation_ready: bool) -> None:
        """iOS uses Appium/WDA for automation and static debug; screen/control remain disabled."""
        device.drivers = DeviceDrivers(
            metrics="pymobiledevice3",
            ui_hierarchy="appium-xcuitest" if automation_ready else "",
            automation="appium-xcuitest" if automation_ready else "",
        )
        device.capabilities = DeviceCapabilities(
            ui_hierarchy=automation_ready,
            metrics=True,
            screenshot=automation_ready,
            automation=automation_ready,
        )

    def _ios_agent_device_to_model(self, info: Dict[str, Any]) -> Optional[Device]:
        device_id = info.get("id")
        if not device_id:
            return None

        device = Device(
            id=str(device_id),
            name=info.get("name") or str(device_id),
            model=info.get("model") or "Unknown",
            brand=info.get("brand") or "Apple",
            os="ios",
            os_version=info.get("os_version") or "Unknown",
            status=DeviceStatus(info.get("status") or DeviceStatus.ONLINE),
            screen_resolution=info.get("screen_resolution") or "Unknown",
            screen_size=info.get("screen_size") or 6.1,
            cpu=info.get("cpu") or "arm64",
            memory=info.get("memory") or "Unknown",
            storage=info.get("storage") or "Unknown",
            battery_level=info.get("battery_level") or 100,
            last_active_at=datetime.now(),
            tags=info.get("tags") or [],
            appium_ready=info.get("appium_ready"),
            automation_status=info.get("automation_status"),
        )
        self._apply_ios_automation_capability(device, bool(info.get("automation_ready")))
        return device

    async def scan_devices(self) -> List[Device]:
        """Scan and update device list"""
        device_list = await adb_service.list_devices()
        ios_device_list = await self._fetch_ios_agent_devices()
        current_ids = set()

        for device_info in device_list:
            device_id = device_info["id"]
            current_ids.add(device_id)

            if device_id in self._devices:
                # Update existing device status
                self._devices[device_id].status = device_info["status"]
                self._devices[device_id].last_active_at = datetime.now()
                await self._refresh_existing_device_metadata(self._devices[device_id])
                self._devices[device_id].refresh_runtime_fields()
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
                        os=info.get("os", "android"),
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

        for device_info in ios_device_list:
            device = self._ios_agent_device_to_model(device_info)
            if not device:
                continue

            device_id = device.id
            current_ids.add(device_id)

            if device_id in self._devices:
                existing = self._devices[device_id]
                existing.name = device.name
                existing.model = device.model
                existing.brand = device.brand
                existing.os = device.os
                existing.os_version = device.os_version
                existing.status = device.status
                existing.screen_resolution = device.screen_resolution
                existing.screen_size = device.screen_size
                existing.cpu = device.cpu
                existing.memory = device.memory
                existing.storage = device.storage
                existing.battery_level = device.battery_level
                existing.appium_ready = device.appium_ready
                existing.automation_status = device.automation_status
                existing.last_active_at = datetime.now()
                existing.refresh_runtime_fields()
                self._apply_ios_automation_capability(existing, bool(device_info.get("automation_ready")))
                await device_db_service.upsert_device(existing)
            else:
                self._devices[device_id] = device
                await device_db_service.upsert_device(device)
                logger.info(f"New iOS device discovered and saved: {device_id}")

        # Mark offline for devices not in current list
        offline_ids = [did for did in self._devices if did not in current_ids]
        for device_id in offline_ids:
            self._devices[device_id].status = DeviceStatus.OFFLINE
            self._devices[device_id].refresh_runtime_fields()

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
        device.refresh_runtime_fields()

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
        device = self._devices.get(device_id)
        if not device:
            return None

        if str(device.os).lower() == "ios":
            return await self.get_ios_screenshot(device_id)

        return await adb_service.get_screenshot(device_id)

    async def _request_ios_agent(self, path: str, method: str = "GET") -> Dict[str, Any]:
        if not settings.IOS_AGENT_URL:
            raise RuntimeError("iOS Agent is not configured")

        url = f"{settings.IOS_AGENT_URL.rstrip('/')}{path}"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.request(method, url)
        except httpx.RequestError as exc:
            raise RuntimeError(f"Unable to reach iOS Agent: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("detail") or detail)
            except Exception:
                pass
            raise RuntimeError(detail or f"iOS Agent request failed with HTTP {response.status_code}")

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("iOS Agent returned invalid payload")
        return payload

    async def get_ios_screenshot(self, device_id: str) -> Optional[bytes]:
        payload = await self._request_ios_agent(f"/devices/{device_id}/screenshot")
        image = payload.get("image")
        if not isinstance(image, str) or not image:
            return None
        try:
            return base64.b64decode(image)
        except Exception as exc:
            raise RuntimeError("iOS Agent returned invalid screenshot data") from exc

    async def get_ios_ui_source(self, device_id: str) -> str:
        payload = await self._request_ios_agent(f"/devices/{device_id}/source")
        source = payload.get("source")
        if not isinstance(source, str) or not source:
            raise RuntimeError("iOS Agent returned empty page source")
        return source

    async def release_ios_debug_session(self, device_id: str) -> bool:
        payload = await self._request_ios_agent(f"/devices/{device_id}/debug-session", method="DELETE")
        return bool(payload.get("released"))

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
