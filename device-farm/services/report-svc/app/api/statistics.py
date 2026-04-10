# Statistics API Routes
from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, timedelta
from typing import Optional
import logging

from app.services.statistics import (
    statistics_service,
    TimeGranularity,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/usage/devices")
async def get_device_usage(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    start_time: Optional[datetime] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[datetime] = Query(None, description="End time (ISO format)"),
):
    """Get device usage statistics"""
    # Default to last 7 days if not specified
    if not start_time:
        start_time = datetime.utcnow() - timedelta(days=7)
    if not end_time:
        end_time = datetime.utcnow()

    stats = statistics_service.get_device_usage_stats(
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
    )

    return {
        "device_usage": stats,
        "total_devices": len(stats),
        "start_time": start_time,
        "end_time": end_time,
    }


@router.get("/usage/tasks")
async def get_task_stats(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    start_time: Optional[datetime] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[datetime] = Query(None, description="End time (ISO format)"),
):
    """Get task execution statistics"""
    # Default to last 7 days if not specified
    if not start_time:
        start_time = datetime.utcnow() - timedelta(days=7)
    if not end_time:
        end_time = datetime.utcnow()

    stats = statistics_service.get_task_execution_stats(
        device_id=device_id,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
    )

    return {
        "task_stats": stats,
        "start_time": start_time,
        "end_time": end_time,
    }


@router.get("/trend")
async def get_usage_trend(
    metric: str = Query("device_hours", description="Metric: device_hours or task_count"),
    granularity: TimeGranularity = Query(TimeGranularity.DAILY, description="Time granularity"),
    start_time: Optional[datetime] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[datetime] = Query(None, description="End time (ISO format)"),
):
    """Get usage trend over time"""
    # Default to last 30 days if not specified
    if not start_time:
        start_time = datetime.utcnow() - timedelta(days=30)
    if not end_time:
        end_time = datetime.utcnow()

    if metric not in ["device_hours", "task_count"]:
        raise HTTPException(
            status_code=400,
            detail="metric must be 'device_hours' or 'task_count'"
        )

    trend = statistics_service.get_usage_trend(
        metric=metric,
        granularity=granularity,
        start_time=start_time,
        end_time=end_time,
    )

    return trend


@router.get("/reports/{report_type}")
async def get_statistics_report(
    report_type: str,
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
):
    """Get statistics report (daily, weekly, monthly)"""
    if report_type not in ["daily", "weekly", "monthly"]:
        raise HTTPException(
            status_code=400,
            detail="report_type must be 'daily', 'weekly', or 'monthly'"
        )

    report = statistics_service.generate_report(
        report_type=report_type,
        device_id=device_id,
        user_id=user_id,
    )

    return report


@router.post("/record/session")
async def record_session(
    device_id: str,
    device_name: str,
    user_id: str,
    start_time: datetime,
    end_time: Optional[datetime] = None,
):
    """Record a device usage session (for testing/manual recording)"""
    statistics_service.record_device_session(
        device_id=device_id,
        device_name=device_name,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
    )

    return {"message": "Session recorded", "device_id": device_id}


@router.post("/record/task")
async def record_task(
    task_id: str,
    device_id: str,
    user_id: str,
    status: str,
    duration_seconds: float,
    script_name: Optional[str] = None,
):
    """Record a task execution (for testing/manual recording)"""
    if status not in ["success", "failed", "cancelled"]:
        raise HTTPException(
            status_code=400,
            detail="status must be 'success', 'failed', or 'cancelled'"
        )

    statistics_service.record_task_execution(
        task_id=task_id,
        device_id=device_id,
        user_id=user_id,
        status=status,
        duration_seconds=duration_seconds,
        script_name=script_name,
    )

    return {"message": "Task recorded", "task_id": task_id}
