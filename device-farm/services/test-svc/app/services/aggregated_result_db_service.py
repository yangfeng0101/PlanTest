# Aggregated Result Database Service
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aggregated_result_db import AggregatedResultDB, AggregationStatus
from app.services.result_aggregator import AggregatedResult, DeviceResult


class AggregatedResultDBService:
    """Service for managing aggregated results in database"""

    async def create_result(
        self,
        db: AsyncSession,
        parallel_task_id: str,
        script_id: str,
        total_devices: int
    ) -> AggregatedResultDB:
        """Create a new aggregated result in database"""
        result = AggregatedResultDB(
            parallel_task_id=parallel_task_id,
            script_id=script_id,
            status=AggregationStatus.IN_PROGRESS,
            started_at=datetime.utcnow(),
            total_devices=total_devices
        )
        db.add(result)
        await db.flush()
        await db.refresh(result)
        return result

    async def get_result(self, db: AsyncSession, result_id: str) -> Optional[AggregatedResultDB]:
        """Get an aggregated result by ID"""
        query = select(AggregatedResultDB).where(AggregatedResultDB.id == result_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_result_by_parallel_task(
        self, db: AsyncSession, parallel_task_id: str
    ) -> Optional[AggregatedResultDB]:
        """Get aggregated result by parallel task ID"""
        query = select(AggregatedResultDB).where(
            AggregatedResultDB.parallel_task_id == parallel_task_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def update_result(
        self,
        db: AsyncSession,
        result_id: str,
        **kwargs
    ) -> Optional[AggregatedResultDB]:
        """Update aggregated result"""
        result = await self.get_result(db, result_id)
        if not result:
            return None

        for key, value in kwargs.items():
            if hasattr(result, key):
                setattr(result, key, value)

        await db.flush()
        await db.refresh(result)
        return result

    async def complete_result(
        self,
        db: AsyncSession,
        result_id: str,
        completed_devices: int,
        failed_devices: int,
        success_rate: float,
        total_duration: float,
        total_tests: int,
        passed_tests: int,
        failed_tests: int,
        skipped_tests: int,
        test_success_rate: float,
        device_results: List[Dict[str, Any]],
        failed_device_ids: List[str]
    ) -> Optional[AggregatedResultDB]:
        """Mark aggregation as completed with final metrics"""
        result = await self.get_result(db, result_id)
        if not result:
            return None

        result.status = AggregationStatus.COMPLETED
        result.finished_at = datetime.utcnow()
        result.completed_devices = completed_devices
        result.failed_devices = failed_devices
        result.success_rate = success_rate
        result.total_duration = total_duration
        result.total_tests = total_tests
        result.passed_tests = passed_tests
        result.failed_tests = failed_tests
        result.skipped_tests = skipped_tests
        result.test_success_rate = test_success_rate
        result.device_results = device_results
        result.failed_device_ids = failed_device_ids

        await db.flush()
        await db.refresh(result)
        return result

    async def list_results(
        self,
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0
    ) -> List[AggregatedResultDB]:
        """List aggregated results"""
        query = select(AggregatedResultDB)
        query = query.order_by(desc(AggregatedResultDB.created_at))
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    def _to_pydantic(self, result_db: AggregatedResultDB) -> AggregatedResult:
        """Convert database model to Pydantic model"""
        device_results = [
            DeviceResult(**dr) if isinstance(dr, dict) else dr
            for dr in (result_db.device_results or [])
        ]

        return AggregatedResult(
            id=result_db.id,
            parallel_task_id=result_db.parallel_task_id,
            script_id=result_db.script_id,
            status=result_db.status,
            started_at=result_db.started_at,
            finished_at=result_db.finished_at,
            total_devices=result_db.total_devices,
            completed_devices=result_db.completed_devices,
            failed_devices=result_db.failed_devices,
            success_rate=result_db.success_rate,
            total_duration=result_db.total_duration,
            total_tests=result_db.total_tests,
            passed_tests=result_db.passed_tests,
            failed_tests=result_db.failed_tests,
            skipped_tests=result_db.skipped_tests,
            test_success_rate=result_db.test_success_rate,
            device_results=device_results,
            failed_device_ids=result_db.failed_device_ids or [],
            created_at=result_db.created_at
        )


# Global service instance
aggregated_result_db_service = AggregatedResultDBService()
