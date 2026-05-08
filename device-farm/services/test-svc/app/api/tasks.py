# Tasks API Router (Database-backed)
import asyncio
import json
import threading
from datetime import datetime
from typing import Optional, List, Dict, Set
import httpx
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.database import get_db, get_db_session
from app.models.models import (
    Task,
    TaskCreate,
    TaskListResponse,
    TaskStatus,
    TaskLogEntry,
)
from app.models.database import TaskDB, TaskLogDB, ScriptDB, TaskStatus as TaskStatusDB
from app.tasks.executor import execute_test_task
from app.config import settings
from app.auth import verify_api_key
from app.services.parallel_executor import (
    parallel_executor_service,
    ParallelTaskCreate,
    ParallelTask,
    ParallelTaskSummary,
    ParallelTaskStatus,
)
from app.services.result_aggregator import (
    result_aggregator_service,
    AggregatedResult,
    ParallelReportSummary,
)
from shared.websocket_manager import BaseConnectionManager
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

_async_loop = None
_async_loop_thread = None
_async_loop_lock = threading.Lock()


async def _get_device(device_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{settings.DEVICE_SERVICE_URL}/api/v1/devices/{device_id}")

    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Device service error: {response.text}")
    return response.json()


async def _occupy_device(device_id: str, user_id: str):
    device = await _get_device(device_id)
    if device.get("status") != "online":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Device is occupied or unavailable",
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.DEVICE_SERVICE_URL}/api/v1/devices/{device_id}/occupy",
            json={"user_id": user_id},
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=response.json().get("detail", "Failed to occupy device"),
        )


def _normalize_device_platform(device: dict) -> str:
    os_name = str(device.get("os") or "").lower()
    if os_name in {"android", "harmony", "harmonyos"}:
        return "android"
    if os_name == "ios":
        return "ios"
    return os_name


def _device_supports_automation(device: dict) -> bool:
    capabilities = device.get("capabilities") or {}
    if not isinstance(capabilities, dict):
        return False
    return bool(capabilities.get("automation"))


async def _validate_task_device(device_id: str, requested_platform: str) -> dict:
    device = await _get_device(device_id)
    if device.get("status") != "online":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Device is occupied or unavailable",
        )

    actual_platform = _normalize_device_platform(device)
    if actual_platform != requested_platform:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Device platform mismatch: device is {actual_platform or 'unknown'}, task requested {requested_platform}",
        )

    if requested_platform == "ios" and not settings.IOS_APPIUM_HOST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IOS_APPIUM_HOST is not configured",
        )

    if not _device_supports_automation(device):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Automation is not supported by this device connection",
        )

    return device


async def _release_device(device_id: str):
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{settings.DEVICE_SERVICE_URL}/api/v1/devices/{device_id}/release")

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to release device: {response.text}",
        )


async def _release_device_best_effort(device_id: str):
    try:
        await _release_device(device_id)
    except Exception as exc:
        logger.warning("Failed to release device %s during cancellation: %s", device_id, exc)


# Convert between enum types
def _to_pydantic_status(db_status: TaskStatusDB) -> TaskStatus:
    return TaskStatus(db_status.value)


def _to_db_status(pydantic_status: TaskStatus) -> TaskStatusDB:
    return TaskStatusDB(pydantic_status.value)


def _task_db_to_pydantic(task_db: TaskDB) -> Task:
    """Convert database model to Pydantic model"""
    return Task(
        id=task_db.id,
        script_id=task_db.script_id,
        device_id=task_db.device_id,
        device_platform=task_db.device_platform.value,
        device_capabilities=task_db.device_capabilities or {},
        parameters=task_db.parameters or {},
        status=_to_pydantic_status(task_db.status),
        created_at=task_db.created_at,
        started_at=task_db.started_at,
        finished_at=task_db.finished_at,
        result=task_db.result,
        error=task_db.error,
        log_file=task_db.log_file,
        report_id=task_db.report_id,
    )


# WebSocket connection manager for logs
class ConnectionManager(BaseConnectionManager):
    """WebSocket connection manager for task logs with per-task subscription"""

    def __init__(self):
        super().__init__(
            connection_timeout=getattr(settings, 'WS_CONNECTION_TIMEOUT', 300),
            heartbeat_interval=getattr(settings, 'WS_HEARTBEAT_INTERVAL', 30),
            cleanup_interval=60,
        )
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        """Accept new WebSocket connection for a specific task"""
        await super().connect(websocket)

        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
        self.active_connections[task_id].append(websocket)

        logger.info(f"WebSocket connected for task {task_id}. Total connections: {self._get_total_connections()}")

    def disconnect(self, websocket: WebSocket, task_id: str):
        """Handle WebSocket disconnection for a task"""
        if task_id in self.active_connections:
            if websocket in self.active_connections[task_id]:
                self.active_connections[task_id].remove(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

        # Remove from base connection tracking
        self._connections.discard(websocket)
        self._connection_times.pop(websocket, None)
        self._last_heartbeat.pop(websocket, None)

        logger.info(f"WebSocket disconnected from task {task_id}. Total connections: {self._get_total_connections()}")

    def _get_total_connections(self) -> int:
        """Get total number of active connections"""
        return sum(len(conns) for conns in self.active_connections.values())

    async def broadcast_log(self, task_id: str, log_entry: TaskLogEntry):
        """Broadcast log entry to all connections for a task"""
        if task_id not in self.active_connections:
            return

        disconnected = []
        for connection in self.active_connections[task_id]:
            try:
                await connection.send_json(log_entry.model_dump())
                self._last_heartbeat[connection] = datetime.utcnow()
            except Exception as e:
                logger.warning(f"Failed to send log to connection: {e}")
                disconnected.append((connection, task_id))

        # Clean up failed connections
        for conn, tid in disconnected:
            self.disconnect(conn, tid)

    def get_connection_stats(self) -> dict:
        """Get connection statistics for monitoring"""
        stats = super().get_connection_stats()
        stats["tasks_with_connections"] = len(self.active_connections)
        stats["connections_per_task"] = {
            task_id: len(conns)
            for task_id, conns in self.active_connections.items()
        }
        return stats


manager = ConnectionManager()


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[TaskStatus] = None,
    script_id: Optional[str] = None,
    device_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """List all tasks with pagination"""
    # Build query
    query = select(TaskDB)

    # Apply filters
    conditions = []
    if status:
        conditions.append(TaskDB.status == _to_db_status(status))
    if script_id:
        conditions.append(TaskDB.script_id == script_id)
    if device_id:
        conditions.append(TaskDB.device_id == device_id)

    if conditions:
        query = query.where(and_(*conditions))

    # Count total
    count_query = select(func.count()).select_from(TaskDB)
    if conditions:
        count_query = count_query.where(and_(*conditions))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sort by created_at descending and paginate
    query = query.order_by(TaskDB.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    task_dbs = result.scalars().all()

    # Convert to Pydantic models
    items = [_task_db_to_pydantic(t) for t in task_dbs]

    return TaskListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 1,
    )


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(verify_api_key),
):
    """Create a new test task"""
    if not task.device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="device_id is required for real device execution",
        )

    script_result = await db.execute(select(ScriptDB).where(ScriptDB.id == task.script_id))
    script_db = script_result.scalar_one_or_none()
    if not script_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Script {task.script_id} not found",
        )
    if getattr(script_db.script_type, "value", script_db.script_type) != "python":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Python scripts are supported",
        )

    await _validate_task_device(task.device_id, task.device_platform.value)
    await _occupy_device(task.device_id, user_id or "test-svc")

    # Create database model
    try:
        task_db = TaskDB(
            script_id=task.script_id,
            device_id=task.device_id,
            device_platform=task.device_platform.value,
            device_capabilities=task.device_capabilities,
            parameters=task.parameters,
            status=TaskStatusDB.PENDING,
        )

        db.add(task_db)
        await db.flush()
        await db.refresh(task_db)
    except Exception:
        await _release_device(task.device_id)
        raise

    # Commit before queueing so workers cannot consume a task that is not visible yet.
    await db.commit()

    try:
        execute_test_task.apply_async(args=[task_db.id], task_id=task_db.id)
    except Exception as exc:
        logger.exception("Failed to enqueue task %s", task_db.id)
        task_db.status = TaskStatusDB.FAILED
        task_db.finished_at = datetime.utcnow()
        task_db.error = f"Failed to enqueue task: {exc}"
        await db.commit()
        await _release_device(task.device_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to enqueue task",
        )

    return _task_db_to_pydantic(task_db)


@router.get("/{task_id}", response_model=Task)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Get task status and details"""
    query = select(TaskDB).where(TaskDB.id == task_id)
    result = await db.execute(query)
    task_db = result.scalar_one_or_none()

    if not task_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    return _task_db_to_pydantic(task_db)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Cancel a running task"""
    query = select(TaskDB).where(TaskDB.id == task_id)
    result = await db.execute(query)
    task_db = result.scalar_one_or_none()

    if not task_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    if task_db.status in {TaskStatusDB.RUNNING, TaskStatusDB.PENDING}:
        from app.tasks.executor import celery_app

        await save_task_log(db, task_id, "WARN", "User requested cancellation")
        celery_app.control.revoke(task_id, terminate=task_db.status == TaskStatusDB.RUNNING)
        task_db.status = TaskStatusDB.CANCELLED
        task_db.finished_at = datetime.utcnow()
        await save_task_log(db, task_id, "WARN", "Task cancellation acknowledged")
        await db.flush()
        await db.commit()
        if task_db.device_id:
            await _release_device_best_effort(task_db.device_id)
            async with get_db_session() as release_log_db:
                await save_task_log(release_log_db, task_id, "INFO", "Device released")

    return None


@router.get("/{task_id}/logs", response_model=List[TaskLogEntry])
async def get_task_logs(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000),
    _: str = Depends(verify_api_key),
):
    """Get task execution logs"""
    query = (
        select(TaskLogDB)
        .where(TaskLogDB.task_id == task_id)
        .order_by(TaskLogDB.timestamp.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    log_dbs = result.scalars().all()

    return [
        TaskLogEntry(
            timestamp=log.timestamp,
            level=log.level,
            message=log.message,
            event_type=log.event_type,
            line_number=log.line_number,
        )
        for log in reversed(log_dbs)
    ]


@router.websocket("/{task_id}/logs")
async def task_logs_websocket(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time task logs"""
    await manager.connect(websocket, task_id)

    try:
        while True:
            # Keep connection alive and wait for client messages
            data = await websocket.receive_text()

            # Handle different message types
            try:
                message = json.loads(data)
                msg_type = message.get("type")

                if msg_type == "ping":
                    # Client sends ping, respond with pong
                    await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
                elif msg_type == "pong":
                    # Client responds to our ping, update heartbeat
                    manager.handle_pong(websocket)
            except json.JSONDecodeError:
                # Legacy: simple ping string
                if data == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})

    except WebSocketDisconnect:
        manager.disconnect(websocket, task_id)
    except Exception as e:
        logger.warning(f"WebSocket error for task {task_id}: {e}")
        manager.disconnect(websocket, task_id)


async def send_task_log(
    task_id: str,
    level: str,
    message: str,
    event_type: Optional[str] = None,
    line_number: Optional[int] = None,
):
    """Send log entry to all connected WebSocket clients"""
    log_entry = TaskLogEntry(level=level, message=message, event_type=event_type, line_number=line_number)
    await manager.broadcast_log(task_id, log_entry)


async def save_task_log(
    db: AsyncSession,
    task_id: str,
    level: str,
    message: str,
    event_type: Optional[str] = None,
    line_number: Optional[int] = None,
):
    """Save log to database and broadcast to WebSocket clients"""
    log_db = TaskLogDB(
        task_id=task_id,
        level=level,
        message=message,
        event_type=event_type,
        line_number=line_number,
    )
    db.add(log_db)
    await db.flush()
    await send_task_log(task_id, level, message, event_type=event_type, line_number=line_number)


# Helper functions for task status updates (used by executor)
async def update_task_status_db(
    task_id: str,
    status: TaskStatus,
    **kwargs,
) -> Optional[Task]:
    """Update task status in database"""
    from app.database import get_db_session

    async with get_db_session() as db:
        query = select(TaskDB).where(TaskDB.id == task_id)
        result = await db.execute(query)
        task_db = result.scalar_one_or_none()

        if not task_db:
            return None

        task_db.status = _to_db_status(status)

        for key, value in kwargs.items():
            if hasattr(task_db, key):
                setattr(task_db, key, value)

        await db.flush()
        await db.refresh(task_db)

        return _task_db_to_pydantic(task_db)


def _run_async(coro):
    """Run async coroutine from sync worker code on a stable event loop."""
    global _async_loop, _async_loop_thread

    with _async_loop_lock:
        if _async_loop is None or not _async_loop.is_running():
            _async_loop = asyncio.new_event_loop()

            def run_loop():
                asyncio.set_event_loop(_async_loop)
                _async_loop.run_forever()

            _async_loop_thread = threading.Thread(
                target=run_loop,
                name="test-svc-sync-async-loop",
                daemon=True,
            )
            _async_loop_thread.start()

        loop = _async_loop

    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


def update_task_status(task_id: str, status: TaskStatus, **kwargs) -> Optional[Task]:
    """Sync wrapper for update_task_status_db"""
    return _run_async(update_task_status_db(task_id, status, **kwargs))


def get_task_by_id(task_id: str) -> Optional[Task]:
    """Get task by ID (sync wrapper)"""
    return _run_async(_get_task_by_id_async(task_id))


async def _get_task_by_id_async(task_id: str) -> Optional[Task]:
    """Get task by ID"""
    from app.database import get_db_session

    async with get_db_session() as db:
        query = select(TaskDB).where(TaskDB.id == task_id)
        result = await db.execute(query)
        task_db = result.scalar_one_or_none()

        if not task_db:
            return None

        return _task_db_to_pydantic(task_db)


# ============ Parallel Execution Endpoints ============

@router.post("/parallel", response_model=ParallelTask, status_code=status.HTTP_201_CREATED)
async def create_parallel_task(
    request: ParallelTaskCreate,
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_api_key),
):
    """Create a parallel execution task for multiple devices

    This endpoint allows executing the same script across multiple devices simultaneously.

    Args:
        request: Parallel task configuration including:
            - script_id: The script to execute
            - device_ids: Specific device IDs (for SPECIFIC strategy)
            - selection_strategy: ALL, RANDOM, or SPECIFIC
            - max_devices: Number of devices to select (for RANDOM)
            - max_concurrency: Maximum concurrent executions (default 5)
            - parameters: Execution parameters

    Returns:
        Created parallel task with sub-tasks for each device
    """
    try:
        parallel_task = await parallel_executor_service.create_parallel_task(request)

        # Start execution in background
        background_tasks.add_task(
            parallel_executor_service.execute_parallel_task,
            parallel_task.id
        )

        return parallel_task
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/parallel/{parallel_task_id}", response_model=ParallelTask)
async def get_parallel_task(
    parallel_task_id: str,
    _: str = Depends(verify_api_key),
):
    """Get parallel task status and details

    Args:
        parallel_task_id: ID of the parallel task

    Returns:
        Parallel task with all sub-task statuses
    """
    parallel_task = await parallel_executor_service.get_parallel_task(parallel_task_id)

    if not parallel_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parallel task {parallel_task_id} not found"
        )

    return parallel_task


@router.get("/parallel/{parallel_task_id}/summary", response_model=ParallelTaskSummary)
async def get_parallel_task_summary(
    parallel_task_id: str,
    _: str = Depends(verify_api_key),
):
    """Get summary of parallel task execution

    Returns aggregated metrics including:
    - Success rate
    - Total duration
    - Device-level results

    Args:
        parallel_task_id: ID of the parallel task

    Returns:
        Summary with aggregated metrics
    """
    summary = await parallel_executor_service.get_parallel_task_summary(parallel_task_id)

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parallel task {parallel_task_id} not found"
        )

    return summary


@router.get("/parallel", response_model=List[ParallelTask])
async def list_parallel_tasks(
    status_filter: Optional[ParallelTaskStatus] = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: str = Depends(verify_api_key),
):
    """List parallel execution tasks

    Args:
        status_filter: Filter by status (pending, running, completed, failed, partial)
        limit: Maximum number of tasks to return
        offset: Offset for pagination

    Returns:
        List of parallel tasks
    """
    return await parallel_executor_service.list_parallel_tasks(
        status=status_filter,
        limit=limit,
        offset=offset
    )


@router.delete("/parallel/{parallel_task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_parallel_task(
    parallel_task_id: str,
    _: str = Depends(verify_api_key),
):
    """Cancel a running parallel task

    This will attempt to cancel all pending/running sub-tasks.

    Args:
        parallel_task_id: ID of the parallel task to cancel
    """
    from app.database import get_db_session

    async with get_db_session() as db:
        parallel_task = await parallel_executor_service.get_parallel_task(parallel_task_id)

        if not parallel_task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parallel task {parallel_task_id} not found"
            )

        if parallel_task.status == ParallelTaskStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot cancel completed task"
            )

        # Cancel all running/pending sub-tasks
        from app.tasks.executor import celery_app

        for sub_task in parallel_task.sub_tasks:
            if sub_task.status in ["pending", "running"]:
                try:
                    celery_app.control.revoke(sub_task.task_id, terminate=True)
                except Exception:
                    pass

        # Update status in database
        from app.services.parallel_task_service import parallel_task_service
        from app.models.parallel_task_db import ParallelTaskStatus as DBParallelTaskStatus

        await parallel_task_service.update_task_status(
            db,
            parallel_task_id,
            status=DBParallelTaskStatus.FAILED,
            finished_at=datetime.utcnow()
        )

    return None


# ============ Result Aggregation Endpoints ============

@router.post("/parallel/{parallel_task_id}/aggregate", response_model=AggregatedResult)
async def aggregate_parallel_results(
    parallel_task_id: str,
    _: str = Depends(verify_api_key),
):
    """Aggregate results from parallel execution

    This endpoint collects and aggregates results from all sub-tasks
    in a parallel execution, generating a comprehensive summary.

    Args:
        parallel_task_id: ID of the parallel task

    Returns:
        Aggregated result with all device results and metrics
    """
    try:
        aggregated = await result_aggregator_service.aggregate_results(parallel_task_id)
        return aggregated
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/parallel/{parallel_task_id}/report", response_model=ParallelReportSummary)
async def get_parallel_report(
    parallel_task_id: str,
    _: str = Depends(verify_api_key),
):
    """Get comprehensive report summary for parallel execution

    Returns aggregated metrics including:
    - Device success rate
    - Test success rate
    - Failed device list with details
    - Status breakdown

    Args:
        parallel_task_id: ID of the parallel task

    Returns:
        Summary report with all aggregated metrics
    """
    summary = result_aggregator_service.generate_report_summary(parallel_task_id)

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parallel task {parallel_task_id} not found"
        )

    return summary


@router.get("/parallel/{parallel_task_id}/devices/{device_id}/logs", response_model=List[str])
async def get_device_execution_logs(
    parallel_task_id: str,
    device_id: str,
    _: str = Depends(verify_api_key),
):
    """Get detailed logs for a specific device in parallel execution

    Args:
        parallel_task_id: ID of the parallel task
        device_id: ID of the device

    Returns:
        List of log entries for the device
    """
    logs = await result_aggregator_service.get_device_logs(parallel_task_id, device_id)

    if logs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parallel task {parallel_task_id} or device {device_id} not found"
        )

    return logs


@router.get("/aggregated", response_model=List[AggregatedResult])
async def list_aggregated_results(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: str = Depends(verify_api_key),
):
    """List aggregated results from parallel executions

    Args:
        limit: Maximum number of results to return
        offset: Offset for pagination

    Returns:
        List of aggregated results
    """
    return result_aggregator_service.list_aggregated_results(
        limit=limit,
        offset=offset
    )


@router.get("/aggregated/{aggregated_result_id}", response_model=AggregatedResult)
async def get_aggregated_result(
    aggregated_result_id: str,
    _: str = Depends(verify_api_key),
):
    """Get aggregated result by ID

    Args:
        aggregated_result_id: ID of the aggregated result

    Returns:
        Aggregated result with all details
    """
    result = result_aggregator_service.get_aggregated_result(aggregated_result_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aggregated result {aggregated_result_id} not found"
        )

    return result


@router.get("/ws/stats")
async def get_websocket_stats(
    _: str = Depends(verify_api_key),
):
    """Get WebSocket connection statistics

    Returns information about active WebSocket connections including:
    - Total number of connections
    - Connections per task
    - Connection ages

    Returns:
        Connection statistics
    """
    return manager.get_connection_stats()
