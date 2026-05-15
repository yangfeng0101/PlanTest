import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ["DEBUG"] = "false"

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT.parent))

from app.models.models import DevicePlatform, Task, TaskStatus
from app.tasks.executor import (
    DeviceBusyRetry,
    acquire_task_device,
    release_task_device,
)


def make_task(**overrides) -> Task:
    data = {
        "id": "task-1",
        "script_id": "script-1",
        "device_id": "device-1",
        "device_platform": DevicePlatform.ANDROID,
        "device_capabilities": {},
        "parameters": {},
        "status": TaskStatus.PENDING,
    }
    data.update(overrides)
    return Task(**data)


class TaskQueueTest(unittest.IsolatedAsyncioTestCase):
    async def test_online_task_acquires_owned_device_lease(self):
        task = make_task()
        with (
            patch("app.tasks.executor.tasks_api._get_device", new=AsyncMock(return_value={"status": "online"})),
            patch("app.tasks.executor.tasks_api._occupy_device", new=AsyncMock()) as occupy,
        ):
            acquired = await acquire_task_device(task)

        self.assertTrue(acquired)
        occupy.assert_awaited_once_with("device-1", "test-svc:task-1")

    async def test_busy_normal_task_stays_pending_for_retry(self):
        task = make_task()
        with patch("app.tasks.executor.tasks_api._get_device", new=AsyncMock(return_value={"status": "busy"})):
            with self.assertRaises(DeviceBusyRetry):
                await acquire_task_device(task)

    async def test_busy_screen_debug_task_shares_screen_lease(self):
        task = make_task(parameters={"screen_debug": True})
        with (
            patch(
                "app.tasks.executor.tasks_api._get_device",
                new=AsyncMock(return_value={"status": "busy", "occupied_by": "screen-user"}),
            ),
            patch("app.tasks.executor.tasks_api._occupy_device", new=AsyncMock()) as occupy,
        ):
            acquired = await acquire_task_device(task)

        self.assertFalse(acquired)
        occupy.assert_not_awaited()

    async def test_release_task_device_only_releases_owned_lease(self):
        with patch("app.tasks.executor.tasks_api._release_device_if_owned", new=AsyncMock()) as release:
            await release_task_device("device-1", "task-1")

        release.assert_awaited_once_with("device-1", "test-svc:task-1")


if __name__ == "__main__":
    unittest.main()
