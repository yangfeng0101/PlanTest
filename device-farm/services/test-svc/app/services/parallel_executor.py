# Parallel Execution Service
import asyncio
import random
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from uuid import uuid4

from app.tasks.executor import execute_test_task
from app.config import settings


class DeviceSelectionStrategy(str, Enum):
    """Strategy for selecting devices"""
    ALL = "all"  # Select all available devices
    RANDOM = "random"  # Randomly select N devices
    SPECIFIC = "specific"  # Use specified device IDs


class ParallelTaskStatus(str, Enum):
    """Status of parallel execution task"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some tasks succeeded, some failed


# Configuration
DEFAULT_MAX_CONCURRENCY = 5


class ParallelTaskCreate(BaseModel):
    """Request model for creating a parallel task"""
    script_id: str
    device_ids: Optional[List[str]] = None  # Required for SPECIFIC strategy
    device_platform: Optional[str] = "android"
    selection_strategy: DeviceSelectionStrategy = DeviceSelectionStrategy.ALL
    max_devices: Optional[int] = None  # For RANDOM strategy, how many to select
    max_concurrency: int = Field(default=DEFAULT_MAX_CONCURRENCY, ge=1, le=20)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    device_capabilities: Dict[str, Any] = Field(default_factory=dict)


class SubTaskInfo(BaseModel):
    """Information about a sub-task in parallel execution"""
    task_id: str
    device_id: str
    status: str = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ParallelTask(BaseModel):
    """Parallel execution task model"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    script_id: str
    status: ParallelTaskStatus = ParallelTaskStatus.PENDING
    selection_strategy: DeviceSelectionStrategy
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    parameters: Dict[str, Any] = Field(default_factory=dict)
    device_capabilities: Dict[str, Any] = Field(default_factory=dict)
    sub_tasks: List[SubTaskInfo] = Field(default_factory=list)
    total_devices: int = 0
    completed_devices: int = 0
    failed_devices: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ParallelTaskSummary(BaseModel):
    """Summary of parallel task execution"""
    parallel_task_id: str
    script_id: str
    status: ParallelTaskStatus
    total_devices: int
    completed_devices: int
    failed_devices: int
    success_rate: float = 0.0
    total_duration: float = 0.0
    sub_tasks: List[SubTaskInfo]


class ParallelExecutorService:
    """Service for managing parallel task execution across multiple devices"""

    def __init__(self, max_concurrency: int = DEFAULT_MAX_CONCURRENCY):
        self.max_concurrency = max_concurrency
        # In-memory storage for parallel tasks (in production, use database)
        self._parallel_tasks: Dict[str, ParallelTask] = {}

    async def get_available_devices(
        self,
        platform: Optional[str] = None,
        capabilities: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Get list of available devices from device-svc

        Args:
            platform: Filter by platform (android/ios)
            capabilities: Additional capability requirements

        Returns:
            List of available device IDs
        """
        # In production, call device-svc API to get available devices
        # For now, return a mock list
        # TODO: Integrate with device-svc API
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                # Call device-svc to get available devices
                params = {"status": "available"}
                if platform:
                    params["platform"] = platform

                response = await client.get(
                    f"{settings.REPORT_SERVICE_URL.replace('8002', '8000')}/api/v1/devices",
                    params=params,
                    timeout=10.0
                )

                if response.status_code == 200:
                    data = response.json()
                    devices = data.get("items", [])
                    return [d.get("id") or d.get("device_id") for d in devices]
        except Exception:
            pass

        # Fallback to mock devices for testing
        return [
            "device-001",
            "device-002",
            "device-003",
            "device-004",
            "device-005",
        ]

    def select_devices(
        self,
        available_devices: List[str],
        strategy: DeviceSelectionStrategy,
        specific_ids: Optional[List[str]] = None,
        max_devices: Optional[int] = None
    ) -> List[str]:
        """Select devices based on strategy

        Args:
            available_devices: List of available device IDs
            strategy: Selection strategy
            specific_ids: Specific device IDs (for SPECIFIC strategy)
            max_devices: Maximum devices to select (for RANDOM strategy)

        Returns:
            Selected device IDs
        """
        if strategy == DeviceSelectionStrategy.ALL:
            return available_devices

        elif strategy == DeviceSelectionStrategy.RANDOM:
            count = min(max_devices or len(available_devices), len(available_devices))
            return random.sample(available_devices, count)

        elif strategy == DeviceSelectionStrategy.SPECIFIC:
            if not specific_ids:
                raise ValueError("Specific device IDs required for SPECIFIC strategy")
            # Validate that specified devices are available
            valid_ids = [d for d in specific_ids if d in available_devices]
            if len(valid_ids) < len(specific_ids):
                invalid = set(specific_ids) - set(valid_ids)
                raise ValueError(f"Devices not available: {invalid}")
            return valid_ids

        return available_devices

    async def create_parallel_task(
        self,
        request: ParallelTaskCreate
    ) -> ParallelTask:
        """Create a new parallel execution task

        Args:
            request: Parallel task creation request

        Returns:
            Created parallel task
        """
        # Get available devices
        available_devices = await self.get_available_devices(
            platform=request.device_platform,
            capabilities=request.device_capabilities
        )

        if not available_devices:
            raise ValueError("No devices available for execution")

        # Select devices based on strategy
        selected_devices = self.select_devices(
            available_devices=available_devices,
            strategy=request.selection_strategy,
            specific_ids=request.device_ids,
            max_devices=request.max_devices
        )

        if not selected_devices:
            raise ValueError("No devices selected for execution")

        # Create parallel task
        parallel_task = ParallelTask(
            script_id=request.script_id,
            selection_strategy=request.selection_strategy,
            max_concurrency=request.max_concurrency,
            parameters=request.parameters,
            device_capabilities=request.device_capabilities,
            total_devices=len(selected_devices),
        )

        # Create sub-tasks for each device
        for device_id in selected_devices:
            sub_task = SubTaskInfo(
                task_id=str(uuid4()),
                device_id=device_id,
            )
            parallel_task.sub_tasks.append(sub_task)

        # Store the parallel task
        self._parallel_tasks[parallel_task.id] = parallel_task

        return parallel_task

    async def execute_parallel_task(self, parallel_task_id: str) -> ParallelTask:
        """Execute a parallel task across multiple devices

        Args:
            parallel_task_id: ID of the parallel task to execute

        Returns:
            Updated parallel task
        """
        parallel_task = self._parallel_tasks.get(parallel_task_id)
        if not parallel_task:
            raise ValueError(f"Parallel task {parallel_task_id} not found")

        parallel_task.status = ParallelTaskStatus.RUNNING
        parallel_task.started_at = datetime.utcnow()

        # Execute sub-tasks with concurrency control
        semaphore = asyncio.Semaphore(parallel_task.max_concurrency)

        async def execute_sub_task(sub_task: SubTaskInfo):
            """Execute a single sub-task"""
            async with semaphore:
                sub_task.status = "running"
                sub_task.started_at = datetime.utcnow()

                try:
                    # Create task in database and queue for execution
                    from app.database import get_db_session
                    from app.models.database import TaskDB, TaskStatus as TaskStatusDB, DevicePlatform

                    async with get_db_session() as db:
                        # Create task record
                        task_db = TaskDB(
                            id=sub_task.task_id,
                            script_id=parallel_task.script_id,
                            device_id=sub_task.device_id,
                            device_platform=DevicePlatform.ANDROID,  # Default, should be configurable
                            device_capabilities=parallel_task.device_capabilities,
                            parameters=parallel_task.parameters,
                            status=TaskStatusDB.PENDING,
                        )
                        db.add(task_db)
                        await db.flush()

                    # Queue the task for Celery execution
                    execute_test_task.delay(sub_task.task_id)

                    # Wait for task completion (polling)
                    max_wait = 3600  # 1 hour max
                    poll_interval = 2  # seconds
                    elapsed = 0

                    while elapsed < max_wait:
                        async with get_db_session() as db:
                            from sqlalchemy import select
                            query = select(TaskDB).where(TaskDB.id == sub_task.task_id)
                            result = await db.execute(query)
                            task_db = result.scalar_one_or_none()

                            if task_db and task_db.status in [
                                TaskStatusDB.SUCCESS,
                                TaskStatusDB.FAILED,
                                TaskStatusDB.CANCELLED
                            ]:
                                sub_task.status = task_db.status.value
                                sub_task.finished_at = task_db.finished_at
                                sub_task.result = task_db.result
                                sub_task.error = task_db.error
                                break

                        await asyncio.sleep(poll_interval)
                        elapsed += poll_interval
                    else:
                        # Timeout
                        sub_task.status = "timeout"
                        sub_task.error = "Task execution timeout"
                        sub_task.finished_at = datetime.utcnow()

                except Exception as e:
                    sub_task.status = "failed"
                    sub_task.error = str(e)
                    sub_task.finished_at = datetime.utcnow()

                return sub_task

        # Execute all sub-tasks concurrently
        tasks = [execute_sub_task(st) for st in parallel_task.sub_tasks]
        await asyncio.gather(*tasks)

        # Update final status
        parallel_task.finished_at = datetime.utcnow()
        completed = sum(1 for st in parallel_task.sub_tasks if st.status == "success")
        failed = sum(1 for st in parallel_task.sub_tasks if st.status in ["failed", "timeout"])

        parallel_task.completed_devices = completed
        parallel_task.failed_devices = failed

        if failed == 0:
            parallel_task.status = ParallelTaskStatus.COMPLETED
        elif completed == 0:
            parallel_task.status = ParallelTaskStatus.FAILED
        else:
            parallel_task.status = ParallelTaskStatus.PARTIAL

        return parallel_task

    def get_parallel_task(self, parallel_task_id: str) -> Optional[ParallelTask]:
        """Get a parallel task by ID

        Args:
            parallel_task_id: ID of the parallel task

        Returns:
            Parallel task or None
        """
        return self._parallel_tasks.get(parallel_task_id)

    def list_parallel_tasks(
        self,
        status: Optional[ParallelTaskStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[ParallelTask]:
        """List parallel tasks

        Args:
            status: Filter by status
            limit: Maximum number of tasks to return
            offset: Offset for pagination

        Returns:
            List of parallel tasks
        """
        tasks = list(self._parallel_tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]

        # Sort by created_at descending
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        return tasks[offset:offset + limit]

    def get_parallel_task_summary(
        self,
        parallel_task_id: str
    ) -> Optional[ParallelTaskSummary]:
        """Get summary of a parallel task

        Args:
            parallel_task_id: ID of the parallel task

        Returns:
            Summary or None
        """
        parallel_task = self.get_parallel_task(parallel_task_id)
        if not parallel_task:
            return None

        # Calculate metrics
        total_duration = 0.0
        if parallel_task.started_at and parallel_task.finished_at:
            total_duration = (
                parallel_task.finished_at - parallel_task.started_at
            ).total_seconds()

        success_rate = 0.0
        if parallel_task.total_devices > 0:
            success_rate = parallel_task.completed_devices / parallel_task.total_devices

        return ParallelTaskSummary(
            parallel_task_id=parallel_task.id,
            script_id=parallel_task.script_id,
            status=parallel_task.status,
            total_devices=parallel_task.total_devices,
            completed_devices=parallel_task.completed_devices,
            failed_devices=parallel_task.failed_devices,
            success_rate=success_rate,
            total_duration=total_duration,
            sub_tasks=parallel_task.sub_tasks,
        )


# Global instance
parallel_executor_service = ParallelExecutorService()
