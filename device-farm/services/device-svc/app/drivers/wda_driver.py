# WebDriverAgent Driver - iOS Automation
import asyncio
import json
import logging
import base64
import httpx
from typing import Optional, Dict, Any, Tuple
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class WDAStatus(Enum):
    """WebDriverAgent status"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class WDAConfig:
    """WebDriverAgent configuration"""
    host: str = "localhost"
    port: int = 8100
    timeout: float = 30.0
    retry_count: int = 3
    retry_delay: float = 1.0


class WDADriver:
    """
    WebDriverAgent driver for iOS automation.

    WebDriverAgent is a WebDriver server implementation for iOS that
    can be used to automate iOS devices. It runs on the device and
    provides a REST API for automation commands.

    Prerequisites:
    - WebDriverAgent must be built and installed on the device
    - Device must be paired and trusted
    - ios-deploy or pymobiledevice3 for starting WDA
    """

    def __init__(self, config: Optional[WDAConfig] = None):
        self.config = config or WDAConfig()
        self._status = WDAStatus.STOPPED
        self._session_id: Optional[str] = None
        self._udid: Optional[str] = None
        self._process: Optional[asyncio.subprocess.Process] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._screen_size: Optional[Tuple[int, int]] = None

    @property
    def base_url(self) -> str:
        """Get the base URL for WDA requests"""
        return f"http://{self.config.host}:{self.config.port}"

    @property
    def status(self) -> WDAStatus:
        """Get current driver status"""
        return self._status

    @property
    def is_running(self) -> bool:
        """Check if WDA is running"""
        return self._status == WDAStatus.RUNNING

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.config.timeout
            )
        return self._client

    async def _execute_pymobiledevice3(self, *args: str) -> str:
        """Execute pymobiledevice3 CLI command"""
        cmd = ["python3", "-m", "pymobiledevice3"]
        cmd.extend(args)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"pymobiledevice3 command failed: {stderr.decode()}")
                raise Exception(f"pymobiledevice3 command failed: {stderr.decode()}")

            return stdout.decode().strip()
        except Exception as e:
            logger.error(f"Error executing pymobiledevice3 command: {e}")
            raise

    async def start_wda(self, udid: str) -> Dict[str, Any]:
        """
        Start WebDriverAgent on the device.

        Args:
            udid: Device Unique Device Identifier

        Returns:
            Dictionary with start result
        """
        if self._status == WDAStatus.RUNNING:
            return {
                "success": True,
                "udid": udid,
                "message": "WDA already running",
                "url": self.base_url
            }

        self._status = WDAStatus.STARTING
        self._udid = udid

        try:
            # Method 1: Try using pymobiledevice3 to run WDA
            # This requires WDA to be built and installed on the device
            logger.info(f"Starting WebDriverAgent on device {udid}")

            # Use xcodebuild to run WDA (requires Xcode)
            # Alternative: use prebuilt WDA with ios-deploy
            cmd = [
                "xcrun", "xcodebuild",
                "-project", "WebDriverAgent.xcodeproj",
                "-scheme", "WebDriverAgentRunner",
                "-destination", f"id={udid}",
                "test"
            ]

            # For now, we'll use a simpler approach with ios-deploy
            # assuming WDA is already installed on the device
            try:
                # Try to start WDA using ios-deploy
                self._process = await asyncio.create_subprocess_exec(
                    "ios-deploy",
                    "--id", udid,
                    "--justlaunch",
                    "--bundle", "com.facebook.WebDriverAgentRunner",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            except FileNotFoundError:
                # ios-deploy not found, try pymobiledevice3
                logger.info("ios-deploy not found, trying pymobiledevice3")
                # pymobiledevice3 can run apps via developer mode
                self._process = await asyncio.create_subprocess_exec(
                    "python3", "-m", "pymobiledevice3",
                    "developer", "dvt",
                    "--udid", udid,
                    "run", "com.facebook.WebDriverAgentRunner",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

            # Wait for WDA to start
            await asyncio.sleep(5)

            # Check if WDA is responding
            for attempt in range(self.config.retry_count):
                try:
                    if await self._health_check():
                        self._status = WDAStatus.RUNNING

                        # Get screen size
                        await self._init_screen_size()

                        return {
                            "success": True,
                            "udid": udid,
                            "message": "WDA started successfully",
                            "url": self.base_url
                        }
                except Exception as e:
                    logger.warning(f"Health check attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(self.config.retry_delay)

            # If we get here, WDA didn't start properly
            self._status = WDAStatus.ERROR
            return {
                "success": False,
                "udid": udid,
                "message": "WDA failed to start - health check failed"
            }

        except Exception as e:
            self._status = WDAStatus.ERROR
            logger.error(f"Error starting WDA: {e}")
            return {
                "success": False,
                "udid": udid,
                "message": f"Error starting WDA: {str(e)}"
            }

    async def stop_wda(self) -> Dict[str, Any]:
        """
        Stop WebDriverAgent.

        Returns:
            Dictionary with stop result
        """
        try:
            # Close the session if active
            if self._session_id:
                await self._delete_session()
                self._session_id = None

            # Kill the process if running
            if self._process and self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()

            # Close HTTP client
            if self._client:
                await self._client.aclose()
                self._client = None

            self._status = WDAStatus.STOPPED
            self._process = None

            return {
                "success": True,
                "message": "WDA stopped successfully"
            }

        except Exception as e:
            logger.error(f"Error stopping WDA: {e}")
            return {
                "success": False,
                "message": f"Error stopping WDA: {str(e)}"
            }

    async def _health_check(self) -> bool:
        """Check if WDA is responding"""
        try:
            client = await self._get_client()
            response = await client.get("/status")
            return response.status_code == 200
        except Exception:
            return False

    async def _init_screen_size(self) -> None:
        """Initialize screen size from WDA"""
        try:
            client = await self._get_client()
            response = await client.get("/session/0/window/size")
            if response.status_code == 200:
                data = response.json()
                size = data.get("value", {})
                self._screen_size = (
                    size.get("width", 0),
                    size.get("height", 0)
                )
        except Exception as e:
            logger.warning(f"Could not get screen size: {e}")

    async def _ensure_session(self) -> str:
        """Ensure we have an active WDA session"""
        if self._session_id:
            return self._session_id

        client = await self._get_client()

        # Create a new session
        capabilities = {
            "capabilities": {
                "alwaysMatch": {
                    "platformName": "iOS",
                    "automationName": "XCUITest"
                }
            }
        }

        response = await client.post("/session", json=capabilities)
        if response.status_code == 200:
            data = response.json()
            self._session_id = data.get("sessionId") or data.get("value", {}).get("sessionId")

            # Get screen size
            await self._init_screen_size()

            return self._session_id

        raise Exception(f"Failed to create WDA session: {response.text}")

    async def _delete_session(self) -> None:
        """Delete the current WDA session"""
        if not self._session_id:
            return

        try:
            client = await self._get_client()
            await client.delete(f"/session/{self._session_id}")
        except Exception as e:
            logger.warning(f"Error deleting session: {e}")

    async def tap(self, x: int, y: int) -> Dict[str, Any]:
        """
        Perform a tap at the specified coordinates.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            Dictionary with tap result
        """
        if not self.is_running:
            return {
                "success": False,
                "message": "WDA is not running"
            }

        try:
            session_id = await self._ensure_session()
            client = await self._get_client()

            # Perform tap using WDA endpoint
            response = await client.post(
                f"/session/{session_id}/wda/tap/0",
                json={"x": x, "y": y}
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "x": x,
                    "y": y,
                    "message": "Tap performed successfully"
                }

            # Try alternative endpoint
            response = await client.post(
                f"/session/{session_id}/actions",
                json={
                    "actions": [{
                        "type": "pointer",
                        "id": "finger1",
                        "parameters": {"pointerType": "touch"},
                        "actions": [
                            {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                            {"type": "pointerDown", "button": 0},
                            {"type": "pause", "duration": 100},
                            {"type": "pointerUp", "button": 0}
                        ]
                    }]
                }
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "x": x,
                    "y": y,
                    "message": "Tap performed successfully"
                }

            return {
                "success": False,
                "message": f"Tap failed: {response.text}"
            }

        except Exception as e:
            logger.error(f"Error performing tap: {e}")
            return {
                "success": False,
                "message": f"Error performing tap: {str(e)}"
            }

    async def double_tap(self, x: int, y: int) -> Dict[str, Any]:
        """
        Perform a double tap at the specified coordinates.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            Dictionary with double tap result
        """
        if not self.is_running:
            return {
                "success": False,
                "message": "WDA is not running"
            }

        try:
            session_id = await self._ensure_session()
            client = await self._get_client()

            # Perform double tap
            response = await client.post(
                f"/session/{session_id}/wda/doubleTap",
                json={"x": x, "y": y}
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "x": x,
                    "y": y,
                    "message": "Double tap performed successfully"
                }

            return {
                "success": False,
                "message": f"Double tap failed: {response.text}"
            }

        except Exception as e:
            logger.error(f"Error performing double tap: {e}")
            return {
                "success": False,
                "message": f"Error performing double tap: {str(e)}"
            }

    async def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.5
    ) -> Dict[str, Any]:
        """
        Perform a swipe from (x1, y1) to (x2, y2).

        Args:
            x1: Start X coordinate
            y1: Start Y coordinate
            x2: End X coordinate
            y2: End Y coordinate
            duration: Swipe duration in seconds

        Returns:
            Dictionary with swipe result
        """
        if not self.is_running:
            return {
                "success": False,
                "message": "WDA is not running"
            }

        try:
            session_id = await self._ensure_session()
            client = await self._get_client()

            # Perform swipe using WDA endpoint
            response = await client.post(
                f"/session/{session_id}/wda/performSwipe",
                json={
                    "startX": x1,
                    "startY": y1,
                    "endX": x2,
                    "endY": y2,
                    "duration": duration
                }
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "start": {"x": x1, "y": y1},
                    "end": {"x": x2, "y": y2},
                    "duration": duration,
                    "message": "Swipe performed successfully"
                }

            # Try alternative endpoint
            response = await client.post(
                f"/session/{session_id}/touch/perform",
                json={
                    "actions": [
                        {"action": "press", "options": {"x": x1, "y": y1}},
                        {"action": "wait", "options": {"ms": int(duration * 1000)}},
                        {"action": "moveTo", "options": {"x": x2, "y": y2}},
                        {"action": "release", "options": {}}
                    ]
                }
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "start": {"x": x1, "y": y1},
                    "end": {"x": x2, "y": y2},
                    "duration": duration,
                    "message": "Swipe performed successfully"
                }

            return {
                "success": False,
                "message": f"Swipe failed: {response.text}"
            }

        except Exception as e:
            logger.error(f"Error performing swipe: {e}")
            return {
                "success": False,
                "message": f"Error performing swipe: {str(e)}"
            }

    async def pinch(
        self,
        x: int,
        y: int,
        scale: float,
        velocity: float = 1.0
    ) -> Dict[str, Any]:
        """
        Perform a pinch gesture at the specified coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            scale: Pinch scale (zoom in > 1, zoom out < 1)
            velocity: Pinch velocity

        Returns:
            Dictionary with pinch result
        """
        if not self.is_running:
            return {
                "success": False,
                "message": "WDA is not running"
            }

        try:
            session_id = await self._ensure_session()
            client = await self._get_client()

            response = await client.post(
                f"/session/{session_id}/wda/pinch",
                json={
                    "scale": scale,
                    "velocity": velocity,
                    "x": x,
                    "y": y
                }
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "x": x,
                    "y": y,
                    "scale": scale,
                    "message": "Pinch performed successfully"
                }

            return {
                "success": False,
                "message": f"Pinch failed: {response.text}"
            }

        except Exception as e:
            logger.error(f"Error performing pinch: {e}")
            return {
                "success": False,
                "message": f"Error performing pinch: {str(e)}"
            }

    async def screenshot(self) -> Dict[str, Any]:
        """
        Take a screenshot of the device screen.

        Returns:
            Dictionary with screenshot data (base64 encoded)
        """
        if not self.is_running:
            return {
                "success": False,
                "message": "WDA is not running"
            }

        try:
            session_id = await self._ensure_session()
            client = await self._get_client()

            response = await client.get(f"/session/{session_id}/screenshot")

            if response.status_code == 200:
                data = response.json()
                # WDA returns base64 encoded screenshot
                screenshot_base64 = data.get("value")

                if screenshot_base64:
                    return {
                        "success": True,
                        "data": screenshot_base64,
                        "format": "png",
                        "message": "Screenshot taken successfully"
                    }

            return {
                "success": False,
                "message": f"Screenshot failed: {response.text}"
            }

        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return {
                "success": False,
                "message": f"Error taking screenshot: {str(e)}"
            }

    async def get_screenshot_bytes(self) -> Optional[bytes]:
        """
        Take a screenshot and return as bytes.

        Returns:
            Screenshot bytes or None on failure
        """
        result = await self.screenshot()
        if result.get("success"):
            return base64.b64decode(result["data"])
        return None

    async def get_screen_size(self) -> Tuple[int, int]:
        """
        Get the screen size.

        Returns:
            Tuple of (width, height)
        """
        if self._screen_size:
            return self._screen_size

        await self._init_screen_size()
        return self._screen_size or (0, 0)

    async def home_button(self) -> Dict[str, Any]:
        """
        Press the home button.

        Returns:
            Dictionary with result
        """
        if not self.is_running:
            return {
                "success": False,
                "message": "WDA is not running"
            }

        try:
            session_id = await self._ensure_session()
            client = await self._get_client()

            response = await client.post(
                f"/session/{session_id}/wda/pressButton",
                json={"name": "home"}
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "message": "Home button pressed"
                }

            return {
                "success": False,
                "message": f"Home button failed: {response.text}"
            }

        except Exception as e:
            logger.error(f"Error pressing home button: {e}")
            return {
                "success": False,
                "message": f"Error pressing home button: {str(e)}"
            }

    async def type_text(self, text: str) -> Dict[str, Any]:
        """
        Type text into the currently focused element.

        Args:
            text: Text to type

        Returns:
            Dictionary with result
        """
        if not self.is_running:
            return {
                "success": False,
                "message": "WDA is not running"
            }

        try:
            session_id = await self._ensure_session()
            client = await self._get_client()

            response = await client.post(
                f"/session/{session_id}/keys",
                json={"value": list(text)}
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "text": text,
                    "message": "Text typed successfully"
                }

            return {
                "success": False,
                "message": f"Type text failed: {response.text}"
            }

        except Exception as e:
            logger.error(f"Error typing text: {e}")
            return {
                "success": False,
                "message": f"Error typing text: {str(e)}"
            }

    async def find_element(
        self,
        locator_type: str,
        locator_value: str
    ) -> Dict[str, Any]:
        """
        Find an element by locator.

        Args:
            locator_type: Type of locator (id, xpath, class_name, etc.)
            locator_value: Locator value

        Returns:
            Dictionary with element info
        """
        if not self.is_running:
            return {
                "success": False,
                "message": "WDA is not running"
            }

        try:
            session_id = await self._ensure_session()
            client = await self._get_client()

            response = await client.post(
                f"/session/{session_id}/element",
                json={
                    "using": locator_type,
                    "value": locator_value
                }
            )

            if response.status_code == 200:
                data = response.json()
                element_id = data.get("value", {}).get("ELEMENT") or \
                            data.get("value", {}).get("element-6066-11e4-a52e-4f735466cecf")

                return {
                    "success": True,
                    "element_id": element_id,
                    "message": "Element found"
                }

            return {
                "success": False,
                "message": f"Element not found: {response.text}"
            }

        except Exception as e:
            logger.error(f"Error finding element: {e}")
            return {
                "success": False,
                "message": f"Error finding element: {str(e)}"
            }

    async def get_page_source(self) -> Dict[str, Any]:
        """
        Get the page source (UI hierarchy).

        Returns:
            Dictionary with page source
        """
        if not self.is_running:
            return {
                "success": False,
                "message": "WDA is not running"
            }

        try:
            session_id = await self._ensure_session()
            client = await self._get_client()

            response = await client.get(f"/session/{session_id}/source")

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "source": data.get("value"),
                    "message": "Page source retrieved"
                }

            return {
                "success": False,
                "message": f"Failed to get page source: {response.text}"
            }

        except Exception as e:
            logger.error(f"Error getting page source: {e}")
            return {
                "success": False,
                "message": f"Error getting page source: {str(e)}"
            }

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop_wda()


# Global instance
wda_driver = WDADriver()
