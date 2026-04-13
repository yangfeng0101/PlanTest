# Device Group Database Service
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group_db import DeviceGroupDB, GroupType
from app.models.group import DeviceGroup, GroupCreate, GroupUpdate, GroupDetail


class GroupService:
    """Service for managing device groups with database persistence"""

    async def list_groups(
        self,
        db: AsyncSession,
        type: Optional[GroupType] = None,
        keyword: Optional[str] = None,
    ) -> List[DeviceGroup]:
        """Get list of all device groups"""
        query = select(DeviceGroupDB)

        # Filter by type
        if type:
            query = query.where(DeviceGroupDB.type == type)

        # Filter by keyword
        if keyword:
            keyword_lower = f"%{keyword.lower()}%"
            query = query.where(
                (DeviceGroupDB.name.ilike(keyword_lower)) |
                (DeviceGroupDB.description.ilike(keyword_lower))
            )

        query = query.order_by(DeviceGroupDB.created_at.desc())
        result = await db.execute(query)
        groups_db = result.scalars().all()

        return [self._to_pydantic(g) for g in groups_db]

    async def get_group(self, db: AsyncSession, group_id: str) -> Optional[DeviceGroupDB]:
        """Get group by ID"""
        query = select(DeviceGroupDB).where(DeviceGroupDB.id == group_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create_group(self, db: AsyncSession, data: GroupCreate) -> DeviceGroup:
        """Create a new device group"""
        group_db = DeviceGroupDB(
            name=data.name,
            description=data.description,
            type=data.type,
            device_ids=data.device_ids,
            color=data.color or "#1890ff",
            icon=data.icon,
        )

        db.add(group_db)
        await db.flush()
        await db.refresh(group_db)

        return self._to_pydantic(group_db)

    async def update_group(
        self,
        db: AsyncSession,
        group_id: str,
        data: GroupUpdate
    ) -> Optional[DeviceGroup]:
        """Update group information"""
        group_db = await self.get_group(db, group_id)
        if not group_db:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Handle device_ids separately
        if 'device_ids' in update_data:
            group_db.device_ids = update_data.pop('device_ids')

        for key, value in update_data.items():
            setattr(group_db, key, value)

        group_db.updated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(group_db)

        return self._to_pydantic(group_db)

    async def delete_group(self, db: AsyncSession, group_id: str) -> bool:
        """Delete a group"""
        group_db = await self.get_group(db, group_id)
        if not group_db:
            return False

        # Prevent deleting system groups
        if group_db.type == GroupType.SYSTEM:
            raise ValueError("Cannot delete system groups")

        await db.delete(group_db)
        await db.flush()
        return True

    async def add_devices(
        self,
        db: AsyncSession,
        group_id: str,
        device_ids: List[str]
    ) -> Optional[DeviceGroup]:
        """Add devices to a group"""
        group_db = await self.get_group(db, group_id)
        if not group_db:
            return None

        current_ids = set(group_db.device_ids)
        new_ids = set(device_ids)
        group_db.device_ids = list(current_ids | new_ids)
        group_db.updated_at = datetime.utcnow()

        await db.flush()
        await db.refresh(group_db)

        return self._to_pydantic(group_db)

    async def remove_devices(
        self,
        db: AsyncSession,
        group_id: str,
        device_ids: List[str]
    ) -> Optional[DeviceGroup]:
        """Remove devices from a group"""
        group_db = await self.get_group(db, group_id)
        if not group_db:
            return None

        current_ids = set(group_db.device_ids)
        remove_ids = set(device_ids)
        group_db.device_ids = list(current_ids - remove_ids)
        group_db.updated_at = datetime.utcnow()

        await db.flush()
        await db.refresh(group_db)

        return self._to_pydantic(group_db)

    def _to_pydantic(self, group_db: DeviceGroupDB) -> DeviceGroup:
        """Convert database model to Pydantic model"""
        return DeviceGroup(
            id=group_db.id,
            name=group_db.name,
            description=group_db.description,
            type=group_db.type,
            device_ids=group_db.device_ids,
            color=group_db.color,
            icon=group_db.icon,
            created_by=group_db.created_by,
            created_at=group_db.created_at,
            updated_at=group_db.updated_at,
        )


# Global instance
group_service = GroupService()
