# Threshold Configuration Database Service
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.threshold_db import DeviceThresholdDB
from app.models.metrics import DeviceThresholdConfig


class ThresholdService:
    """Service for managing device threshold configurations in database"""

    # Default threshold values
    DEFAULTS = {
        'cpu_warning': 80.0,
        'cpu_critical': 95.0,
        'memory_warning': 80.0,
        'memory_critical': 95.0,
        'battery_warning': 20.0,
        'battery_critical': 10.0,
        'temperature_warning': 45.0,
        'temperature_critical': 55.0,
    }

    async def get_threshold(
        self,
        db: AsyncSession,
        device_id: str
    ) -> DeviceThresholdConfig:
        """Get threshold configuration for a device"""
        query = select(DeviceThresholdDB).where(DeviceThresholdDB.device_id == device_id)
        result = await db.execute(query)
        threshold_db = result.scalar_one_or_none()

        if threshold_db:
            return self._to_pydantic(threshold_db)
        else:
            # Return default config
            return DeviceThresholdConfig(device_id=device_id)

    async def set_threshold(
        self,
        db: AsyncSession,
        device_id: str,
        config: DeviceThresholdConfig
    ) -> DeviceThresholdConfig:
        """Set or update threshold configuration for a device"""
        query = select(DeviceThresholdDB).where(DeviceThresholdDB.device_id == device_id)
        result = await db.execute(query)
        threshold_db = result.scalar_one_or_none()

        if threshold_db:
            # Update existing
            threshold_db.cpu_warning = config.cpu_warning
            threshold_db.cpu_critical = config.cpu_critical
            threshold_db.memory_warning = config.memory_warning
            threshold_db.memory_critical = config.memory_critical
            threshold_db.battery_warning = config.battery_warning
            threshold_db.battery_critical = config.battery_critical
            threshold_db.temperature_warning = config.temperature_warning
            threshold_db.temperature_critical = config.temperature_critical
            threshold_db.updated_at = datetime.utcnow()
        else:
            # Create new
            threshold_db = DeviceThresholdDB(
                device_id=device_id,
                cpu_warning=config.cpu_warning,
                cpu_critical=config.cpu_critical,
                memory_warning=config.memory_warning,
                memory_critical=config.memory_critical,
                battery_warning=config.battery_warning,
                battery_critical=config.battery_critical,
                temperature_warning=config.temperature_warning,
                temperature_critical=config.temperature_critical,
            )
            db.add(threshold_db)

        await db.flush()
        await db.refresh(threshold_db)
        return self._to_pydantic(threshold_db)

    async def delete_threshold(
        self,
        db: AsyncSession,
        device_id: str
    ) -> bool:
        """Delete threshold configuration for a device"""
        query = select(DeviceThresholdDB).where(DeviceThresholdDB.device_id == device_id)
        result = await db.execute(query)
        threshold_db = result.scalar_one_or_none()

        if not threshold_db:
            return False

        await db.delete(threshold_db)
        await db.flush()
        return True

    def _to_pydantic(self, threshold_db: DeviceThresholdDB) -> DeviceThresholdConfig:
        """Convert database model to Pydantic model"""
        return DeviceThresholdConfig(
            device_id=threshold_db.device_id,
            cpu_warning=threshold_db.cpu_warning,
            cpu_critical=threshold_db.cpu_critical,
            memory_warning=threshold_db.memory_warning,
            memory_critical=threshold_db.memory_critical,
            battery_warning=threshold_db.battery_warning,
            battery_critical=threshold_db.battery_critical,
            temperature_warning=threshold_db.temperature_warning,
            temperature_critical=threshold_db.temperature_critical,
        )


# Global service instance
threshold_service = ThresholdService()
