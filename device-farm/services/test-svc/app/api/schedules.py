# Schedules API Router
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, HTTPException, Query, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, String

from app.models.schedule import (
    Schedule,
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleListResponse,
    ScheduleEnableRequest,
    ScheduleType,
    ScheduleStatus,
    IntervalUnit,
    ScriptRunSchedule,
    ScriptRunScheduleCreate,
    ScriptRunScheduleListResponse,
    ScriptRunScheduleMode,
    ScriptRunScheduleUpdate,
)
from app.database import get_db
from app.auth import verify_api_key
from app.api import tasks as tasks_api
from app.tasks.scheduler import (
    add_crontab_schedule,
    add_interval_schedule,
    add_onetime_schedule,
    remove_schedule as remove_celery_schedule,
)

router = APIRouter()

SCRIPT_RUN_KIND = "script_run"
SCRIPT_RUN_TASK_NAME = "script_run"


def _utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


def _load_timezone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timezone: {tz_name}",
        ) from exc


def _parse_time_of_day(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="time_of_day must be HH:MM",
        ) from exc

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="time_of_day must be a valid HH:MM value",
        )
    return hour, minute


def compute_next_daily_run(time_of_day: str, timezone_name: str, after: Optional[datetime] = None) -> datetime:
    """Return the next daily run time as naive UTC."""
    hour, minute = _parse_time_of_day(time_of_day)
    tz = _load_timezone(timezone_name)
    after_utc = _aware_utc(after or datetime.utcnow())
    local_after = after_utc.astimezone(tz)
    candidate = local_after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_after:
        candidate = candidate + timedelta(days=1)
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


def _script_run_kwargs(
    data: ScriptRunScheduleCreate,
    device_platform: str,
    *,
    existing: Optional[dict] = None,
) -> dict:
    metadata = dict(existing or {})
    metadata.update(
        {
            "kind": SCRIPT_RUN_KIND,
            "script_id": data.script_id,
            "device_id": data.device_id,
            "device_platform": device_platform,
            "parameters": data.parameters or {},
            "timezone": data.timezone,
            "repeat": data.schedule_mode.value,
            "time_of_day": data.time_of_day,
        }
    )
    metadata.pop("last_error", None)
    metadata.pop("last_task_id", None)
    metadata.pop("last_trigger_at", None)
    return metadata


async def _resolve_device_platform(device_id: str) -> str:
    device = await tasks_api._get_device(device_id)
    device_status = str(device.get("status") or "").lower()
    if device_status not in {"online", "busy"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Device is offline or unavailable",
        )
    platform = tasks_api._normalize_device_platform(device)
    if platform not in {"android", "ios"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported device platform: {platform or 'unknown'}",
        )
    if platform == "ios" and not tasks_api.settings.IOS_APPIUM_HOST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IOS_APPIUM_HOST is not configured",
        )
    if not tasks_api._device_supports_automation(device):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Automation is not supported by this device connection",
        )
    return platform


def _apply_script_run_schedule(schedule_db, data: ScriptRunScheduleCreate, device_platform: str) -> None:
    now = datetime.utcnow()
    if data.schedule_mode == ScriptRunScheduleMode.ONCE:
        run_at = _utc_naive(data.run_at)
        if run_at <= now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="run_at must be in the future",
            )
        schedule_db.schedule_type = ScheduleType.ONETIME
        schedule_db.run_at = run_at
        schedule_db.next_run_at = run_at
        schedule_db.executed = False
        schedule_db.minute = "*"
        schedule_db.hour = "*"
        schedule_db.day_of_month = "*"
        schedule_db.month_of_year = "*"
        schedule_db.day_of_week = "*"
    else:
        hour, minute = _parse_time_of_day(data.time_of_day)
        schedule_db.schedule_type = ScheduleType.CRONTAB
        schedule_db.run_at = None
        schedule_db.next_run_at = compute_next_daily_run(data.time_of_day, data.timezone)
        schedule_db.executed = False
        schedule_db.minute = str(minute)
        schedule_db.hour = str(hour)
        schedule_db.day_of_month = "*"
        schedule_db.month_of_year = "*"
        schedule_db.day_of_week = "*"

    schedule_db.task = SCRIPT_RUN_TASK_NAME
    schedule_db.args = []
    schedule_db.kwargs = _script_run_kwargs(data, device_platform, existing=schedule_db.kwargs or {})


def _task_status_value(task_db) -> Optional[str]:
    if not task_db:
        return None
    return str(getattr(task_db.status, "value", task_db.status))


def _db_to_script_run(schedule_db, last_task=None) -> ScriptRunSchedule:
    metadata = schedule_db.kwargs or {}
    raw_status = getattr(schedule_db.status, "value", schedule_db.status)
    normalized_status = str(raw_status).lower()
    last_task_status = _task_status_value(last_task)
    last_task_error = getattr(last_task, "error", None) if last_task else None
    repeat = metadata.get("repeat") or (
        ScriptRunScheduleMode.ONCE.value if schedule_db.schedule_type == ScheduleType.ONETIME else ScriptRunScheduleMode.DAILY.value
    )
    return ScriptRunSchedule(
        id=schedule_db.id,
        name=schedule_db.name,
        script_id=metadata.get("script_id", ""),
        device_id=metadata.get("device_id", ""),
        device_platform=metadata.get("device_platform"),
        schedule_mode=ScriptRunScheduleMode(repeat),
        run_at=schedule_db.run_at,
        time_of_day=metadata.get("time_of_day") or (
            f"{int(schedule_db.hour):02d}:{int(schedule_db.minute):02d}"
            if schedule_db.schedule_type == ScheduleType.CRONTAB
            and str(schedule_db.hour).isdigit()
            and str(schedule_db.minute).isdigit()
            else None
        ),
        timezone=metadata.get("timezone") or "Asia/Shanghai",
        parameters=metadata.get("parameters") or {},
        enabled=normalized_status == ScheduleStatus.ENABLED.value,
        status=ScheduleStatus(normalized_status),
        next_run_at=schedule_db.next_run_at,
        last_run_at=schedule_db.last_run_at,
        total_run_count=schedule_db.total_run_count or 0,
        executed=bool(schedule_db.executed),
        last_task_id=metadata.get("last_task_id"),
        last_task_status=last_task_status,
        last_task_error=last_task_error,
        last_task_finished_at=getattr(last_task, "finished_at", None) if last_task else None,
        last_error=metadata.get("last_error") or (
            last_task_error if last_task_status in {"failed", "cancelled"} else None
        ),
        created_at=schedule_db.created_at,
        updated_at=schedule_db.updated_at,
    )


def _script_run_query():
    from app.models.schedule import ScheduleDB

    return select(ScheduleDB).where(ScheduleDB.task == SCRIPT_RUN_TASK_NAME)


def _status_matches(column, status_value: ScheduleStatus):
    return column.cast(String).in_([status_value.value, status_value.name])


async def _load_last_tasks_for_schedules(schedules_db, db: AsyncSession) -> dict:
    from app.models.database import TaskDB

    task_ids = [
        (schedule_db.kwargs or {}).get("last_task_id")
        for schedule_db in schedules_db
        if (schedule_db.kwargs or {}).get("last_task_id")
    ]
    if not task_ids:
        return {}

    result = await db.execute(select(TaskDB).where(TaskDB.id.in_(task_ids)))
    return {task.id: task for task in result.scalars().all()}


async def _db_to_script_run_with_task(schedule_db, db: AsyncSession) -> ScriptRunSchedule:
    task_map = await _load_last_tasks_for_schedules([schedule_db], db)
    return _db_to_script_run(schedule_db, task_map.get((schedule_db.kwargs or {}).get("last_task_id")))


@router.get("", response_model=ScheduleListResponse)
async def list_schedules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    schedule_type: Optional[ScheduleType] = None,
    status: Optional[ScheduleStatus] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """
    Get all schedules with pagination.

    - **page**: Page number (1-indexed)
    - **page_size**: Items per page
    - **schedule_type**: Filter by schedule type
    - **status**: Filter by status
    - **search**: Search in name and task
    """
    from app.models.schedule import ScheduleDB

    query = select(ScheduleDB)

    # Apply filters
    if schedule_type:
        query = query.where(ScheduleDB.schedule_type == schedule_type)

    if status:
        query = query.where(ScheduleDB.status == status)

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            ScheduleDB.name.ilike(search_pattern) |
            ScheduleDB.task.ilike(search_pattern)
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Order by created_at descending
    query = query.order_by(ScheduleDB.created_at.desc())

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    schedules_db = result.scalars().all()

    # Convert to Pydantic models
    items = [_db_to_pydantic(s) for s in schedules_db]

    return ScheduleListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 1
    )


@router.post("", response_model=Schedule, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    schedule_create: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """
    Create a new schedule.

    - **name**: Unique name for the schedule
    - **task**: Celery task name to execute
    - **schedule_type**: Type of schedule (crontab/interval/onetime)
    - **crontab**: Required if schedule_type is CRONTAB
    - **interval**: Required if schedule_type is INTERVAL
    - **onetime**: Required if schedule_type is ONETIME
    """
    from app.models.schedule import ScheduleDB

    # Check if name already exists
    existing = await db.execute(
        select(ScheduleDB).where(ScheduleDB.name == schedule_create.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Schedule with name '{schedule_create.name}' already exists"
        )

    # Create database model
    schedule_db = ScheduleDB(
        id=str(__import__('uuid').uuid4()),
        name=schedule_create.name,
        task=schedule_create.task,
        schedule_type=schedule_create.schedule_type,
        args=schedule_create.args,
        kwargs=schedule_create.kwargs,
        description=schedule_create.description,
        status=ScheduleStatus.ENABLED if schedule_create.enabled else ScheduleStatus.DISABLED,
    )

    # Set type-specific fields
    if schedule_create.schedule_type == ScheduleType.CRONTAB:
        schedule_db.minute = schedule_create.crontab.minute
        schedule_db.hour = schedule_create.crontab.hour
        schedule_db.day_of_month = schedule_create.crontab.day_of_month
        schedule_db.month_of_year = schedule_create.crontab.month_of_year
        schedule_db.day_of_week = schedule_create.crontab.day_of_week

        # Add to Celery Beat if enabled
        if schedule_create.enabled:
            add_crontab_schedule(
                name=schedule_create.name,
                task=schedule_create.task,
                minute=schedule_create.crontab.minute,
                hour=schedule_create.crontab.hour,
                day_of_month=schedule_create.crontab.day_of_month,
                month_of_year=schedule_create.crontab.month_of_year,
                day_of_week=schedule_create.crontab.day_of_week,
                args=schedule_create.args,
                kwargs=schedule_create.kwargs,
            )

    elif schedule_create.schedule_type == ScheduleType.INTERVAL:
        schedule_db.interval_every = schedule_create.interval.every
        schedule_db.interval_unit = schedule_create.interval.unit

        # Add to Celery Beat if enabled
        if schedule_create.enabled:
            add_interval_schedule(
                name=schedule_create.name,
                task=schedule_create.task,
                every=schedule_create.interval.every,
                unit=schedule_create.interval.unit,
                args=schedule_create.args,
                kwargs=schedule_create.kwargs,
            )

    elif schedule_create.schedule_type == ScheduleType.ONETIME:
        schedule_db.run_at = schedule_create.onetime.run_at
        schedule_db.executed = False

        # Calculate next run time
        schedule_db.next_run_at = schedule_create.onetime.run_at

        # Add one-time schedule if enabled
        if schedule_create.enabled:
            add_onetime_schedule(
                name=schedule_create.name,
                task=schedule_create.task,
                run_at=schedule_create.onetime.run_at,
                args=schedule_create.args,
                kwargs=schedule_create.kwargs,
            )

    # Save to database
    db.add(schedule_db)
    await db.commit()
    await db.refresh(schedule_db)

    return _db_to_pydantic(schedule_db)


@router.get("/script-runs", response_model=ScriptRunScheduleListResponse)
async def list_script_run_schedules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[ScheduleStatus] = Query(None, alias="status"),
    script_id: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """List product-level script run schedules."""
    from app.models.schedule import ScheduleDB

    query = _script_run_query()
    if status_filter:
        query = query.where(_status_matches(ScheduleDB.status, status_filter))
    if script_id:
        query = query.where(ScheduleDB.kwargs["script_id"].as_string() == script_id)
    if search:
        pattern = f"%{search}%"
        query = query.where(ScheduleDB.name.ilike(pattern))

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(
        query.order_by(ScheduleDB.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    schedules_db = result.scalars().all()
    task_map = await _load_last_tasks_for_schedules(schedules_db, db)

    return ScriptRunScheduleListResponse(
        items=[
            _db_to_script_run(item, task_map.get((item.kwargs or {}).get("last_task_id")))
            for item in schedules_db
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 1,
    )


@router.post("/script-runs", response_model=ScriptRunSchedule, status_code=status.HTTP_201_CREATED)
async def create_script_run_schedule(
    schedule_create: ScriptRunScheduleCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Create a script run schedule."""
    from app.models.schedule import ScheduleDB

    existing = await db.execute(select(ScheduleDB).where(ScheduleDB.name == schedule_create.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Schedule with name '{schedule_create.name}' already exists",
        )

    device_platform = await _resolve_device_platform(schedule_create.device_id)
    schedule_db = ScheduleDB(
        id=str(uuid4()),
        name=schedule_create.name,
        task=SCRIPT_RUN_TASK_NAME,
        schedule_type=ScheduleType.ONETIME,
        args=[],
        kwargs={},
        description="Script run schedule",
        status=ScheduleStatus.ENABLED.value if schedule_create.enabled else ScheduleStatus.DISABLED.value,
    )
    _apply_script_run_schedule(schedule_db, schedule_create, device_platform)
    if not schedule_create.enabled:
        schedule_db.status = ScheduleStatus.DISABLED.value

    db.add(schedule_db)
    await db.commit()
    await db.refresh(schedule_db)
    return _db_to_script_run(schedule_db)


async def _get_script_run_schedule(schedule_id: str, db: AsyncSession):
    from app.models.schedule import ScheduleDB

    result = await db.execute(_script_run_query().where(ScheduleDB.id == schedule_id))
    schedule_db = result.scalar_one_or_none()
    if not schedule_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Script run schedule {schedule_id} not found",
        )
    return schedule_db


@router.get("/script-runs/{schedule_id}", response_model=ScriptRunSchedule)
async def get_script_run_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Get a script run schedule."""
    schedule_db = await _get_script_run_schedule(schedule_id, db)
    return await _db_to_script_run_with_task(schedule_db, db)


def _merge_script_run_update(schedule_db, schedule_update: ScriptRunScheduleUpdate) -> ScriptRunScheduleCreate:
    metadata = schedule_db.kwargs or {}
    current_mode = metadata.get("repeat") or (
        ScriptRunScheduleMode.ONCE.value if schedule_db.schedule_type == ScheduleType.ONETIME else ScriptRunScheduleMode.DAILY.value
    )
    return ScriptRunScheduleCreate(
        name=schedule_update.name if schedule_update.name is not None else schedule_db.name,
        script_id=schedule_update.script_id if schedule_update.script_id is not None else metadata.get("script_id", ""),
        device_id=schedule_update.device_id if schedule_update.device_id is not None else metadata.get("device_id", ""),
        schedule_mode=schedule_update.schedule_mode or ScriptRunScheduleMode(current_mode),
        run_at=schedule_update.run_at if schedule_update.run_at is not None else schedule_db.run_at,
        time_of_day=schedule_update.time_of_day if schedule_update.time_of_day is not None else metadata.get("time_of_day"),
        timezone=schedule_update.timezone if schedule_update.timezone is not None else metadata.get("timezone", "Asia/Shanghai"),
        parameters=schedule_update.parameters if schedule_update.parameters is not None else metadata.get("parameters", {}),
        enabled=(str(getattr(schedule_db.status, "value", schedule_db.status)).lower() == ScheduleStatus.ENABLED.value),
    )


@router.put("/script-runs/{schedule_id}", response_model=ScriptRunSchedule)
async def update_script_run_schedule(
    schedule_id: str,
    schedule_update: ScriptRunScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Update a script run schedule."""
    from app.models.schedule import ScheduleDB

    schedule_db = await _get_script_run_schedule(schedule_id, db)
    merged = _merge_script_run_update(schedule_db, schedule_update)

    if merged.name != schedule_db.name:
        existing = await db.execute(select(ScheduleDB).where(ScheduleDB.name == merged.name))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Schedule with name '{merged.name}' already exists",
            )

    device_platform = await _resolve_device_platform(merged.device_id)
    schedule_db.name = merged.name
    _apply_script_run_schedule(schedule_db, merged, device_platform)
    schedule_db.status = ScheduleStatus.ENABLED.value if merged.enabled else ScheduleStatus.DISABLED.value
    schedule_db.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(schedule_db)
    return await _db_to_script_run_with_task(schedule_db, db)


@router.post("/script-runs/{schedule_id}/enable", response_model=ScriptRunSchedule)
async def toggle_script_run_schedule(
    schedule_id: str,
    enable_request: ScheduleEnableRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Enable or disable a script run schedule."""
    schedule_db = await _get_script_run_schedule(schedule_id, db)

    if enable_request.enabled:
        metadata = schedule_db.kwargs or {}
        mode = ScriptRunScheduleMode(metadata.get("repeat") or ScriptRunScheduleMode.ONCE.value)
        if mode == ScriptRunScheduleMode.ONCE:
            if not schedule_db.run_at or schedule_db.run_at <= datetime.utcnow():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot enable an expired one-time schedule",
                )
            schedule_db.next_run_at = schedule_db.run_at
            schedule_db.executed = False
        else:
            schedule_db.next_run_at = compute_next_daily_run(
                metadata.get("time_of_day") or f"{int(schedule_db.hour):02d}:{int(schedule_db.minute):02d}",
                metadata.get("timezone") or "Asia/Shanghai",
            )
        schedule_db.status = ScheduleStatus.ENABLED.value
    else:
        schedule_db.status = ScheduleStatus.DISABLED.value

    schedule_db.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(schedule_db)
    return await _db_to_script_run_with_task(schedule_db, db)


@router.delete("/script-runs/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script_run_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Delete a script run schedule."""
    schedule_db = await _get_script_run_schedule(schedule_id, db)
    await db.delete(schedule_db)
    await db.commit()
    return None


@router.get("/{schedule_id}", response_model=Schedule)
async def get_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Get a schedule by ID."""
    from app.models.schedule import ScheduleDB

    result = await db.execute(
        select(ScheduleDB).where(ScheduleDB.id == schedule_id)
    )
    schedule_db = result.scalar_one_or_none()

    if not schedule_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )

    return _db_to_pydantic(schedule_db)


@router.put("/{schedule_id}", response_model=Schedule)
async def update_schedule(
    schedule_id: str,
    schedule_update: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """
    Update an existing schedule.

    Note: Changing schedule configuration requires removing and re-adding to Celery Beat.
    """
    from app.models.schedule import ScheduleDB

    result = await db.execute(
        select(ScheduleDB).where(ScheduleDB.id == schedule_id)
    )
    schedule_db = result.scalar_one_or_none()

    if not schedule_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )

    # Check for name conflict if name is being changed
    if schedule_update.name and schedule_update.name != schedule_db.name:
        existing = await db.execute(
            select(ScheduleDB).where(ScheduleDB.name == schedule_update.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Schedule with name '{schedule_update.name}' already exists"
            )

    # Track if we need to update Celery schedule
    needs_celery_update = False
    old_name = schedule_db.name

    # Update basic fields
    if schedule_update.name is not None:
        schedule_db.name = schedule_update.name
        needs_celery_update = True

    if schedule_update.task is not None:
        schedule_db.task = schedule_update.task
        needs_celery_update = True

    if schedule_update.args is not None:
        schedule_db.args = schedule_update.args
        needs_celery_update = True

    if schedule_update.kwargs is not None:
        schedule_db.kwargs = schedule_update.kwargs
        needs_celery_update = True

    if schedule_update.description is not None:
        schedule_db.description = schedule_update.description

    # Update type-specific configuration
    if schedule_db.schedule_type == ScheduleType.CRONTAB and schedule_update.crontab:
        schedule_db.minute = schedule_update.crontab.minute
        schedule_db.hour = schedule_update.crontab.hour
        schedule_db.day_of_month = schedule_update.crontab.day_of_month
        schedule_db.month_of_year = schedule_update.crontab.month_of_year
        schedule_db.day_of_week = schedule_update.crontab.day_of_week
        needs_celery_update = True

    elif schedule_db.schedule_type == ScheduleType.INTERVAL and schedule_update.interval:
        schedule_db.interval_every = schedule_update.interval.every
        schedule_db.interval_unit = schedule_update.interval.unit
        needs_celery_update = True

    elif schedule_db.schedule_type == ScheduleType.ONETIME and schedule_update.onetime:
        schedule_db.run_at = schedule_update.onetime.run_at
        schedule_db.next_run_at = schedule_update.onetime.run_at
        needs_celery_update = True

    schedule_db.updated_at = datetime.utcnow()

    # Update Celery Beat if needed and schedule is enabled
    if needs_celery_update and schedule_db.status == ScheduleStatus.ENABLED:
        # Remove old schedule
        remove_celery_schedule(old_name)

        # Add updated schedule
        if schedule_db.schedule_type == ScheduleType.CRONTAB:
            add_crontab_schedule(
                name=schedule_db.name,
                task=schedule_db.task,
                minute=schedule_db.minute,
                hour=schedule_db.hour,
                day_of_month=schedule_db.day_of_month,
                month_of_year=schedule_db.month_of_year,
                day_of_week=schedule_db.day_of_week,
                args=schedule_db.args,
                kwargs=schedule_db.kwargs,
            )
        elif schedule_db.schedule_type == ScheduleType.INTERVAL:
            add_interval_schedule(
                name=schedule_db.name,
                task=schedule_db.task,
                every=schedule_db.interval_every,
                unit=schedule_db.interval_unit,
                args=schedule_db.args,
                kwargs=schedule_db.kwargs,
            )
        elif schedule_db.schedule_type == ScheduleType.ONETIME and not schedule_db.executed:
            add_onetime_schedule(
                name=schedule_db.name,
                task=schedule_db.task,
                run_at=schedule_db.run_at,
                args=schedule_db.args,
                kwargs=schedule_db.kwargs,
            )

    await db.commit()
    await db.refresh(schedule_db)

    return _db_to_pydantic(schedule_db)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Delete a schedule."""
    from app.models.schedule import ScheduleDB

    result = await db.execute(
        select(ScheduleDB).where(ScheduleDB.id == schedule_id)
    )
    schedule_db = result.scalar_one_or_none()

    if not schedule_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )

    # Remove from Celery Beat
    remove_celery_schedule(schedule_db.name)

    # Delete from database
    await db.delete(schedule_db)
    await db.commit()

    return None


@router.post("/{schedule_id}/enable", response_model=Schedule)
async def toggle_schedule(
    schedule_id: str,
    enable_request: ScheduleEnableRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """
    Enable or disable a schedule.

    - **enabled**: True to enable, False to disable
    """
    from app.models.schedule import ScheduleDB

    result = await db.execute(
        select(ScheduleDB).where(ScheduleDB.id == schedule_id)
    )
    schedule_db = result.scalar_one_or_none()

    if not schedule_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )

    new_status = ScheduleStatus.ENABLED if enable_request.enabled else ScheduleStatus.DISABLED

    if enable_request.enabled and schedule_db.status != ScheduleStatus.ENABLED:
        # Enable the schedule
        schedule_db.status = ScheduleStatus.ENABLED

        # Add to Celery Beat
        if schedule_db.schedule_type == ScheduleType.CRONTAB:
            add_crontab_schedule(
                name=schedule_db.name,
                task=schedule_db.task,
                minute=schedule_db.minute,
                hour=schedule_db.hour,
                day_of_month=schedule_db.day_of_month,
                month_of_year=schedule_db.month_of_year,
                day_of_week=schedule_db.day_of_week,
                args=schedule_db.args,
                kwargs=schedule_db.kwargs,
            )
        elif schedule_db.schedule_type == ScheduleType.INTERVAL:
            add_interval_schedule(
                name=schedule_db.name,
                task=schedule_db.task,
                every=schedule_db.interval_every,
                unit=schedule_db.interval_unit,
                args=schedule_db.args,
                kwargs=schedule_db.kwargs,
            )
        elif schedule_db.schedule_type == ScheduleType.ONETIME and not schedule_db.executed:
            add_onetime_schedule(
                name=schedule_db.name,
                task=schedule_db.task,
                run_at=schedule_db.run_at,
                args=schedule_db.args,
                kwargs=schedule_db.kwargs,
            )

    elif not enable_request.enabled and schedule_db.status == ScheduleStatus.ENABLED:
        # Disable the schedule
        schedule_db.status = ScheduleStatus.DISABLED

        # Remove from Celery Beat
        remove_celery_schedule(schedule_db.name)

    schedule_db.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(schedule_db)

    return _db_to_pydantic(schedule_db)


def _db_to_pydantic(schedule_db) -> Schedule:
    """Convert SQLAlchemy model to Pydantic model."""
    return Schedule(
        id=schedule_db.id,
        name=schedule_db.name,
        task=schedule_db.task,
        schedule_type=schedule_db.schedule_type,
        args=schedule_db.args or [],
        kwargs=schedule_db.kwargs or {},
        description=schedule_db.description,
        status=schedule_db.status,
        minute=schedule_db.minute,
        hour=schedule_db.hour,
        day_of_month=schedule_db.day_of_month,
        month_of_year=schedule_db.month_of_year,
        day_of_week=schedule_db.day_of_week,
        interval_every=schedule_db.interval_every,
        interval_unit=schedule_db.interval_unit,
        run_at=schedule_db.run_at,
        executed=schedule_db.executed,
        last_run_at=schedule_db.last_run_at,
        next_run_at=schedule_db.next_run_at,
        total_run_count=schedule_db.total_run_count or 0,
        created_at=schedule_db.created_at,
        updated_at=schedule_db.updated_at,
    )
