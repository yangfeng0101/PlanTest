import os
import sys
import unittest
import json
from pathlib import Path

os.environ["DEBUG"] = "false"
os.environ["IOS_APPIUM_HOST"] = "http://ios-appium:4724"
os.environ["IOS_XCODE_ORG_ID"] = "TEAMID123"
os.environ["IOS_WDA_BUNDLE_ID"] = "com.example.WebDriverAgentRunner"

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT.parent))

from app.services.task_diagnostics import merge_task_diagnostics


class TaskDiagnosticsTest(unittest.TestCase):
    def test_merges_ios_device_snapshot_and_appium_diagnostics(self):
        device = {
            "id": "ios-udid",
            "name": "du-iPhone",
            "os": "ios",
            "os_version": "17.5",
            "status": "online",
            "appium_ready": True,
            "automation_status": "verified_ready",
            "capabilities": {"automation": True, "screen_mirror": False},
            "drivers": {"automation": "appium-xcuitest", "screen": ""},
        }

        capabilities = merge_task_diagnostics(
            {"noReset": True, "_device_snapshot": {"id": "stale"}},
            device=device,
            platform="ios",
            device_id="ios-udid",
        )

        self.assertEqual(capabilities["_device_snapshot"]["id"], "ios-udid")
        self.assertEqual(capabilities["_device_snapshot"]["automation_status"], "verified_ready")
        self.assertTrue(capabilities["_device_snapshot"]["automation"])
        self.assertEqual(capabilities["_appium_diagnostics"]["appium_host"], "http://ios-appium:4724")
        self.assertEqual(capabilities["_appium_diagnostics"]["capabilities"]["xcodeOrgId"], "configured")
        self.assertEqual(capabilities["noReset"], True)

        payload = json.dumps(capabilities)
        self.assertNotIn("TEAMID123", payload)
        self.assertNotIn("com.example.WebDriverAgentRunner", payload)

    def test_android_only_merges_device_snapshot(self):
        device = {
            "id": "android-serial",
            "name": "Pixel",
            "os": "android",
            "os_version": "14",
            "status": "online",
            "capabilities": {"automation": True},
            "drivers": {"automation": "appium-uiautomator2"},
        }

        capabilities = merge_task_diagnostics(
            {"automationName": "UiAutomator2"},
            device=device,
            platform="android",
            device_id="android-serial",
        )

        self.assertEqual(capabilities["_device_snapshot"]["id"], "android-serial")
        self.assertNotIn("_appium_diagnostics", capabilities)


if __name__ == "__main__":
    unittest.main()
