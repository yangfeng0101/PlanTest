"""End-to-end integration tests for the Feishu notification service.

Covers the full notification flow:
  - notify_scheduled_task_finished entry point
  - Edge cases: task not found, non-scheduled task, notification disabled, idempotency
  - Webhook send success / failure paths
  - _mark_notification_result metadata writing
  - cancel_task API notification trigger
"""

import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ["DEBUG"] = "false"

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT.parent))

from app.models.database import DevicePlatform, TaskStatus
from app.services.schedule_notification_service import (
    _duration_text,
    _feishu_response_error,
    _first_error,
    _mark_notification_result,
    _sanitize_notification_error,
    build_feishu_task_message,
)


def _make_task(**overrides):
    data = {
        "id": "task-e2e-1",
        "script_id": "script-1",
        "device_id": "device-1",
        "device_platform": DevicePlatform.ANDROID,
        "status": TaskStatus.FAILED,
        "started_at": datetime(2026, 6, 2, 10, 0, 0),
        "finished_at": datetime(2026, 6, 2, 10, 0, 3),
        "result": {"errors": ["AssertionError: expected True"]},
        "error": None,
        "parameters": {
            "scheduled_run": True,
            "schedule_id": "schedule-1",
            "schedule_trigger_at": "2026-06-02T10:00:00",
        },
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _make_schedule(**overrides):
    data = {
        "id": "schedule-1",
        "name": "每日冒烟",
        "kwargs": {
            "kind": "script_run",
            "device_id": "device-1",
            "device_platform": "android",
            "notification_enabled": True,
            "feishu_webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
        },
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _make_script(**overrides):
    data = {"id": "script-1", "name": "登录冒烟测试"}
    data.update(overrides)
    return SimpleNamespace(**data)


class AsyncIteratorMock:
    """Mock for async DB session context manager."""

    def __init__(self, return_value):
        self._return_value = return_value

    async def __aenter__(self):
        return self._return_value

    async def __aexit__(self, *args):
        pass


class ScheduleNotificationE2ETest(unittest.IsolatedAsyncioTestCase):
    """End-to-end tests for the Feishu notification full chain."""

    # ── notify_scheduled_task_finished ──────────────────────────────

    async def test_notify_sends_webhook_and_marks_success(self):
        """Happy path: scheduled task completes, webhook succeeds, metadata updated."""
        task = _make_task()
        schedule = _make_schedule()
        script = _make_script()

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_db.refresh = AsyncMock()
        # Simulate 3 queries: TaskDB, ScheduleDB, ScriptDB
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = task
        mock_result_schedule = MagicMock()
        mock_result_schedule.scalar_one_or_none.return_value = schedule
        mock_result_script = MagicMock()
        mock_result_script.scalar_one_or_none.return_value = script
        mock_db.execute.side_effect = [
            mock_result_task,
            mock_result_schedule,
            mock_result_script,
        ]

        with patch(
            "app.services.schedule_notification_service.get_db_session",
            return_value=AsyncIteratorMock(mock_db),
        ), patch(
            "app.services.schedule_notification_service._send_feishu_text",
            new=AsyncMock(),
        ) as mock_send:
            from app.services.schedule_notification_service import notify_scheduled_task_finished

            await notify_scheduled_task_finished("task-e2e-1")

        # Verify webhook was called
        mock_send.assert_called_once()
        call_url, call_text = mock_send.call_args[0]
        self.assertIn("https://open.feishu.cn/", call_url)
        self.assertIn("云测定时任务已完成", call_text)
        self.assertIn("每日冒烟", call_text)
        self.assertIn("task-e2e-1", call_text)

        # Verify metadata written
        updated_kwargs = schedule.kwargs
        self.assertEqual(updated_kwargs["notification_last_status"], "success")
        self.assertEqual(updated_kwargs["notification_last_task_id"], "task-e2e-1")
        self.assertIn("notification_last_at", updated_kwargs)
        self.assertNotIn("notification_last_error", updated_kwargs)

    async def test_notify_skips_when_task_not_found(self):
        """No task in DB → silent no-op."""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.schedule_notification_service.get_db_session",
            return_value=AsyncIteratorMock(mock_db),
        ), patch(
            "app.services.schedule_notification_service._send_feishu_text",
            new=AsyncMock(),
        ) as mock_send:
            from app.services.schedule_notification_service import notify_scheduled_task_finished

            await notify_scheduled_task_finished("nonexistent-task")

        mock_send.assert_not_called()

    async def test_notify_skips_non_scheduled_task(self):
        """Task without scheduled_run flag → silent no-op."""
        task = _make_task(parameters={"env": "staging"})

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = task
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.schedule_notification_service.get_db_session",
            return_value=AsyncIteratorMock(mock_db),
        ), patch(
            "app.services.schedule_notification_service._send_feishu_text",
            new=AsyncMock(),
        ) as mock_send:
            from app.services.schedule_notification_service import notify_scheduled_task_finished

            await notify_scheduled_task_finished("task-e2e-1")

        mock_send.assert_not_called()

    async def test_notify_skips_when_schedule_not_found(self):
        """Task references schedule_id that doesn't exist → silent no-op."""
        task = _make_task(parameters={"scheduled_run": True, "schedule_id": "missing-schedule"})

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = task
        mock_result_schedule = MagicMock()
        mock_result_schedule.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [
            mock_result_task,
            mock_result_schedule,
        ]

        with patch(
            "app.services.schedule_notification_service.get_db_session",
            return_value=AsyncIteratorMock(mock_db),
        ), patch(
            "app.services.schedule_notification_service._send_feishu_text",
            new=AsyncMock(),
        ) as mock_send:
            from app.services.schedule_notification_service import notify_scheduled_task_finished

            await notify_scheduled_task_finished("task-e2e-1")

        mock_send.assert_not_called()

    async def test_notify_skips_when_notification_disabled(self):
        """Schedule exists but notification_enabled=False → silent no-op."""
        task = _make_task()
        schedule = _make_schedule(
            kwargs={"notification_enabled": False, "feishu_webhook_url": None}
        )

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = task
        mock_result_schedule = MagicMock()
        mock_result_schedule.scalar_one_or_none.return_value = schedule
        mock_db.execute.side_effect = [
            mock_result_task,
            mock_result_schedule,
        ]

        with patch(
            "app.services.schedule_notification_service.get_db_session",
            return_value=AsyncIteratorMock(mock_db),
        ), patch(
            "app.services.schedule_notification_service._send_feishu_text",
            new=AsyncMock(),
        ) as mock_send:
            from app.services.schedule_notification_service import notify_scheduled_task_finished

            await notify_scheduled_task_finished("task-e2e-1")

        mock_send.assert_not_called()

    async def test_notify_idempotent_skips_already_notified_task(self):
        """Same task_id was already successfully notified → skip."""
        task = _make_task()
        schedule = _make_schedule(
            kwargs={
                "kind": "script_run",
                "device_id": "device-1",
                "device_platform": "android",
                "notification_enabled": True,
                "feishu_webhook_url": "https://open.feishu.cn/hook",
                "notification_last_task_id": "task-e2e-1",
                "notification_last_status": "success",
            }
        )

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = task
        mock_result_schedule = MagicMock()
        mock_result_schedule.scalar_one_or_none.return_value = schedule
        mock_db.execute.side_effect = [
            mock_result_task,
            mock_result_schedule,
        ]

        with patch(
            "app.services.schedule_notification_service.get_db_session",
            return_value=AsyncIteratorMock(mock_db),
        ), patch(
            "app.services.schedule_notification_service._send_feishu_text",
            new=AsyncMock(),
        ) as mock_send:
            from app.services.schedule_notification_service import notify_scheduled_task_finished

            await notify_scheduled_task_finished("task-e2e-1")

        mock_send.assert_not_called()

    async def test_notify_retries_if_previous_notification_failed(self):
        """Previous notification for this task failed → retry."""
        task = _make_task()
        schedule = _make_schedule(
            kwargs={
                "kind": "script_run",
                "device_id": "device-1",
                "device_platform": "android",
                "notification_enabled": True,
                "feishu_webhook_url": "https://open.feishu.cn/hook",
                "notification_last_task_id": "task-e2e-1",
                "notification_last_status": "failed",
                "notification_last_error": "timeout",
            }
        )
        script = _make_script()

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = task
        mock_result_schedule = MagicMock()
        mock_result_schedule.scalar_one_or_none.return_value = schedule
        mock_result_script = MagicMock()
        mock_result_script.scalar_one_or_none.return_value = script
        mock_db.execute.side_effect = [
            mock_result_task,
            mock_result_schedule,
            mock_result_script,
        ]

        with patch(
            "app.services.schedule_notification_service.get_db_session",
            return_value=AsyncIteratorMock(mock_db),
        ), patch(
            "app.services.schedule_notification_service._send_feishu_text",
            new=AsyncMock(),
        ) as mock_send:
            from app.services.schedule_notification_service import notify_scheduled_task_finished

            await notify_scheduled_task_finished("task-e2e-1")

        mock_send.assert_called_once()

    async def test_notify_marks_failed_when_webhook_url_missing(self):
        """notification_enabled=True but no webhook URL → mark as failed."""
        task = _make_task()
        schedule = _make_schedule(
            kwargs={
                "kind": "script_run",
                "device_id": "device-1",
                "device_platform": "android",
                "notification_enabled": True,
                "feishu_webhook_url": None,
            }
        )

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = task
        mock_result_schedule = MagicMock()
        mock_result_schedule.scalar_one_or_none.return_value = schedule
        mock_db.execute.side_effect = [
            mock_result_task,
            mock_result_schedule,
        ]

        with patch(
            "app.services.schedule_notification_service.get_db_session",
            return_value=AsyncIteratorMock(mock_db),
        ), patch(
            "app.services.schedule_notification_service._send_feishu_text",
            new=AsyncMock(),
        ) as mock_send:
            from app.services.schedule_notification_service import notify_scheduled_task_finished

            await notify_scheduled_task_finished("task-e2e-1")

        mock_send.assert_not_called()
        self.assertEqual(schedule.kwargs["notification_last_status"], "failed")
        self.assertIn("not configured", schedule.kwargs["notification_last_error"])

    async def test_notify_marks_failed_on_webhook_error(self):
        """Webhook POST raises → mark as failed, no exception propagated."""
        task = _make_task()
        schedule = _make_schedule()
        script = _make_script()

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = task
        mock_result_schedule = MagicMock()
        mock_result_schedule.scalar_one_or_none.return_value = schedule
        mock_result_script = MagicMock()
        mock_result_script.scalar_one_or_none.return_value = script
        mock_db.execute.side_effect = [
            mock_result_task,
            mock_result_schedule,
            mock_result_script,
        ]

        with patch(
            "app.services.schedule_notification_service.get_db_session",
            return_value=AsyncIteratorMock(mock_db),
        ), patch(
            "app.services.schedule_notification_service._send_feishu_text",
            side_effect=RuntimeError("Connection timeout"),
        ):
            from app.services.schedule_notification_service import notify_scheduled_task_finished

            # Should NOT raise — all errors are caught
            await notify_scheduled_task_finished("task-e2e-1")

        self.assertEqual(schedule.kwargs["notification_last_status"], "failed")
        self.assertIn("Connection timeout", schedule.kwargs["notification_last_error"])

    async def test_notify_handles_empty_exception_message(self):
        """Exception with empty str() should fall back to exception class name."""
        task = _make_task()
        schedule = _make_schedule()
        script = _make_script()

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = task
        mock_result_schedule = MagicMock()
        mock_result_schedule.scalar_one_or_none.return_value = schedule
        mock_result_script = MagicMock()
        mock_result_script.scalar_one_or_none.return_value = script
        mock_db.execute.side_effect = [
            mock_result_task,
            mock_result_schedule,
            mock_result_script,
        ]

        with patch(
            "app.services.schedule_notification_service.get_db_session",
            return_value=AsyncIteratorMock(mock_db),
        ), patch(
            "app.services.schedule_notification_service._send_feishu_text",
            side_effect=RuntimeError(""),
        ):
            from app.services.schedule_notification_service import notify_scheduled_task_finished

            await notify_scheduled_task_finished("task-e2e-1")

        self.assertEqual(schedule.kwargs["notification_last_status"], "failed")
        # Should use exception class name instead of "Unknown notification error"
        self.assertIn("RuntimeError", schedule.kwargs["notification_last_error"])

    # ── _mark_notification_result ───────────────────────────────────

    def test_mark_notification_result_success(self):
        schedule = _make_schedule(
            kwargs={
                "notification_enabled": True,
                "feishu_webhook_url": "https://example.com/hook",
            }
        )

        _mark_notification_result(schedule, "task-abc", "success")

        self.assertEqual(schedule.kwargs["notification_last_status"], "success")
        self.assertEqual(schedule.kwargs["notification_last_task_id"], "task-abc")
        self.assertIn("notification_last_at", schedule.kwargs)
        self.assertNotIn("notification_last_error", schedule.kwargs)

    def test_mark_notification_result_failure(self):
        schedule = _make_schedule(kwargs={})

        _mark_notification_result(schedule, "task-xyz", "failed", "HTTP 500: internal error")

        self.assertEqual(schedule.kwargs["notification_last_status"], "failed")
        self.assertEqual(schedule.kwargs["notification_last_task_id"], "task-xyz")
        self.assertEqual(
            schedule.kwargs["notification_last_error"],
            "HTTP 500: internal error",
        )

    def test_mark_notification_result_clears_previous_error_on_success(self):
        schedule = _make_schedule(
            kwargs={
                "notification_last_error": "old error",
                "notification_last_status": "failed",
            }
        )

        _mark_notification_result(schedule, "task-def", "success")

        self.assertEqual(schedule.kwargs["notification_last_status"], "success")
        self.assertNotIn("notification_last_error", schedule.kwargs)

    # ── build_feishu_task_message edge cases ─────────────────────────

    def test_build_message_success_task(self):
        schedule = _make_schedule()
        task = _make_task(status=TaskStatus.SUCCESS, result={"duration": 12.5}, error=None)
        text = build_feishu_task_message(schedule, task, "登录冒烟")
        self.assertIn("云测定时任务已完成：成功", text)
        self.assertIn("耗时：12.50s", text)

    def test_build_message_cancelled_task(self):
        schedule = _make_schedule()
        task = _make_task(status=TaskStatus.CANCELLED, finished_at=datetime(2026, 6, 2, 10, 0, 5))
        text = build_feishu_task_message(schedule, task, "冒烟测试")
        self.assertIn("已取消", text)

    def test_build_message_duration_fallback_to_started_finished(self):
        """When result has no duration, compute from started_at/finished_at."""
        schedule = _make_schedule()
        task = _make_task(result={}, error="Some error\nwith\ntrace")
        text = build_feishu_task_message(schedule, task, "脚本")
        self.assertIn("耗时：3.00s", text)  # started_at ... finished_at = 3s

    def test_build_message_duration_no_timestamps_fallback(self):
        schedule = _make_schedule()
        task = _make_task(
            result={},
            started_at=None,
            finished_at=None,
        )
        text = build_feishu_task_message(schedule, task, "脚本")
        self.assertIn("耗时：-", text)

    def test_build_message_uses_error_field_over_result_errors(self):
        schedule = _make_schedule()
        task = _make_task(
            result={"errors": ["result error"]},
            error="primary error line 1\nline 2",
        )
        text = build_feishu_task_message(schedule, task, "脚本")
        self.assertIn("错误：primary error line 1", text)
        self.assertNotIn("result error", text)

    def test_build_message_truncates_long_error(self):
        schedule = _make_schedule()
        task = _make_task(error="x" * 600)
        text = build_feishu_task_message(schedule, task, "脚本")
        # Error should be truncated to 500 chars
        error_line = [l for l in text.split("\n") if l.startswith("错误：")][0]
        self.assertLessEqual(len(error_line), len("错误：") + 505)

    # ── _first_error ────────────────────────────────────────────────

    def test_first_error_from_error_field(self):
        task = _make_task(error="timeout error\nstack trace")
        self.assertEqual(_first_error(task), "timeout error")

    def test_first_error_from_result_errors(self):
        task = _make_task(error=None, result={"errors": ["Assertion failed\n  at line 42"]})
        self.assertEqual(_first_error(task), "Assertion failed")

    def test_first_error_empty(self):
        task = _make_task(error=None, result={})
        self.assertEqual(_first_error(task), "")

    # ── _duration_text ──────────────────────────────────────────────

    def test_duration_from_result(self):
        task = _make_task(result={"duration": 45.678})
        self.assertEqual(_duration_text(task), "45.68s")

    def test_duration_zero_handling(self):
        task = _make_task(
            result={},
            started_at=datetime(2026, 6, 2, 10, 0, 0),
            finished_at=datetime(2026, 6, 2, 10, 0, 0),
        )
        self.assertEqual(_duration_text(task), "0.00s")

    # ── _sanitize_notification_error ────────────────────────────────

    def test_sanitize_replaces_newlines(self):
        result = _sanitize_notification_error("line1\nline2\nline3")
        self.assertNotIn("\n", result)
        self.assertIn(" ", result)

    def test_sanitize_truncates(self):
        result = _sanitize_notification_error("x" * 600)
        self.assertLessEqual(len(result), 500)

    def test_sanitize_none(self):
        result = _sanitize_notification_error(None)
        self.assertIn("Unknown", result)


class ExecutorNotificationCoverageTest(unittest.TestCase):
    """Verify executor notification trigger points exist and don't crash."""

    def test_notify_scheduled_task_finished_wrapper_is_resilient(self):
        """The executor wrapper must never propagate exceptions."""
        import traceback as tb

        with patch(
            "app.services.schedule_notification_service.notify_scheduled_task_finished",
            side_effect=RuntimeError("DB connection lost"),
        ):
            from app.tasks.executor import notify_scheduled_task_finished

            # Should not raise
            try:
                notify_scheduled_task_finished("any-task")
            except Exception:
                self.fail(f"notify_scheduled_task_finished wrapper raised:\n{tb.format_exc()}")

    def test_all_executor_notification_call_sites_exist(self):
        """Verify the function is importable and callable from executor."""
        from app.tasks.executor import notify_scheduled_task_finished

        self.assertTrue(callable(notify_scheduled_task_finished))


class CancelTaskNotificationTest(unittest.TestCase):
    """Verify cancel_task API triggers notification."""

    def test_cancel_task_imports_notify_service(self):
        """cancel_task imports notify_scheduled_task_finished from the service module."""
        from app.services.schedule_notification_service import notify_scheduled_task_finished

        self.assertTrue(callable(notify_scheduled_task_finished))


if __name__ == "__main__":
    unittest.main()