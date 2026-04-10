# Celery Beat Scheduler Configuration
"""
Celery Beat configuration for scheduled task execution.

Supports:
- Cron expressions for precise scheduling
- Interval-based scheduling (every N seconds/minutes/hours)
- One-time scheduled tasks
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
from celery.schedules import crontab, schedule
from pydantic import BaseModel, Field, validator

from app.tasks import celery_app
from app.config import settings


class ScheduleType(str, Enum):
    """Type of schedule"""
    CRONTAB = "crontab"      # Cron expression based
    INTERVAL = "interval"    # Interval based (every N seconds/minutes/hours)
    ONETIME = "onetime"      # One-time execution at specific time


class IntervalUnit(str, Enum):
    """Unit for interval scheduling"""
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"


# Pydantic models for schedule configuration
class CrontabSchedule(BaseModel):
    """Crontab schedule configuration"""
    minute: str = "*"          # 0-59
    hour: str = "*"            # 0-23
    day_of_month: str = "*"    # 1-31
    month_of_year: str = "*"   # 1-12
    day_of_week: str = "*"     # 0-6 (Sunday=0)

    def to_crontab(self) -> crontab:
        """Convert to Celery crontab object"""
        return crontab(
            minute=self.minute,
            hour=self.hour,
            day_of_month=self.day_of_month,
            month_of_year=self.month_of_year,
            day_of_week=self.day_of_week,
        )


class IntervalSchedule(BaseModel):
    """Interval schedule configuration"""
    every: int = Field(..., gt=0, description="Interval value")
    unit: IntervalUnit = IntervalUnit.MINUTES

    def to_schedule(self) -> schedule:
        """Convert to Celery schedule object"""
        kwargs = {self.unit.value: self.every}
        return schedule(run_every=timedelta(**kwargs))


class OneTimeSchedule(BaseModel):
    """One-time schedule configuration"""
    run_at: datetime = Field(..., description="When to run the task")
    executed: bool = Field(default=False, description="Whether already executed")

    def is_due(self) -> bool:
        """Check if the task is due"""
        if self.executed:
            return False
        return datetime.utcnow() >= self.run_at


class ScheduleConfig(BaseModel):
    """Complete schedule configuration"""
    name: str = Field(..., description="Unique name for the schedule")
    task: str = Field(..., description="Celery task name to execute")
    schedule_type: ScheduleType
    args: List[Any] = Field(default_factory=list, description="Positional arguments for the task")
    kwargs: Dict[str, Any] = Field(default_factory=dict, description="Keyword arguments for the task")
    enabled: bool = Field(default=True, description="Whether the schedule is enabled")

    # One of these must be set based on schedule_type
    crontab: Optional[CrontabSchedule] = None
    interval: Optional[IntervalSchedule] = None
    onetime: Optional[OneTimeSchedule] = None

    @validator('crontab', always=True)
    def validate_crontab(cls, v, values):
        if values.get('schedule_type') == ScheduleType.CRONTAB and v is None:
            raise ValueError("crontab is required for CRONTAB schedule type")
        return v

    @validator('interval', always=True)
    def validate_interval(cls, v, values):
        if values.get('schedule_type') == ScheduleType.INTERVAL and v is None:
            raise ValueError("interval is required for INTERVAL schedule type")
        return v

    @validator('onetime', always=True)
    def validate_onetime(cls, v, values):
        if values.get('schedule_type') == ScheduleType.ONETIME and v is None:
            raise ValueError("onetime is required for ONETIME schedule type")
        return v

    def to_celery_schedule(self):
        """Convert to Celery schedule object"""
        if self.schedule_type == ScheduleType.CRONTAB:
            return self.crontab.to_crontab()
        elif self.schedule_type == ScheduleType.INTERVAL:
            return self.interval.to_schedule()
        else:
            raise ValueError(f"Cannot convert {self.schedule_type} to Celery schedule")


# Default schedules for the system
DEFAULT_SCHEDULES: Dict[str, Dict[str, Any]] = {
    # Example: Clean up old task results every hour
    "cleanup-task-results": {
        "task": "app.tasks.scheduler.cleanup_task_results",
        "schedule": crontab(minute=0),  # Every hour at minute 0
    },
    # Example: Check for expired reservations every minute
    "check-expired-reservations": {
        "task": "app.tasks.scheduler.check_expired_reservations",
        "schedule": schedule(run_every=timedelta(minutes=1)),
    },
    # Example: Generate daily report at midnight
    "generate-daily-report": {
        "task": "app.tasks.scheduler.generate_daily_report",
        "schedule": crontab(minute=0, hour=0),  # Every day at midnight
    },
}


def configure_celery_beat():
    """
    Configure Celery Beat with default schedules.

    This function updates the Celery app configuration with
    the beat schedule settings.
    """
    celery_app.conf.beat_schedule = DEFAULT_SCHEDULES.copy()

    # Additional Beat configuration
    celery_app.conf.update(
        # Store beat schedule in Redis for persistence
        beat_scheduler=settings.CELERY_BEAT_SCHEDULER,

        # Schedule file location (for file-based persistence)
        beat_schedule_filename=settings.CELERY_BEAT_SCHEDULE_FILENAME,

        # Sync every 3 minutes
        beat_sync_every=3 * 60,

        # How often to wake up to check schedule (in seconds)
        # Lower values = more precise but more resource usage
        worker_send_task_events=True,
    )

    return celery_app


# Scheduled task implementations
@celery_app.task(name="app.tasks.scheduler.cleanup_task_results")
def cleanup_task_results():
    """
    Clean up old task results from the result backend.
    Runs every hour.
    """
    from celery.result import AsyncResult
    from datetime import datetime, timedelta

    # Get current time
    now = datetime.utcnow()

    # Results older than this will be cleaned up
    max_age = timedelta(hours=24)

    # Log cleanup
    print(f"[{now}] Running task result cleanup...")

    # Note: Actual cleanup would require iterating through results
    # This is a placeholder that would be implemented based on the backend
    return {
        "status": "completed",
        "timestamp": now.isoformat(),
        "message": "Task result cleanup completed"
    }


@celery_app.task(name="app.tasks.scheduler.check_expired_reservations")
def check_expired_reservations():
    """
    Check for expired device reservations and release devices.
    Runs every minute.
    """
    from datetime import datetime

    now = datetime.utcnow()
    print(f"[{now}] Checking for expired reservations...")

    # This would call the reservation service to check and release
    # expired reservations. Placeholder for actual implementation.
    return {
        "status": "completed",
        "timestamp": now.isoformat(),
        "message": "Expired reservation check completed"
    }


@celery_app.task(name="app.tasks.scheduler.generate_daily_report")
def generate_daily_report():
    """
    Generate daily usage and statistics report.
    Runs at midnight every day.
    """
    from datetime import datetime, date

    now = datetime.utcnow()
    today = date.today()

    print(f"[{now}] Generating daily report for {today}...")

    # This would call the report service to generate daily statistics
    # Placeholder for actual implementation.
    return {
        "status": "completed",
        "timestamp": now.isoformat(),
        "date": today.isoformat(),
        "message": "Daily report generation initiated"
    }


@celery_app.task(name="app.tasks.scheduler.execute_scheduled_task")
def execute_scheduled_task(
    script_id: str,
    device_id: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None
):
    """
    Execute a test script as a scheduled task.

    This is the main entry point for scheduled test executions.

    Args:
        script_id: The ID of the script to execute
        device_id: Optional device ID to run on
        parameters: Optional parameters for the script
    """
    from datetime import datetime
    from app.tasks.executor import execute_test_task

    now = datetime.utcnow()
    print(f"[{now}] Executing scheduled task: script={script_id}, device={device_id}")

    # Create a task record and execute
    # This would integrate with the task execution system
    result = {
        "script_id": script_id,
        "device_id": device_id,
        "parameters": parameters or {},
        "scheduled_at": now.isoformat(),
        "status": "initiated"
    }

    # Trigger actual execution through the executor
    # execute_test_task.delay(task_id)

    return result


@celery_app.task(name="app.tasks.scheduler.execute_onetime_task")
def execute_onetime_task(
    task_name: str,
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None
):
    """
    Execute a one-time scheduled task.

    Args:
        task_name: The name of the Celery task to execute
        args: Positional arguments for the task
        kwargs: Keyword arguments for the task
    """
    from datetime import datetime

    now = datetime.utcnow()
    print(f"[{now}] Executing one-time task: {task_name}")

    # Get the task by name and execute it
    task = celery_app.tasks.get(task_name)
    if task:
        result = task.apply_async(
            args=args or [],
            kwargs=kwargs or {}
        )
        return {
            "status": "executed",
            "task_id": result.id,
            "task_name": task_name,
            "timestamp": now.isoformat()
        }
    else:
        return {
            "status": "error",
            "error": f"Task {task_name} not found",
            "timestamp": now.isoformat()
        }


# Helper functions for schedule management
def add_crontab_schedule(
    name: str,
    task: str,
    minute: str = "*",
    hour: str = "*",
    day_of_month: str = "*",
    month_of_year: str = "*",
    day_of_week: str = "*",
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    enabled: bool = True
) -> ScheduleConfig:
    """
    Add a crontab-based schedule.

    Args:
        name: Unique name for the schedule
        task: Celery task name to execute
        minute: Cron minute expression (default: every minute)
        hour: Cron hour expression (default: every hour)
        day_of_month: Cron day of month expression
        month_of_year: Cron month expression
        day_of_week: Cron day of week expression
        args: Positional arguments for the task
        kwargs: Keyword arguments for the task
        enabled: Whether the schedule is enabled

    Returns:
        ScheduleConfig object
    """
    config = ScheduleConfig(
        name=name,
        task=task,
        schedule_type=ScheduleType.CRONTAB,
        crontab=CrontabSchedule(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
        ),
        args=args or [],
        kwargs=kwargs or {},
        enabled=enabled,
    )

    # Add to Celery Beat schedule
    celery_app.conf.beat_schedule[name] = {
        "task": task,
        "schedule": config.to_celery_schedule(),
        "args": config.args,
        "kwargs": config.kwargs,
    }

    return config


def add_interval_schedule(
    name: str,
    task: str,
    every: int,
    unit: IntervalUnit = IntervalUnit.MINUTES,
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    enabled: bool = True
) -> ScheduleConfig:
    """
    Add an interval-based schedule.

    Args:
        name: Unique name for the schedule
        task: Celery task name to execute
        every: Interval value
        unit: Unit for the interval (seconds/minutes/hours/days)
        args: Positional arguments for the task
        kwargs: Keyword arguments for the task
        enabled: Whether the schedule is enabled

    Returns:
        ScheduleConfig object
    """
    config = ScheduleConfig(
        name=name,
        task=task,
        schedule_type=ScheduleType.INTERVAL,
        interval=IntervalSchedule(every=every, unit=unit),
        args=args or [],
        kwargs=kwargs or {},
        enabled=enabled,
    )

    # Add to Celery Beat schedule
    celery_app.conf.beat_schedule[name] = {
        "task": task,
        "schedule": config.to_celery_schedule(),
        "args": config.args,
        "kwargs": config.kwargs,
    }

    return config


def add_onetime_schedule(
    name: str,
    task: str,
    run_at: datetime,
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    enabled: bool = True
) -> ScheduleConfig:
    """
    Add a one-time schedule.

    Note: One-time schedules are handled differently from regular
    Celery Beat schedules. They use apply_async with eta.

    Args:
        name: Unique name for the schedule
        task: Celery task name to execute
        run_at: When to run the task
        args: Positional arguments for the task
        kwargs: Keyword arguments for the task
        enabled: Whether the schedule is enabled

    Returns:
        ScheduleConfig object
    """
    config = ScheduleConfig(
        name=name,
        task=task,
        schedule_type=ScheduleType.ONETIME,
        onetime=OneTimeSchedule(run_at=run_at),
        args=args or [],
        kwargs=kwargs or {},
        enabled=enabled,
    )

    # For one-time tasks, use apply_async with eta
    if enabled:
        celery_task = celery_app.tasks.get(task)
        if celery_task:
            celery_task.apply_async(
                args=config.args,
                kwargs=config.kwargs,
                eta=run_at
            )

    return config


def remove_schedule(name: str) -> bool:
    """
    Remove a schedule from Celery Beat.

    Args:
        name: Name of the schedule to remove

    Returns:
        True if removed, False if not found
    """
    if name in celery_app.conf.beat_schedule:
        del celery_app.conf.beat_schedule[name]
        return True
    return False


def get_schedule(name: str) -> Optional[Dict[str, Any]]:
    """
    Get a schedule by name.

    Args:
        name: Name of the schedule

    Returns:
        Schedule configuration or None if not found
    """
    return celery_app.conf.beat_schedule.get(name)


def list_schedules() -> Dict[str, Dict[str, Any]]:
    """
    List all schedules.

    Returns:
        Dictionary of all schedules
    """
    return celery_app.conf.beat_schedule.copy()


def enable_schedule(name: str) -> bool:
    """
    Enable a schedule.

    Args:
        name: Name of the schedule

    Returns:
        True if enabled, False if not found
    """
    schedule = get_schedule(name)
    if schedule:
        schedule["enabled"] = True
        celery_app.conf.beat_schedule[name] = schedule
        return True
    return False


def disable_schedule(name: str) -> bool:
    """
    Disable a schedule.

    Args:
        name: Name of the schedule

    Returns:
        True if disabled, False if not found
    """
    schedule = get_schedule(name)
    if schedule:
        schedule["enabled"] = False
        celery_app.conf.beat_schedule[name] = schedule
        return True
    return False


# Initialize Celery Beat configuration
configure_celery_beat()
