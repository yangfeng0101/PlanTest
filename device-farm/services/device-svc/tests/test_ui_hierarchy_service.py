import unittest
import os
import sys
from pathlib import Path

os.environ["DEBUG"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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

IOS_SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AppiumAUT>
  <XCUIElementTypeApplication type="XCUIElementTypeApplication" name="Settings" label="Settings" enabled="true" visible="true" accessible="false" x="0" y="0" width="393" height="852">
    <XCUIElementTypeButton type="XCUIElementTypeButton" name="General" label="通用" enabled="true" visible="true" accessible="true" x="20" y="120" width="120" height="44" />
    <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" label="Apple ID" value="Apple ID" enabled="true" visible="true" accessible="true" x="20.5" y="180.2" width="180.4" height="28.1" />
  </XCUIElementTypeApplication>
</AppiumAUT>
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

    def test_parse_ios_source_elements_and_selectors(self):
        result = self.service.parse_ios_hierarchy(
            IOS_SAMPLE_XML,
            "ios-1",
        )

        self.assertEqual(result.device_id, "ios-1")
        self.assertEqual(result.platform, "ios")
        self.assertEqual(result.screen.width, 393)
        self.assertEqual(len(result.elements), 3)

        button = next(e for e in result.elements if e.class_name == "XCUIElementTypeButton")
        self.assertEqual(button.text, "通用")
        self.assertEqual(button.content_desc, "General")
        self.assertTrue(button.clickable)
        self.assertEqual(button.bounds.x, 20)
        self.assertEqual(button.bounds.y, 120)
        self.assertEqual(button.bounds.width, 120)
        self.assertEqual(button.bounds.height, 44)
        self.assertEqual(button.xpath, "//*[@name='General']")
        self.assertIn("accessible", button.attributes)
        self.assertEqual(
            [s.type for s in button.selector_suggestions],
            ["accessibility_id", "ios_predicate", "ios_class_chain", "text", "xpath"],
        )

        text = next(e for e in result.elements if e.text == "Apple ID")
        self.assertEqual(text.center.x, 110)
        self.assertEqual(text.center.y, 194)
        self.assertEqual(text.selector_suggestions[0].type, "accessibility_id")

    def test_ios_screen_uses_viewport_bounds_not_offscreen_elements(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<AppiumAUT>
  <XCUIElementTypeApplication type="XCUIElementTypeApplication" x="0" y="0" width="414" height="896">
    <XCUIElementTypeWindow type="XCUIElementTypeWindow" x="0" y="0" width="414" height="896">
      <XCUIElementTypeOther type="XCUIElementTypeOther" x="414" y="896" width="414" height="896" />
    </XCUIElementTypeWindow>
  </XCUIElementTypeApplication>
</AppiumAUT>
"""

        result = self.service.parse_ios_hierarchy(xml, "ios-1")

        self.assertEqual(result.screen.width, 414)
        self.assertEqual(result.screen.height, 896)


if __name__ == "__main__":
    unittest.main()
