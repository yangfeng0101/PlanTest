# Parallel Task Database Service
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.parallel_task_db import (
    ParallelTaskDB,
    ParallelTaskStatus,
    DeviceSelectionStrategy
)
from app.services.parallel_executor import (
    ParallelTask,
    ParallelTaskCreate,
    ParallelTaskSummary,
    SubTaskInfo
)


class ParallelTaskService:
    """Service for managing parallel tasks in database"""

    async def create_task(
        self,
        db: AsyncSession,
        script_id: str,
        selection_strategy: DeviceSelectionStrategy,
        max_concurrency: int,
        parameters: Dict[str, Any],
        device_capabilities: Dict[str, Any],
        sub_tasks: List[Dict[str, Any]],
        total_devices: int
    ) -> ParallelTaskDB:
        """Create a new parallel task in database"""
        task = ParallelTaskDB(
            script_id=script_id,
            status=ParallelTaskStatus.PENDING,
            selection_strategy=selection_strategy,
            max_concurrency=max_concurrency,
            parameters=parameters,
            device_capabilities=device_capabilities,
            sub_tasks=sub_tasks,
            total_devices=total_devices
        )
        db.add(task)
        await db.flush()
        await db.refresh(task)
        return task

    async def get_task(self, db: AsyncSession, task_id: str) -> Optional[ParallelTaskDB]:
        """Get a parallel task by ID"""
        query = select(ParallelTaskDB).where(ParallelTaskDB.id == task_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        db: AsyncSession,
        status: Optional[ParallelTaskStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[ParallelTaskDB]:
        """List parallel tasks with optional filtering"""
        query = select(ParallelTaskDB)

        if status:
            query = query.where(ParallelTaskDB.status == status)

        query = query.order_by(desc(ParallelTaskDB.created_at))
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def update_task_status(
        self,
        db: AsyncSession,
        task_id: str,
        status: ParallelTaskStatus,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None
    ) -> Optional[ParallelTaskDB]:
        """Update task status"""
        task = await self.get_task(db, task_id)
        if not task:
            return None

        task.status = status
        if started_at:
            task.started_at = started_at
        if finished_at:
            task.finished_at = finished_at

        await db.flush()
        await db.refresh(task)
        return task

    async def update_task_progress(
        self,
        db: AsyncSession,
        task_id: str,
        completed_devices: int,
        failed_devices: int,
        sub_tasks: List[Dict[str, Any]]
    ) -> Optional[ParallelTaskDB]:
        """Update task progress"""
        task = await self.get_task(db, task_id)
        if not task:
            return None

        task.completed_devices = completed_devices
        task.failed_devices = failed_devices
        task.sub_tasks = sub_tasks

        await db.flush()
        await db.refresh(task)
        return task

    async def delete_task(self, db: AsyncSession, task_id: str) -> bool:
        """Delete a parallel task"""
        task = await self.get_task(db, task_id)
        if not task:
            return False

        await db.delete(task)
        await db.flush()
        return True

    def _to_pydantic(self, task_db: ParallelTaskDB) -> ParallelTask:
        """Convert database model to Pydantic model"""
        sub_tasks = [
            SubTaskInfo(**st) if isinstance(st, dict) else st
            for st in (task_db.sub_tasks or [])
        ]

        return ParallelTask(
            id=task_db.id,
            script_id=task_db.script_id,
            status=task_db.status,
            selection_strategy=task_db.selection_strategy,
            max_concurrency=task_db.max_concurrency,
            parameters=task_db.parameters or {},
            device_capabilities=task_db.device_capabilities or {},
            sub_tasks=sub_tasks,
            total_devices=task_db.total_devices,
            completed_devices=task_db.completed_devices,
            failed_devices=task_db.failed_devices,
            created_at=task_db.created_at,
            started_at=task_db.started_at,
            finished_at=task_db.finished_at
        )


# Global service instance
parallel_task_service = ParallelTaskService()
