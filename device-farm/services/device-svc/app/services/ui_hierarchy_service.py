import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.models.ui_hierarchy import (
    SelectorSuggestion,
    UIBounds,
    UIElement,
    UIHierarchyResponse,
    UIPoint,
    UIScreen,
)
from app.services.adb_service import adb_service


class UIHierarchyError(Exception):
    """Raised when the current UI hierarchy cannot be captured or parsed."""


class UIHierarchyService:
    DUMP_PATH_TEMPLATE = "/sdcard/window_dump_{stamp}.xml"

    async def get_ui_hierarchy(self, device_id: str, screen_resolution: str = "") -> UIHierarchyResponse:
        xml_text = await self.dump_android_hierarchy(device_id)
        screen = self._screen_from_resolution(screen_resolution)
        return self.parse_android_hierarchy(xml_text, device_id, screen)

    def _is_busy_dump_error(self, detail: str) -> bool:
        lowered = detail.lower()
        return (
            "could not get idle state" in lowered
            or "timed out" in lowered
            or "was killed while waiting" in lowered
            or "exit code 137" in lowered
        )

    def _busy_dump_error(self) -> UIHierarchyError:
        return UIHierarchyError(
            "设备当前页面一直处于忙碌状态或 UIAutomator 无响应，无法获取控件树。"
            "请先等待页面停止加载/动画，或返回一个稳定页面后再获取控件。"
        )

    async def dump_android_hierarchy(self, device_id: str) -> str:
        first_error = ""
        try:
            output = await adb_service.execute_adb(
                "exec-out",
                "uiautomator",
                "dump",
                "--compressed",
                "/dev/tty",
                device_id=device_id,
                timeout=8.0,
            )
            xml_text = self._extract_xml(output)
            if xml_text:
                return xml_text
        except Exception as exc:
            first_error = str(exc)
            if self._is_busy_dump_error(first_error):
                raise self._busy_dump_error() from exc

        dump_path = self.DUMP_PATH_TEMPLATE.format(stamp=int(time.time() * 1000))
        try:
            await adb_service.execute_adb(
                "shell",
                "uiautomator",
                "dump",
                "--compressed",
                dump_path,
                device_id=device_id,
                timeout=8.0,
            )
            output = await adb_service.execute_adb(
                "exec-out",
                "cat",
                dump_path,
                device_id=device_id,
                timeout=5.0,
            )
            xml_text = self._extract_xml(output)
            if not xml_text:
                raise UIHierarchyError("UI hierarchy dump is empty")
            return xml_text
        except UIHierarchyError:
            raise
        except Exception as exc:
            detail = str(exc) or first_error or "unknown error"
            if self._is_busy_dump_error(detail):
                raise self._busy_dump_error() from exc
            raise UIHierarchyError(f"Failed to dump UI hierarchy: {detail}") from exc
        finally:
            try:
                await adb_service.execute_adb("shell", "rm", "-f", dump_path, device_id=device_id, timeout=3.0)
            except Exception:
                pass

    def parse_android_hierarchy(
        self,
        xml_text: str,
        device_id: str,
        screen: Optional[UIScreen] = None,
    ) -> UIHierarchyResponse:
        xml_text = self._extract_xml(xml_text)
        if not xml_text:
            raise UIHierarchyError("UI hierarchy XML is empty")

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise UIHierarchyError(f"Invalid UI hierarchy XML: {exc}") from exc

        if root.tag != "hierarchy":
            hierarchy = root.find(".//hierarchy")
            if hierarchy is None:
                raise UIHierarchyError("UI hierarchy XML does not contain a hierarchy root")
            root = hierarchy

        elements: List[UIElement] = []
        uid_counter = 0

        def next_uid() -> str:
            nonlocal uid_counter
            uid = f"node-{uid_counter}"
            uid_counter += 1
            return uid

        def build_node(
            xml_node: ET.Element,
            parent_uid: Optional[str],
            depth: int,
            absolute_path: str,
        ) -> Dict[str, Any]:
            uid = next_uid()
            element = self._element_from_xml(xml_node, uid, parent_uid, depth, absolute_path)
            elements.append(element)

            tree_node: Dict[str, Any] = element.model_dump()
            tree_node["children"] = []

            class_counts: Dict[str, int] = {}
            for child in list(xml_node):
                class_name = child.attrib.get("class", "node") or "node"
                class_counts[class_name] = class_counts.get(class_name, 0) + 1
                child_path = f"{absolute_path}/{class_name}[{class_counts[class_name]}]"
                tree_node["children"].append(build_node(child, uid, depth + 1, child_path))

            return tree_node

        tree: Dict[str, Any] = {
            "uid": "root",
            "class_name": "hierarchy",
            "children": [],
        }

        class_counts: Dict[str, int] = {}
        for child in list(root):
            class_name = child.attrib.get("class", "node") or "node"
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
            absolute_path = f"/hierarchy/{class_name}[{class_counts[class_name]}]"
            tree["children"].append(build_node(child, None, 0, absolute_path))

        if screen is None or screen.width <= 0 or screen.height <= 0:
            screen = self._screen_from_elements(elements)

        return UIHierarchyResponse(
            device_id=device_id,
            platform="android",
            captured_at=datetime.utcnow(),
            screen=screen,
            elements=elements,
            tree=tree,
        )

    def parse_ios_hierarchy(
        self,
        xml_text: str,
        device_id: str,
        screen: Optional[UIScreen] = None,
    ) -> UIHierarchyResponse:
        xml_text = self._extract_ios_xml(xml_text)
        if not xml_text:
            raise UIHierarchyError("iOS page source XML is empty")

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise UIHierarchyError(f"Invalid iOS page source XML: {exc}") from exc

        elements: List[UIElement] = []
        uid_counter = 0

        def next_uid() -> str:
            nonlocal uid_counter
            uid = f"ios-node-{uid_counter}"
            uid_counter += 1
            return uid

        def build_node(
            xml_node: ET.Element,
            parent_uid: Optional[str],
            depth: int,
            absolute_path: str,
        ) -> Dict[str, Any]:
            uid = next_uid()
            element = self._ios_element_from_xml(xml_node, uid, parent_uid, depth, absolute_path)
            elements.append(element)

            tree_node: Dict[str, Any] = element.model_dump()
            tree_node["children"] = []

            type_counts: Dict[str, int] = {}
            for child in list(xml_node):
                class_name = self._ios_class_name(child)
                type_counts[class_name] = type_counts.get(class_name, 0) + 1
                child_path = f"{absolute_path}/{class_name}[{type_counts[class_name]}]"
                tree_node["children"].append(build_node(child, uid, depth + 1, child_path))

            return tree_node

        root_class = self._ios_class_name(root)
        tree: Dict[str, Any] = {
            "uid": "root",
            "class_name": root_class,
            "children": [],
        }

        if list(root):
            type_counts: Dict[str, int] = {}
            for child in list(root):
                class_name = self._ios_class_name(child)
                type_counts[class_name] = type_counts.get(class_name, 0) + 1
                absolute_path = f"/{root_class}/{class_name}[{type_counts[class_name]}]"
                tree["children"].append(build_node(child, None, 0, absolute_path))
        else:
            tree["children"].append(build_node(root, None, 0, f"/{root_class}[1]"))

        if screen is None or screen.width <= 0 or screen.height <= 0:
            screen = self._ios_screen_from_elements(elements)

        return UIHierarchyResponse(
            device_id=device_id,
            platform="ios",
            captured_at=datetime.utcnow(),
            screen=screen,
            elements=elements,
            tree=tree,
        )

    def _element_from_xml(
        self,
        xml_node: ET.Element,
        uid: str,
        parent_uid: Optional[str],
        depth: int,
        absolute_path: str,
    ) -> UIElement:
        attrs = xml_node.attrib
        bounds = self.parse_bounds(attrs.get("bounds", ""))
        center = UIPoint(
            x=bounds.x + bounds.width // 2,
            y=bounds.y + bounds.height // 2,
        )
        resource_id = attrs.get("resource-id", "")
        text = attrs.get("text", "")
        content_desc = attrs.get("content-desc", "")
        class_name = attrs.get("class", "")
        package = attrs.get("package", "")
        primary_xpath = self._primary_xpath(resource_id, content_desc, text, class_name, absolute_path)

        return UIElement(
            uid=uid,
            parent_uid=parent_uid,
            depth=depth,
            index=self._to_int(attrs.get("index"), 0),
            class_name=class_name,
            resource_id=resource_id,
            text=text,
            content_desc=content_desc,
            package=package,
            bounds=bounds,
            center=center,
            clickable=self._to_bool(attrs.get("clickable")),
            enabled=self._to_bool(attrs.get("enabled")),
            selected=self._to_bool(attrs.get("selected")),
            focused=self._to_bool(attrs.get("focused")),
            scrollable=self._to_bool(attrs.get("scrollable")),
            xpath=primary_xpath,
            selector_suggestions=self._selector_suggestions(resource_id, content_desc, text, primary_xpath),
            attributes={
                "absolute_xpath": absolute_path,
                "checkable": self._to_bool(attrs.get("checkable")),
                "checked": self._to_bool(attrs.get("checked")),
                "focusable": self._to_bool(attrs.get("focusable")),
                "long_clickable": self._to_bool(attrs.get("long-clickable")),
                "password": self._to_bool(attrs.get("password")),
            },
        )

    def parse_bounds(self, raw: str) -> UIBounds:
        match = re.match(r"^\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]$", raw or "")
        if not match:
            return UIBounds()

        x1, y1, x2, y2 = [int(v) for v in match.groups()]
        return UIBounds(
            x=x1,
            y=y1,
            width=max(0, x2 - x1),
            height=max(0, y2 - y1),
        )

    def parse_ios_bounds(self, attrs: Dict[str, Any]) -> UIBounds:
        x = self._to_float(attrs.get("x"), 0)
        y = self._to_float(attrs.get("y"), 0)
        width = self._to_float(attrs.get("width"), 0)
        height = self._to_float(attrs.get("height"), 0)
        return UIBounds(
            x=round(x),
            y=round(y),
            width=max(0, round(width)),
            height=max(0, round(height)),
        )

    def _selector_suggestions(
        self,
        resource_id: str,
        content_desc: str,
        text: str,
        xpath: str,
    ) -> List[SelectorSuggestion]:
        suggestions: List[SelectorSuggestion] = []
        if resource_id:
            suggestions.append(SelectorSuggestion(type="id", value=resource_id))
        if content_desc:
            suggestions.append(SelectorSuggestion(type="accessibility_id", value=content_desc))
        if text:
            suggestions.append(SelectorSuggestion(type="text", value=text))
        if xpath:
            suggestions.append(SelectorSuggestion(type="xpath", value=xpath))
        return suggestions

    def _ios_selector_suggestions(
        self,
        accessibility_id: str,
        label: str,
        value: str,
        class_name: str,
        xpath: str,
    ) -> List[SelectorSuggestion]:
        suggestions: List[SelectorSuggestion] = []
        if accessibility_id:
            suggestions.append(SelectorSuggestion(type="accessibility_id", value=accessibility_id))
            suggestions.append(SelectorSuggestion(type="ios_predicate", value=f"name == {self._ios_predicate_literal(accessibility_id)}"))
        elif label:
            suggestions.append(SelectorSuggestion(type="ios_predicate", value=f"label == {self._ios_predicate_literal(label)}"))
        elif value:
            suggestions.append(SelectorSuggestion(type="ios_predicate", value=f"value == {self._ios_predicate_literal(value)}"))
        if class_name:
            if accessibility_id:
                suggestions.append(
                    SelectorSuggestion(
                        type="ios_class_chain",
                        value=f"**/{class_name}[`name == {self._ios_predicate_literal(accessibility_id)}`]",
                    )
                )
            else:
                suggestions.append(SelectorSuggestion(type="ios_class_chain", value=f"**/{class_name}"))
        if label:
            suggestions.append(SelectorSuggestion(type="text", value=label))
        if xpath:
            suggestions.append(SelectorSuggestion(type="xpath", value=xpath))
        return suggestions

    def _primary_xpath(
        self,
        resource_id: str,
        content_desc: str,
        text: str,
        class_name: str,
        absolute_path: str,
    ) -> str:
        if resource_id:
            return f"//*[@resource-id={self._xpath_literal(resource_id)}]"
        if content_desc:
            return f"//*[@content-desc={self._xpath_literal(content_desc)}]"
        if text:
            return f"//*[@text={self._xpath_literal(text)}]"
        if class_name:
            return f"{absolute_path}"
        return absolute_path

    def _ios_primary_xpath(
        self,
        accessibility_id: str,
        label: str,
        value: str,
        class_name: str,
        absolute_path: str,
    ) -> str:
        if accessibility_id:
            return f"//*[@name={self._xpath_literal(accessibility_id)}]"
        if label:
            return f"//*[@label={self._xpath_literal(label)}]"
        if value:
            return f"//*[@value={self._xpath_literal(value)}]"
        if class_name:
            return absolute_path
        return absolute_path

    def _ios_element_from_xml(
        self,
        xml_node: ET.Element,
        uid: str,
        parent_uid: Optional[str],
        depth: int,
        absolute_path: str,
    ) -> UIElement:
        attrs = xml_node.attrib
        bounds = self.parse_ios_bounds(attrs)
        center = UIPoint(
            x=bounds.x + bounds.width // 2,
            y=bounds.y + bounds.height // 2,
        )
        class_name = self._ios_class_name(xml_node)
        name = attrs.get("name", "")
        label = attrs.get("label", "")
        value = attrs.get("value", "")
        text = label or value or name
        content_desc = name or label
        xpath = self._ios_primary_xpath(content_desc, label, value, class_name, absolute_path)
        enabled = self._to_bool(attrs.get("enabled"))
        visible = self._to_bool(attrs.get("visible"))
        accessible = self._to_bool(attrs.get("accessible"))

        return UIElement(
            uid=uid,
            parent_uid=parent_uid,
            depth=depth,
            index=self._to_int(attrs.get("index"), 0),
            class_name=class_name,
            resource_id="",
            text=text,
            content_desc=content_desc,
            package="",
            bounds=bounds,
            center=center,
            clickable=enabled and (visible or accessible),
            enabled=enabled,
            selected=self._to_bool(attrs.get("selected")),
            focused=self._to_bool(attrs.get("focused")),
            scrollable=class_name in {"XCUIElementTypeScrollView", "XCUIElementTypeTable", "XCUIElementTypeCollectionView"},
            xpath=xpath,
            selector_suggestions=self._ios_selector_suggestions(content_desc, label, value, class_name, xpath),
            attributes={
                "absolute_xpath": absolute_path,
                "type": class_name,
                "name": name,
                "label": label,
                "value": value,
                "visible": visible,
                "accessible": accessible,
            },
        )

    def _ios_class_name(self, xml_node: ET.Element) -> str:
        return xml_node.attrib.get("type") or xml_node.tag or "XCUIElementTypeOther"

    def _xpath_literal(self, value: str) -> str:
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        parts = value.split("'")
        return "concat(" + ', "\"\'\"", '.join(f"'{part}'" for part in parts) + ")"

    def _ios_predicate_literal(self, value: str) -> str:
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"

    def _extract_xml(self, output: str) -> str:
        if not output:
            return ""
        start = output.find("<?xml")
        if start == -1:
            start = output.find("<hierarchy")
        end = output.rfind("</hierarchy>")
        if start == -1 or end == -1:
            return ""
        return output[start : end + len("</hierarchy>")].strip()

    def _extract_ios_xml(self, output: str) -> str:
        if not output:
            return ""
        start = output.find("<?xml")
        if start == -1:
            start = output.find("<AppiumAUT")
        if start == -1:
            start = output.find("<XCUIElementType")
        if start == -1:
            return ""
        return output[start:].strip()

    def _screen_from_resolution(self, resolution: str) -> UIScreen:
        match = re.search(r"(\d+)x(\d+)", resolution or "")
        if not match:
            return UIScreen()
        return UIScreen(width=int(match.group(1)), height=int(match.group(2)))

    def screen_from_resolution(self, resolution: str) -> UIScreen:
        return self._screen_from_resolution(resolution)

    def _screen_from_elements(self, elements: List[UIElement]) -> UIScreen:
        max_x = 0
        max_y = 0
        for element in elements:
            max_x = max(max_x, element.bounds.x + element.bounds.width)
            max_y = max(max_y, element.bounds.y + element.bounds.height)
        return UIScreen(width=max_x, height=max_y)

    def _ios_screen_from_elements(self, elements: List[UIElement]) -> UIScreen:
        for class_name in ("XCUIElementTypeApplication", "XCUIElementTypeWindow"):
            for element in elements:
                bounds = element.bounds
                if (
                    element.class_name == class_name
                    and bounds.x == 0
                    and bounds.y == 0
                    and bounds.width > 0
                    and bounds.height > 0
                ):
                    return UIScreen(width=bounds.width, height=bounds.height)
        return self._screen_from_elements(elements)

    def _to_bool(self, value: Any) -> bool:
        return str(value).lower() == "true"

    def _to_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _to_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


ui_hierarchy_service = UIHierarchyService()
