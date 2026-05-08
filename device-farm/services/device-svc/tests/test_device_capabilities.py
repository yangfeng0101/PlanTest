import unittest
import os
import sys
from pathlib import Path

os.environ["DEBUG"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import Device


class DeviceCapabilitiesTest(unittest.TestCase):
    def test_harmony_via_adb_runtime_capabilities(self):
        device = Device(
            id="serial-1",
            name="华为 P50 Pro",
            model="JAD-AL50",
            brand="HUAWEI",
            os="harmony",
            os_version="4.2.0",
            screen_resolution="1228x2700",
            screen_size=6.6,
            cpu="arm64-v8a",
            memory="7488MB",
            storage="464GB",
        )

        self.assertEqual(device.display_os, "HarmonyOS")
        self.assertEqual(device.display_os_version, "4.2.0")
        self.assertEqual(device.connection_type, "adb")
        self.assertEqual(device.drivers.metrics, "adb")
        self.assertEqual(device.drivers.screen, "scrcpy")
        self.assertEqual(device.drivers.ui_hierarchy, "uiautomator")
        self.assertEqual(device.drivers.automation, "appium-uiautomator2")
        self.assertTrue(device.capabilities.metrics)
        self.assertTrue(device.capabilities.screen_mirror)
        self.assertTrue(device.capabilities.ui_hierarchy)
        self.assertTrue(device.capabilities.automation)

    def test_android_runtime_capabilities(self):
        device = Device(
            id="serial-2",
            name="Pixel",
            model="Pixel",
            brand="Google",
            os="android",
            os_version="14",
            screen_resolution="1080x2400",
            screen_size=6.1,
            cpu="arm64-v8a",
            memory="8192MB",
            storage="128GB",
        )

        self.assertEqual(device.display_os, "Android")
        self.assertEqual(device.connection_type, "adb")
        self.assertEqual(device.drivers.metrics, "adb")
        self.assertTrue(device.capabilities.remote_control)
        self.assertTrue(device.capabilities.automation)

    def test_ios_runtime_capabilities_do_not_enable_screen_v1(self):
        device = Device(
            id="ios-1",
            name="iPhone",
            model="iPhone16,1",
            brand="Apple",
            os="ios",
            os_version="17.5",
            screen_resolution="1179x2556",
            screen_size=6.1,
            cpu="arm64",
            memory="Unknown",
            storage="Unknown",
        )

        self.assertEqual(device.display_os, "iOS")
        self.assertEqual(device.connection_type, "wda")
        self.assertEqual(device.drivers.metrics, "pymobiledevice3")
        self.assertEqual(device.drivers.screen, "")
        self.assertEqual(device.drivers.ui_hierarchy, "")
        self.assertEqual(device.drivers.control, "")
        self.assertEqual(device.drivers.automation, "")
        self.assertTrue(device.capabilities.metrics)
        self.assertFalse(device.capabilities.screen_mirror)
        self.assertFalse(device.capabilities.remote_control)
        self.assertFalse(device.capabilities.ui_hierarchy)
        self.assertFalse(device.capabilities.screenshot)
        self.assertFalse(device.capabilities.automation)
        self.assertIsNone(device.appium_ready)
        self.assertIsNone(device.automation_status)


if __name__ == "__main__":
    unittest.main()
