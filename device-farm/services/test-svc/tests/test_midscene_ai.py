import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["DEBUG"] = "false"

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT.parent))

from app.config import settings
from app.tasks.executor import DeviceFarmApp


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"success": True, "result": {"center": [12, 34]}}


class FakeClient:
    last_json = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        self.__class__.last_json = json
        return FakeResponse()


class MidsceneAITest(unittest.TestCase):
    def setUp(self):
        self.original_runner_url = settings.MIDSCENE_RUNNER_URL
        settings.MIDSCENE_RUNNER_URL = "http://midscene-runner:8005"
        FakeClient.last_json = None

    def tearDown(self):
        settings.MIDSCENE_RUNNER_URL = self.original_runner_url

    def test_ios_ai_operation_is_forwarded_with_platform(self):
        context = {
            "task_id": "task-ios",
            "device_id": "ios-udid",
            "platform": "ios",
            "driver": object(),
            "logs": [],
        }
        app = DeviceFarmApp(context)

        with (
            patch("httpx.Client", FakeClient),
            patch("app.tasks.executor.log_message"),
        ):
            result = app.ai_locate("设置")

        self.assertEqual(result, {"center": [12, 34]})
        self.assertEqual(FakeClient.last_json["platform"], "ios")
        self.assertEqual(FakeClient.last_json["operation"], "ai_locate")
        self.assertEqual(FakeClient.last_json["device_id"], "ios-udid")

    def test_ai_operation_defaults_to_android_platform(self):
        context = {
            "task_id": "task-android",
            "device_id": "android-serial",
            "driver": object(),
            "logs": [],
        }
        app = DeviceFarmApp(context)

        with (
            patch("httpx.Client", FakeClient),
            patch("app.tasks.executor.log_message"),
        ):
            result = app.ai_locate("设置")

        self.assertEqual(result, {"center": [12, 34]})
        self.assertEqual(FakeClient.last_json["platform"], "android")
        self.assertEqual(FakeClient.last_json["operation"], "ai_locate")
        self.assertEqual(FakeClient.last_json["device_id"], "android-serial")


if __name__ == "__main__":
    unittest.main()
