# Appium Driver Wrapper
import asyncio
import json
import logging
import os
import subprocess
from typing import Optional, Dict, Any, Union
from functools import wraps
from urllib.parse import urlsplit, urlunsplit

from appium import webdriver
from appium.options.common.base import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy

from app.config import settings

logger = logging.getLogger(__name__)


def retry_on_failure(max_retries=3, delay=1):
    """Decorator to retry operations on failure"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(delay * (attempt + 1))
            raise last_exception
        return wrapper
    return decorator


class AppiumDriver:
    """Appium driver wrapper for mobile automation"""

    INTERNAL_CAPS = {"_device_snapshot", "_appium_diagnostics"}

    SERVICE_OWNED_CAPS = {
        "platformName",
        "automationName",
        "deviceName",
        "udid",
        "remoteAdbHost",
        "xcodeOrgId",
        "xcodeSigningId",
        "updatedWDABundleId",
        "allowProvisioningDeviceRegistration",
    }

    def __init__(
        self,
        platform: str = "android",
        device_id: Optional[str] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        appium_host: Optional[str] = None,
        udid: Optional[str] = None,  # iOS UDID or Android serial
        app_path: Optional[str] = None,  # Path to app (APK/IPA)
        bundle_id: Optional[str] = None,  # Bundle ID for installed app
    ):
        self.platform = platform.lower()
        self.device_id = device_id or udid
        self.udid = udid or device_id
        self.capabilities = capabilities or {}
        default_appium_host = settings.IOS_APPIUM_HOST if self.platform == "ios" else settings.APPIUM_HOST
        self.appium_host = appium_host or default_appium_host
        if self.platform == "ios" and not self.appium_host:
            raise RuntimeError("IOS_APPIUM_HOST is required for iOS Appium sessions")
        self.app_path = app_path
        self.bundle_id = bundle_id
        self.driver: Optional[webdriver.WebDriver] = None
        self.session_id: Optional[str] = None
        self._initialized = False

    @staticmethod
    def explain_appium_error(platform: str, error: Union[Exception, str]) -> Optional[str]:
        if platform.lower() != "ios":
            return None

        detail = str(error).lower()
        hint_patterns = [
            (
                ("connection refused", "failed to establish a new connection", "max retries exceeded", "cannot connect"),
                "无法连接 iOS Appium 服务，请确认 Mac 宿主机 Appium 已启动且 IOS_APPIUM_HOST 可从 test-worker 访问。",
            ),
            (
                ("no account for team", "xcodeorgid", "development team", "requires a development team"),
                "WDA 签名 Team 配置异常，请确认 Xcode 已登录 Apple ID，且 IOS_XCODE_ORG_ID 是有效 Team ID。",
            ),
            (
                ("bundle identifier", "updatedwdabundleid", "already exists"),
                "WDA bundle id 可能不可用或冲突，请配置唯一的 IOS_WDA_BUNDLE_ID。",
            ),
            (
                ("invalid code signature", "not trusted", "profile has not been explicitly trusted", "developer app certificate"),
                "iPhone 未信任开发者证书或签名无效，请在设备的 VPN 与设备管理中信任证书后重试。",
            ),
            (
                ("device is locked", "passcode", "trust", "lockdown", "not paired", "pair"),
                "iPhone 可能未解锁、未信任本机或配对状态异常，请解锁设备并重新信任 Mac。",
            ),
            (
                ("could not find device", "device not found", "unknown device", "invalid device id", "udid"),
                "未找到目标 iPhone，请确认 UDID 正确、设备在线且 iOS Agent 能看到该设备。",
            ),
            (
                ("webdriveragent", "wda", "timed out", "timeout", "xcodebuild failed", "failed to launch"),
                "WDA 启动或连接超时，请检查 Xcode 签名、Developer Mode、设备信任状态和 WebDriverAgent 是否能在真机运行。",
            ),
        ]

        for patterns, hint in hint_patterns:
            if any(pattern in detail for pattern in patterns):
                return hint
        return "iOS Appium/WDA session 创建失败，请查看原始错误并检查 Mac Appium、WDA 签名和 iPhone 信任状态。"

    @classmethod
    def format_appium_error(cls, platform: str, error: Union[Exception, str]) -> str:
        hint = cls.explain_appium_error(platform, error)
        if not hint:
            return str(error)
        return f"{hint} 原始错误: {error}"

    @staticmethod
    def _sanitize_url(url: str) -> str:
        try:
            parts = urlsplit(url)
        except Exception:
            return url
        if not parts.username and not parts.password:
            return url
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme, f"redacted@{host}", parts.path, parts.query, parts.fragment))

    def _adb_command(self, *args: str) -> list[str]:
        command = ["adb"]
        adb_host = settings.APPIUM_REMOTE_ADB_HOST or os.getenv("ADB_SERVER_HOST")
        adb_port = os.getenv("ADB_SERVER_PORT", "5037")

        if adb_host:
            command.extend(["-H", adb_host])
        if adb_port:
            command.extend(["-P", adb_port])
        if self.udid:
            command.extend(["-s", self.udid])

        command.extend(args)
        return command

    def _resolve_launch_activity(self, package_name: str) -> str:
        command = self._adb_command(
            "shell",
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            package_name,
        )

        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("ADB is not installed in the test worker image") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            detail = stderr or stdout or str(exc)
            raise RuntimeError(f"Failed to resolve launch activity for {package_name}: {detail}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Timed out resolving launch activity for {package_name}") from exc

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        for line in reversed(lines):
            if "/" in line and not line.startswith("No activity found"):
                component = line
                break
        else:
            raise RuntimeError(f"No launch activity found for package {package_name}")

        if component.startswith(package_name + "/"):
            activity = component.split("/", 1)[1]
            logger.info("Resolved launch activity for %s: %s", package_name, activity)
            return activity

        logger.info("Resolved launch component for %s: %s", package_name, component)
        return component

    def _normalize_android_launch_caps(self, caps: Dict[str, Any]) -> Dict[str, Any]:
        app_package = caps.get("appPackage")
        app_activity = caps.get("appActivity")

        if app_package and not app_activity:
            caps["appActivity"] = self._resolve_launch_activity(str(app_package))
            caps.setdefault("appWaitPackage", app_package)
            caps.setdefault("appWaitActivity", "*")

        return caps

    def _remove_capability_aliases(self, caps: Dict[str, Any], key: str) -> None:
        caps.pop(key, None)
        caps.pop(f"appium:{key}", None)

    def _set_service_capability(self, caps: Dict[str, Any], key: str, value: Any) -> None:
        self._remove_capability_aliases(caps, key)
        if value is not None:
            caps[key] = value

    def _strip_internal_capabilities(self, caps: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: value
            for key, value in caps.items()
            if key not in self.INTERNAL_CAPS and not key.startswith("_")
        }

    def _enforce_service_owned_capabilities(self, caps: Dict[str, Any]) -> Dict[str, Any]:
        """Keep task-supplied caps from changing the reserved device/session target."""
        for key in self.SERVICE_OWNED_CAPS:
            self._remove_capability_aliases(caps, key)

        if self.platform == "android":
            self._set_service_capability(caps, "platformName", "Android")
            self._set_service_capability(caps, "automationName", "UiAutomator2")
            self._set_service_capability(caps, "deviceName", self.device_id or "Android Device")
            self._set_service_capability(caps, "udid", self.udid)
            if settings.APPIUM_REMOTE_ADB_HOST:
                self._set_service_capability(caps, "remoteAdbHost", settings.APPIUM_REMOTE_ADB_HOST)
        else:
            self._set_service_capability(caps, "platformName", "iOS")
            self._set_service_capability(caps, "automationName", "XCUITest")
            self._set_service_capability(caps, "deviceName", self.device_id or "iOS Device")
            self._set_service_capability(caps, "udid", self.udid)
            if settings.IOS_XCODE_ORG_ID:
                self._set_service_capability(caps, "xcodeOrgId", settings.IOS_XCODE_ORG_ID)
                self._set_service_capability(caps, "xcodeSigningId", settings.IOS_XCODE_SIGNING_ID)
            if settings.IOS_WDA_BUNDLE_ID:
                self._set_service_capability(caps, "updatedWDABundleId", settings.IOS_WDA_BUNDLE_ID)
            if settings.IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION:
                self._set_service_capability(caps, "allowProvisioningDeviceRegistration", True)

        return caps

    def _build_capabilities(self) -> Dict[str, Any]:
        if self.platform == "android":
            default_caps = {
                "platformName": "Android",
                "automationName": "UiAutomator2",
                "deviceName": self.device_id or "Android Device",
                "udid": self.udid,
                "noReset": True,
                "newCommandTimeout": settings.APPIUM_TIMEOUT,
                "adbExecTimeout": 120000,
                "uiautomator2ServerInstallTimeout": 120000,
                "uiautomator2ServerLaunchTimeout": 120000,
                "disableWindowAnimation": True,
                "ignoreUnimportantViews": True,
                "enablePerformanceLogging": True,
            }
            if settings.APPIUM_REMOTE_ADB_HOST:
                default_caps["remoteAdbHost"] = settings.APPIUM_REMOTE_ADB_HOST
            # Add app path if provided
            if self.app_path:
                default_caps["app"] = self.app_path
            # Add bundle_id (appPackage) if provided
            if self.bundle_id:
                default_caps["appPackage"] = self.bundle_id
                default_caps["appActivity"] = ".MainActivity"  # Common default, can be overridden
        else:  # iOS
            default_caps = {
                "platformName": "iOS",
                "automationName": "XCUITest",
                "deviceName": self.device_id or "iOS Device",
                "udid": self.udid,
                "noReset": True,
                "newCommandTimeout": settings.APPIUM_TIMEOUT,
                "skipLogCapture": True,
                "waitForQuiescence": False,
            }
            if settings.IOS_XCODE_ORG_ID:
                default_caps["xcodeOrgId"] = settings.IOS_XCODE_ORG_ID
                default_caps["xcodeSigningId"] = settings.IOS_XCODE_SIGNING_ID
            if settings.IOS_WDA_BUNDLE_ID:
                default_caps["updatedWDABundleId"] = settings.IOS_WDA_BUNDLE_ID
            if settings.IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION:
                default_caps["allowProvisioningDeviceRegistration"] = True
            # Add app path if provided
            if self.app_path:
                default_caps["app"] = self.app_path
            # Add bundle_id if provided
            if self.bundle_id:
                default_caps["bundleId"] = self.bundle_id

        # Merge with user capabilities
        caps = {**default_caps, **self._strip_internal_capabilities(self.capabilities)}
        caps = self._enforce_service_owned_capabilities(caps)
        if self.platform == "android":
            caps = self._normalize_android_launch_caps(caps)
        return caps

    def _build_options(self) -> AppiumOptions:
        """Build Appium options based on platform and capabilities"""
        options = AppiumOptions()
        caps = self._build_capabilities()

        for key, value in caps.items():
            if value is not None:  # Skip None values
                options.set_capability(key, value)

        return options

    def sanitized_diagnostics(self) -> Dict[str, Any]:
        caps = self._build_capabilities()
        sensitive_capability_keys = {"xcodeOrgId", "xcodeSigningId", "updatedWDABundleId"}
        sensitive_words = ("token", "secret", "password", "cookie", "api_key", "apikey")
        sanitized_caps: Dict[str, Any] = {}

        for key, value in caps.items():
            normalized = key.lower()
            if key in sensitive_capability_keys:
                sanitized_caps[key] = "configured" if value else "not_configured"
            elif any(word in normalized for word in sensitive_words):
                sanitized_caps[key] = "redacted"
            else:
                sanitized_caps[key] = value

        return {
            "platform": self.platform,
            "udid": self.udid,
            "appium_host": self._sanitize_url(self.appium_host),
            "automation_name": caps.get("automationName"),
            "no_reset": caps.get("noReset"),
            "capabilities": sanitized_caps,
            "ios_signing": {
                "xcodeOrgId": "configured" if settings.IOS_XCODE_ORG_ID else "not_configured",
                "xcodeSigningId": "configured" if settings.IOS_XCODE_SIGNING_ID else "not_configured",
                "updatedWDABundleId": "configured" if settings.IOS_WDA_BUNDLE_ID else "not_configured",
                "allowProvisioningDeviceRegistration": bool(settings.IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION),
            } if self.platform == "ios" else {},
        }

    def __getattr__(self, name: str):
        """Delegate unknown attributes to the underlying Appium WebDriver."""
        if self.driver is not None and hasattr(self.driver, name):
            return getattr(self.driver, name)
        raise AttributeError(f"{self.__class__.__name__!s} has no attribute {name!r}")

    @retry_on_failure(max_retries=3, delay=2)
    def initialize(self) -> "AppiumDriver":
        """Initialize the Appium driver"""
        if self._initialized and self.driver is not None:
            logger.debug(f"Driver already initialized for {self.platform}:{self.udid}")
            return self

        options = self._build_options()

        logger.info(f"Initializing Appium driver for {self.platform}:{self.udid}")
        logger.debug(f"Appium host: {self.appium_host}")

        try:
            self.driver = webdriver.Remote(
                command_executor=self.appium_host,
                options=options
            )

            self.session_id = self.driver.session_id
            self._initialized = True
            logger.info(f"Appium driver initialized successfully, session_id: {self.session_id}")
            return self
        except Exception as e:
            error_msg = self.format_appium_error(self.platform, e)
            logger.error(f"Failed to initialize Appium driver: {error_msg}")
            raise RuntimeError(error_msg) from e

    def quit(self):
        """Quit the driver session"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info(f"Appium driver quit for session {self.session_id}")
            except Exception as e:
                logger.warning(f"Error quitting driver: {e}")
            finally:
                self.driver = None
                self.session_id = None
                self._initialized = False

    def is_active(self) -> bool:
        """Check if driver session is active"""
        return self._initialized and self.driver is not None

    # Element finding methods
    def find_element_by_id(self, element_id: str):
        """Find element by resource ID"""
        return self.driver.find_element(AppiumBy.ID, element_id)

    def find_element_by_xpath(self, xpath: str):
        """Find element by XPath"""
        return self.driver.find_element(AppiumBy.XPATH, xpath)

    def find_element_by_accessibility_id(self, accessibility_id: str):
        """Find element by accessibility ID"""
        return self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, accessibility_id)

    def find_element_by_class_name(self, class_name: str):
        """Find element by class name"""
        return self.driver.find_element(AppiumBy.CLASS_NAME, class_name)

    def find_element_by_android_uiautomator(self, uiautomator: str):
        """Find element using Android UIAutomator (Android only)"""
        return self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, uiautomator)

    def find_element_by_ios_predicate(self, predicate: str):
        """Find element using iOS predicate (iOS only)"""
        return self.driver.find_element(AppiumBy.IOS_PREDICATE, predicate)

    def find_element_by_ios_class_chain(self, class_chain: str):
        """Find element using iOS class chain (iOS only)"""
        return self.driver.find_element(AppiumBy.IOS_CLASS_CHAIN, class_chain)

    # Element interaction methods
    def click(self, element):
        """Click on an element"""
        element.click()

    def send_keys(self, element, text: str):
        """Send keys to an element"""
        element.send_keys(text)

    def clear(self, element):
        """Clear text from an element"""
        element.clear()

    def get_text(self, element) -> str:
        """Get text from an element"""
        return element.text

    def get_attribute(self, element, attribute: str) -> str:
        """Get attribute value from an element"""
        return element.get_attribute(attribute)

    # Navigation methods
    def back(self):
        """Navigate back"""
        self.driver.back()

    def launch_app(self):
        """Launch the app"""
        if hasattr(self.driver, "launch_app"):
            self.driver.launch_app()

    def activate_app(self, package_name: str):
        """Activate an installed app by package name or bundle id."""
        if hasattr(self.driver, "activate_app"):
            self.driver.activate_app(package_name)
            return
        raise RuntimeError("activate_app is not supported by this Appium session")

    def terminate_app(self, package_name: str):
        """Terminate an installed app by package name or bundle id."""
        if hasattr(self.driver, "terminate_app"):
            self.driver.terminate_app(package_name)
            return
        raise RuntimeError("terminate_app is not supported by this Appium session")

    def close_app(self):
        """Close the app"""
        if hasattr(self.driver, "close_app"):
            self.driver.close_app()

    def reset_app(self):
        """Reset the app"""
        if hasattr(self.driver, "reset"):
            self.driver.reset()

    # Gestures
    def tap(self, x: int, y: int):
        """Tap at coordinates"""
        from appium.webdriver.common.touch_action import TouchAction
        action = TouchAction(self.driver)
        action.tap(x=x, y=y).perform()

    def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 500):
        """Swipe from one point to another"""
        from appium.webdriver.common.touch_action import TouchAction
        action = TouchAction(self.driver)
        action.press(x=start_x, y=start_y).wait(duration).move_to(x=end_x, y=end_y).release().perform()

    def scroll_to_element(self, element):
        """Scroll to an element"""
        self.driver.execute_script("mobile: scroll", {"element": element.id})

    # Screenshot and recording
    def take_screenshot(self) -> bytes:
        """Take a screenshot"""
        return self.driver.get_screenshot_as_png()

    def get_screenshot_as_png(self) -> bytes:
        """Expose the standard Selenium/Appium screenshot method."""
        return self.driver.get_screenshot_as_png()

    def save_screenshot(self, file_path: str):
        """Save screenshot to file"""
        self.driver.save_screenshot(file_path)

    def start_recording_screen(self):
        """Start screen recording"""
        if hasattr(self.driver, "start_recording_screen"):
            self.driver.start_recording_screen()

    def stop_recording_screen(self) -> str:
        """Stop screen recording and return base64 encoded video"""
        if hasattr(self.driver, "stop_recording_screen"):
            return self.driver.stop_recording_screen()
        return ""

    # Waiting methods
    def implicitly_wait(self, time_to_wait: int):
        """Set implicit wait timeout"""
        self.driver.implicitly_wait(time_to_wait)

    def set_script_timeout(self, time_to_wait: int):
        """Set script timeout"""
        self.driver.set_script_timeout(time_to_wait)

    # Page source
    def get_page_source(self) -> str:
        """Get page source"""
        return self.driver.page_source

    # Context and window management
    def get_contexts(self) -> list:
        """Get available contexts"""
        return self.driver.contexts

    def get_current_context(self) -> str:
        """Get current context"""
        return self.driver.current_context

    def switch_to_context(self, context_name: str):
        """Switch to a specific context"""
        self.driver.switch_to.context(context_name)

    # Alert handling
    def is_alert_present(self) -> bool:
        """Check if alert is present"""
        try:
            alert = self.driver.switch_to.alert
            return alert is not None
        except Exception:
            return False

    def accept_alert(self):
        """Accept alert"""
        self.driver.switch_to.alert.accept()

    def dismiss_alert(self):
        """Dismiss alert"""
        self.driver.switch_to.alert.dismiss()

    def get_alert_text(self) -> str:
        """Get alert text"""
        return self.driver.switch_to.alert.text

    # Custom Appium commands
    def execute_script(self, script: str, *args):
        """Execute JavaScript/Appium script"""
        return self.driver.execute_script(script, *args)

    def execute_driver_script(self, script: str, timeout_ms: int = None):
        """Execute driver script"""
        params = {"script": script}
        if timeout_ms:
            params["timeout"] = timeout_ms
        return self.driver.execute_script("mobile: driverScript", params)

    # Device info
    def get_device_time(self) -> str:
        """Get device time"""
        return self.driver.device_time

    def get_device_info(self) -> dict:
        """Get device info"""
        return self.driver.execute_script("mobile: deviceInfo")

    def get_screen_size(self) -> dict:
        """Get screen size"""
        size = self.driver.get_window_size()
        return {"width": size["width"], "height": size["height"]}
