import unittest
import os
import sys
from pathlib import Path

os.environ.setdefault("DEBUG", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models import Device, DeviceDrivers, DeviceMetrics
from app.services.metrics_service import MetricsCollector


class MetricsCollectorTest(unittest.IsolatedAsyncioTestCase):
    async def test_harmony_device_prefers_adb_metrics_when_available(self):
        collector = MetricsCollector()
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

        adb_metrics = DeviceMetrics(device_id=device.id, cpu_usage=12.5, memory_usage=42.0)
        calls = []

        async def collect_android_metrics(device_id):
            calls.append(("adb", device_id))
            return adb_metrics

        async def collect_harmony_metrics(device_id):
            calls.append(("hdc", device_id))
            return DeviceMetrics(device_id=device_id)

        collector.collect_android_metrics = collect_android_metrics
        collector.collect_harmony_metrics = collect_harmony_metrics

        result = await collector.collect_device_metrics(device)

        self.assertIs(result, adb_metrics)
        self.assertEqual(calls, [("adb", device.id)])

    async def test_collects_with_hdc_when_metrics_driver_is_hdc(self):
        collector = MetricsCollector()
        device = Device(
            id="serial-1",
            name="Harmony Device",
            model="Unknown",
            brand="Huawei",
            os="harmony",
            os_version="4.0",
            screen_resolution="1080x1920",
            screen_size=5.5,
            cpu="Unknown",
            memory="Unknown",
            storage="Unknown",
        )
        device.drivers = DeviceDrivers(metrics="hdc")

        hdc_metrics = DeviceMetrics(device_id=device.id, cpu_usage=9.0)
        calls = []

        async def collect_android_metrics(device_id):
            calls.append(("adb", device_id))
            return None

        async def collect_harmony_metrics(device_id):
            calls.append(("hdc", device_id))
            return hdc_metrics

        collector.collect_android_metrics = collect_android_metrics
        collector.collect_harmony_metrics = collect_harmony_metrics

        result = await collector.collect_device_metrics(device)

        self.assertIs(result, hdc_metrics)
        self.assertEqual(calls, [("hdc", device.id)])


if __name__ == "__main__":
    unittest.main()
