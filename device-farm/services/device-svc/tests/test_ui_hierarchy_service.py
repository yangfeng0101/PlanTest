import unittest
import os
import sys
from pathlib import Path

os.environ.setdefault("DEBUG", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models.ui_hierarchy import UIScreen
from app.services.ui_hierarchy_service import UIHierarchyError, UIHierarchyService


SAMPLE_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.demo" content-desc="" clickable="false" enabled="true" selected="false" focused="false" scrollable="false" bounds="[0,0][1080,2400]">
    <node index="0" text="登录" resource-id="com.demo:id/login" class="android.widget.Button" package="com.demo" content-desc="登录按钮" clickable="true" enabled="true" selected="false" focused="false" scrollable="false" bounds="[10,20][110,60]" />
    <node index="1" text="用户名" resource-id="" class="android.widget.TextView" package="com.demo" content-desc="" clickable="false" enabled="true" selected="false" focused="false" scrollable="false" bounds="[20,80][220,120]" />
  </node>
</hierarchy>
"""


class UIHierarchyServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = UIHierarchyService()

    def test_parse_bounds(self):
        bounds = self.service.parse_bounds("[10,20][110,60]")

        self.assertEqual(bounds.x, 10)
        self.assertEqual(bounds.y, 20)
        self.assertEqual(bounds.width, 100)
        self.assertEqual(bounds.height, 40)

    def test_parse_xml_elements_and_selectors(self):
        result = self.service.parse_android_hierarchy(
            SAMPLE_XML,
            "device-1",
            UIScreen(width=1080, height=2400),
        )

        self.assertEqual(result.device_id, "device-1")
        self.assertEqual(result.screen.width, 1080)
        self.assertEqual(len(result.elements), 3)

        button = next(e for e in result.elements if e.resource_id == "com.demo:id/login")
        self.assertEqual(button.text, "登录")
        self.assertEqual(button.content_desc, "登录按钮")
        self.assertTrue(button.clickable)
        self.assertEqual(button.center.x, 60)
        self.assertEqual(button.center.y, 40)
        self.assertEqual(button.xpath, "//*[@resource-id='com.demo:id/login']")
        self.assertEqual([s.type for s in button.selector_suggestions], ["id", "accessibility_id", "text", "xpath"])

        text = next(e for e in result.elements if e.text == "用户名")
        self.assertEqual(text.xpath, "//*[@text='用户名']")
        self.assertEqual(text.selector_suggestions[0].type, "text")

    def test_prefers_device_screen_resolution_over_element_max_bounds(self):
        result = self.service.parse_android_hierarchy(
            SAMPLE_XML,
            "device-1",
            UIScreen(width=1228, height=2700),
        )

        self.assertEqual(result.screen.width, 1228)
        self.assertEqual(result.screen.height, 2700)

    def test_extract_xml_from_uiautomator_noise(self):
        noisy = "UI hierchary dumped to: /dev/tty\n" + SAMPLE_XML + "\nDone"
        result = self.service.parse_android_hierarchy(noisy, "device-1")

        self.assertEqual(len(result.elements), 3)

    def test_empty_xml_fails_cleanly(self):
        with self.assertRaises(UIHierarchyError):
            self.service.parse_android_hierarchy("", "device-1")

    def test_invalid_xml_fails_cleanly(self):
        with self.assertRaises(UIHierarchyError):
            self.service.parse_android_hierarchy("<hierarchy><node></hierarchy>", "device-1")


if __name__ == "__main__":
    unittest.main()
