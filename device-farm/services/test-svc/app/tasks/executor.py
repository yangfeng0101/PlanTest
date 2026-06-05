# Test Execution Task
import json
import math
import os
import random
import re
import sys
import tempfile
import traceback
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from celery import shared_task
from celery.utils.log import get_task_logger

from app.tasks.__init__ import celery_app
from app.config import settings
from app.models.models import Task, TaskStatus, ExecutionResult
from app.services.storage import get_storage_service

logger = get_task_logger(__name__)

# Import tasks API for database operations
from app.api import tasks as tasks_api

SDK_VERSION = "1.3.0"

ALLOWED_IMPORTS = {
    "datetime": __import__("datetime"),
    "decimal": __import__("decimal"),
    "json": json,
    "math": math,
    "random": random,
    "re": re,
    "requests": __import__("requests"),
    "time": time,
    "uuid": uuid,
}


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    """Allow scripts to import approved utility modules only."""
    if level != 0:
        raise ImportError("Relative imports are not supported")

    root_name = name.split(".", 1)[0]
    if root_name not in ALLOWED_IMPORTS:
        raise ImportError(f"Import of '{name}' is not allowed")

    return __import__(name, globals, locals, fromlist, level)


class DeviceFarmApp:
    """Small SDK exposed to test scripts for common mobile automation actions."""

    def __init__(self, context: dict):
        self.context = context

    @property
    def driver(self):
        return self.context["driver"]

    def log(self, message: str, level: str = "INFO"):
        log_message(self.context, message, level)

    def version(self) -> str:
        return SDK_VERSION

    def wait(self, seconds: float = 1):
        time.sleep(float(seconds))

    def screenshot(self) -> str:
        return run_async(take_screenshot_async(self.context))

    def activate_app(self, package_name: str):
        raw = _raw_driver(self.driver)
        raw.activate_app(str(package_name))
        log_message(self.context, f"Activated app: {package_name}", "INFO")

    def launch_app(self, package_name: Optional[str] = None):
        if package_name:
            self.activate_app(package_name)
            return

        driver = self.driver
        raw = _raw_driver(driver)
        if hasattr(driver, "launch_app"):
            driver.launch_app()
        elif hasattr(raw, "launch_app"):
            raw.launch_app()
        else:
            raise RuntimeError("launch_app is not supported by this Appium session")
        log_message(self.context, "Launched current app", "INFO")

    def terminate_app(self, package_name: str):
        raw = _raw_driver(self.driver)
        raw.terminate_app(str(package_name))
        log_message(self.context, f"Terminated app: {package_name}", "INFO")

    def close_app(self, package_name: Optional[str] = None):
        if package_name:
            self.terminate_app(package_name)
            return

        driver = self.driver
        raw = _raw_driver(driver)
        if hasattr(driver, "close_app"):
            driver.close_app()
        elif hasattr(raw, "close_app"):
            raw.close_app()
        else:
            raise RuntimeError("close_app is not supported by this Appium session")
        log_message(self.context, "Closed current app", "INFO")

    def restart_app(self, package_name: str, wait_seconds: float = 1):
        self.terminate_app(package_name)
        self.wait(wait_seconds)
        self.activate_app(package_name)

    def back(self):
        raw = _raw_driver(self.driver)
        raw.back()
        log_message(self.context, "Pressed back", "INFO")

    def home(self):
        if self.context.get("platform") == "ios":
            raise RuntimeError("app.home is not supported for iOS v1. Use app.driver APIs if your XCUITest session supports a home button action.")
        self.press_key(3)

    def tap(self, x: int, y: int):
        tap(self.context, x, y)

    def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 500):
        driver = self.context["driver"]
        if hasattr(driver, "swipe"):
            driver.swipe(int(start_x), int(start_y), int(end_x), int(end_y), int(duration))
        else:
            raw = _raw_driver(driver)
            raw.swipe(int(start_x), int(start_y), int(end_x), int(end_y), int(duration))
        log_message(self.context, f"Swiped from ({start_x}, {start_y}) to ({end_x}, {end_y})", "INFO")

    def input_text(self, text: str):
        input_text(self.context, text)

    def clear_text(self, by=None, value: Optional[str] = None, timeout: float = 0):
        if by is not None and value is not None:
            element = self.find(by, value, timeout)
        else:
            element = _raw_driver(self.driver).switch_to.active_element
        element.clear()
        log_message(self.context, "Cleared text", "INFO")
        return element

    def press_key(self, keycode: int):
        press_key(self.context, keycode)

    def source(self) -> str:
        return self.driver.get_page_source()

    def has_text(self, text: str) -> bool:
        return str(text) in self.source()

    def assert_text(self, text: str):
        assert_text(self.context, text)

    def find(self, by, value: str, timeout: float = 0):
        if timeout and timeout > 0:
            deadline = time.time() + float(timeout)
            last_error = None
            while time.time() < deadline:
                try:
                    return self.driver.find_element(by, value)
                except Exception as exc:
                    last_error = exc
                    time.sleep(0.5)
            raise last_error or RuntimeError(f"Element not found: {value}")

        return self.driver.find_element(by, value)

    def find_all(self, by, value: str):
        return self.driver.find_elements(by, value)

    def wait_element(self, by, value: str, timeout: float = 10):
        return self.find(by, value, timeout)

    def exists(self, by, value: str, timeout: float = 0) -> bool:
        try:
            self.find(by, value, timeout)
            return True
        except Exception:
            return False

    def click(self, by, value: str, timeout: float = 0):
        element = self.find(by, value, timeout)
        element.click()
        log_message(self.context, f"Clicked element: {value}", "INFO")
        return element

    def get_text(self, by, value: str, timeout: float = 0) -> str:
        return self.find(by, value, timeout).text

    def click_text(self, text: str, timeout: float = 5):
        from appium.webdriver.common.appiumby import AppiumBy

        quoted = json.dumps(str(text), ensure_ascii=False)
        if self.context.get("platform") == "ios":
            xpath = f"//*[@label={quoted} or @name={quoted} or @value={quoted}]"
        else:
            xpath = f"//*[@text={quoted} or @content-desc={quoted}]"
        return self.click(AppiumBy.XPATH, xpath, timeout)

    def tap_text(self, text: str, timeout: float = 5):
        return self.click_text(text, timeout)

    def wait_text(self, text: str, timeout: float = 10):
        deadline = time.time() + float(timeout)
        while time.time() < deadline:
            if self.has_text(text):
                log_message(self.context, f"Text appeared: {text}", "INFO")
                return True
            time.sleep(0.5)
        raise AssertionError(f"Text not found within {timeout}s: {text}")

    def ai(self, instruction: str, timeout: float = 30):
        return self._run_ai_operation("ai", {"instruction": str(instruction)}, timeout)

    def ai_act(self, instruction: str, timeout: float = 30):
        return self._run_ai_operation("ai_act", {"instruction": str(instruction)}, timeout)

    def ai_locate(self, target: str, timeout: float = 10, deep_locate: bool = False):
        return self._run_ai_operation(
            "ai_locate",
            {"target": str(target), "deep_locate": bool(deep_locate)},
            timeout,
        )

    def ai_tap(self, target: str, timeout: float = 10, deep_locate: bool = False):
        return self._run_ai_operation(
            "ai_tap",
            {"target": str(target), "deep_locate": bool(deep_locate)},
            timeout,
        )

    def ai_input(self, target: str, text: str, clear: bool = True, timeout: float = 10, deep_locate: bool = False):
        return self._run_ai_operation(
            "ai_input",
            {
                "target": str(target),
                "text": str(text),
                "mode": "replace" if clear else "typeOnly",
                "deep_locate": bool(deep_locate),
            },
            timeout,
        )

    def ai_clear(self, target: str, timeout: float = 10, deep_locate: bool = False):
        return self._run_ai_operation(
            "ai_clear",
            {"target": str(target), "deep_locate": bool(deep_locate)},
            timeout,
        )

    def ai_key(self, key: str, target: Optional[str] = None, timeout: float = 10, deep_locate: bool = False):
        return self._run_ai_operation(
            "ai_key",
            {"key": str(key), "target": str(target) if target is not None else None, "deep_locate": bool(deep_locate)},
            timeout,
        )

    def ai_scroll(
        self,
        target: Optional[str] = None,
        direction: str = "down",
        distance: Optional[int] = None,
        scroll_type: str = "singleAction",
        timeout: float = 15,
        deep_locate: bool = False,
    ):
        return self._run_ai_operation(
            "ai_scroll",
            {
                "target": str(target) if target is not None else None,
                "direction": str(direction),
                "distance": distance,
                "scroll_type": str(scroll_type),
                "deep_locate": bool(deep_locate),
            },
            timeout,
        )

    def ai_long_press(self, target: str, duration: Optional[int] = None, timeout: float = 10, deep_locate: bool = False):
        return self._run_ai_operation(
            "ai_long_press",
            {
                "target": str(target),
                "duration": duration,
                "deep_locate": bool(deep_locate),
            },
            timeout,
        )

    def ai_double_tap(self, target: str, timeout: float = 10, deep_locate: bool = False):
        return self._run_ai_operation(
            "ai_double_tap",
            {"target": str(target), "deep_locate": bool(deep_locate)},
            timeout,
        )

    def ai_wait(self, assertion: str, timeout: float = 15, check_interval: float = 3):
        self._run_ai_operation(
            "ai_wait",
            {"assertion": str(assertion), "check_interval_ms": int(float(check_interval) * 1000)},
            timeout,
        )
        return True

    def ai_assert(self, assertion: str, error_message: Optional[str] = None, timeout: float = 10):
        try:
            return self._run_ai_operation(
                "ai_assert",
                {"assertion": str(assertion), "error_message": error_message},
                timeout,
            )
        except Exception as exc:
            raise AssertionError(str(exc)) from exc

    def _run_ai_operation(self, operation: str, payload: dict, timeout: float):
        import httpx

        runner_url = settings.MIDSCENE_RUNNER_URL.rstrip("/")
        if not runner_url:
            error = "Midscene AI runner is not configured. Set MIDSCENE_RUNNER_URL for test-worker."
            log_message(self.context, error, "ERROR")
            raise RuntimeError(error)

        device_id = self.context.get("device_id")
        if not device_id:
            error = "Midscene AI operation requires a bound device_id."
            log_message(self.context, error, "ERROR")
            raise RuntimeError(error)

        timeout_seconds = float(timeout)
        request_body = {
            "task_id": self.context["task_id"],
            "device_id": device_id,
            "platform": self.context.get("platform") or "android",
            "operation": operation,
            "payload": payload,
            "timeout_ms": int(timeout_seconds * 1000),
        }

        log_message(self.context, f"AI operation started: {operation}", "INFO")
        try:
            with httpx.Client(timeout=timeout_seconds + 10) as client:
                response = client.post(f"{runner_url}/api/v1/ai/execute", json=request_body)
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("error") or exc.response.text
            except Exception:
                detail = exc.response.text
            log_message(self.context, f"AI operation failed: {detail}", "ERROR")
            raise RuntimeError(detail) from exc
        except httpx.RequestError as exc:
            error = f"Midscene AI runner request failed: {exc}"
            log_message(self.context, error, "ERROR")
            raise RuntimeError(error) from exc

        if not result.get("success"):
            error = result.get("error") or "Midscene AI operation failed"
            log_message(self.context, f"AI operation failed: {error}", "ERROR")
            raise RuntimeError(error)

        log_message(self.context, f"AI operation completed: {operation}", "INFO")
        return result.get("result")


def assert_true(value, message: str = "Assertion failed"):
    if not value:
        raise AssertionError(message)


def assert_equal(actual, expected, message: Optional[str] = None):
    if actual != expected:
        raise AssertionError(message or f"Expected {expected!r}, got {actual!r}")


def update_task_status(task_id: str, status: TaskStatus, **kwargs):
    """Update task status in database"""
    return tasks_api.update_task_status(task_id, status, **kwargs)


def notify_scheduled_task_finished(task_id: str):
    """Send scheduled-run completion notifications without affecting execution."""
    try:
        from app.services.schedule_notification_service import notify_scheduled_task_finished as notify

        run_async(notify(task_id))
    except Exception as exc:
        logger.warning("Failed to process scheduled task notification for %s: %s", task_id, exc, exc_info=True)


def run_async(coro):
    """Run async helpers on the worker's stable async loop."""
    return tasks_api._run_async(coro)


class DeviceBusyRetry(Exception):
    """Raised when a task should stay pending until the device is free."""


def _task_device_owner(task_id: str) -> str:
    return f"test-svc:{task_id}"


def _is_screen_debug_task(task: Task) -> bool:
    parameters = task.parameters or {}
    return bool(parameters.get("screen_debug"))


async def acquire_task_device(task: Task) -> bool:
    """Acquire the device for task execution.

    Returns True when this worker acquired a device-svc lease and must release it.
    Returns False for screen-page debug tasks that intentionally share an active
    screen session lease.
    """
    if not task.device_id:
        return False

    device = await tasks_api._get_device(task.device_id)
    device_status = str(device.get("status") or "").lower()

    if device_status == "online":
        await tasks_api._occupy_device(task.device_id, _task_device_owner(task.id))
        return True

    if device_status == "busy" and _is_screen_debug_task(task):
        occupied_by = device.get("occupied_by") or device.get("occupiedBy") or "unknown"
        logger.info(
            "Task %s is sharing active screen session for device %s occupied by %s",
            task.id,
            task.device_id,
            occupied_by,
        )
        return False

    if device_status == "busy":
        raise DeviceBusyRetry(f"Device {task.device_id} is busy; task remains queued")

    raise RuntimeError(f"Device {task.device_id} is offline or unavailable (status: {device_status or 'unknown'})")


@celery_app.task(bind=True, name="execute_test_task", max_retries=None)
def execute_test_task(self, task_id: str):
    """Execute a test task

    Args:
        task_id: The ID of the task to execute
    """
    logger.info(f"Starting execution of task {task_id}")

    # Get task details from database
    task = tasks_api.get_task_by_id(task_id)
    if not task:
        logger.error(f"Task {task_id} not found")
        return {"success": False, "error": "Task not found"}

    if task.status == TaskStatus.CANCELLED:
        logger.info(f"Task {task_id} was cancelled before execution")
        notify_scheduled_task_finished(task_id)
        return {"success": False, "error": "Task cancelled"}

    device_lease_acquired = False
    notification_due = False
    try:
        device_lease_acquired = run_async(acquire_task_device(task))
    except DeviceBusyRetry as exc:
        if self.request.retries == 0 or self.request.retries % 12 == 0:
            run_async(send_log(task_id, "INFO", f"{exc}; retrying shortly"))
        raise self.retry(exc=exc, countdown=5)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 409:
            retry_error = DeviceBusyRetry(f"Device {task.device_id} is busy; task remains queued")
            if self.request.retries == 0 or self.request.retries % 12 == 0:
                run_async(send_log(task_id, "INFO", f"{retry_error}; retrying shortly"))
            raise self.retry(exc=retry_error, countdown=5)

        error_msg = str(exc)
        logger.error(f"Task {task_id} failed before execution: {error_msg}")
        update_task_status(
            task_id,
            TaskStatus.FAILED,
            finished_at=datetime.utcnow(),
            error=error_msg,
        )
        notify_scheduled_task_finished(task_id)
        run_async(send_log(task_id, "ERROR", f"Task failed before execution: {error_msg}"))
        return {"success": False, "error": error_msg}

    device_id_for_release = task.device_id
    task = tasks_api.get_task_by_id(task_id)
    if not task:
        logger.error(f"Task {task_id} not found after acquiring device")
        if device_lease_acquired and device_id_for_release:
            try:
                run_async(release_task_device(device_id_for_release, task_id))
            except Exception as release_error:
                logger.warning(f"Failed to release device lease for missing task {task_id}: {release_error}")
        notify_scheduled_task_finished(task_id)
        return {"success": False, "error": "Task not found"}

    if task.status == TaskStatus.CANCELLED:
        logger.info(f"Task {task_id} was cancelled before execution after acquiring device")
        if device_lease_acquired:
            try:
                run_async(release_task_device(task.device_id, task_id))
            except Exception as release_error:
                logger.warning(f"Failed to release device {task.device_id}: {release_error}")
        notify_scheduled_task_finished(task_id)
        return {"success": False, "error": "Task cancelled"}

    # Update status to running
    update_task_status(
        task_id,
        TaskStatus.RUNNING,
        started_at=datetime.utcnow()
    )

    # Send log
    run_async(send_log(task_id, "INFO", f"Task {task_id} started"))

    task_finished = False
    try:
        # Load script
        script = load_script(task.script_id)
        if not script:
            raise Exception(f"Script {task.script_id} not found")

        run_async(send_log(task_id, "INFO", f"Loaded script: {script.name}"))

        # Initialize Appium driver. Real execution must fail loudly if Appium is unavailable.
        run_async(send_log(task_id, "INFO", "Initializing Appium driver..."))
        driver = initialize_driver(task)

        try:
            # Execute the test script
            run_async(send_log(task_id, "INFO", "Executing test script..."))
            result = execute_script(
                script,
                driver,
                task.parameters,
                task_id,
                task.device_id,
                task.device_platform.value,
            )

            final_status = TaskStatus.SUCCESS if result.success else TaskStatus.FAILED

            if result.success:
                run_async(send_log(
                    task_id,
                    "INFO",
                    f"Task completed successfully. Passed: {result.passed_tests}, Failed: {result.failed_tests}"
                ))
            else:
                run_async(send_log(
                    task_id,
                    "ERROR",
                    f"Task completed with failures. Passed: {result.passed_tests}, Failed: {result.failed_tests}"
                ))

            update_task_status(
                task_id,
                final_status,
                finished_at=datetime.utcnow(),
                result=result.model_dump(mode="json"),
                error="; ".join(result.errors) if result.errors else None,
            )
            task_finished = True
            notification_due = True

            return {
                "success": result.success,
                "result": result.model_dump(mode="json")
            }

        finally:
            # Cleanup driver
            if driver:
                cleanup_driver(driver)

    except Exception as e:
        error_msg = str(e)
        error_trace = traceback.format_exc()

        logger.error(f"Task {task_id} failed: {error_msg}")
        logger.error(error_trace)

        # Update task with error
        update_task_status(
            task_id,
            TaskStatus.FAILED,
            finished_at=datetime.utcnow(),
            error=error_msg
        )
        notification_due = True

        run_async(send_log(task_id, "ERROR", f"Task failed: {error_msg}"))
        task_finished = True

        return {
            "success": False,
            "error": error_msg,
            "traceback": error_trace
        }
    finally:
        if task.device_id and device_lease_acquired:
            try:
                run_async(release_task_device(task.device_id, task_id))
                if not task_finished:
                    run_async(send_log(task_id, "INFO", "Device released"))
            except Exception as release_error:
                logger.warning(f"Failed to release device {task.device_id}: {release_error}")
        if notification_due:
            notify_scheduled_task_finished(task_id)


def load_script(script_id: str):
    """Load script from database"""
    from app.api import scripts as scripts_api
    return scripts_api._get_script_db(script_id)


def initialize_driver(task: Task):
    """Initialize Appium driver for the device"""
    from app.drivers.appium import AppiumDriver

    platform = task.device_platform.value
    driver = AppiumDriver(
        platform=platform,
        device_id=task.device_id,
        capabilities=task.device_capabilities
    )
    if platform == "ios":
        diagnostics = driver.sanitized_diagnostics()
        caps = diagnostics.get("capabilities", {})
        run_async(send_log(
            task.id,
            "INFO",
            "iOS Appium session initializing: "
            f"host={diagnostics.get('appium_host')}, "
            f"udid={diagnostics.get('udid')}, "
            f"automationName={diagnostics.get('automation_name')}",
        ))
        run_async(send_log(
            task.id,
            "DEBUG",
            f"iOS diagnostics: {json.dumps({'capabilities': caps, 'ios_signing': diagnostics.get('ios_signing')}, ensure_ascii=False, sort_keys=True)}",
        ))
    try:
        driver.initialize()
    except Exception as exc:
        if platform == "ios":
            run_async(send_log(task.id, "ERROR", f"iOS Appium session failed: {exc}"))
        raise
    if platform == "ios":
        run_async(send_log(task.id, "INFO", f"iOS Appium session ready: session_id={driver.session_id}"))
    return driver


def execute_script(
    script,
    driver,
    parameters: dict,
    task_id: str,
    device_id: Optional[str] = None,
    platform: str = "android",
) -> ExecutionResult:
    """Execute the test script"""
    start_time = datetime.utcnow()

    # Create execution context
    context = {
        "driver": driver,
        "device_id": device_id,
        "parameters": parameters,
        "task_id": task_id,
        "platform": platform,
        "logs": [],
        "screenshots": [],
        "videos": [],
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
        "debug_trace_lines": bool(parameters.get("debug_trace_lines")),
    }

    try:
        if script.script_type.value == "python":
            execute_python_script(script.content, context)
        else:
            raise ValueError(f"Unsupported script type: {script.script_type}")

    except Exception as e:
        context["errors"].append(str(e))
        context["failed"] += 1
        log_message(context, f"Script failed: {e}", "ERROR")

    # Calculate duration
    duration = (datetime.utcnow() - start_time).total_seconds()

    return ExecutionResult(
        task_id=task_id,
        success=len(context["errors"]) == 0 and context["failed"] == 0,
        duration=duration,
        total_tests=context["passed"] + context["failed"] + context["skipped"],
        passed_tests=context["passed"],
        failed_tests=context["failed"],
        skipped_tests=context["skipped"],
        errors=context["errors"],
        screenshots=context["screenshots"],
        videos=context["videos"],
        logs=context["logs"],
    )


# Safe builtins for restricted Python execution
# Only includes functions that cannot be used for malicious purposes
SAFE_BUILTINS = {
    # Safe type constructors
    'bool': bool,
    'int': int,
    'float': float,
    'str': str,
    'list': list,
    'dict': dict,
    'tuple': tuple,
    'set': set,
    'frozenset': frozenset,
    'bytes': bytes,
    'bytearray': bytearray,

    # Safe built-in functions
    'abs': abs,
    'all': all,
    'any': any,
    'bin': bin,
    'chr': chr,
    'divmod': divmod,
    'enumerate': enumerate,
    'filter': filter,
    'format': format,
    'hex': hex,
    'isinstance': isinstance,
    'issubclass': issubclass,
    'iter': iter,
    'len': len,
    'map': map,
    'max': max,
    'min': min,
    'next': next,
    'oct': oct,
    'ord': ord,
    'pow': pow,
    'print': print,
    'range': range,
    'reversed': reversed,
    'round': round,
    'slice': slice,
    'sorted': sorted,
    'sum': sum,
    'zip': zip,

    # Safe type checking
    'type': type,
    'callable': callable,
    'hasattr': hasattr,
    'getattr': getattr,
    'setattr': setattr,
    'delattr': delattr,

    # Safe constants
    'True': True,
    'False': False,
    'None': None,

    # Safe exceptions (for error handling)
    'Exception': Exception,
    'ValueError': ValueError,
    'TypeError': TypeError,
    'KeyError': KeyError,
    'IndexError': IndexError,
    'AttributeError': AttributeError,
    'RuntimeError': RuntimeError,
    'AssertionError': AssertionError,
    'StopIteration': StopIteration,

    # Math functions (safe)
    'complex': complex,
    '__import__': safe_import,

    # Removed dangerous functions:
    # - open (file access)
    # - exec, eval, compile (code execution)
    # - unrestricted __import__/import (module loading)
    # - globals, locals, vars (introspection)
    # - dir (introspection)
    # - input (user input)
    # - memoryview (memory access)
    # - object, property, staticmethod, classmethod, super (can be used for exploits)
    # - help (introspection)
    # - breakpoint (debugger)
    # - ascii, repr (potential information leakage)
}


def execute_python_script(content: str, context: dict):
    """Execute Python test script in a restricted sandbox"""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False
    ) as f:
        f.write(content)
        temp_path = f.name

    try:
        # Prepare execution namespace with restricted builtins
        # This prevents code injection by limiting available functions
        from appium.webdriver.common.appiumby import AppiumBy
        app = DeviceFarmApp(context)

        namespace = {
            "__builtins__": SAFE_BUILTINS,
            "driver": context["driver"],
            "params": context["parameters"],
            "task_id": context["task_id"],
            "app": app,
            "AppiumBy": AppiumBy,
            "Decimal": Decimal,
            "date": date,
            "datetime": datetime,
            "timedelta": timedelta,
            "test_pass": lambda: test_pass(context),
            "test_fail": lambda msg="": test_fail(context, msg),
            "test_skip": lambda: test_skip(context),
            "assert_true": assert_true,
            "assert_equal": assert_equal,
            "take_screenshot": lambda: run_async(take_screenshot_async(context)),
            "screenshot": lambda: run_async(take_screenshot_async(context)),
            "wait": lambda seconds=1: time.sleep(float(seconds)),
            "swipe": lambda start_x, start_y, end_x, end_y, duration=500: app.swipe(start_x, start_y, end_x, end_y, duration),
            "tap": lambda x, y: tap(context, x, y),
            "input_text": lambda text: input_text(context, text),
            "press_key": lambda keycode: press_key(context, keycode),
            "assert_text": lambda text: assert_text(context, text),
            "log": lambda msg, level="INFO": log_message(context, msg, level),
        }

        # Execute the script in restricted mode
        previous_trace = sys.gettrace()
        trace_lines = context.get("debug_trace_lines")
        trace_state = {
            "last_seen_line": None,
            "last_emitted_line": None,
            "last_emit_at": 0.0,
        }
        trace_emit_interval_seconds = 0.2

        def emit_script_line(line_number: int, force: bool = False):
            now = time.monotonic()
            if not force:
                if line_number == trace_state["last_emitted_line"]:
                    return
                if now - trace_state["last_emit_at"] < trace_emit_interval_seconds:
                    return

            trace_state["last_emitted_line"] = line_number
            trace_state["last_emit_at"] = now
            run_async(send_log(
                context["task_id"],
                "DEBUG",
                f"Executing line {line_number}",
                event_type="script_line",
                line_number=line_number,
            ))

        def trace_script_lines(frame, event, arg):
            if event == "line" and frame.f_code.co_filename == temp_path:
                line_number = frame.f_lineno
                trace_state["last_seen_line"] = line_number
                emit_script_line(line_number)
            return trace_script_lines

        try:
            if trace_lines:
                sys.settrace(trace_script_lines)
            with open(temp_path, "r") as f:
                exec(compile(f.read(), temp_path, "exec"), namespace)
        finally:
            if trace_lines:
                if trace_state["last_seen_line"] != trace_state["last_emitted_line"]:
                    emit_script_line(trace_state["last_seen_line"], force=True)
                sys.settrace(previous_trace)

    finally:
        os.unlink(temp_path)


def cleanup_driver(driver):
    """Cleanup Appium driver"""
    try:
        if hasattr(driver, "quit"):
            driver.quit()
    except Exception as e:
        logger.error(f"Error cleaning up driver: {e}")


# Helper functions for test scripts
def test_pass(context: dict):
    context["passed"] += 1


def test_fail(context: dict, message: str = ""):
    context["failed"] += 1
    if message:
        context["errors"].append(message)


def test_skip(context: dict):
    context["skipped"] += 1


def take_screenshot(context: dict) -> str:
    """Take a screenshot and save it to MinIO"""
    return run_async(take_screenshot_async(context))


async def take_screenshot_async(context: dict) -> str:
    """Take a screenshot and save it to MinIO (async)"""
    try:
        storage = get_storage_service()
        task_id = context["task_id"]
        index = len(context["screenshots"])

        # Take actual screenshot from driver if available
        driver = context.get("driver")
        screenshot_data = None

        if driver and hasattr(driver, "get_screenshot_as_png"):
            screenshot_data = driver.get_screenshot_as_png()
        elif driver and hasattr(driver, "take_screenshot"):
            screenshot_data = driver.take_screenshot()
        elif driver and getattr(driver, "driver", None) and hasattr(driver.driver, "get_screenshot_as_png"):
            screenshot_data = driver.driver.get_screenshot_as_png()
        else:
            raise RuntimeError("Driver does not support screenshots")

        # Upload to MinIO
        object_name, url = await storage.upload_screenshot_bytes(
            task_id=task_id,
            data=screenshot_data,
            index=index,
        )

        context["screenshots"].append(url)
        from app.models.models import TaskLogEntry

        context["logs"].append(TaskLogEntry(level="DEBUG", message=f"Screenshot saved: {object_name}"))
        await send_log(task_id, "DEBUG", f"Screenshot saved: {object_name}")
        return url

    except Exception as e:
        logger.error(f"Failed to take screenshot: {e}")
        context["errors"].append(f"Screenshot failed: {e}")
        raise


def log_message(context: dict, message: str, level: str = "INFO"):
    """Add a log message"""
    from app.models.models import TaskLogEntry
    entry = TaskLogEntry(level=level, message=message)
    context["logs"].append(entry)
    run_async(send_log(context["task_id"], level, message))


async def send_log(
    task_id: str,
    level: str,
    message: str,
    event_type: Optional[str] = None,
    line_number: Optional[int] = None,
):
    """Persist log and broadcast it via WebSocket."""
    from app.api.tasks import save_task_log
    from app.database import get_db_session

    async with get_db_session() as db:
        await save_task_log(db, task_id, level, message, event_type=event_type, line_number=line_number)


async def release_task_device(device_id: str, task_id: str):
    await tasks_api._release_device_if_owned(device_id, _task_device_owner(task_id))


def _raw_driver(driver):
    return getattr(driver, "driver", driver)


def tap(context: dict, x: int, y: int):
    driver = context["driver"]
    if hasattr(driver, "tap"):
        driver.tap(int(x), int(y))
    else:
        raw = _raw_driver(driver)
        raw.tap([(int(x), int(y))])
    log_message(context, f"Tapped at ({x}, {y})", "INFO")


def input_text(context: dict, text: str):
    raw = _raw_driver(context["driver"])
    active = raw.switch_to.active_element
    active.send_keys(str(text))
    log_message(context, "Input text sent", "INFO")


def press_key(context: dict, keycode: int):
    raw = _raw_driver(context["driver"])
    if hasattr(raw, "press_keycode"):
        raw.press_keycode(int(keycode))
    else:
        raise RuntimeError("press_key is only supported by Android Appium sessions")
    log_message(context, f"Pressed keycode {keycode}", "INFO")


def assert_text(context: dict, text: str):
    page_source = context["driver"].get_page_source()
    if str(text) not in page_source:
        raise AssertionError(f"Text not found: {text}")
    log_message(context, f"Text found: {text}", "INFO")
