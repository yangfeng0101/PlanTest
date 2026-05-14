import importlib.util
import json
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

    def test_appium_error_extracts_json_message_and_adds_trust_hint(self):
        payload = {
            "value": {
                "message": (
                    "Unable to launch com.example.wda.xctrunner because it has an invalid code signature, "
                    "inadequate entitlements or its profile has not been explicitly trusted by the user"
                )
            }
        }

        detail = self.app_module.sanitize_appium_error(json.dumps(payload))

        self.assertIn("WDA 启动被 iPhone 安全策略拒绝", detail)
        self.assertIn("VPN 与设备管理", detail)

    def test_invalid_session_response_detection(self):
        response = httpx.Response(404)
        self.assertTrue(self.app_module.is_invalid_session_response(response))

        response = httpx.Response(500, json={"value": {"error": "invalid session id"}})
        self.assertTrue(self.app_module.is_invalid_session_response(response))

        response = httpx.Response(500, json={"value": {"error": "unknown error"}})
        self.assertFalse(self.app_module.is_invalid_session_response(response))

    def test_broken_wda_session_detail_detection(self):
        self.assertTrue(
            self.app_module.is_broken_wda_session_detail("Could not proxy command to the remote server")
        )
        self.assertTrue(self.app_module.is_broken_wda_session_detail("connect ECONNREFUSED 127.0.0.1:8100"))
        self.assertFalse(self.app_module.is_broken_wda_session_detail("xcodebuild failed with code 65"))

    def test_screen_from_window_rect_uses_positive_dimensions(self):
        screen = self.app_module.screen_from_window_rect({"x": 0, "y": 0, "width": 414, "height": 896})

        self.assertEqual(screen, {"width": 414, "height": 896})
        self.assertIsNone(self.app_module.screen_from_window_rect({"width": 0, "height": 896}))

    def test_wda_session_id_from_status_supports_top_level_session_id(self):
        payload = {"sessionId": "wda-session-1", "value": {"ready": True}}

        self.assertEqual(self.app_module.wda_session_id_from_status(payload), "wda-session-1")
        self.assertEqual(
            self.app_module.wda_session_id_from_status({"value": {"sessionId": "wda-session-2"}}),
            "wda-session-2",
        )
        self.assertIsNone(self.app_module.wda_session_id_from_status({"value": {"ready": True}}))

    def test_tap_actions_payload_uses_viewport_coordinates(self):
        payload = self.app_module.tap_actions_payload(12.4, 56.6)
        actions = payload["actions"][0]["actions"]

        self.assertEqual(actions[0]["type"], "pointerMove")
        self.assertEqual(actions[0]["origin"], "viewport")
        self.assertEqual(actions[0]["x"], 12)
        self.assertEqual(actions[0]["y"], 57)
        self.assertEqual(actions[1]["type"], "pointerDown")
        self.assertEqual(actions[-1]["type"], "pointerUp")

    def test_swipe_actions_payload_uses_duration_and_points(self):
        payload = self.app_module.swipe_actions_payload(10.2, 20.8, 110.4, 220.6, 650)
        actions = payload["actions"][0]["actions"]

        self.assertEqual(actions[0]["type"], "pointerMove")
        self.assertEqual(actions[0]["x"], 10)
        self.assertEqual(actions[0]["y"], 21)
        self.assertEqual(actions[3]["type"], "pointerMove")
        self.assertEqual(actions[3]["duration"], 650)
        self.assertEqual(actions[3]["x"], 110)
        self.assertEqual(actions[3]["y"], 221)
        self.assertEqual(actions[-1]["type"], "pointerUp")

    def test_long_press_actions_payload_holds_at_viewport_point(self):
        payload = self.app_module.long_press_actions_payload(12.4, 56.6, 900)
        actions = payload["actions"][0]["actions"]

        self.assertEqual(actions[0]["type"], "pointerMove")
        self.assertEqual(actions[0]["origin"], "viewport")
        self.assertEqual(actions[1]["type"], "pointerDown")
        self.assertEqual(actions[2], {"type": "pause", "duration": 900})
        self.assertEqual(actions[3]["type"], "pointerUp")

    def test_active_element_id_supports_w3c_and_legacy_keys(self):
        self.assertEqual(
            self.app_module.element_id_from_active_element({"element-6066-11e4-a52e-4f735466cecf": "w3c-id"}),
            "w3c-id",
        )
        self.assertEqual(self.app_module.element_id_from_active_element({"ELEMENT": "legacy-id"}), "legacy-id")
        self.assertIsNone(self.app_module.element_id_from_active_element({}))

    def test_text_value_payload_does_not_drop_non_ascii_text(self):
        payload = self.app_module.text_value_payload("你好abc")

        self.assertEqual(payload["text"], "你好abc")
        self.assertEqual(payload["value"], ["你", "好", "a", "b", "c"])

    def test_no_active_element_error_detection(self):
        self.assertTrue(self.app_module.is_no_active_element_error("unable to find an element using '(null)'"))
        self.assertFalse(self.app_module.is_no_active_element_error("xcodebuild failed"))

    def test_python_executable_prefers_current_prefix(self):
        executable = self.app_module.python_executable()

        self.assertTrue(executable)


class IOSAgentDebugSessionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ.pop("IOS_XCODE_ORG_ID", None)
        os.environ.pop("IOS_XCODE_SIGNING_ID", None)
        os.environ.pop("IOS_WDA_BUNDLE_ID", None)
        os.environ.pop("IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION", None)
        self.app_module = load_app_module()
        self.app_module.debug_sessions.clear()
        self.app_module.stream_sessions.clear()
        self.app_module.debug_session_locks.clear()
        self.app_module.stream_session_locks.clear()
        self.app_module.debug_command_locks.clear()

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

        async def fake_wda_session_id():
            return "wda-session-1"

        self.app_module.ensure_debug_allowed = fake_allowed
        self.app_module.create_appium_session = fake_create
        self.app_module.delete_appium_session = fake_delete
        self.app_module.optional_wda_session_id = fake_wda_session_id

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

    async def test_tap_endpoint_posts_actions_and_does_not_require_screen(self):
        screen_calls = []
        actions_calls = []

        async def fake_actions(udid, script, args, actions_payload):
            actions_calls.append((udid, script, args, actions_payload))
            return True, "wda direct actions"

        async def fake_screen(udid):
            screen_calls.append(udid)
            return {"width": 414, "height": 896}

        self.app_module.run_low_latency_actions_with_fallback = fake_actions
        self.app_module.appium_screen = fake_screen

        response = await self.app_module.tap_device("ios-udid", self.app_module.TapRequest(x=10.2, y=20.8))

        self.assertTrue(response["success"])
        self.assertEqual(response["x"], 10)
        self.assertEqual(response["y"], 21)
        self.assertIsNone(response["screen"])
        self.assertEqual(response["control_method"], "wda direct actions")
        self.assertIsInstance(response["latency_ms"], int)
        self.assertEqual(actions_calls[0][0], "ios-udid")
        self.assertEqual(actions_calls[0][1], "mobile: tap")
        self.assertEqual(actions_calls[0][2], {"x": 10, "y": 21})
        self.assertEqual(actions_calls[0][3]["actions"][0]["actions"][0]["x"], 10)
        self.assertEqual(screen_calls, [])

    async def test_tap_endpoint_can_include_screen_when_requested(self):
        async def fake_actions(udid, script, args, actions_payload):
            return True, "wda direct actions"

        async def fake_screen(udid):
            return {"width": 414, "height": 896}

        self.app_module.run_low_latency_actions_with_fallback = fake_actions
        self.app_module.appium_screen = fake_screen

        response = await self.app_module.tap_device(
            "ios-udid",
            self.app_module.TapRequest(x=10.2, y=20.8, includeScreen=True),
        )

        self.assertEqual(response["screen"], {"width": 414, "height": 896})

    async def test_tap_endpoint_falls_back_to_w3c_actions(self):
        async def fake_get_debug_session(udid):
            return "appium-session-1", True

        async def fake_wda_actions(udid, payload):
            raise self.app_module.HTTPException(status_code=502, detail="direct wda unsupported")

        requests = []

        async def fake_request(udid, method, endpoint, payload=None):
            requests.append((method, endpoint, payload))
            if endpoint == "execute/sync":
                raise self.app_module.HTTPException(status_code=502, detail="mobile tap unsupported")
            return {}, True

        async def fake_release(udid):
            requests.append(("POST", "release", None))

        self.app_module.get_debug_session = fake_get_debug_session
        self.app_module.wda_actions = fake_wda_actions
        self.app_module._appium_session_request = fake_request
        self.app_module.release_pointer_actions_unlocked = fake_release

        reused, control_method = await self.app_module.run_low_latency_actions_with_fallback(
            "ios-udid",
            "mobile: tap",
            {"x": 10, "y": 20},
            self.app_module.tap_actions_payload(10, 20),
        )

        self.assertTrue(reused)
        self.assertEqual(control_method, "w3c actions")
        self.assertEqual(requests[0][1], "execute/sync")
        self.assertEqual(requests[1][1], "actions")
        self.assertEqual(requests[2], ("POST", "release", None))

    async def test_text_endpoint_sends_to_active_element_without_echoing_text(self):
        calls = []

        async def fake_get(udid, endpoint):
            calls.append(("GET", endpoint, None))
            return {"element-6066-11e4-a52e-4f735466cecf": "element-1"}, False

        async def fake_post(udid, endpoint, payload):
            calls.append(("POST", endpoint, payload))
            return {}, True

        async def fake_screen(udid):
            return None

        self.app_module.appium_session_get = fake_get
        self.app_module.appium_session_post = fake_post
        self.app_module.appium_screen = fake_screen

        response = await self.app_module.input_text_device("ios-udid", self.app_module.TextRequest(text="secret"))

        self.assertTrue(response["success"])
        self.assertEqual(response["text_length"], 6)
        self.assertNotIn("text", response)
        self.assertIsNone(response["screen"])
        self.assertEqual(response["control_method"], "element value")
        self.assertIsInstance(response["latency_ms"], int)
        self.assertEqual(calls[0], ("GET", "element/active", None))
        self.assertEqual(calls[1], ("POST", "element/element-1/value", {"text": "secret", "value": list("secret")}))

    async def test_swipe_endpoint_posts_actions_and_returns_screen(self):
        screen_calls = []
        actions_calls = []

        async def fake_actions(udid, script, args, actions_payload):
            actions_calls.append((udid, script, args, actions_payload))
            return False, "wda direct actions"

        async def fake_screen(udid):
            screen_calls.append(udid)
            return {"width": 414, "height": 896}

        self.app_module.run_low_latency_actions_with_fallback = fake_actions
        self.app_module.appium_screen = fake_screen

        response = await self.app_module.swipe_device(
            "ios-udid",
            self.app_module.SwipeRequest(startX=10, startY=20, endX=30, endY=40, durationMs=700),
        )

        self.assertTrue(response["success"])
        self.assertEqual(response["durationMs"], 700)
        self.assertIsNone(response["screen"])
        self.assertEqual(response["control_method"], "wda direct actions")
        self.assertEqual(actions_calls[0][1], "mobile: dragFromToForDuration")
        self.assertEqual(actions_calls[0][2]["duration"], 0.7)
        self.assertEqual(screen_calls, [])

    async def test_long_press_endpoint_posts_actions_and_returns_screen(self):
        actions_calls = []

        async def fake_actions(udid, script, args, actions_payload):
            actions_calls.append((udid, script, args, actions_payload))
            return True, "wda direct actions"

        async def fake_screen(udid):
            return {"width": 414, "height": 896}

        self.app_module.run_low_latency_actions_with_fallback = fake_actions
        self.app_module.appium_screen = fake_screen

        response = await self.app_module.long_press_device(
            "ios-udid",
            self.app_module.LongPressRequest(x=10, y=20, durationMs=1200),
        )

        self.assertTrue(response["success"])
        self.assertEqual(response["durationMs"], 1200)
        self.assertIsNone(response["screen"])
        self.assertEqual(response["control_method"], "wda direct actions")
        self.assertEqual(actions_calls[0][1], "mobile: touchAndHold")
        self.assertEqual(actions_calls[0][2]["duration"], 1.2)

    async def test_clear_text_endpoint_clears_active_element_without_echoing_text(self):
        calls = []

        async def fake_get(udid, endpoint):
            calls.append(("GET", endpoint, None))
            return {"ELEMENT": "element-1"}, False

        async def fake_post(udid, endpoint, payload):
            calls.append(("POST", endpoint, payload))
            return {}, True

        async def fake_screen(udid):
            return None

        self.app_module.appium_session_get = fake_get
        self.app_module.appium_session_post = fake_post
        self.app_module.appium_screen = fake_screen

        response = await self.app_module.clear_text_device("ios-udid")

        self.assertTrue(response["success"])
        self.assertEqual(response["device_id"], "ios-udid")
        self.assertFalse(response["session_reused"])
        self.assertIsNone(response["screen"])
        self.assertEqual(response["control_method"], "element clear")
        self.assertIsInstance(response["latency_ms"], int)
        self.assertEqual(calls[0], ("GET", "element/active", None))
        self.assertEqual(calls[1], ("POST", "element/element-1/clear", {}))

    async def test_screenshot_endpoint_rebuilds_broken_wda_session_once(self):
        calls = []
        cleared = []

        async def fake_get(udid, endpoint):
            calls.append((udid, endpoint))
            if len(calls) == 1:
                raise self.app_module.HTTPException(
                    status_code=502,
                    detail="Could not proxy command to the remote server",
                )
            return "base64-png", False

        async def fake_clear(udid):
            cleared.append(udid)
            return True

        async def fake_screen(udid):
            return {"width": 414, "height": 896}

        self.app_module.appium_session_get = fake_get
        self.app_module.clear_debug_session = fake_clear
        self.app_module.appium_screen = fake_screen

        response = await self.app_module.get_device_screenshot("ios-udid")

        self.assertEqual(len(calls), 2)
        self.assertEqual(cleared, ["ios-udid"])
        self.assertTrue(response["session_rebuilt"])
        self.assertFalse(response["session_reused"])
        self.assertEqual(response["screen"], {"width": 414, "height": 896})

    async def test_screenshot_endpoint_keeps_generic_appium_error(self):
        async def fake_get(udid, endpoint):
            raise self.app_module.HTTPException(status_code=502, detail="xcodebuild failed with code 65")

        self.app_module.appium_session_get = fake_get

        with self.assertRaises(self.app_module.HTTPException) as ctx:
            await self.app_module.get_device_screenshot("ios-udid")

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("xcodebuild failed", ctx.exception.detail)

    async def test_text_endpoint_maps_missing_active_element_to_clear_error(self):
        async def fake_get(udid, endpoint):
            raise self.app_module.HTTPException(status_code=502, detail="unable to find an element using '(null)'")

        self.app_module.appium_session_get = fake_get

        with self.assertRaises(self.app_module.HTTPException) as ctx:
            await self.app_module.input_text_device("ios-udid", self.app_module.TextRequest(text="secret"))

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Tap an input field", ctx.exception.detail)

    async def test_clear_text_endpoint_maps_missing_active_element_to_focus_error(self):
        async def fake_get(udid, endpoint):
            raise self.app_module.HTTPException(status_code=502, detail="no such element")

        self.app_module.appium_session_get = fake_get

        with self.assertRaises(self.app_module.HTTPException) as ctx:
            await self.app_module.clear_text_device("ios-udid")

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Tap an input field", ctx.exception.detail)

    async def test_appium_session_post_rebuilds_invalid_session_once(self):
        session_calls = []
        requests = []

        async def fake_get_debug_session(udid):
            session_id = "session-1" if not session_calls else "session-2"
            session_calls.append((udid, session_id))
            return session_id, bool(session_calls) and len(session_calls) == 1

        class FakeAsyncClient:
            def __init__(self, timeout):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def request(self, method, url, json=None):
                requests.append((method, url, json))
                if len(requests) == 1:
                    return httpx.Response(404, json={"value": {"error": "invalid session id"}})
                return httpx.Response(200, json={"value": {"ok": True}})

        self.app_module.get_debug_session = fake_get_debug_session
        self.app_module.httpx.AsyncClient = FakeAsyncClient

        value, reused = await self.app_module.appium_session_post("ios-udid", "actions", {"actions": []})

        self.assertEqual(value, {"ok": True})
        self.assertFalse(reused)
        self.assertIn("/session/session-1/actions", requests[0][1])
        self.assertIn("/session/session-2/actions", requests[1][1])

    async def test_stream_session_creates_mjpeg_session_and_returns_public_url(self):
        calls = []

        async def fake_allowed(udid):
            calls.append(("allowed", udid))

        async def fake_clear_debug(udid):
            calls.append(("clear_debug", udid))
            return False

        async def fake_create(udid, extra_caps):
            calls.append(("create", udid, extra_caps))
            return "stream-session-1"

        async def fake_configure(session_id):
            calls.append(("configure", session_id))

        async def fake_request(session_id, method, endpoint, payload=None):
            calls.append(("request", session_id, method, endpoint, payload))
            return {"x": 0, "y": 0, "width": 414, "height": 896}

        async def fake_wda_session_id():
            calls.append(("wda_session_id",))
            return "wda-session-1"

        self.app_module.ensure_debug_allowed = fake_allowed
        self.app_module.clear_debug_session = fake_clear_debug
        self.app_module.create_appium_session_with_caps = fake_create
        self.app_module.configure_mjpeg_settings = fake_configure
        self.app_module.request_appium_session = fake_request
        self.app_module.optional_wda_session_id = fake_wda_session_id

        session, reused = await self.app_module.get_stream_session("ios-udid")

        self.assertFalse(reused)
        self.assertEqual(session["session_id"], "stream-session-1")
        self.assertEqual(session["mjpeg_port"], 9100)
        self.assertEqual(session["mjpeg_url"], "http://host.docker.internal:9100")
        self.assertEqual(session["screen"], {"width": 414, "height": 896})
        self.assertEqual(session["wda_session_id"], "wda-session-1")
        self.assertEqual(calls[2][0], "create")
        self.assertEqual(calls[2][2], {"appium:mjpegServerPort": 9100})

        session_again, reused_again = await self.app_module.get_stream_session("ios-udid")
        self.assertTrue(reused_again)
        self.assertIs(session_again, session)

    async def test_debug_session_reuses_active_stream_session(self):
        async def fake_allowed(udid):
            return None

        self.app_module.ensure_debug_allowed = fake_allowed
        self.app_module.stream_sessions["ios-udid"] = {
            "session_id": "stream-session-1",
            "mjpeg_port": 9100,
            "last_used_at": time.time(),
        }

        session_id, reused = await self.app_module.get_debug_session("ios-udid")

        self.assertEqual(session_id, "stream-session-1")
        self.assertTrue(reused)
        self.assertGreater(self.app_module.stream_sessions["ios-udid"]["last_used_at"], 0)

    async def test_stale_stream_session_is_replaced(self):
        deleted = []
        calls = []

        async def fake_allowed(udid):
            return None

        async def fake_delete(session_id):
            deleted.append(session_id)

        async def fake_clear_debug(udid):
            return False

        async def fake_create(udid, extra_caps):
            calls.append((udid, extra_caps))
            return "stream-session-2"

        async def fake_configure(session_id):
            return None

        async def fake_request(session_id, method, endpoint, payload=None):
            return {"x": 0, "y": 0, "width": 414, "height": 896}

        async def fake_wda_session_id():
            return "wda-session-2"

        self.app_module.ensure_debug_allowed = fake_allowed
        self.app_module.delete_appium_session = fake_delete
        self.app_module.clear_debug_session = fake_clear_debug
        self.app_module.create_appium_session_with_caps = fake_create
        self.app_module.configure_mjpeg_settings = fake_configure
        self.app_module.request_appium_session = fake_request
        self.app_module.optional_wda_session_id = fake_wda_session_id
        self.app_module.stream_sessions["ios-udid"] = {
            "session_id": "stream-session-1",
            "mjpeg_port": 9100,
            "last_used_at": time.time() - self.app_module.DEBUG_SESSION_TTL_SECONDS - 1,
        }

        session, reused = await self.app_module.get_stream_session("ios-udid")

        self.assertFalse(reused)
        self.assertEqual(deleted, ["stream-session-1"])
        self.assertEqual(session["session_id"], "stream-session-2")
        self.assertEqual(calls[0][1], {"appium:mjpegServerPort": 9100})


if __name__ == "__main__":
    unittest.main()
