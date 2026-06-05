import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

os.environ["DEBUG"] = "false"

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT.parent))

from app.models.database import TaskStatus
from app.models.schedule import ScheduleStatus, ScheduleType
from app.api.schedules import _db_to_script_run, _script_run_kwargs, compute_next_daily_run
from app.models.schedule import ScriptRunScheduleCreate, ScriptRunScheduleMode
from app.services.script_schedule_runner import _record_schedule_success, process_due_script_schedule


class FakeDB:
    def __init__(self):
        self.commit_count = 0

    async def commit(self):
        self.commit_count += 1


def make_schedule(**overrides):
    data = {
        "id": "schedule-1",
        "name": "daily",
        "task": "script_run",
        "schedule_type": ScheduleType.CRONTAB,
        "run_at": None,
        "executed": False,
        "status": ScheduleStatus.ENABLED,
        "minute": "30",
        "hour": "9",
        "day_of_month": "*",
        "month_of_year": "*",
        "day_of_week": "*",
        "kwargs": {
            "kind": "script_run",
            "script_id": "script-1",
            "device_id": "device-1",
            "device_platform": "android",
            "repeat": "daily",
            "time_of_day": "09:30",
            "timezone": "Asia/Shanghai",
            "parameters": {"env": "staging"},
        },
        "last_run_at": None,
        "next_run_at": datetime.utcnow() - timedelta(seconds=1),
        "total_run_count": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class ScriptScheduleRunnerTest(unittest.IsolatedAsyncioTestCase):
    def test_compute_next_daily_run_returns_future_utc_time(self):
        next_run = compute_next_daily_run(
            "09:30",
            "Asia/Shanghai",
            after=datetime(2026, 5, 21, 1, 0, 0),
        )

        self.assertEqual(next_run, datetime(2026, 5, 21, 1, 30, 0))

    def test_once_success_expires_schedule(self):
        schedule = make_schedule(
            schedule_type=ScheduleType.ONETIME,
            run_at=datetime.utcnow() - timedelta(seconds=1),
            kwargs={
                "kind": "script_run",
                "script_id": "script-1",
                "device_id": "device-1",
                "device_platform": "android",
                "repeat": "once",
                "parameters": {},
            },
        )

        _record_schedule_success(schedule, "task-1", datetime.utcnow())

        self.assertEqual(schedule.status, ScheduleStatus.EXPIRED)
        self.assertTrue(schedule.executed)
        self.assertIsNone(schedule.next_run_at)
        self.assertEqual(schedule.kwargs["last_task_id"], "task-1")
        self.assertIn("last_trigger_at", schedule.kwargs)

    def test_update_metadata_clears_previous_task_state(self):
        payload = ScriptRunScheduleCreate(
            name="schedule",
            script_id="script-2",
            device_id="device-2",
            schedule_mode=ScriptRunScheduleMode.ONCE,
            run_at=datetime.utcnow() + timedelta(minutes=5),
            parameters={},
        )

        metadata = _script_run_kwargs(
            payload,
            "android",
            existing={
                "last_task_id": "old-task",
                "last_error": "old-error",
                "last_trigger_at": "old-trigger",
                "notification_last_status": "failed",
                "notification_last_error": "old notification error",
                "notification_last_at": "2026-06-02T00:00:00",
                "notification_last_task_id": "old-task",
            },
        )

        self.assertNotIn("last_task_id", metadata)
        self.assertNotIn("last_error", metadata)
        self.assertNotIn("last_trigger_at", metadata)
        self.assertNotIn("notification_last_status", metadata)
        self.assertNotIn("notification_last_error", metadata)
        self.assertNotIn("notification_last_at", metadata)
        self.assertNotIn("notification_last_task_id", metadata)

    def test_script_run_notification_config_is_stored_but_not_exposed(self):
        payload = ScriptRunScheduleCreate(
            name="schedule",
            script_id="script-2",
            device_id="device-2",
            schedule_mode=ScriptRunScheduleMode.ONCE,
            run_at=datetime.utcnow() + timedelta(minutes=5),
            parameters={},
            notification_enabled=True,
            feishu_webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/token",
        )

        metadata = _script_run_kwargs(payload, "android")
        schedule = make_schedule(kwargs=metadata)
        response = _db_to_script_run(schedule)

        self.assertTrue(metadata["notification_enabled"])
        self.assertEqual(
            metadata["feishu_webhook_url"],
            "https://open.feishu.cn/open-apis/bot/v2/hook/token",
        )
        self.assertTrue(response.notification_enabled)
        self.assertTrue(response.feishu_webhook_configured)
        self.assertFalse(hasattr(response, "feishu_webhook_url"))

    def test_script_run_response_includes_last_task_status_and_error(self):
        schedule = make_schedule(
            kwargs={
                "kind": "script_run",
                "script_id": "script-1",
                "device_id": "device-1",
                "device_platform": "android",
                "repeat": "daily",
                "time_of_day": "09:30",
                "timezone": "Asia/Shanghai",
                "parameters": {},
                "last_task_id": "task-1",
            },
        )
        task = SimpleNamespace(
            id="task-1",
            status=TaskStatus.FAILED,
            error="Assertion failed",
            finished_at=datetime.utcnow(),
        )

        response = _db_to_script_run(schedule, task)

        self.assertEqual(response.last_task_id, "task-1")
        self.assertEqual(response.last_task_status, "failed")
        self.assertEqual(response.last_error, "Assertion failed")

    async def test_due_schedule_creates_real_task_with_queue_parameters(self):
        schedule = make_schedule()
        db = FakeDB()
        task_db = SimpleNamespace(id="task-1")

        with patch(
            "app.services.script_schedule_runner.tasks_api.create_task_record",
            new=AsyncMock(return_value=task_db),
        ) as create_task, patch(
            "app.services.script_schedule_runner.tasks_api.execute_test_task.apply_async",
        ) as enqueue_task:
            task_id = await process_due_script_schedule(schedule, db)

        self.assertEqual(task_id, "task-1")
        self.assertEqual(db.commit_count, 1)
        self.assertEqual(create_task.await_args.kwargs, {"enqueue": False})
        enqueue_task.assert_called_once_with(args=["task-1"], task_id="task-1")
        created_task = create_task.await_args.args[0]
        self.assertEqual(created_task.script_id, "script-1")
        self.assertEqual(created_task.device_id, "device-1")
        self.assertTrue(created_task.parameters["scheduled_run"])
        self.assertEqual(created_task.parameters["schedule_id"], "schedule-1")
        self.assertEqual(created_task.parameters["schedule_trigger_at"], schedule.kwargs["last_trigger_at"])
        self.assertEqual(created_task.parameters["env"], "staging")
        self.assertGreater(schedule.next_run_at, datetime.utcnow())

    async def test_trigger_failure_records_last_error_without_task(self):
        schedule = make_schedule(
            schedule_type=ScheduleType.ONETIME,
            run_at=datetime.utcnow() - timedelta(seconds=1),
            kwargs={
                "kind": "script_run",
                "script_id": "missing-script",
                "device_id": "device-1",
                "device_platform": "android",
                "repeat": "once",
                "parameters": {},
            },
        )
        db = FakeDB()

        with patch(
            "app.services.script_schedule_runner.tasks_api.create_task_record",
            new=AsyncMock(side_effect=HTTPException(status_code=404, detail="Script missing")),
        ):
            task_id = await process_due_script_schedule(schedule, db)

        self.assertIsNone(task_id)
        self.assertEqual(schedule.status, ScheduleStatus.DISABLED)
        self.assertIsNone(schedule.next_run_at)
        self.assertEqual(schedule.kwargs["last_error"], "Script missing")
        self.assertEqual(db.commit_count, 1)


if __name__ == "__main__":
    unittest.main()
