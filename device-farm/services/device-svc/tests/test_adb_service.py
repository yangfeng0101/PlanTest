import unittest
import os
import sys
from pathlib import Path

os.environ.setdefault("DEBUG", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.adb_service import ADBService


class ADBServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_detects_harmony_os_from_huawei_adb_properties(self):
        service = ADBService()
        props = {
            ("shell", "getprop", "ro.product.model"): "JAD-AL50",
            ("shell", "getprop", "ro.product.brand"): "HUAWEI",
            ("shell", "getprop", "ro.build.version.release"): "12",
            ("shell", "getprop", "hw_sc.build.os.enable"): "true",
            ("shell", "getprop", "hw_sc.build.platform.version"): "4.2.0",
            ("shell", "getprop", "hw_sc.build.os.version"): "3.0.0",
            ("shell", "wm", "size"): "Physical size: 1228x2700",
            ("shell", "wm", "density"): "Physical density: 480",
            ("shell", "getprop", "ro.product.cpu.abi"): "arm64-v8a",
            ("shell", "cat", "/proc/meminfo"): "MemTotal:        7667712 kB",
            ("shell", "df", "/data"): "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-1 486539264 1 1 1% /data",
            ("shell", "dumpsys", "battery"): "level: 94",
        }

        async def fake_execute_adb(*args, device_id=None, timeout=10.0):
            return props.get(args, "")

        service.execute_adb = fake_execute_adb

        info = await service.get_device_info("serial-1")

        self.assertEqual(info["name"], "华为 P50 Pro")
        self.assertEqual(info["os"], "harmony")
        self.assertEqual(info["os_version"], "4.2.0")


if __name__ == "__main__":
    unittest.main()
