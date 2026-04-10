# Schedules API Router
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from celery.schedules import crontab, schedule

from app.models.schedule import (
    Schedule,
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleListResponse,
    ScheduleEnableRequest,
    ScheduleType,
    ScheduleStatus,
    IntervalUnit,
)
from app.database import get_db
from app.config import settings
from app.auth import verify_api_key
from app.tasks.scheduler import (
    celery_app,
    add_crontab_schedule,
    add_interval_schedule,
    add_onetime_schedule,
    remove_schedule as remove_celery_schedule,
)

router = APIRouter()


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
