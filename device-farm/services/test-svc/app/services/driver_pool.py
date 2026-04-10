# Appium Driver Connection Pool
import asyncio
import time
from typing import Optional, Dict, Any
from collections import OrderedDict
from threading import Lock
import logging

from appium import webdriver
from appium.options.common.base import AppiumOptions

from app.config import settings
from app.drivers.appium import AppiumDriver

logger = logging.getLogger(__name__)


class DriverPoolConfig:
    """Configuration for driver pool"""
    def __init__(
        self,
        max_drivers: int = 50,
        idle_timeout: int = 1800,  # 30 minutes
        max_wait_time: int = 60,  # Max wait time to acquire a driver
        health_check_interval: int = 60,  # Health check every 60 seconds
    ):
        self.max_drivers = max_drivers
        self.idle_timeout = idle_timeout
        self.max_wait_time = max_wait_time
        self.health_check_interval = health_check_interval


class PooledDriver:
    """Wrapper for a pooled Appium driver"""
    def __init__(self, driver: AppiumDriver, device_id: str, platform: str):
        self.driver = driver
        self.device_id = device_id
        self.platform = platform
        self.last_used = time.time()
        self.in_use = False
        self.session_id = driver.session_id

    def touch(self):
        """Update last used timestamp"""
        self.last_used = time.time()

    def is_expired(self, idle_timeout: int) -> bool:
        """Check if driver has been idle too long"""
        return not self.in_use and (time.time() - self.last_used) > idle_timeout

    def is_healthy(self) -> bool:
        """Check if driver session is still active"""
        try:
            if self.driver.driver is None:
                return False
            # Simple health check - get page source
            self.driver.driver.page_source
            return True
        except Exception:
            return False


class DriverPool:
    """
    Connection pool for Appium drivers.

    Manages driver instances per device, recycling connections for efficiency.
    Thread-safe and supports concurrent access.
    """

    def __init__(self, config: Optional[DriverPoolConfig] = None):
        self.config = config or DriverPoolConfig()
        self._pool: OrderedDict[str, PooledDriver] = OrderedDict()
        self._lock = Lock()
        self._semaphore = asyncio.Semaphore(self.config.max_drivers)
        self._health_check_task: Optional[asyncio.Task] = None

    async def start_health_check(self):
        """Start background health check task"""
        if self._health_check_task is None:
            self._health_check_task = asyncio.create_task(self._health_check_loop())

    async def stop_health_check(self):
        """Stop background health check task"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

    async def _health_check_loop(self):
        """Periodic health check to clean up expired drivers"""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._cleanup_expired_drivers()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    async def _cleanup_expired_drivers(self):
        """Remove expired drivers from pool"""
        with self._lock:
            expired_keys = []
            for key, pooled_driver in self._pool.items():
                if pooled_driver.is_expired(self.config.idle_timeout):
                    expired_keys.append(key)

            for key in expired_keys:
                pooled_driver = self._pool.pop(key)
                try:
                    pooled_driver.driver.quit()
                    logger.info(f"Removed expired driver for device {pooled_driver.device_id}")
                except Exception as e:
                    logger.warning(f"Error quitting expired driver: {e}")

    async def acquire(
        self,
        device_id: str,
        platform: str,
        capabilities: Optional[Dict[str, Any]] = None,
    ) -> AppiumDriver:
        """
        Acquire a driver for the specified device.

        Args:
            device_id: Device identifier (UDID for iOS, serial for Android)
            platform: "android" or "ios"
            capabilities: Optional additional capabilities

        Returns:
            AppiumDriver instance ready for use
        """
        pool_key = f"{platform}:{device_id}"

        # Check if we have an available driver in pool
        with self._lock:
            if pool_key in self._pool:
                pooled_driver = self._pool[pool_key]
                if not pooled_driver.in_use and pooled_driver.is_healthy():
                    pooled_driver.in_use = True
                    pooled_driver.touch()
                    logger.info(f"Reusing pooled driver for {pool_key}")
                    return pooled_driver.driver

        # Need to create new driver
        async with self._semaphore:
            # Double-check after acquiring semaphore
            with self._lock:
                if pool_key in self._pool:
                    pooled_driver = self._pool[pool_key]
                    if not pooled_driver.in_use and pooled_driver.is_healthy():
                        pooled_driver.in_use = True
                        pooled_driver.touch()
                        return pooled_driver.driver

            # Create new driver
            driver = await self._create_driver(device_id, platform, capabilities)

            with self._lock:
                # Remove old driver if exists
                if pool_key in self._pool:
                    old_pooled = self._pool.pop(pool_key)
                    try:
                        old_pooled.driver.quit()
                    except Exception:
                        pass

                # Add to pool
                pooled_driver = PooledDriver(driver, device_id, platform)
                pooled_driver.in_use = True
                self._pool[pool_key] = pooled_driver

                # Evict oldest if pool is full
                if len(self._pool) > self.config.max_drivers:
                    oldest_key = next(iter(self._pool))
                    oldest_pooled = self._pool.pop(oldest_key)
                    try:
                        oldest_pooled.driver.quit()
                        logger.info(f"Evicted oldest driver for {oldest_key}")
                    except Exception:
                        pass

            return driver

    async def _create_driver(
        self,
        device_id: str,
        platform: str,
        capabilities: Optional[Dict[str, Any]] = None,
    ) -> AppiumDriver:
        """Create a new Appium driver"""
        driver = AppiumDriver(
            platform=platform,
            device_id=device_id,
            capabilities=capabilities,
        )

        # Initialize in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, driver.initialize)

        logger.info(f"Created new Appium driver for {platform}:{device_id}")
        return driver

    async def release(self, device_id: str, platform: str):
        """
        Release a driver back to the pool.

        Args:
            device_id: Device identifier
            platform: "android" or "ios"
        """
        pool_key = f"{platform}:{device_id}"

        with self._lock:
            if pool_key in self._pool:
                pooled_driver = self._pool[pool_key]
                pooled_driver.in_use = False
                pooled_driver.touch()
                logger.info(f"Released driver for {pool_key}")

    async def remove(self, device_id: str, platform: str):
        """
        Remove a driver from the pool entirely.

        Args:
            device_id: Device identifier
            platform: "android" or "ios"
        """
        pool_key = f"{platform}:{device_id}"

        with self._lock:
            if pool_key in self._pool:
                pooled_driver = self._pool.pop(pool_key)
                try:
                    pooled_driver.driver.quit()
                    logger.info(f"Removed driver for {pool_key}")
                except Exception as e:
                    logger.warning(f"Error quitting driver: {e}")

    async def clear(self):
        """Clear all drivers from pool"""
        with self._lock:
            for key, pooled_driver in self._pool.items():
                try:
                    pooled_driver.driver.quit()
                except Exception:
                    pass
            self._pool.clear()
            logger.info("Cleared all drivers from pool")

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics"""
        with self._lock:
            total = len(self._pool)
            in_use = sum(1 for pd in self._pool.values() if pd.in_use)
            available = total - in_use

            by_platform = {"android": 0, "ios": 0}
            for key in self._pool.keys():
                platform = key.split(":")[0]
                if platform in by_platform:
                    by_platform[platform] += 1

            return {
                "total_drivers": total,
                "in_use": in_use,
                "available": available,
                "max_drivers": self.config.max_drivers,
                "by_platform": by_platform,
            }

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_health_check()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop_health_check()
        await self.clear()


# Global driver pool instance
_driver_pool: Optional[DriverPool] = None


def get_driver_pool() -> DriverPool:
    """Get the global driver pool instance"""
    global _driver_pool
    if _driver_pool is None:
        _driver_pool = DriverPool()
    return _driver_pool


async def init_driver_pool():
    """Initialize the global driver pool"""
    global _driver_pool
    _driver_pool = DriverPool()
    await _driver_pool.start_health_check()
    return _driver_pool


async def shutdown_driver_pool():
    """Shutdown the global driver pool"""
    global _driver_pool
    if _driver_pool:
        await _driver_pool.stop_health_check()
        await _driver_pool.clear()
        _driver_pool = None
