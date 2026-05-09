import os
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

os.environ["DEBUG"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import Device, DeviceStatus
from app.routes import devices as device_routes
from app.services.device_service import DeviceService


def make_device(device_id: str, os_name: str = "ios", status: DeviceStatus = DeviceStatus.ONLINE) -> Device:
    device = Device(
        id=device_id,
        name="Device",
        model="iPhone16,1" if os_name == "ios" else "Pixel",
        brand="Apple" if os_name == "ios" else "Google",
        os=os_name,
        os_version="17.5" if os_name == "ios" else "14",
        status=status,
        screen_resolution="1179x2556",
        screen_size=6.1,
        cpu="arm64",
        memory="Unknown",
        storage="Unknown",
    )
    if os_name == "ios":
        DeviceService()._apply_ios_automation_capability(device, automation_ready=True)
    return device


class FakeDeviceService:
    def __init__(self, device: Device):
        self.device = device
        self.tap_calls = []
        self.text_calls = []

    async def get_device(self, device_id: str):
        return self.device if self.device.id == device_id else None

    async def tap_ios_debug(self, device_id: str, x: float, y: float):
        self.tap_calls.append((device_id, x, y))
        return {"device_id": device_id, "success": True, "x": round(x), "y": round(y)}

    async def input_ios_debug_text(self, device_id: str, text: str):
        self.text_calls.append((device_id, text))
        return {"device_id": device_id, "success": True, "text_length": len(text)}


class IOSDebugRoutesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_device_service = device_routes.device_service

    async def asyncTearDown(self):
        device_routes.device_service = self.original_device_service

    async def test_ios_tap_is_proxied_to_ios_agent(self):
        fake = FakeDeviceService(make_device("ios-1"))
        device_routes.device_service = fake

        response = await device_routes.tap_ios_static_debug(
            "ios-1",
            device_routes.IOSDebugTapRequest(x=10.2, y=20.8),
        )

        self.assertEqual(response["success"], True)
        self.assertEqual(fake.tap_calls, [("ios-1", 10.2, 20.8)])

    async def test_ios_text_is_proxied_without_echoing_text(self):
        fake = FakeDeviceService(make_device("ios-1"))
        device_routes.device_service = fake

        response = await device_routes.input_ios_static_debug_text(
            "ios-1",
            device_routes.IOSDebugTextRequest(text="secret"),
        )

        self.assertEqual(response, {"device_id": "ios-1", "success": True, "text_length": 6})
        self.assertEqual(fake.text_calls, [("ios-1", "secret")])

    async def test_ios_debug_operation_rejects_busy_device(self):
        fake = FakeDeviceService(make_device("ios-1", status=DeviceStatus.BUSY))
        device_routes.device_service = fake

        with self.assertRaises(HTTPException) as ctx:
            await device_routes.tap_ios_static_debug(
                "ios-1",
                device_routes.IOSDebugTapRequest(x=10, y=20),
            )

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(fake.tap_calls, [])

    async def test_ios_debug_operation_rejects_non_ios_device(self):
        fake = FakeDeviceService(make_device("android-1", os_name="android"))
        device_routes.device_service = fake

        with self.assertRaises(HTTPException) as ctx:
            await device_routes.tap_ios_static_debug(
                "android-1",
                device_routes.IOSDebugTapRequest(x=10, y=20),
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(fake.tap_calls, [])


if __name__ == "__main__":
    unittest.main()
