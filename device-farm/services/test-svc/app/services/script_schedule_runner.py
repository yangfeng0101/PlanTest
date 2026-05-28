import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import String, select

from app.api import schedules as schedules_api
from app.api import tasks as tasks_api
from app.config import settings
from app.database import get_db_session
from app.models.database import TaskStatus as TaskStatusDB
from app.models.models import DevicePlatform, TaskCreate
from app.models.schedule import ScheduleDB, ScheduleStatus, ScriptRunScheduleMode

logger = logging.getLogger(__name__)

_runner_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def _trigger_key(schedule_db: ScheduleDB) -> str:
    trigger_at = schedule_db.next_run_at or datetime.utcnow()
    return trigger_at.isoformat()


def _task_parameters(schedule_id: str, metadata: dict, trigger_key: str) -> dict:
    parameters = dict(metadata.get("parameters") or {})
    parameters.update(
        {
            "scheduled_run": True,
            "schedule_id": schedule_id,
            "schedule_trigger_at": trigger_key,
        }
    )
    return parameters


def _task_capabilities(platform: str) -> dict:
    return {
        "automationName": "XCUITest" if platform == "ios" else "UiAutomator2",
        "noReset": True,
    }


def _record_schedule_success(schedule_db: ScheduleDB, task_id: str, now: datetime) -> None:
    metadata = dict(schedule_db.kwargs or {})
    metadata["last_task_id"] = task_id
    metadata["last_trigger_at"] = _trigger_key(schedule_db)
    metadata.pop("last_error", None)
    schedule_db.kwargs = metadata
    schedule_db.last_run_at = now
    schedule_db.total_run_count = (schedule_db.total_run_count or 0) + 1
    schedule_db.updated_at = now

    mode = ScriptRunScheduleMode(metadata.get("repeat") or ScriptRunScheduleMode.ONCE.value)
    if mode == ScriptRunScheduleMode.ONCE:
        schedule_db.executed = True
        schedule_db.status = ScheduleStatus.EXPIRED.value
        schedule_db.next_run_at = None
        return

    schedule_db.next_run_at = schedules_api.compute_next_daily_run(
        metadata.get("time_of_day") or f"{int(schedule_db.hour):02d}:{int(schedule_db.minute):02d}",
        metadata.get("timezone") or "Asia/Shanghai",
        after=now + timedelta(seconds=1),
    )


def _record_schedule_failure(schedule_db: ScheduleDB, error: str, now: datetime) -> None:
    metadata = dict(schedule_db.kwargs or {})
    metadata["last_error"] = error
    schedule_db.kwargs = metadata
    schedule_db.last_run_at = now
    schedule_db.updated_at = now

    mode = ScriptRunScheduleMode(metadata.get("repeat") or ScriptRunScheduleMode.ONCE.value)
    if mode == ScriptRunScheduleMode.ONCE:
        schedule_db.status = ScheduleStatus.DISABLED.value
        schedule_db.next_run_at = None
        return

    schedule_db.next_run_at = schedules_api.compute_next_daily_run(
        metadata.get("time_of_day") or f"{int(schedule_db.hour):02d}:{int(schedule_db.minute):02d}",
        metadata.get("timezone") or "Asia/Shanghai",
        after=now + timedelta(seconds=1),
    )


async def process_due_script_schedule(schedule_db: ScheduleDB, db) -> Optional[str]:
    metadata = schedule_db.kwargs or {}
    if metadata.get("kind") != schedules_api.SCRIPT_RUN_KIND:
        return None

    now = datetime.utcnow()
    trigger_key = _trigger_key(schedule_db)
    try:
        platform = metadata.get("device_platform")
        if platform not in {"android", "ios"}:
            platform = await schedules_api._resolve_device_platform(metadata.get("device_id", ""))

        task = TaskCreate(
            script_id=metadata.get("script_id", ""),
            device_id=metadata.get("device_id"),
            device_platform=DevicePlatform.IOS if platform == "ios" else DevicePlatform.ANDROID,
            device_capabilities=_task_capabilities(platform),
            parameters=_task_parameters(schedule_db.id, metadata, trigger_key),
        )
        task_db = await tasks_api.create_task_record(task, db, enqueue=False)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        _record_schedule_failure(schedule_db, detail, now)
        await db.commit()
        logger.warning("Script schedule %s failed: %s", schedule_db.id, detail)
        return None
    except Exception as exc:
        error = str(exc)
        _record_schedule_failure(schedule_db, error, now)
        await db.commit()
        logger.exception("Script schedule %s failed", schedule_db.id)
        return None

    _record_schedule_success(schedule_db, task_db.id, now)
    await db.commit()

    try:
        tasks_api.execute_test_task.apply_async(args=[task_db.id], task_id=task_db.id)
    except Exception as exc:
        error = f"Failed to enqueue task: {exc}"
        logger.exception("Failed to enqueue scheduled task %s", task_db.id)
        task_db.status = TaskStatusDB.FAILED
        task_db.finished_at = datetime.utcnow()
        task_db.error = error
        metadata = dict(schedule_db.kwargs or {})
        metadata["last_error"] = error
        schedule_db.kwargs = metadata
        await db.commit()

    logger.info("Script schedule %s created task %s", schedule_db.id, task_db.id)
    return task_db.id


async def run_due_script_schedules(limit: int = 20) -> int:
    now = datetime.utcnow()
    async with get_db_session() as db:
        result = await db.execute(
            select(ScheduleDB)
            .where(
                ScheduleDB.task == schedules_api.SCRIPT_RUN_TASK_NAME,
                ScheduleDB.status.cast(String).in_([ScheduleStatus.ENABLED.value, ScheduleStatus.ENABLED.name]),
                ScheduleDB.next_run_at.is_not(None),
                ScheduleDB.next_run_at <= now,
            )
            .order_by(ScheduleDB.next_run_at.asc())
            .limit(limit)
        )
        schedules = result.scalars().all()

        created = 0
        for schedule_db in schedules:
            task_id = await process_due_script_schedule(schedule_db, db)
            if task_id:
                created += 1
        return created


async def _runner_loop() -> None:
    assert _stop_event is not None
    interval = max(1, int(getattr(settings, "SCRIPT_SCHEDULE_POLL_INTERVAL_SECONDS", 10)))
    while not _stop_event.is_set():
        try:
            await run_due_script_schedules()
        except Exception:
            logger.exception("Script schedule runner tick failed")

        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def start_script_schedule_runner() -> None:
    global _runner_task, _stop_event
    if _runner_task and not _runner_task.done():
        return

    _stop_event = asyncio.Event()
    _runner_task = asyncio.create_task(_runner_loop(), name="script-schedule-runner")
    logger.info("Script schedule runner started")


async def stop_script_schedule_runner() -> None:
    global _runner_task, _stop_event
    if not _runner_task:
        return

    if _stop_event:
        _stop_event.set()
    _runner_task.cancel()
    try:
        await _runner_task
    except asyncio.CancelledError:
        pass
    finally:
        _runner_task = None
        _stop_event = None
        logger.info("Script schedule runner stopped")
