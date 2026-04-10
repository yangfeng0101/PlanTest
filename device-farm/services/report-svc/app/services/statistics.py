# Statistics Service for Device Farm
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict
from enum import Enum
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class TimeGranularity(str, Enum):
    """Time granularity for statistics"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class DeviceUsageStats(BaseModel):
    """Device usage statistics"""
    device_id: str
    device_name: str
    total_usage_minutes: float
    session_count: int
    average_session_minutes: float
    last_used: Optional[datetime] = None


class TaskExecutionStats(BaseModel):
    """Task execution statistics"""
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    success_rate: float
    average_duration_seconds: float
    total_duration_seconds: float


class TimeSeriesPoint(BaseModel):
    """Single point in time series"""
    timestamp: datetime
    value: float


class UsageTrend(BaseModel):
    """Usage trend over time"""
    metric: str
    data: List[TimeSeriesPoint]
    granularity: TimeGranularity


class StatisticsReport(BaseModel):
    """Statistics report"""
    report_type: str
    start_time: datetime
    end_time: datetime
    generated_at: datetime

    # Device usage
    device_usage: List[DeviceUsageStats] = []
    total_device_hours: float = 0.0

    # Task execution
    task_stats: Optional[TaskExecutionStats] = None

    # Top devices
    top_devices: List[Dict[str, Any]] = []

    # Top users
    top_users: List[Dict[str, Any]] = []

    # Trends
    usage_trend: Optional[UsageTrend] = None


# In-memory statistics storage (in production, use database)
_device_sessions: List[Dict[str, Any]] = []
_task_executions: List[Dict[str, Any]] = []


class StatisticsService:
    """Service for tracking and reporting statistics"""

    def record_device_session(
        self,
        device_id: str,
        device_name: str,
        user_id: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
    ) -> None:
        """Record a device usage session"""
        session = {
            "device_id": device_id,
            "device_name": device_name,
            "user_id": user_id,
            "start_time": start_time,
            "end_time": end_time or datetime.utcnow(),
        }
        _device_sessions.append(session)
        logger.debug(f"Recorded device session: {device_id} by {user_id}")

    def record_task_execution(
        self,
        task_id: str,
        device_id: str,
        user_id: str,
        status: str,  # success, failed, cancelled
        duration_seconds: float,
        script_name: Optional[str] = None,
    ) -> None:
        """Record a task execution"""
        execution = {
            "task_id": task_id,
            "device_id": device_id,
            "user_id": user_id,
            "status": status,
            "duration_seconds": duration_seconds,
            "script_name": script_name,
            "executed_at": datetime.utcnow(),
        }
        _task_executions.append(execution)
        logger.debug(f"Recorded task execution: {task_id} on {device_id}")

    def get_device_usage_stats(
        self,
        device_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[DeviceUsageStats]:
        """Get device usage statistics"""
        # Filter sessions
        sessions = _device_sessions
        if device_id:
            sessions = [s for s in sessions if s["device_id"] == device_id]
        if start_time:
            sessions = [s for s in sessions if s["start_time"] >= start_time]
        if end_time:
            sessions = [s for s in sessions if s["start_time"] <= end_time]

        # Aggregate by device
        device_data: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "sessions": [],
                "total_minutes": 0.0,
            }
        )

        for session in sessions:
            did = session["device_id"]
            device_data[did]["sessions"].append(session)
            if session["end_time"]:
                duration = (session["end_time"] - session["start_time"]).total_seconds() / 60
                device_data[did]["total_minutes"] += duration

        # Build stats
        stats = []
        for did, data in device_data.items():
            # Get device name from first session
            device_name = data["sessions"][0]["device_name"] if data["sessions"] else "Unknown"

            session_count = len(data["sessions"])
            total_minutes = data["total_minutes"]
            avg_minutes = total_minutes / session_count if session_count > 0 else 0

            last_used = max(s["start_time"] for s in data["sessions"]) if data["sessions"] else None

            stats.append(DeviceUsageStats(
                device_id=did,
                device_name=device_name,
                total_usage_minutes=round(total_minutes, 2),
                session_count=session_count,
                average_session_minutes=round(avg_minutes, 2),
                last_used=last_used,
            ))

        # Sort by total usage
        stats.sort(key=lambda x: x.total_usage_minutes, reverse=True)
        return stats

    def get_task_execution_stats(
        self,
        device_id: Optional[str] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> TaskExecutionStats:
        """Get task execution statistics"""
        # Filter executions
        executions = _task_executions
        if device_id:
            executions = [e for e in executions if e["device_id"] == device_id]
        if user_id:
            executions = [e for e in executions if e["user_id"] == user_id]
        if start_time:
            executions = [e for e in executions if e["executed_at"] >= start_time]
        if end_time:
            executions = [e for e in executions if e["executed_at"] <= end_time]

        # Calculate stats
        total = len(executions)
        successful = sum(1 for e in executions if e["status"] == "success")
        failed = sum(1 for e in executions if e["status"] == "failed")
        success_rate = (successful / total * 100) if total > 0 else 0

        durations = [e["duration_seconds"] for e in executions]
        total_duration = sum(durations)
        avg_duration = total_duration / total if total > 0 else 0

        return TaskExecutionStats(
            total_tasks=total,
            successful_tasks=successful,
            failed_tasks=failed,
            success_rate=round(success_rate, 2),
            average_duration_seconds=round(avg_duration, 2),
            total_duration_seconds=round(total_duration, 2),
        )

    def get_usage_trend(
        self,
        metric: str,  # "device_hours" or "task_count"
        granularity: TimeGranularity,
        start_time: datetime,
        end_time: datetime,
    ) -> UsageTrend:
        """Get usage trend over time"""
        data_points = []

        # Generate time buckets
        current = start_time
        while current <= end_time:
            # Determine next bucket
            if granularity == TimeGranularity.HOURLY:
                next_time = current + timedelta(hours=1)
            elif granularity == TimeGranularity.DAILY:
                next_time = current + timedelta(days=1)
            elif granularity == TimeGranularity.WEEKLY:
                next_time = current + timedelta(weeks=1)
            else:  # MONTHLY
                # Approximate month
                next_time = current + timedelta(days=30)

            # Calculate value for this bucket
            if metric == "device_hours":
                sessions = [
                    s for s in _device_sessions
                    if current <= s["start_time"] < next_time
                ]
                total_minutes = sum(
                    (s["end_time"] - s["start_time"]).total_seconds() / 60
                    for s in sessions if s["end_time"]
                )
                value = total_minutes / 60  # Convert to hours
            else:  # task_count
                executions = [
                    e for e in _task_executions
                    if current <= e["executed_at"] < next_time
                ]
                value = len(executions)

            data_points.append(TimeSeriesPoint(
                timestamp=current,
                value=round(value, 2),
            ))

            current = next_time

        return UsageTrend(
            metric=metric,
            data=data_points,
            granularity=granularity,
        )

    def generate_report(
        self,
        report_type: str,  # "daily", "weekly", "monthly"
        device_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> StatisticsReport:
        """Generate a statistics report"""
        now = datetime.utcnow()

        # Determine time range
        if report_type == "daily":
            start_time = now - timedelta(days=1)
        elif report_type == "weekly":
            start_time = now - timedelta(weeks=1)
        else:  # monthly
            start_time = now - timedelta(days=30)

        # Get device usage
        device_usage = self.get_device_usage_stats(
            device_id=device_id,
            start_time=start_time,
            end_time=now,
        )

        # Get task stats
        task_stats = self.get_task_execution_stats(
            device_id=device_id,
            user_id=user_id,
            start_time=start_time,
            end_time=now,
        )

        # Calculate total device hours
        total_hours = sum(s.total_usage_minutes for s in device_usage) / 60

        # Top devices
        top_devices = [
            {
                "device_id": s.device_id,
                "device_name": s.device_name,
                "usage_hours": round(s.total_usage_minutes / 60, 2),
            }
            for s in device_usage[:5]
        ]

        # Top users (from sessions)
        user_sessions: Dict[str, float] = defaultdict(float)
        for session in _device_sessions:
            if start_time <= session["start_time"] <= now:
                if session["end_time"]:
                    duration = (session["end_time"] - session["start_time"]).total_seconds() / 60
                    user_sessions[session["user_id"]] += duration

        top_users = sorted(
            [
                {"user_id": uid, "usage_hours": round(mins / 60, 2)}
                for uid, mins in user_sessions.items()
            ],
            key=lambda x: x["usage_hours"],
            reverse=True,
        )[:5]

        # Usage trend
        granularity = TimeGranularity.HOURLY if report_type == "daily" else TimeGranularity.DAILY
        usage_trend = self.get_usage_trend(
            metric="device_hours",
            granularity=granularity,
            start_time=start_time,
            end_time=now,
        )

        return StatisticsReport(
            report_type=report_type,
            start_time=start_time,
            end_time=now,
            generated_at=now,
            device_usage=device_usage,
            total_device_hours=round(total_hours, 2),
            task_stats=task_stats,
            top_devices=top_devices,
            top_users=top_users,
            usage_trend=usage_trend,
        )


# Global instance
statistics_service = StatisticsService()
