import unittest
import os
import sys
from pathlib import Path

os.environ.setdefault("DEBUG", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models.device_model_map import get_market_name, should_refresh_device_name


class DeviceModelMapTest(unittest.TestCase):
    def test_huawei_p50_pro_model_codes(self):
        self.assertEqual(get_market_name("JAD-AL50"), "华为 P50 Pro")
        self.assertEqual(get_market_name("JAD-AL00"), "华为 P50 Pro")
        self.assertEqual(get_market_name("JAD-LX9"), "华为 P50 Pro")

    def test_refreshes_generated_names_only(self):
        self.assertTrue(should_refresh_device_name("JAD-AL50", "JAD-AL50", "serial-1"))
        self.assertTrue(should_refresh_device_name("serial-1", "JAD-AL50", "serial-1"))
        self.assertFalse(should_refresh_device_name("测试机 A", "JAD-AL50", "serial-1"))


if __name__ == "__main__":
    unittest.main()
