import os
import sys
import unittest
import json
from pathlib import Path

os.environ["DEBUG"] = "false"
os.environ["IOS_APPIUM_HOST"] = "http://ios-appium:4724"
os.environ["IOS_XCODE_ORG_ID"] = "TEAMID123"
os.environ["IOS_XCODE_SIGNING_ID"] = "Apple Development"
os.environ["IOS_WDA_BUNDLE_ID"] = "com.example.WebDriverAgentRunner"
os.environ["IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION"] = "true"
os.environ["APPIUM_REMOTE_ADB_HOST"] = "host.docker.internal"

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT.parent))

from app.drivers.appium import AppiumDriver


class AppiumCapabilitiesTest(unittest.TestCase):
    def test_ios_service_owned_caps_override_task_caps(self):
        driver = AppiumDriver(
            platform="ios",
            device_id="real-ios-udid",
            capabilities={
                "udid": "other-ios-udid",
                "appium:udid": "other-prefixed-ios-udid",
                "platformName": "Android",
                "automationName": "UiAutomator2",
                "appium:xcodeOrgId": "OTHERTEAM",
                "updatedWDABundleId": "com.bad.WebDriverAgentRunner",
                "bundleId": "com.apple.Preferences",
            },
        )

        caps = driver._build_options().capabilities

        self.assertEqual(caps["platformName"], "iOS")
        self.assertEqual(caps["appium:automationName"], "XCUITest")
        self.assertEqual(caps["appium:udid"], "real-ios-udid")
        self.assertEqual(caps["appium:xcodeOrgId"], "TEAMID123")
        self.assertEqual(caps["appium:updatedWDABundleId"], "com.example.WebDriverAgentRunner")
        self.assertEqual(caps["appium:bundleId"], "com.apple.Preferences")
        self.assertNotIn("udid", caps)
        self.assertNotIn("automationName", caps)

    def test_ios_internal_diagnostic_caps_are_not_sent_to_appium(self):
        driver = AppiumDriver(
            platform="ios",
            device_id="real-ios-udid",
            capabilities={
                "_device_snapshot": {"id": "real-ios-udid"},
                "_appium_diagnostics": {"appium_host": "http://ios-appium:4724"},
                "noReset": True,
            },
        )

        caps = driver._build_options().capabilities

        self.assertNotIn("_device_snapshot", caps)
        self.assertNotIn("appium:_device_snapshot", caps)
        self.assertNotIn("_appium_diagnostics", caps)
        self.assertNotIn("appium:_appium_diagnostics", caps)
        self.assertEqual(caps["appium:udid"], "real-ios-udid")

    def test_ios_sanitized_diagnostics_do_not_expose_signing_values(self):
        driver = AppiumDriver(
            platform="ios",
            device_id="real-ios-udid",
            capabilities={"noReset": True},
        )

        diagnostics = driver.sanitized_diagnostics()
        payload = json.dumps(diagnostics)

        self.assertEqual(diagnostics["appium_host"], "http://ios-appium:4724")
        self.assertEqual(diagnostics["capabilities"]["xcodeOrgId"], "configured")
        self.assertEqual(diagnostics["capabilities"]["updatedWDABundleId"], "configured")
        self.assertNotIn("TEAMID123", payload)
        self.assertNotIn("com.example.WebDriverAgentRunner", payload)

    def test_ios_error_hint_keeps_original_error(self):
        message = AppiumDriver.format_appium_error("ios", "No Account for Team TEAMID123")

        self.assertIn("WDA 签名 Team 配置异常", message)
        self.assertIn("原始错误", message)
        self.assertIn("No Account for Team", message)

    def test_sanitized_diagnostics_redact_appium_host_credentials(self):
        driver = AppiumDriver(
            platform="ios",
            device_id="real-ios-udid",
            appium_host="http://user:pass@ios-appium:4724",
        )

        diagnostics = driver.sanitized_diagnostics()

        self.assertEqual(diagnostics["appium_host"], "http://redacted@ios-appium:4724")
        self.assertNotIn("user:pass", json.dumps(diagnostics))

    def test_android_service_owned_caps_override_task_caps(self):
        driver = AppiumDriver(
            platform="android",
            device_id="real-android-serial",
            capabilities={
                "udid": "other-android-serial",
                "appium:udid": "other-prefixed-android-serial",
                "platformName": "iOS",
                "automationName": "XCUITest",
                "remoteAdbHost": "evil-host",
                "appPackage": "com.example.app",
                "appActivity": ".MainActivity",
            },
        )

        caps = driver._build_options().capabilities

        self.assertEqual(caps["platformName"], "Android")
        self.assertEqual(caps["appium:automationName"], "UiAutomator2")
        self.assertEqual(caps["appium:udid"], "real-android-serial")
        self.assertEqual(caps["appium:remoteAdbHost"], "host.docker.internal")
        self.assertEqual(caps["appium:appPackage"], "com.example.app")
        self.assertEqual(caps["appium:appActivity"], ".MainActivity")
        self.assertNotIn("udid", caps)
        self.assertNotIn("automationName", caps)


if __name__ == "__main__":
    unittest.main()
