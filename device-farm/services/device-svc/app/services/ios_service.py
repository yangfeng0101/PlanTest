# iOS Service - Device Management via pymobiledevice3
import asyncio
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.config import settings
from app.models import Device, DeviceStatus

logger = logging.getLogger(__name__)


class IOSDeviceService:
    """iOS device service using pymobiledevice3 for usbmuxd communication"""

    def __init__(self):
        self._devices_cache: Dict[str, Device] = {}

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

    async def _execute_pymobiledevice3_json(self, *args: str) -> Any:
        """Execute pymobiledevice3 CLI command and parse JSON output"""
        output = await self._execute_pymobiledevice3(*args)
        if output:
            return json.loads(output)
        return None

    async def discover_devices(self) -> List[Dict[str, Any]]:
        """
        Discover iOS devices via usbmuxd.
        Returns list of device info dictionaries.
        """
        try:
            # Use pymobiledevice3 to list connected devices
            result = await self._execute_pymobiledevice3_json("usbmux", "list", "--json")

            if not result:
                return []

            devices = []
            for device_info in result:
                # Each device has: SerialNumber (UDID), ConnectionType, DeviceID
                udid = device_info.get("SerialNumber") or device_info.get("UDID")
                if not udid:
                    continue

                devices.append({
                    "id": udid,
                    "device_id": device_info.get("DeviceID"),
                    "connection_type": device_info.get("ConnectionType", "USB"),
                    "status": DeviceStatus.ONLINE
                })

            return devices
        except Exception as e:
            logger.error(f"Error discovering iOS devices: {e}")
            return []

    async def get_device_info(self, udid: str) -> Dict[str, Any]:
        """
        Get detailed device information.

        Args:
            udid: Device Unique Device Identifier

        Returns:
            Dictionary with device information
        """
        info = {"id": udid, "os": "ios"}

        try:
            # Get basic device info via lockdownd
            device_info = await self._execute_pymobiledevice3_json(
                "lockdown", "info", "--udid", udid, "--json"
            )

            if device_info:
                # Device name
                info["name"] = device_info.get("DeviceName", udid)
                info["model"] = device_info.get("ProductType", "Unknown")
                info["brand"] = "Apple"

                # OS version
                info["os_version"] = device_info.get("ProductVersion", "Unknown")
                info["build_version"] = device_info.get("BuildVersion", "Unknown")

                # Hardware info
                info["device_class"] = device_info.get("DeviceClass", "Unknown")
                info["product_type"] = device_info.get("ProductType", "Unknown")
                info["model_number"] = device_info.get("ModelNumber", "Unknown")

                # Screen resolution (iOS doesn't expose this directly via lockdown)
                # Will need to get from display info or use defaults
                info["screen_resolution"] = self._get_screen_resolution(
                    device_info.get("ProductType", "")
                )
                info["screen_size"] = self._get_screen_size(
                    device_info.get("ProductType", "")
                )

                # CPU info
                info["cpu"] = device_info.get("CPUArchitecture", "arm64")

                # Memory and storage require additional queries
                info["memory"] = "Unknown"
                info["storage"] = "Unknown"
                info["battery_level"] = 100

                # Try to get battery info
                try:
                    battery_info = await self._get_battery_info(udid)
                    if battery_info:
                        info["battery_level"] = battery_info.get("CurrentCapacity", 100)
                except Exception as e:
                    logger.warning(f"Could not get battery info: {e}")

                # Try to get storage info
                try:
                    storage_info = await self._get_storage_info(udid)
                    if storage_info:
                        info["storage"] = storage_info
                except Exception as e:
                    logger.warning(f"Could not get storage info: {e}")

        except Exception as e:
            logger.error(f"Error getting iOS device info: {e}")
            info["name"] = udid
            info["model"] = "Unknown"
            info["brand"] = "Apple"
            info["os_version"] = "Unknown"
            info["screen_resolution"] = "Unknown"
            info["screen_size"] = 5.5
            info["cpu"] = "Unknown"
            info["memory"] = "Unknown"
            info["storage"] = "Unknown"

        return info

    async def _get_battery_info(self, udid: str) -> Optional[Dict[str, Any]]:
        """Get battery information from device"""
        try:
            result = await self._execute_pymobiledevice3_json(
                "lockdown", "get", "--domain", "com.apple.mobile.battery",
                "--udid", udid, "--json"
            )
            return result
        except Exception:
            return None

    async def _get_storage_info(self, udid: str) -> Optional[str]:
        """Get storage information from device"""
        try:
            result = await self._execute_pymobiledevice3_json(
                "lockdown", "get", "--domain", "com.apple.disk_usage",
                "--udid", udid, "--json"
            )

            if result and "TotalDiskCapacity" in result:
                total_bytes = result["TotalDiskCapacity"]
                total_gb = total_bytes // (1024 * 1024 * 1024)
                return f"{total_gb}GB"
        except Exception:
            pass
        return None

    def _get_screen_resolution(self, product_type: str) -> str:
        """Get screen resolution based on product type"""
        # Common iOS device resolutions
        resolutions = {
            # iPhone
            "iPhone14,2": "1170x2532",  # iPhone 13 Pro
            "iPhone14,3": "1284x2778",  # iPhone 13 Pro Max
            "iPhone15,2": "1179x2556",  # iPhone 14 Pro
            "iPhone15,3": "1290x2796",  # iPhone 14 Pro Max
            "iPhone16,1": "1179x2556",  # iPhone 15 Pro
            "iPhone16,2": "1320x2868",  # iPhone 15 Pro Max
            # iPad
            "iPad13,1": "1620x2160",  # iPad Air 4
            "iPad13,8": "2048x2732",  # iPad Pro 12.9 5th gen
        }
        return resolutions.get(product_type, "1170x2532")

    def _get_screen_size(self, product_type: str) -> float:
        """Get screen size in inches based on product type"""
        # Common iOS device screen sizes
        sizes = {
            # iPhone
            "iPhone14,2": 6.1,   # iPhone 13 Pro
            "iPhone14,3": 6.7,   # iPhone 13 Pro Max
            "iPhone15,2": 6.1,   # iPhone 14 Pro
            "iPhone15,3": 6.7,   # iPhone 14 Pro Max
            "iPhone16,1": 6.1,   # iPhone 15 Pro
            "iPhone16,2": 6.7,   # iPhone 15 Pro Max
            # iPad
            "iPad13,1": 10.9,    # iPad Air 4
            "iPad13,8": 12.9,    # iPad Pro 12.9 5th gen
        }
        return sizes.get(product_type, 6.1)

    async def pair_device(self, udid: str) -> Dict[str, Any]:
        """
        Pair with an iOS device.

        Args:
            udid: Device Unique Device Identifier

        Returns:
            Dictionary with pairing result
        """
        try:
            result = await self._execute_pymobiledevice3_json(
                "usbmux", "pair", "--udid", udid, "--json"
            )

            return {
                "success": True,
                "udid": udid,
                "message": "Device paired successfully",
                "details": result
            }
        except Exception as e:
            error_msg = str(e)
            if "PasswordRequired" in error_msg or "UserPairingRequired" in error_msg:
                return {
                    "success": False,
                    "udid": udid,
                    "message": "Device requires manual pairing confirmation on the device screen",
                    "requires_confirmation": True
                }
            return {
                "success": False,
                "udid": udid,
                "message": f"Pairing failed: {error_msg}",
                "requires_confirmation": False
            }

    async def unpair_device(self, udid: str) -> Dict[str, Any]:
        """
        Unpair an iOS device.

        Args:
            udid: Device Unique Device Identifier

        Returns:
            Dictionary with unpairing result
        """
        try:
            await self._execute_pymobiledevice3(
                "usbmux", "unpair", "--udid", udid
            )

            return {
                "success": True,
                "udid": udid,
                "message": "Device unpaired successfully"
            }
        except Exception as e:
            return {
                "success": False,
                "udid": udid,
                "message": f"Unpairing failed: {str(e)}"
            }

    async def get_pairing_status(self, udid: str) -> Dict[str, Any]:
        """
        Check if device is paired.

        Args:
            udid: Device Unique Device Identifier

        Returns:
            Dictionary with pairing status
        """
        try:
            # Try to get lockdown info - will fail if not paired
            await self._execute_pymobiledevice3_json(
                "lockdown", "info", "--udid", udid, "--json"
            )
            return {
                "paired": True,
                "udid": udid
            }
        except Exception as e:
            error_msg = str(e)
            return {
                "paired": False,
                "udid": udid,
                "error": error_msg
            }

    async def list_apps(self, udid: str) -> List[Dict[str, Any]]:
        """
        List installed applications on device.

        Args:
            udid: Device Unique Device Identifier

        Returns:
            List of installed apps
        """
        try:
            result = await self._execute_pymobiledevice3_json(
                "apps", "list", "--udid", udid, "--json"
            )

            if not result:
                return []

            apps = []
            for app_id, app_info in result.items():
                apps.append({
                    "bundle_id": app_id,
                    "name": app_info.get("CFBundleDisplayName", app_id),
                    "version": app_info.get("CFBundleShortVersionString", "Unknown"),
                    "install_type": app_info.get("ApplicationType", "Unknown")
                })

            return apps
        except Exception as e:
            logger.error(f"Error listing apps: {e}")
            return []

    async def install_app(self, udid: str, ipa_path: str) -> Dict[str, Any]:
        """
        Install an IPA to device.

        Args:
            udid: Device Unique Device Identifier
            ipa_path: Path to IPA file

        Returns:
            Dictionary with installation result
        """
        try:
            await self._execute_pymobiledevice3(
                "apps", "install", "--udid", udid, ipa_path
            )

            return {
                "success": True,
                "udid": udid,
                "message": "App installed successfully"
            }
        except Exception as e:
            return {
                "success": False,
                "udid": udid,
                "message": f"Installation failed: {str(e)}"
            }

    async def uninstall_app(self, udid: str, bundle_id: str) -> Dict[str, Any]:
        """
        Uninstall an app from device.

        Args:
            udid: Device Unique Device Identifier
            bundle_id: Bundle identifier of the app

        Returns:
            Dictionary with uninstallation result
        """
        try:
            await self._execute_pymobiledevice3(
                "apps", "uninstall", "--udid", udid, bundle_id
            )

            return {
                "success": True,
                "udid": udid,
                "bundle_id": bundle_id,
                "message": "App uninstalled successfully"
            }
        except Exception as e:
            return {
                "success": False,
                "udid": udid,
                "bundle_id": bundle_id,
                "message": f"Uninstallation failed: {str(e)}"
            }

    async def get_device_logs(self, udid: str, lines: int = 100) -> str:
        """
        Get device logs (oslog).

        Args:
            udid: Device Unique Device Identifier
            lines: Number of log lines to retrieve

        Returns:
            Log content as string
        """
        try:
            result = await self._execute_pymobiledevice3(
                "oslog", "stream", "--udid", udid, "--no-color"
            )
            # oslog stream is continuous, so we just return empty
            # In real implementation, would need to handle streaming
            return result or ""
        except Exception as e:
            logger.error(f"Error getting device logs: {e}")
            return ""


# Global instance
ios_service = IOSDeviceService()
