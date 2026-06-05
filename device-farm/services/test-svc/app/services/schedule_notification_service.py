import logging
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import get_db_session
from app.models.database import ScriptDB, TaskDB
from app.models.schedule import ScheduleDB

logger = logging.getLogger(__name__)


TERMINAL_STATUS_TEXT = {
    "success": "成功",
    "failed": "失败",
    "cancelled": "已取消",
}


def _status_value(value) -> str:
    return str(getattr(value, "value", value) or "").lower()


def _duration_text(task_db: TaskDB) -> str:
    result = task_db.result or {}
    duration = result.get("duration")
    if isinstance(duration, (int, float)):
        return f"{duration:.2f}s"
    if task_db.started_at and task_db.finished_at:
        seconds = max((task_db.finished_at - task_db.started_at).total_seconds(), 0)
        return f"{seconds:.2f}s"
    return "-"


def _first_error(task_db: TaskDB) -> str:
    if task_db.error:
        return task_db.error.splitlines()[0]
    result = task_db.result or {}
    errors = result.get("errors")
    if isinstance(errors, list) and errors:
        return str(errors[0]).splitlines()[0]
    return ""


def build_feishu_task_message(schedule_db: ScheduleDB, task_db: TaskDB, script_name: str) -> str:
    """Build a short Feishu text notification for a scheduled task result."""
    metadata = schedule_db.kwargs or {}
    status_value = _status_value(task_db.status)
    status_text = TERMINAL_STATUS_TEXT.get(status_value, status_value or "未知")
    lines = [
        f"云测定时任务已完成：{status_text}",
        f"计划：{schedule_db.name}",
        f"脚本：{script_name or task_db.script_id}",
        f"设备：{metadata.get('device_id') or task_db.device_id or '-'}",
        f"平台：{metadata.get('device_platform') or _status_value(task_db.device_platform) or '-'}",
        f"任务：{task_db.id}",
        f"耗时：{_duration_text(task_db)}",
    ]
    finished_at = task_db.finished_at or datetime.utcnow()
    lines.append(f"完成时间：{finished_at.isoformat(sep=' ', timespec='seconds')}")

    error = _first_error(task_db)
    if error:
        lines.append(f"错误：{error[:500]}")

    return "\n".join(lines)


def _sanitize_notification_error(error: Optional[str]) -> str:
    value = (error or "Unknown notification error").replace("\n", " ").strip()
    return value[:500]


def _feishu_response_error(response: httpx.Response) -> Optional[str]:
    if response.status_code >= 400:
        return f"Feishu webhook HTTP {response.status_code}: {response.text[:300]}"

    try:
        payload = response.json()
    except Exception:
        return None

    code = payload.get("code", payload.get("StatusCode"))
    if code not in (None, 0):
        message = payload.get("msg") or payload.get("message") or payload.get("StatusMessage") or "Feishu webhook returned error"
        return f"Feishu webhook code {code}: {message}"
    return None


async def _send_feishu_text(webhook_url: str, text: str) -> None:
    timeout = max(1, int(getattr(settings, "FEISHU_NOTIFICATION_TIMEOUT_SECONDS", 5)))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            webhook_url,
            json={"msg_type": "text", "content": {"text": text}},
        )

    error = _feishu_response_error(response)
    if error:
        raise RuntimeError(error)


def _mark_notification_result(schedule_db: ScheduleDB, task_id: str, status: str, error: Optional[str] = None) -> None:
    """Write notification result to schedule metadata.

    Mutates schedule_db.kwargs and schedule_db.updated_at in-place.
    The caller MUST hold an active DB session that will commit the changes
    (e.g. via get_db_session() context manager).
    """
    now = datetime.utcnow()
    metadata = dict(schedule_db.kwargs or {})
    metadata["notification_last_status"] = status
    metadata["notification_last_task_id"] = task_id
    metadata["notification_last_at"] = now.isoformat()
    if error:
        metadata["notification_last_error"] = _sanitize_notification_error(error)
    else:
        metadata.pop("notification_last_error", None)
    schedule_db.kwargs = metadata
    schedule_db.updated_at = now


async def notify_scheduled_task_finished(task_id: str) -> None:
    """Send a Feishu notification for a scheduled task terminal state.

    Notification errors are recorded on the schedule metadata and never raised to
    the task execution path.
    """
    async with get_db_session() as db:
        task_result = await db.execute(select(TaskDB).where(TaskDB.id == task_id))
        task_db = task_result.scalar_one_or_none()
        if not task_db:
            return

        parameters = task_db.parameters or {}
        schedule_id = parameters.get("schedule_id") if parameters.get("scheduled_run") else None
        if not schedule_id:
            return

        schedule_result = await db.execute(select(ScheduleDB).where(ScheduleDB.id == schedule_id))
        schedule_db = schedule_result.scalar_one_or_none()
        if not schedule_db:
            return

        metadata = dict(schedule_db.kwargs or {})
        if not metadata.get("notification_enabled"):
            return

        if (
            metadata.get("notification_last_task_id") == task_id
            and metadata.get("notification_last_status") == "success"
        ):
            return

        webhook_url = metadata.get("feishu_webhook_url")
        if not webhook_url:
            _mark_notification_result(schedule_db, task_id, "failed", "Feishu webhook is not configured")
            return

        script_name = task_db.script_id
        script_result = await db.execute(select(ScriptDB).where(ScriptDB.id == task_db.script_id))
        script_db = script_result.scalar_one_or_none()
        if script_db:
            script_name = script_db.name

        message = build_feishu_task_message(schedule_db, task_db, script_name)

        try:
            await _send_feishu_text(webhook_url, message)
            # Re-read schedule metadata to avoid racing with concurrent
            # notifications (e.g. executor and cancel_task API).
            await db.refresh(schedule_db)
            fresh_metadata = dict(schedule_db.kwargs or {})
            if (
                fresh_metadata.get("notification_last_task_id") == task_id
                and fresh_metadata.get("notification_last_status") == "success"
            ):
                return
            _mark_notification_result(schedule_db, task_id, "success")
        except Exception as exc:
            error = _sanitize_notification_error(str(exc) or f"{type(exc).__name__}")
            logger.warning("Scheduled task %s Feishu notification failed: %s", task_id, error)
            _mark_notification_result(schedule_db, task_id, "failed", error)
