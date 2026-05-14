from datetime import datetime
import unittest

from app.models.device import Device, DeviceStatus
from app.services.device_service import DeviceService


class DeviceOccupancyScanTest(unittest.TestCase):
    def make_device(self, status=DeviceStatus.ONLINE, occupied_by=None):
        return Device(
            id="device-1",
            name="device-1",
            model="model",
            brand="brand",
            os="android",
            os_version="1",
            status=status,
            screen_resolution="1080x1920",
            screen_size=6.0,
            cpu="arm64",
            memory="4GB",
            storage="64GB",
            occupied_by=occupied_by,
            occupied_at=datetime.utcnow() if occupied_by else None,
        )

    def test_scan_preserves_busy_when_connected_device_is_occupied(self):
        service = DeviceService()
        device = self.make_device(status=DeviceStatus.BUSY, occupied_by="screen-user")

        merged = service._merge_scanned_status(device, DeviceStatus.ONLINE)

        self.assertEqual(merged, DeviceStatus.BUSY)

    def test_scan_heals_online_device_with_existing_occupier_to_busy(self):
        service = DeviceService()
        device = self.make_device(status=DeviceStatus.ONLINE, occupied_by="screen-user")

        merged = service._merge_scanned_status(device, DeviceStatus.ONLINE)

        self.assertEqual(merged, DeviceStatus.BUSY)

    def test_scan_keeps_unoccupied_online_device_online(self):
        service = DeviceService()
        device = self.make_device(status=DeviceStatus.ONLINE)

        merged = service._merge_scanned_status(device, DeviceStatus.ONLINE)

        self.assertEqual(merged, DeviceStatus.ONLINE)

    def test_scan_allows_offline_to_override_busy_connection_state(self):
        service = DeviceService()
        device = self.make_device(status=DeviceStatus.BUSY, occupied_by="screen-user")

        merged = service._merge_scanned_status(device, DeviceStatus.OFFLINE)

        self.assertEqual(merged, DeviceStatus.OFFLINE)


if __name__ == "__main__":
    unittest.main()
