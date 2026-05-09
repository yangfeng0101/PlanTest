import importlib.util
import os
import sys
import time
import unittest
from pathlib import Path

import httpx


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def load_app_module():
    spec = importlib.util.spec_from_file_location("ios_agent_app_for_test", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class IOSAgentAppTest(unittest.TestCase):
    def setUp(self):
        os.environ.pop("IOS_XCODE_ORG_ID", None)
        os.environ.pop("IOS_XCODE_SIGNING_ID", None)
        os.environ.pop("IOS_WDA_BUNDLE_ID", None)
        os.environ.pop("IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION", None)
        self.app_module = load_app_module()

    def test_debug_capabilities_include_required_xcuitest_defaults(self):
        caps = self.app_module.ios_debug_capabilities("ios-udid")

        self.assertEqual(caps["platformName"], "iOS")
        self.assertEqual(caps["appium:automationName"], "XCUITest")
        self.assertEqual(caps["appium:udid"], "ios-udid")
        self.assertTrue(caps["appium:noReset"])
        self.assertFalse(caps["appium:waitForQuiescence"])
        self.assertNotIn("appium:xcodeOrgId", caps)
        self.assertNotIn("appium:updatedWDABundleId", caps)

    def test_debug_capabilities_add_signing_flags_only_when_configured(self):
        os.environ["IOS_XCODE_ORG_ID"] = "TEAMID123"
        os.environ["IOS_XCODE_SIGNING_ID"] = "Apple Development"
        os.environ["IOS_WDA_BUNDLE_ID"] = "com.example.wda"
        os.environ["IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION"] = "true"
        module = load_app_module()

        caps = module.ios_debug_capabilities("ios-udid")

        self.assertEqual(caps["appium:xcodeOrgId"], "TEAMID123")
        self.assertEqual(caps["appium:xcodeSigningId"], "Apple Development")
        self.assertEqual(caps["appium:updatedWDABundleId"], "com.example.wda")
        self.assertTrue(caps["appium:allowProvisioningDeviceRegistration"])

    def test_appium_error_sanitizes_signing_values(self):
        os.environ["IOS_XCODE_ORG_ID"] = "TEAMID123"
        os.environ["IOS_WDA_BUNDLE_ID"] = "com.example.wda"
        module = load_app_module()

        detail = module.sanitize_appium_error("team TEAMID123 failed for com.example.wda")

        self.assertEqual(detail, "team <configured> failed for <configured>")

    def test_invalid_session_response_detection(self):
        response = httpx.Response(404)
        self.assertTrue(self.app_module.is_invalid_session_response(response))

        response = httpx.Response(500, json={"value": {"error": "invalid session id"}})
        self.assertTrue(self.app_module.is_invalid_session_response(response))

        response = httpx.Response(500, json={"value": {"error": "unknown error"}})
        self.assertFalse(self.app_module.is_invalid_session_response(response))


class IOSAgentDebugSessionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ.pop("IOS_XCODE_ORG_ID", None)
        os.environ.pop("IOS_XCODE_SIGNING_ID", None)
        os.environ.pop("IOS_WDA_BUNDLE_ID", None)
        os.environ.pop("IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION", None)
        self.app_module = load_app_module()
        self.app_module.debug_sessions.clear()
        self.app_module.debug_session_locks.clear()

    async def test_debug_session_is_reused_until_ttl_expires(self):
        calls = 0

        async def fake_allowed(udid):
            return None

        async def fake_create(udid):
            nonlocal calls
            calls += 1
            return f"session-{calls}"

        async def fake_delete(session_id):
            return None

        self.app_module.ensure_debug_allowed = fake_allowed
        self.app_module.create_appium_session = fake_create
        self.app_module.delete_appium_session = fake_delete

        session_id, reused = await self.app_module.get_debug_session("ios-udid")
        self.assertEqual(session_id, "session-1")
        self.assertFalse(reused)

        session_id, reused = await self.app_module.get_debug_session("ios-udid")
        self.assertEqual(session_id, "session-1")
        self.assertTrue(reused)
        self.assertEqual(calls, 1)

        self.app_module.debug_sessions["ios-udid"]["last_used_at"] = time.time() - self.app_module.DEBUG_SESSION_TTL_SECONDS - 1
        session_id, reused = await self.app_module.get_debug_session("ios-udid")
        self.assertEqual(session_id, "session-2")
        self.assertFalse(reused)
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
