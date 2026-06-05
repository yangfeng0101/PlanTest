import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx

os.environ["DEBUG"] = "false"

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT.parent))

from app.models.database import DevicePlatform, TaskStatus
from app.services.schedule_notification_service import (
    _feishu_response_error,
    build_feishu_task_message,
)


class ScheduleNotificationServiceTest(unittest.TestCase):
    def test_build_feishu_task_message_includes_task_result(self):
        schedule = SimpleNamespace(
            id="schedule-1",
            name="每日冒烟",
            kwargs={"device_id": "device-1", "device_platform": "android"},
        )
        task = SimpleNamespace(
            id="task-1",
            script_id="script-1",
            device_id="device-1",
            device_platform=DevicePlatform.ANDROID,
            status=TaskStatus.FAILED,
            started_at=datetime(2026, 6, 2, 10, 0, 0),
            finished_at=datetime(2026, 6, 2, 10, 0, 3),
            result={"errors": ["Assertion failed\ntrace"]},
            error=None,
        )

        text = build_feishu_task_message(schedule, task, "登录冒烟")

        self.assertIn("云测定时任务已完成：失败", text)
        self.assertIn("计划：每日冒烟", text)
        self.assertIn("脚本：登录冒烟", text)
        self.assertIn("任务：task-1", text)
        self.assertIn("耗时：3.00s", text)
        self.assertIn("错误：Assertion failed", text)

    def test_feishu_response_error_accepts_success_code(self):
        response = httpx.Response(200, json={"code": 0, "msg": "success"})

        self.assertIsNone(_feishu_response_error(response))

    def test_feishu_response_error_returns_code_message(self):
        response = httpx.Response(200, json={"code": 19021, "msg": "invalid webhook"})

        self.assertIn("19021", _feishu_response_error(response))

    def test_feishu_response_error_returns_http_error(self):
        response = httpx.Response(500, text="server error")

        self.assertIn("HTTP 500", _feishu_response_error(response))


if __name__ == "__main__":
    unittest.main()
