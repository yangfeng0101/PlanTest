# Tasks API Router (Database-backed)
import asyncio
import json
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.models import (
    Task,
    TaskCreate,
    TaskListResponse,
    TaskStatus,
    TaskLogEntry,
)
from app.models.database import TaskDB, TaskLogDB, TaskStatus as TaskStatusDB
from app.tasks.executor import execute_test_task
from app.config import settings
from app.auth import verify_api_key

router = APIRouter()


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
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
        self.active_connections[task_id].append(websocket)

    def disconnect(self, websocket: WebSocket, task_id: str):
        if task_id in self.active_connections:
            if websocket in self.active_connections[task_id]:
                self.active_connections[task_id].remove(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

    async def broadcast_log(self, task_id: str, log_entry: TaskLogEntry):
        if task_id in self.active_connections:
            for connection in self.active_connections[task_id]:
                try:
                    await connection.send_json(log_entry.model_dump())
                except Exception:
                    pass


manager = ConnectionManager()


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[TaskStatus] = None,
    script_id: Optional[str] = None,
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
    _: str = Depends(verify_api_key),
):
    """Create a new test task"""
    # Create database model
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

    # Queue the task for execution
    execute_test_task.delay(task_db.id)

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

    if task_db.status == TaskStatusDB.RUNNING:
        # Revoke Celery task
        from app.tasks.executor import celery_app

        celery_app.control.revoke(task_id, terminate=True)
        task_db.status = TaskStatusDB.CANCELLED
        task_db.finished_at = datetime.utcnow()

    elif task_db.status == TaskStatusDB.PENDING:
        task_db.status = TaskStatusDB.CANCELLED

    await db.flush()

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
        TaskLogEntry(timestamp=log.timestamp, level=log.level, message=log.message)
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

            # Client can send ping to keep connection alive
            if data == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket, task_id)
    except Exception:
        manager.disconnect(websocket, task_id)


async def send_task_log(task_id: str, level: str, message: str):
    """Send log entry to all connected WebSocket clients"""
    log_entry = TaskLogEntry(level=level, message=message)
    await manager.broadcast_log(task_id, log_entry)


async def save_task_log(db: AsyncSession, task_id: str, level: str, message: str):
    """Save log to database and broadcast to WebSocket clients"""
    log_db = TaskLogDB(
        task_id=task_id,
        level=level,
        message=message,
    )
    db.add(log_db)
    await db.flush()
    await send_task_log(task_id, level, message)


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
    """Run async coroutine, handling existing event loops"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        return asyncio.run(coro)

    # There's a running loop, need to run in a new thread
    # This is needed when called from Celery workers that have their own event loop
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, coro)
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
