# Device Metrics Collection Service
import asyncio
import re
import logging
import json
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
import redis.asyncio as redis

from app.config import settings
from app.models import DeviceMetrics, Device
from app.services import device_service
from app.services.adb_service import adb_service
from app.services.ios_service import ios_service
from app.services.harmony_service import harmony_service

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Base class for device metrics collectors"""

    def __init__(self):
        self._running = False
        self._collection_task: Optional[asyncio.Task] = None
        self._metrics_cache: Dict[str, DeviceMetrics] = {}
        self._redis: Optional[redis.Redis] = None
        self._previous_network: Dict[str, Dict[str, int]] = {}  # Track previous network values for speed calculation
        self._previous_time: Dict[str, datetime] = {}  # Track previous collection time
        self._alerts_cache: Dict[str, List[Any]] = {}  # Cache recent alerts by device_id

    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection"""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
        return self._redis

    async def collect_android_metrics(self, device_id: str) -> Optional[DeviceMetrics]:
        """Collect metrics from Android device using ADB"""
        try:
            metrics = DeviceMetrics(device_id=device_id)

            # Get CPU usage
            cpu_output = await adb_service.execute_adb(
                "shell", "dumpsys", "cpuinfo", "-n",
                device_id=device_id
            )
            metrics.cpu_usage = self._parse_android_cpu(cpu_output)

            # Get CPU temperature
            try:
                temp_output = await adb_service.execute_adb(
                    "shell", "cat", "/sys/class/thermal/thermal_zone0/temp",
                    device_id=device_id
                )
                if temp_output and temp_output.isdigit():
                    temp = int(temp_output) / 1000.0  # Convert from millidegrees
                    metrics.cpu_temperature = temp
                    metrics.device_temperature = temp
            except Exception:
                pass

            # Get memory info
            mem_output = await adb_service.execute_adb(
                "shell", "dumpsys", "meminfo",
                device_id=device_id
            )
            mem_data = self._parse_android_memory(mem_output)
            metrics.memory_usage = mem_data.get("usage", 0.0)
            metrics.memory_total_mb = mem_data.get("total_mb")
            metrics.memory_used_mb = mem_data.get("used_mb")
            metrics.memory_free_mb = mem_data.get("free_mb")

            # Get network info
            net_output = await adb_service.execute_adb(
                "shell", "cat", "/proc/net/dev",
                device_id=device_id
            )
            net_data = self._parse_android_network(net_output, device_id)
            metrics.network_rx_bytes = net_data.get("rx_bytes", 0)
            metrics.network_tx_bytes = net_data.get("tx_bytes", 0)
            metrics.network_rx_speed_kbps = net_data.get("rx_speed_kbps", 0.0)
            metrics.network_tx_speed_kbps = net_data.get("tx_speed_kbps", 0.0)

            # Get battery info
            battery_output = await adb_service.execute_adb(
                "shell", "dumpsys", "battery",
                device_id=device_id
            )
            battery_data = self._parse_android_battery(battery_output)
            metrics.battery_level = battery_data.get("level", 100)
            metrics.battery_status = battery_data.get("status", "unknown")
            metrics.battery_temperature = battery_data.get("temperature")

            # Get uptime
            try:
                uptime_output = await adb_service.execute_adb(
                    "shell", "cat", "/proc/uptime",
                    device_id=device_id
                )
                if uptime_output:
                    uptime_str = uptime_output.split()[0]
                    metrics.uptime_seconds = int(float(uptime_str))
            except Exception:
                pass

            return metrics

        except Exception as e:
            logger.error(f"Error collecting Android metrics for {device_id}: {e}")
            return None

    def _parse_android_cpu(self, output: str) -> float:
        """Parse CPU usage from dumpsys cpuinfo output"""
        try:
            # Look for total CPU usage line like: "Total: 25% user + 10% kernel + 5% iowait + 1% irq + 1% softirq"
            for line in output.split('\n'):
                if line.strip().startswith('Total:'):
                    # Extract percentages
                    total = 0.0
                    matches = re.findall(r'(\d+(?:\.\d+)?)%', line)
                    for match in matches:
                        total += float(match)
                    return min(total, 100.0)

            # Fallback: look for line like "25% TOTAL"
            for line in output.split('\n'):
                if 'TOTAL' in line:
                    match = re.search(r'(\d+(?:\.\d+)?)%', line)
                    if match:
                        return min(float(match.group(1)), 100.0)

            return 0.0
        except Exception:
            return 0.0

    def _parse_android_memory(self, output: str) -> Dict[str, Any]:
        """Parse memory info from dumpsys meminfo output"""
        try:
            result = {}
            total_mem = 0
            used_mem = 0

            # Look for "Total PSS by process" section
            in_pss_section = False
            for line in output.split('\n'):
                if 'Total PSS:' in line:
                    # Example: "Total PSS: 1,234,567 kB"
                    match = re.search(r'(\d+(?:,\d+)*)\s*kB', line)
                    if match:
                        used_mem = int(match.group(1).replace(',', ''))

                if 'RAM:' in line:
                    # Example: "RAM: 3,836,204K total, 1,234,567K free"
                    match = re.search(r'(\d+(?:,\d+)*)K total', line)
                    if match:
                        total_mem = int(match.group(1).replace(',', ''))

            if total_mem > 0 and used_mem > 0:
                result["usage"] = (used_mem / total_mem) * 100
                result["total_mb"] = total_mem // 1024
                result["used_mb"] = used_mem // 1024
                result["free_mb"] = (total_mem - used_mem) // 1024

            return result
        except Exception:
            return {"usage": 0.0}

    def _parse_android_network(self, output: str, device_id: str) -> Dict[str, Any]:
        """Parse network info from /proc/net/dev output"""
        try:
            result = {"rx_bytes": 0, "tx_bytes": 0, "rx_speed_kbps": 0.0, "tx_speed_kbps": 0.0}

            # Find wlan0 or rmnet0 interface
            for line in output.split('\n'):
                if 'wlan0' in line or 'rmnet0' in line:
                    # Format: interface: rx_bytes rx_packets rx_errs rx_drop rx_fifo rx_frame rx_compressed rx_multicast
                    #                       tx_bytes tx_packets tx_errs tx_drop tx_fifo tx_colls tx_carrier tx_compressed
                    parts = line.split()
                    if len(parts) >= 10:
                        interface = parts[0].rstrip(':')
                        rx_bytes = int(parts[1])
                        tx_bytes = int(parts[9])
                        result["rx_bytes"] = rx_bytes
                        result["tx_bytes"] = tx_bytes

                        # Calculate speed
                        now = datetime.utcnow()
                        if device_id in self._previous_network:
                            prev_rx = self._previous_network[device_id].get("rx_bytes", 0)
                            prev_tx = self._previous_network[device_id].get("tx_bytes", 0)
                            prev_time = self._previous_time.get(device_id, now)

                            time_diff = (now - prev_time).total_seconds()
                            if time_diff > 0:
                                rx_diff = rx_bytes - prev_rx
                                tx_diff = tx_bytes - prev_tx
                                # Convert to KB/s
                                result["rx_speed_kbps"] = (rx_diff / time_diff) / 1024
                                result["tx_speed_kbps"] = (tx_diff / time_diff) / 1024

                        # Update previous values
                        self._previous_network[device_id] = {"rx_bytes": rx_bytes, "tx_bytes": tx_bytes}
                        self._previous_time[device_id] = now
                        break

            return result
        except Exception:
            return {"rx_bytes": 0, "tx_bytes": 0, "rx_speed_kbps": 0.0, "tx_speed_kbps": 0.0}

    def _parse_android_battery(self, output: str) -> Dict[str, Any]:
        """Parse battery info from dumpsys battery output"""
        result = {"level": 100, "status": "unknown", "temperature": None}

        try:
            for line in output.split('\n'):
                line = line.strip()

                if line.startswith('level:'):
                    result["level"] = int(line.split(':')[1].strip())

                elif line.startswith('status:'):
                    status_code = int(line.split(':')[1].strip())
                    status_map = {
                        1: "unknown",  # BATTERY_STATUS_UNKNOWN
                        2: "charging",  # BATTERY_STATUS_CHARGING
                        3: "discharging",  # BATTERY_STATUS_DISCHARGING
                        4: "discharging",  # BATTERY_STATUS_NOT_CHARGING
                        5: "full",  # BATTERY_STATUS_FULL
                    }
                    result["status"] = status_map.get(status_code, "unknown")

                elif line.startswith('temperature:'):
                    temp = int(line.split(':')[1].strip())
                    result["temperature"] = temp / 10.0  # Convert from deci-degrees

            return result
        except Exception:
            return result

    async def collect_ios_metrics(self, device_id: str) -> Optional[DeviceMetrics]:
        """Collect metrics from iOS device using pymobiledevice3"""
        try:
            metrics = DeviceMetrics(device_id=device_id)

            # Get device info which includes battery
            try:
                device_info = await ios_service._execute_pymobiledevice3_json(
                    "lockdown", "info", "--udid", device_id, "--json"
                )

                if device_info:
                    # Battery info may be in lockdown info
                    metrics.battery_level = device_info.get("BatteryCurrentCapacity", 100)
                    metrics.battery_status = "unknown"

            except Exception as e:
                logger.debug(f"Could not get iOS lockdown info: {e}")

            # Try to get more detailed battery info
            try:
                battery_info = await ios_service._get_battery_info(device_id)
                if battery_info:
                    metrics.battery_level = battery_info.get("CurrentCapacity", metrics.battery_level)

                    # Determine battery status
                    is_charging = battery_info.get("IsCharging", False)
                    fully_charged = battery_info.get("FullyCharged", False)
                    if fully_charged:
                        metrics.battery_status = "full"
                    elif is_charging:
                        metrics.battery_status = "charging"
                    else:
                        metrics.battery_status = "discharging"
            except Exception:
                pass

            # iOS doesn't expose CPU/Memory easily via lockdown
            # These would require DeveloperDiskImage and specific commands
            # For now, we'll set defaults and note that advanced metrics
            # would require additional setup
            metrics.cpu_usage = 0.0
            metrics.memory_usage = 0.0

            return metrics

        except Exception as e:
            logger.error(f"Error collecting iOS metrics for {device_id}: {e}")
            return None

    async def collect_harmony_metrics(self, device_id: str) -> Optional[DeviceMetrics]:
        """Collect metrics from HarmonyOS device using HDC"""
        try:
            metrics = DeviceMetrics(device_id=device_id)

            # Get CPU usage
            try:
                cpu_output = await harmony_service.execute_hdc(
                    "shell", "cat", "/proc/stat",
                    device_id=device_id
                )
                metrics.cpu_usage = self._parse_harmony_cpu(cpu_output)
            except Exception:
                pass

            # Get memory info
            try:
                mem_output = await harmony_service.execute_hdc(
                    "shell", "cat", "/proc/meminfo",
                    device_id=device_id
                )
                mem_data = self._parse_harmony_memory(mem_output)
                metrics.memory_usage = mem_data.get("usage", 0.0)
                metrics.memory_total_mb = mem_data.get("total_mb")
                metrics.memory_used_mb = mem_data.get("used_mb")
            except Exception:
                pass

            # Get battery info
            try:
                battery_output = await harmony_service.execute_hdc(
                    "shell", "dumpsys", "batterystats",
                    device_id=device_id
                )
                battery_data = self._parse_harmony_battery(battery_output)
                metrics.battery_level = battery_data.get("level", 100)
                metrics.battery_status = battery_data.get("status", "unknown")
            except Exception:
                pass

            # Get network info
            try:
                net_output = await harmony_service.execute_hdc(
                    "shell", "cat", "/proc/net/dev",
                    device_id=device_id
                )
                net_data = self._parse_android_network(net_output, device_id)  # Same format
                metrics.network_rx_bytes = net_data.get("rx_bytes", 0)
                metrics.network_tx_bytes = net_data.get("tx_bytes", 0)
                metrics.network_rx_speed_kbps = net_data.get("rx_speed_kbps", 0.0)
                metrics.network_tx_speed_kbps = net_data.get("tx_speed_kbps", 0.0)
            except Exception:
                pass

            return metrics

        except Exception as e:
            logger.error(f"Error collecting HarmonyOS metrics for {device_id}: {e}")
            return None

    def _parse_harmony_cpu(self, output: str) -> float:
        """Parse CPU usage from HarmonyOS /proc/stat"""
        try:
            lines = output.strip().split('\n')
            if lines:
                # First line is aggregate CPU: cpu user nice system idle iowait irq softirq
                parts = lines[0].split()
                if parts[0] == 'cpu' and len(parts) >= 5:
                    user = int(parts[1])
                    nice = int(parts[2])
                    system = int(parts[3])
                    idle = int(parts[4])

                    total = user + nice + system + idle
                    if total > 0:
                        usage = ((total - idle) / total) * 100
                        return min(usage, 100.0)

            return 0.0
        except Exception:
            return 0.0

    def _parse_harmony_memory(self, output: str) -> Dict[str, Any]:
        """Parse memory info from HarmonyOS /proc/meminfo"""
        try:
            result = {}
            total_kb = 0
            free_kb = 0
            available_kb = 0

            for line in output.split('\n'):
                if line.startswith('MemTotal:'):
                    total_kb = int(line.split()[1])
                elif line.startswith('MemFree:'):
                    free_kb = int(line.split()[1])
                elif line.startswith('MemAvailable:'):
                    available_kb = int(line.split()[1])

            if total_kb > 0:
                used_kb = total_kb - (available_kb or free_kb)
                result["usage"] = (used_kb / total_kb) * 100
                result["total_mb"] = total_kb // 1024
                result["used_mb"] = used_kb // 1024
                result["free_mb"] = (available_kb or free_kb) // 1024

            return result
        except Exception:
            return {"usage": 0.0}

    def _parse_harmony_battery(self, output: str) -> Dict[str, Any]:
        """Parse battery info from HarmonyOS dumpsys batterystats"""
        result = {"level": 100, "status": "unknown"}

        try:
            for line in output.split('\n'):
                line = line.strip()

                if 'level:' in line.lower():
                    match = re.search(r'level[:\s]+(\d+)', line, re.IGNORECASE)
                    if match:
                        result["level"] = int(match.group(1))

                if 'status:' in line.lower():
                    if 'charging' in line.lower():
                        result["status"] = "charging"
                    elif 'full' in line.lower():
                        result["status"] = "full"
                    elif 'discharging' in line.lower():
                        result["status"] = "discharging"

            return result
        except Exception:
            return result

    async def collect_device_metrics(self, device: Device) -> Optional[DeviceMetrics]:
        """Collect metrics for a device based on its OS type"""
        if device.os == "android":
            return await self.collect_android_metrics(device.id)
        elif device.os == "ios":
            return await self.collect_ios_metrics(device.id)
        elif device.os == "harmony":
            return await self.collect_harmony_metrics(device.id)
        else:
            logger.warning(f"Unknown OS type for device {device.id}: {device.os}")
            return None

    async def store_metrics(self, metrics: DeviceMetrics):
        """Store metrics in Redis with expiration"""
        try:
            r = await self._get_redis()
            key = f"metrics:{metrics.device_id}"

            # Store as JSON with 24-hour expiration
            await r.setex(
                key,
                timedelta(hours=24),
                metrics.model_dump_json()
            )

            # Also add to time-series list for history
            history_key = f"metrics_history:{metrics.device_id}"
            timestamp = metrics.timestamp.isoformat()
            await r.zadd(
                history_key,
                {metrics.model_dump_json(): metrics.timestamp.timestamp()}
            )

            # Trim history to keep last 24 hours
            cutoff = (datetime.utcnow() - timedelta(hours=24)).timestamp()
            await r.zremrangebyscore(history_key, '-inf', cutoff)

            # Set expiration on history key
            await r.expire(history_key, timedelta(hours=24))

        except Exception as e:
            logger.error(f"Error storing metrics: {e}")

    async def get_cached_metrics(self, device_id: str) -> Optional[DeviceMetrics]:
        """Get cached metrics from Redis"""
        try:
            r = await self._get_redis()
            key = f"metrics:{device_id}"
            data = await r.get(key)

            if data:
                return DeviceMetrics.model_validate_json(data)
            return None

        except Exception as e:
            logger.error(f"Error getting cached metrics: {e}")
            return None

    async def get_metrics_history(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[DeviceMetrics]:
        """Get historical metrics from Redis"""
        try:
            r = await self._get_redis()
            history_key = f"metrics_history:{device_id}"

            # Get metrics within time range
            results = await r.zrangebyscore(
                history_key,
                start_time.timestamp(),
                end_time.timestamp()
            )

            metrics_list = []
            for data in results:
                try:
                    metrics = DeviceMetrics.model_validate_json(data)
                    metrics_list.append(metrics)
                except Exception:
                    continue

            return metrics_list

        except Exception as e:
            logger.error(f"Error getting metrics history: {e}")
            return []

    async def start_collection(self):
        """Start metrics collection background task"""
        if self._running:
            return

        self._running = True
        self._collection_task = asyncio.create_task(self._collection_loop())
        logger.info("Metrics collection started")

    async def stop_collection(self):
        """Stop metrics collection"""
        self._running = False

        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass

        if self._redis:
            await self._redis.close()

        logger.info("Metrics collection stopped")

    async def _collection_loop(self):
        """Background loop for metrics collection"""
        while self._running:
            try:
                # Get all online devices
                devices = await device_service.get_devices()

                for device in devices:
                    if device.status == "online":
                        metrics = await self.collect_device_metrics(device)
                        if metrics:
                            self._metrics_cache[device.id] = metrics
                            await self.store_metrics(metrics)

            except Exception as e:
                logger.error(f"Error in metrics collection loop: {e}")

            await asyncio.sleep(settings.METRICS_COLLECTION_INTERVAL)

    def get_current_metrics(self, device_id: str) -> Optional[DeviceMetrics]:
        """Get current cached metrics for a device"""
        return self._metrics_cache.get(device_id)

    def get_all_current_metrics(self) -> Dict[str, DeviceMetrics]:
        """Get all current cached metrics"""
        return self._metrics_cache.copy()

    def add_alert(self, device_id: str, alert: Any):
        """Add an alert to the cache for a device"""
        if device_id not in self._alerts_cache:
            self._alerts_cache[device_id] = []
        self._alerts_cache[device_id].insert(0, alert)
        # Keep only last 100 alerts per device
        self._alerts_cache[device_id] = self._alerts_cache[device_id][:100]

    def get_device_alerts(self, device_id: str) -> List[Any]:
        """Get cached alerts for a device"""
        return self._alerts_cache.get(device_id, [])


# Global instance
metrics_collector = MetricsCollector()
