# Harmony Service - Device Management via HDC (HarmonyOS Device Connector)
import asyncio
import re
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.config import settings
from app.models import Device, DeviceStatus

logger = logging.getLogger(__name__)


class HarmonyDeviceService:
    """HarmonyOS device service using HDC for device communication"""

    def __init__(self):
        # HDC path - can be configured via settings
        self.hdc_path = getattr(settings, 'HDC_PATH', 'hdc')
        self._devices_cache: Dict[str, Device] = {}

    async def _execute_hdc(self, *args: str, device_id: Optional[str] = None) -> str:
        """Execute HDC command"""
        cmd = [self.hdc_path]
        if device_id:
            cmd.extend(["-t", device_id])
        cmd.extend(args)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"HDC command failed: {stderr.decode()}")
                raise Exception(f"HDC command failed: {stderr.decode()}")

            return stdout.decode().strip()
        except Exception as e:
            logger.error(f"Error executing HDC command: {e}")
            raise

    async def execute_hdc(self, *args: str, device_id: Optional[str] = None) -> str:
        """Public method to execute HDC command (wrapper for _execute_hdc)"""
        return await self._execute_hdc(*args, device_id=device_id)

    async def discover_devices(self) -> List[Dict[str, Any]]:
        """
        Discover HarmonyOS devices via HDC.
        Returns list of device info dictionaries.
        """
        try:
            # hdc list targets returns connected devices
            output = await self._execute_hdc("list", "targets")
            devices = []

            for line in output.split('\n'):
                line = line.strip()
                if not line or line.startswith('['):
                    continue

                # HDC output format: <serial>[:<status>]
                # e.g., "1234567890abcdef" or "1234567890abcdef:device"
                parts = line.split(':')
                serial = parts[0]
                status_str = parts[1] if len(parts) > 1 else "device"

                if status_str == "device" or status_str == "authorised":
                    status = DeviceStatus.ONLINE
                elif status_str == "offline":
                    status = DeviceStatus.OFFLINE
                elif status_str == "unauthorised":
                    # Device needs authorization
                    status = DeviceStatus.OFFLINE
                else:
                    status = DeviceStatus.OFFLINE

                devices.append({
                    "id": serial,
                    "status": status
                })

            return devices
        except Exception as e:
            logger.error(f"Error discovering HarmonyOS devices: {e}")
            return []

    async def get_device_info(self, serial: str) -> Dict[str, Any]:
        """
        Get detailed device information.

        Args:
            serial: Device serial number

        Returns:
            Dictionary with device information
        """
        info = {"id": serial, "os": "harmony"}

        try:
            # Get device model
            model = await self._execute_hdc(
                "shell", "getprop", "ro.product.model",
                device_id=serial
            )
            info["model"] = model or "Unknown"

            # Get device brand
            brand = await self._execute_hdc(
                "shell", "getprop", "ro.product.brand",
                device_id=serial
            )
            info["brand"] = brand or "Huawei"

            # Get device name
            name = await self._execute_hdc(
                "shell", "getprop", "ro.product.device",
                device_id=serial
            )
            info["name"] = name or model or serial

            # Get OS version (HarmonyOS version)
            os_version = await self._execute_hdc(
                "shell", "getprop", "ro.build.version.harmonyos",
                device_id=serial
            )
            if not os_version or os_version == "Unknown":
                # Fallback to API level
                os_version = await self._execute_hdc(
                    "shell", "getprop", "ro.build.version.sdk",
                    device_id=serial
                )
            info["os_version"] = os_version or "Unknown"

            # Get screen resolution
            resolution = await self._execute_hdc(
                "shell", "param", "get", "const.display.resolution",
                device_id=serial
            )
            if not resolution or resolution == "Unknown":
                # Alternative method
                resolution = await self._execute_hdc(
                    "shell", "wm", "size",
                    device_id=serial
                )
            match = re.search(r'(\d+x\d+)', resolution)
            info["screen_resolution"] = match.group(1) if match else "Unknown"

            # Get screen density
            density = await self._execute_hdc(
                "shell", "param", "get", "const.display.density",
                device_id=serial
            )
            if not density:
                density = await self._execute_hdc(
                    "shell", "wm", "density",
                    device_id=serial
                )
            match = re.search(r'(\d+)', density)
            info["screen_density"] = int(match.group(1)) if match else 0

            # Get CPU info
            cpu = await self._execute_hdc(
                "shell", "getprop", "ro.product.cpu.abi",
                device_id=serial
            )
            info["cpu"] = cpu or "Unknown"

            # Get memory info
            meminfo = await self._execute_hdc(
                "shell", "cat", "/proc/meminfo",
                device_id=serial
            )
            match = re.search(r'MemTotal:\s+(\d+)', meminfo)
            if match:
                total_mb = int(match.group(1)) // 1024
                info["memory"] = f"{total_mb}MB"
            else:
                info["memory"] = "Unknown"

            # Get storage info
            storage = await self._execute_hdc(
                "shell", "df", "/data",
                device_id=serial
            )
            lines = storage.split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 2:
                    total_kb = int(parts[1])
                    total_gb = total_kb // (1024 * 1024)
                    info["storage"] = f"{total_gb}GB"
                else:
                    info["storage"] = "Unknown"
            else:
                info["storage"] = "Unknown"

            # Get battery level
            battery = await self._execute_hdc(
                "shell", "dumpsys", "battery",
                device_id=serial
            )
            match = re.search(r'level:\s*(\d+)', battery)
            info["battery_level"] = int(match.group(1)) if match else 100

            # Calculate screen size (approximate)
            if info.get("screen_resolution") != "Unknown":
                try:
                    w, h = map(int, info["screen_resolution"].split('x'))
                    density = info.get("screen_density", 480)
                    diagonal = ((w/density)**2 + (h/density)**2)**0.5
                    info["screen_size"] = round(diagonal, 1)
                except:
                    info["screen_size"] = 6.5
            else:
                info["screen_size"] = 6.5

        except Exception as e:
            logger.error(f"Error getting HarmonyOS device info: {e}")
            info["name"] = serial
            info["model"] = "Unknown"
            info["brand"] = "Huawei"
            info["os_version"] = "Unknown"
            info["screen_resolution"] = "Unknown"
            info["screen_size"] = 6.5
            info["cpu"] = "Unknown"
            info["memory"] = "Unknown"
            info["storage"] = "Unknown"

        return info

    async def install_app(self, serial: str, hap_path: str) -> Dict[str, Any]:
        """
        Install a HAP (HarmonyOS Ability Package) to device.

        Args:
            serial: Device serial number
            hap_path: Path to HAP file

        Returns:
            Dictionary with installation result
        """
        try:
            result = await self._execute_hdc(
                "install", hap_path,
                device_id=serial
            )

            if "success" in result.lower():
                return {
                    "success": True,
                    "serial": serial,
                    "message": "HAP installed successfully"
                }
            else:
                return {
                    "success": False,
                    "serial": serial,
                    "message": f"Installation failed: {result}"
                }
        except Exception as e:
            return {
                "success": False,
                "serial": serial,
                "message": f"Installation failed: {str(e)}"
            }

    async def uninstall_app(self, serial: str, package: str) -> Dict[str, Any]:
        """
        Uninstall an app from device.

        Args:
            serial: Device serial number
            package: Package name (bundle identifier)

        Returns:
            Dictionary with uninstallation result
        """
        try:
            result = await self._execute_hdc(
                "uninstall", package,
                device_id=serial
            )

            if "success" in result.lower():
                return {
                    "success": True,
                    "serial": serial,
                    "package": package,
                    "message": "App uninstalled successfully"
                }
            else:
                return {
                    "success": False,
                    "serial": serial,
                    "package": package,
                    "message": f"Uninstallation failed: {result}"
                }
        except Exception as e:
            return {
                "success": False,
                "serial": serial,
                "package": package,
                "message": f"Uninstallation failed: {str(e)}"
            }

    async def start_app(self, serial: str, bundle: str, ability: str) -> bool:
        """
        Start an app on device.

        Args:
            serial: Device serial number
            bundle: Bundle identifier
            ability: Ability name (entry point)

        Returns:
            True if successful
        """
        try:
            # HarmonyOS uses AA (Ability Manager) tool
            await self._execute_hdc(
                "shell", "aa", "start", "-a", ability, "-b", bundle,
                device_id=serial
            )
            return True
        except Exception as e:
            logger.error(f"Error starting app: {e}")
            return False

    async def stop_app(self, serial: str, bundle: str) -> bool:
        """
        Force stop an app.

        Args:
            serial: Device serial number
            bundle: Bundle identifier

        Returns:
            True if successful
        """
        try:
            await self._execute_hdc(
                "shell", "aa", "force-stop", bundle,
                device_id=serial
            )
            return True
        except Exception as e:
            logger.error(f"Error stopping app: {e}")
            return False

    async def get_screenshot(self, serial: str) -> Optional[bytes]:
        """
        Take a screenshot from device.

        Args:
            serial: Device serial number

        Returns:
            Screenshot as bytes (PNG format)
        """
        try:
            # Take screenshot on device
            await self._execute_hdc(
                "shell", "snapshot_display", "-f", "/data/local/tmp/screenshot.png",
                device_id=serial
            )

            # Pull screenshot to local
            process = await asyncio.create_subprocess_exec(
                self.hdc_path, "-t", serial, "file", "recv",
                "/data/local/tmp/screenshot.png", "-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            # Cleanup
            await self._execute_hdc(
                "shell", "rm", "/data/local/tmp/screenshot.png",
                device_id=serial
            )

            return stdout
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return None

    async def list_apps(self, serial: str) -> List[Dict[str, Any]]:
        """
        List installed applications on device.

        Args:
            serial: Device serial number

        Returns:
            List of installed apps
        """
        try:
            result = await self._execute_hdc(
                "shell", "bm", "dump", "-a",
                device_id=serial
            )

            apps = []
            # Parse bundle dump output
            # Format varies, typically shows bundle info
            current_app = {}
            for line in result.split('\n'):
                line = line.strip()
                if line.startswith('ID:'):
                    if current_app and 'id' in current_app:
                        apps.append(current_app)
                    current_app = {'id': line.split(':')[1].strip()}
                elif line.startswith('Label:'):
                    current_app['name'] = line.split(':')[1].strip()
                elif line.startswith('Version:'):
                    current_app['version'] = line.split(':')[1].strip()

            if current_app and 'id' in current_app:
                apps.append(current_app)

            return apps
        except Exception as e:
            logger.error(f"Error listing apps: {e}")
            return []

    async def get_device_logs(self, serial: str, lines: int = 100) -> str:
        """
        Get device logs (hilog).

        Args:
            serial: Device serial number
            lines: Number of log lines to retrieve

        Returns:
            Log content as string
        """
        try:
            return await self._execute_hdc(
                "shell", "hilog", "-x", "-T", str(lines),
                device_id=serial
            )
        except Exception as e:
            logger.error(f"Error getting device logs: {e}")
            return ""

    async def shell(self, serial: str, command: str) -> str:
        """
        Execute shell command on device.

        Args:
            serial: Device serial number
            command: Shell command to execute

        Returns:
            Command output
        """
        try:
            return await self._execute_hdc(
                "shell", command,
                device_id=serial
            )
        except Exception as e:
            logger.error(f"Error executing shell command: {e}")
            return ""


# Global instance
harmony_service = HarmonyDeviceService()
