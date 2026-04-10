# Result Aggregator Service
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from uuid import uuid4

from app.services.parallel_executor import (
    ParallelTask,
    ParallelTaskStatus,
    SubTaskInfo,
    parallel_executor_service,
)
from app.config import settings


class AggregationStatus(str, Enum):
    """Status of result aggregation"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class DeviceResult(BaseModel):
    """Result from a single device execution"""
    device_id: str
    task_id: str
    status: str  # success, failed, timeout, cancelled
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration: float = 0.0
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    success_rate: float = 0.0
    error: Optional[str] = None
    logs: List[str] = Field(default_factory=list)
    screenshots: List[str] = Field(default_factory=list)


class AggregatedResult(BaseModel):
    """Aggregated result from parallel execution"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    parallel_task_id: str
    script_id: str
    status: AggregationStatus = AggregationStatus.PENDING
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # Summary metrics
    total_devices: int = 0
    completed_devices: int = 0
    failed_devices: int = 0
    success_rate: float = 0.0  # Device success rate
    total_duration: float = 0.0

    # Test metrics (aggregated across all devices)
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    test_success_rate: float = 0.0

    # Device-level results
    device_results: List[DeviceResult] = Field(default_factory=list)

    # Failed devices summary
    failed_device_ids: List[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)


class ParallelReportSummary(BaseModel):
    """Summary report for parallel execution"""
    parallel_task_id: str
    script_id: str
    status: ParallelTaskStatus

    # Device summary
    total_devices: int
    completed_devices: int
    failed_devices: int
    device_success_rate: float

    # Test summary
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    test_success_rate: float

    # Timing
    total_duration: float
    avg_device_duration: float

    # Failed devices
    failed_device_ids: List[str]
    failed_device_details: List[Dict[str, Any]] = Field(default_factory=list)

    # Status breakdown
    status_breakdown: Dict[str, int] = Field(default_factory=dict)


class ResultAggregatorService:
    """Service for aggregating results from parallel execution"""

    def __init__(self):
        # In-memory storage for aggregated results (in production, use database)
        self._aggregated_results: Dict[str, AggregatedResult] = {}

    async def aggregate_results(
        self,
        parallel_task_id: str
    ) -> AggregatedResult:
        """Aggregate results from a parallel task

        Args:
            parallel_task_id: ID of the parallel task

        Returns:
            Aggregated result with all device results
        """
        parallel_task = parallel_executor_service.get_parallel_task(parallel_task_id)
        if not parallel_task:
            raise ValueError(f"Parallel task {parallel_task_id} not found")

        # Create aggregation result
        aggregated = AggregatedResult(
            parallel_task_id=parallel_task_id,
            script_id=parallel_task.script_id,
            status=AggregationStatus.IN_PROGRESS,
            started_at=datetime.utcnow(),
            total_devices=parallel_task.total_devices,
        )

        # Fetch results from each sub-task
        device_results = []
        for sub_task in parallel_task.sub_tasks:
            device_result = await self._fetch_device_result(sub_task)
            device_results.append(device_result)

        aggregated.device_results = device_results

        # Calculate aggregated metrics
        self._calculate_metrics(aggregated)

        # Store result
        aggregated.status = AggregationStatus.COMPLETED
        aggregated.finished_at = datetime.utcnow()
        self._aggregated_results[aggregated.id] = aggregated

        return aggregated

    async def _fetch_device_result(
        self,
        sub_task: SubTaskInfo
    ) -> DeviceResult:
        """Fetch result from a single device execution

        Args:
            sub_task: Sub-task information

        Returns:
            Device result with execution details
        """
        result = DeviceResult(
            device_id=sub_task.device_id,
            task_id=sub_task.task_id,
            status=sub_task.status,
            started_at=sub_task.started_at,
            finished_at=sub_task.finished_at,
            error=sub_task.error,
        )

        # Calculate duration
        if result.started_at and result.finished_at:
            result.duration = (result.finished_at - result.started_at).total_seconds()

        # Fetch task details from database
        try:
            from app.database import get_db_session
            from app.models.database import TaskDB, TaskLogDB
            from sqlalchemy import select

            async with get_db_session() as db:
                # Get task
                query = select(TaskDB).where(TaskDB.id == sub_task.task_id)
                task_result = await db.execute(query)
                task_db = task_result.scalar_one_or_none()

                if task_db:
                    # Parse result data
                    if task_db.result:
                        result.total_tests = task_db.result.get("total_tests", 0)
                        result.passed_tests = task_db.result.get("passed_tests", 0)
                        result.failed_tests = task_db.result.get("failed_tests", 0)
                        result.skipped_tests = task_db.result.get("skipped_tests", 0)
                        result.screenshots = task_db.result.get("screenshots", [])

                    # Calculate success rate
                    if result.total_tests > 0:
                        result.success_rate = (result.passed_tests / result.total_tests) * 100

                # Get logs
                log_query = (
                    select(TaskLogDB)
                    .where(TaskLogDB.task_id == sub_task.task_id)
                    .order_by(TaskLogDB.timestamp)
                )
                log_result = await db.execute(log_query)
                log_dbs = log_result.scalars().all()
                result.logs = [
                    f"[{log.level}] {log.message}"
                    for log in log_dbs
                ]

        except Exception as e:
            result.error = f"Failed to fetch task details: {str(e)}"

        return result

    def _calculate_metrics(self, aggregated: AggregatedResult):
        """Calculate aggregated metrics

        Args:
            aggregated: Aggregated result to update
        """
        completed = 0
        failed = 0
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        skipped_tests = 0
        total_duration = 0.0
        failed_device_ids = []

        for device_result in aggregated.device_results:
            # Count completed/failed devices
            if device_result.status == "success":
                completed += 1
            else:
                failed += 1
                failed_device_ids.append(device_result.device_id)

            # Aggregate test metrics
            total_tests += device_result.total_tests
            passed_tests += device_result.passed_tests
            failed_tests += device_result.failed_tests
            skipped_tests += device_result.skipped_tests

            # Sum duration
            total_duration += device_result.duration

        # Update aggregated result
        aggregated.completed_devices = completed
        aggregated.failed_devices = failed
        aggregated.total_tests = total_tests
        aggregated.passed_tests = passed_tests
        aggregated.failed_tests = failed_tests
        aggregated.skipped_tests = skipped_tests
        aggregated.total_duration = total_duration
        aggregated.failed_device_ids = failed_device_ids

        # Calculate rates
        if aggregated.total_devices > 0:
            aggregated.success_rate = (completed / aggregated.total_devices) * 100

        if total_tests > 0:
            aggregated.test_success_rate = (passed_tests / total_tests) * 100

    def get_aggregated_result(
        self,
        aggregated_result_id: str
    ) -> Optional[AggregatedResult]:
        """Get aggregated result by ID

        Args:
            aggregated_result_id: ID of the aggregated result

        Returns:
            Aggregated result or None
        """
        return self._aggregated_results.get(aggregated_result_id)

    def get_aggregated_result_by_parallel_task(
        self,
        parallel_task_id: str
    ) -> Optional[AggregatedResult]:
        """Get aggregated result by parallel task ID

        Args:
            parallel_task_id: ID of the parallel task

        Returns:
            Aggregated result or None
        """
        for result in self._aggregated_results.values():
            if result.parallel_task_id == parallel_task_id:
                return result
        return None

    def generate_report_summary(
        self,
        parallel_task_id: str
    ) -> Optional[ParallelReportSummary]:
        """Generate summary report for parallel execution

        Args:
            parallel_task_id: ID of the parallel task

        Returns:
            Summary report or None
        """
        parallel_task = parallel_executor_service.get_parallel_task(parallel_task_id)
        if not parallel_task:
            return None

        aggregated = self.get_aggregated_result_by_parallel_task(parallel_task_id)

        # Calculate metrics
        device_success_rate = 0.0
        if parallel_task.total_devices > 0:
            device_success_rate = (
                parallel_task.completed_devices / parallel_task.total_devices
            ) * 100

        # Calculate average duration
        avg_duration = 0.0
        if aggregated and aggregated.completed_devices > 0:
            avg_duration = aggregated.total_duration / aggregated.completed_devices

        # Build status breakdown
        status_breakdown = {}
        failed_device_details = []

        if aggregated:
            for dr in aggregated.device_results:
                status_breakdown[dr.status] = status_breakdown.get(dr.status, 0) + 1
                if dr.status != "success":
                    failed_device_details.append({
                        "device_id": dr.device_id,
                        "status": dr.status,
                        "error": dr.error,
                        "duration": dr.duration,
                    })

        return ParallelReportSummary(
            parallel_task_id=parallel_task.id,
            script_id=parallel_task.script_id,
            status=parallel_task.status,
            total_devices=parallel_task.total_devices,
            completed_devices=parallel_task.completed_devices,
            failed_devices=parallel_task.failed_devices,
            device_success_rate=device_success_rate,
            total_tests=aggregated.total_tests if aggregated else 0,
            passed_tests=aggregated.passed_tests if aggregated else 0,
            failed_tests=aggregated.failed_tests if aggregated else 0,
            skipped_tests=aggregated.skipped_tests if aggregated else 0,
            test_success_rate=aggregated.test_success_rate if aggregated else 0.0,
            total_duration=aggregated.total_duration if aggregated else 0.0,
            avg_device_duration=avg_duration,
            failed_device_ids=aggregated.failed_device_ids if aggregated else [],
            failed_device_details=failed_device_details,
            status_breakdown=status_breakdown,
        )

    async def get_device_logs(
        self,
        parallel_task_id: str,
        device_id: str
    ) -> List[str]:
        """Get detailed logs for a specific device

        Args:
            parallel_task_id: ID of the parallel task
            device_id: ID of the device

        Returns:
            List of log entries
        """
        aggregated = self.get_aggregated_result_by_parallel_task(parallel_task_id)
        if not aggregated:
            return []

        for device_result in aggregated.device_results:
            if device_result.device_id == device_id:
                return device_result.logs

        return []

    def list_aggregated_results(
        self,
        limit: int = 20,
        offset: int = 0
    ) -> List[AggregatedResult]:
        """List aggregated results

        Args:
            limit: Maximum number of results to return
            offset: Offset for pagination

        Returns:
            List of aggregated results
        """
        results = list(self._aggregated_results.values())
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[offset:offset + limit]


# Global instance
result_aggregator_service = ResultAggregatorService()
