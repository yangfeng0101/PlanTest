# Appium Driver Wrapper
import asyncio
import json
import logging
from typing import Optional, Dict, Any
from functools import wraps

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
        self.appium_host = appium_host or settings.APPIUM_HOST
        self.app_path = app_path
        self.bundle_id = bundle_id
        self.driver: Optional[webdriver.WebDriver] = None
        self.session_id: Optional[str] = None
        self._initialized = False

    def _build_options(self) -> AppiumOptions:
        """Build Appium options based on platform and capabilities"""
        options = AppiumOptions()

        # Platform-specific default capabilities
        if self.platform == "android":
            default_caps = {
                "platformName": "Android",
                "automationName": "UiAutomator2",
                "deviceName": self.device_id or "Android Device",
                "udid": self.udid,
                "noReset": True,
                "newCommandTimeout": settings.APPIUM_TIMEOUT,
                # Enable real device connection
                "skipServerInstallation": True,  # Skip uiautomator2 server installation if already present
                "skipDeviceInitialization": True,  # Skip device initialization
                "disableWindowAnimation": True,
                "ignoreUnimportantViews": True,
                "enablePerformanceLogging": True,
            }
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
                # Enable real device connection
                "usePrebuiltWDA": True,  # Use pre-built WebDriverAgent
                "skipLogCapture": True,
                "waitForQuiescence": False,
            }
            # Add app path if provided
            if self.app_path:
                default_caps["app"] = self.app_path
            # Add bundle_id if provided
            if self.bundle_id:
                default_caps["bundleId"] = self.bundle_id

        # Merge with user capabilities
        caps = {**default_caps, **self.capabilities}

        for key, value in caps.items():
            if value is not None:  # Skip None values
                options.set_capability(key, value)

        return options

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
            logger.error(f"Failed to initialize Appium driver: {e}")
            raise

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
