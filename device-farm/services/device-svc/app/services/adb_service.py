# ADB Service - Device Management via ADB
import asyncio
import re
from typing import List, Optional, Dict, Any
from datetime import datetime
import subprocess
import logging

from app.config import settings
from app.models import Device, DeviceStatus
from app.models.device_model_map import get_market_name

logger = logging.getLogger(__name__)


class ADBService:
    """ADB service for device management"""

    def __init__(self):
        self.adb_path = settings.ADB_PATH
        self._devices_cache: Dict[str, Device] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def _get_device_lock(self, device_id: Optional[str]) -> asyncio.Lock:
        """Get or create a lock for a specific device"""
        if not device_id:
            return self._global_lock
        if device_id not in self._locks:
            self._locks[device_id] = asyncio.Lock()
        return self._locks[device_id]

    async def execute_adb(self, *args: str, device_id: Optional[str] = None, timeout: float = 10.0) -> str:
        """Execute ADB command with per-device lock and timeout"""
        lock = self._get_device_lock(device_id)
        async with lock:
            cmd = [self.adb_path]
            
            # Add host and port if configured
            if settings.ADB_SERVER_HOST and settings.ADB_SERVER_HOST != "localhost":
                cmd.extend(["-H", settings.ADB_SERVER_HOST])
            if settings.ADB_SERVER_PORT:
                cmd.extend(["-P", str(settings.ADB_SERVER_PORT)])
                
            if device_id:
                cmd.extend(["-s", device_id])
            cmd.extend(args)

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except:
                        pass
                    logger.error(f"ADB command timed out after {timeout}s: {' '.join(cmd)}")
                    raise Exception(f"ADB command timed out after {timeout}s")

                if process.returncode != 0:
                    err_msg = stderr.decode().strip()
                    # If it's a daemon not running error, try one more time
                    if "daemon not running" in err_msg:
                        await asyncio.sleep(1)
                        # Recursive call with same timeout
                        return await self.execute_adb(*args, device_id=device_id, timeout=timeout)

                    logger.error(f"ADB command failed: {err_msg}")
                    raise Exception(f"ADB command failed: {err_msg}")

                return stdout.decode().strip()
            except Exception as e:
                if not isinstance(e, asyncio.TimeoutError):
                    logger.error(f"Error executing ADB command: {e}")
                raise

    async def list_devices(self) -> List[Dict[str, str]]:
        """List all connected devices"""
        output = await self.execute_adb("devices", "-l")
        devices = []

        lines = output.split('\n')
        for line in lines[1:]:  # Skip header
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 2:
                device_id = parts[0]
                status = parts[1]

                if status == "device":
                    devices.append({
                        "id": device_id,
                        "status": DeviceStatus.ONLINE
                    })
                elif status == "offline":
                    devices.append({
                        "id": device_id,
                        "status": DeviceStatus.OFFLINE
                    })

        return devices

    async def get_device_info(self, device_id: str) -> Dict[str, Any]:
        """Get detailed device information"""
        info = {"id": device_id}

        try:
            # Get device model
            model = await self.execute_adb(
                "shell", "getprop", "ro.product.model",
                device_id=device_id
            )
            info["model"] = model or "Unknown"

            # Get device brand
            brand = await self.execute_adb(
                "shell", "getprop", "ro.product.brand",
                device_id=device_id
            )
            info["brand"] = brand or "Unknown"

            # Get device name (market name from model mapping)
            market_name = get_market_name(model) if model else model
            info["name"] = market_name or model or device_id

            # Get OS version
            os_version = await self.execute_adb(
                "shell", "getprop", "ro.build.version.release",
                device_id=device_id
            )
            info["os_version"] = os_version or "Unknown"

            # Get screen resolution
            resolution = await self.execute_adb(
                "shell", "wm", "size",
                device_id=device_id
            )
            match = re.search(r'(\d+x\d+)', resolution)
            info["screen_resolution"] = match.group(1) if match else "Unknown"

            # Get screen density
            density = await self.execute_adb(
                "shell", "wm", "density",
                device_id=device_id
            )
            match = re.search(r'(\d+)', density)
            info["screen_density"] = int(match.group(1)) if match else 0

            # Get CPU info
            cpu = await self.execute_adb(
                "shell", "getprop", "ro.product.cpu.abi",
                device_id=device_id
            )
            info["cpu"] = cpu or "Unknown"

            # Get memory info
            meminfo = await self.execute_adb(
                "shell", "cat", "/proc/meminfo",
                device_id=device_id
            )
            match = re.search(r'MemTotal:\s+(\d+)', meminfo)
            if match:
                total_mb = int(match.group(1)) // 1024
                info["memory"] = f"{total_mb}MB"
            else:
                info["memory"] = "Unknown"

            # Get storage info
            storage = await self.execute_adb(
                "shell", "df", "/data",
                device_id=device_id
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
            battery = await self.execute_adb(
                "shell", "dumpsys", "battery",
                device_id=device_id
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
                    info["screen_size"] = 5.5
            else:
                info["screen_size"] = 5.5

        except Exception as e:
            logger.error(f"Error getting device info: {e}")

        return info

    async def get_screenshot(self, device_id: str) -> Optional[bytes]:
        """Take a screenshot from device"""
        try:
            # Take screenshot on device
            await self.execute_adb(
                "shell", "screencap", "-p", "/sdcard/screenshot.png",
                device_id=device_id
            )

            # Pull screenshot to local
            process = await asyncio.create_subprocess_exec(
                self.adb_path, "-s", device_id, "exec-out",
                "cat", "/sdcard/screenshot.png",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            # Cleanup
            await self.execute_adb(
                "shell", "rm", "/sdcard/screenshot.png",
                device_id=device_id
            )

            return stdout
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return None

    async def install_app(self, device_id: str, apk_path: str) -> bool:
        """Install APK to device"""
        try:
            result = await self.execute_adb(
                "install", "-r", apk_path,
                device_id=device_id
            )
            return "Success" in result
        except Exception as e:
            logger.error(f"Error installing app: {e}")
            return False

    async def uninstall_app(self, device_id: str, package: str) -> bool:
        """Uninstall app from device"""
        try:
            result = await self.execute_adb(
                "uninstall", package,
                device_id=device_id
            )
            return "Success" in result
        except Exception as e:
            logger.error(f"Error uninstalling app: {e}")
            return False

    async def start_app(self, device_id: str, package: str, activity: str) -> bool:
        """Start an app on device"""
        try:
            await self.execute_adb(
                "shell", "am", "start", "-n", f"{package}/{activity}",
                device_id=device_id
            )
            return True
        except Exception as e:
            logger.error(f"Error starting app: {e}")
            return False

    async def stop_app(self, device_id: str, package: str) -> bool:
        """Force stop an app"""
        try:
            await self.execute_adb(
                "shell", "am", "force-stop", package,
                device_id=device_id
            )
            return True
        except Exception as e:
            logger.error(f"Error stopping app: {e}")
            return False

    async def get_device_logs(self, device_id: str, lines: int = 100) -> str:
        """Get logcat output"""
        try:
            return await self.execute_adb(
                "logcat", "-t", str(lines),
                device_id=device_id
            )
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
            return ""


# Global instance
adb_service = ADBService()
