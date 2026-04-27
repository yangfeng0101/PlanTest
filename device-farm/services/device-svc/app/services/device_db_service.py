# Device Database Service - Persistence Layer
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, update, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
import logging
import json

from app.database import AsyncSessionLocal, get_db_session
from app.models.device_db import DeviceDB, DeviceStatusDB
from app.models.device import Device, DeviceStatus, DeviceFilter

logger = logging.getLogger(__name__)


class DeviceDatabaseService:
    """Service for device database operations"""

    async def get_all_devices(self) -> List[Device]:
        """Get all devices from database"""
        async with get_db_session() as session:
            result = await session.execute(select(DeviceDB))
            db_devices = result.scalars().all()
            return [self._db_to_model(d) for d in db_devices]

    async def get_device(self, device_id: str) -> Optional[Device]:
        """Get a single device by ID"""
        async with get_db_session() as session:
            result = await session.execute(
                select(DeviceDB).where(DeviceDB.id == device_id)
            )
            db_device = result.scalar_one_or_none()
            return self._db_to_model(db_device) if db_device else None

    async def upsert_device(self, device: Device) -> Device:
        """Create or update a device"""
        async with get_db_session() as session:
            db_device = self._model_to_db(device)
            # Use merge to handle both insert and update
            merged = await session.merge(db_device)
            await session.flush()
            await session.refresh(merged)
            return self._db_to_model(merged)

    async def upsert_devices(self, devices: List[Device]) -> List[Device]:
        """Batch upsert devices"""
        results = []
        for device in devices:
            result = await self.upsert_device(device)
            results.append(result)
        return results

    async def update_device_status(
        self,
        device_id: str,
        status: DeviceStatus,
        occupied_by: Optional[str] = None,
        occupied_at: Optional[datetime] = None
    ) -> Optional[Device]:
        """Update device status"""
        async with get_db_session() as session:
            result = await session.execute(
                select(DeviceDB).where(DeviceDB.id == device_id)
            )
            db_device = result.scalar_one_or_none()
            if not db_device:
                return None

            db_device.status = status.value if hasattr(status, 'value') else status
            db_device.occupied_by = occupied_by
            db_device.occupied_at = occupied_at
            db_device.updated_at = datetime.utcnow()

            await session.flush()
            await session.refresh(db_device)
            return self._db_to_model(db_device)

    async def update_device_info(
        self,
        device_id: str,
        name: Optional[str] = None,
        os: Optional[str] = None,
        os_version: Optional[str] = None,
        tags: Optional[List[str]] = None,
        battery_level: Optional[int] = None,
        status: Optional[DeviceStatus] = None
    ) -> Optional[Device]:
        """Update device information"""
        async with get_db_session() as session:
            result = await session.execute(
                select(DeviceDB).where(DeviceDB.id == device_id)
            )
            db_device = result.scalar_one_or_none()
            if not db_device:
                return None

            if name is not None:
                db_device.name = name
            if os is not None:
                db_device.os = os
            if os_version is not None:
                db_device.os_version = os_version
            if tags is not None:
                db_device.tags = tags
            if battery_level is not None:
                db_device.battery_level = battery_level
            if status is not None:
                db_device.status = status.value if hasattr(status, 'value') else status

            db_device.updated_at = datetime.utcnow()

            await session.flush()
            await session.refresh(db_device)
            return self._db_to_model(db_device)

    async def set_devices_offline(self, device_ids: List[str]) -> int:
        """Set multiple devices to offline status"""
        if not device_ids:
            return 0

        async with get_db_session() as session:
            result = await session.execute(
                update(DeviceDB)
                .where(DeviceDB.id.in_(device_ids))
                .values(status=DeviceStatusDB.OFFLINE, updated_at=datetime.utcnow())
            )
            return result.rowcount

    async def delete_device(self, device_id: str) -> bool:
        """Delete a device from database"""
        async with get_db_session() as session:
            result = await session.execute(
                delete(DeviceDB).where(DeviceDB.id == device_id)
            )
            return result.rowcount > 0

    async def get_devices_by_filter(self, filter: DeviceFilter) -> List[Device]:
        """Get devices with filtering"""
        async with get_db_session() as session:
            query = select(DeviceDB)

            if filter.status:
                query = query.where(DeviceDB.status == DeviceStatusDB(filter.status.value))
            if filter.brand:
                query = query.where(DeviceDB.brand == filter.brand)
            if filter.os_version:
                query = query.where(DeviceDB.os_version == filter.os_version)
            if filter.keyword:
                keyword = filter.keyword.lower()
                query = query.where(
                    or_(
                        DeviceDB.name.ilike(f"%{keyword}%"),
                        DeviceDB.model.ilike(f"%{keyword}%"),
                        DeviceDB.id.ilike(f"%{keyword}%")
                    )
                )
            # Note: tags filtering requires JSON operations

            result = await session.execute(query)
            db_devices = result.scalars().all()
            devices = [self._db_to_model(d) for d in db_devices]

            # Filter by tags in Python (could be optimized with JSON query)
            if filter.tags:
                devices = [
                    d for d in devices
                    if any(tag in d.tags for tag in filter.tags)
                ]

            return devices

    async def get_device_stats(self) -> Dict[str, Any]:
        """Get device statistics from database"""
        devices = await self.get_all_devices()

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

    def _db_to_model(self, db_device: DeviceDB) -> Device:
        """Convert database model to Pydantic model"""
        return Device(
            id=db_device.id,
            name=db_device.name,
            model=db_device.model,
            brand=db_device.brand,
            os=db_device.os,
            os_version=db_device.os_version,
            status=DeviceStatus(db_device.status if isinstance(db_device.status, str) else db_device.status.value),
            screen_resolution=db_device.screen_resolution,
            screen_size=db_device.screen_size,
            cpu=db_device.cpu,
            memory=db_device.memory,
            storage=db_device.storage,
            battery_level=db_device.battery_level,
            occupied_by=db_device.occupied_by,
            occupied_at=db_device.occupied_at,
            last_active_at=db_device.last_active_at,
            created_at=db_device.created_at,
            updated_at=db_device.updated_at,
            tags=db_device.tags,
            thumbnail=db_device.thumbnail,
        )

    def _model_to_db(self, device: Device) -> DeviceDB:
        """Convert Pydantic model to database model"""
        return DeviceDB(
            id=device.id,
            name=device.name,
            model=device.model,
            brand=device.brand,
            os=device.os,
            os_version=device.os_version,
            status=device.status.value if hasattr(device.status, 'value') else device.status,
            screen_resolution=device.screen_resolution,
            screen_size=device.screen_size,
            cpu=device.cpu,
            memory=device.memory,
            storage=device.storage,
            battery_level=device.battery_level,
            occupied_by=device.occupied_by,
            occupied_at=device.occupied_at,
            last_active_at=device.last_active_at,
            created_at=device.created_at,
            updated_at=device.updated_at,
            tags_json=json.dumps(device.tags),
            thumbnail=device.thumbnail,
        )


# Global instance
device_db_service = DeviceDatabaseService()
