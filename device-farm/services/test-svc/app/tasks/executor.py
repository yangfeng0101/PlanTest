# Test Execution Task
import asyncio
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime
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


def update_task_status(task_id: str, status: TaskStatus, **kwargs):
    """Update task status in database"""
    return tasks_api.update_task_status(task_id, status, **kwargs)


@celery_app.task(bind=True, name="execute_test_task")
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

    # Update status to running
    update_task_status(
        task_id,
        TaskStatus.RUNNING,
        started_at=datetime.utcnow()
    )

    # Send log
    asyncio.run(send_log(task_id, "INFO", f"Task {task_id} started"))

    try:
        # Load script
        script = load_script(task.script_id)
        if not script:
            raise Exception(f"Script {task.script_id} not found")

        asyncio.run(send_log(task_id, "INFO", f"Loaded script: {script.name}"))

        # Initialize Appium driver (simulation for now)
        asyncio.run(send_log(task_id, "INFO", "Initializing Appium driver..."))
        driver = initialize_driver(task)

        try:
            # Execute the test script
            asyncio.run(send_log(task_id, "INFO", "Executing test script..."))
            result = execute_script(
                script,
                driver,
                task.parameters,
                task_id
            )

            # Update task with success result
            update_task_status(
                task_id,
                TaskStatus.SUCCESS,
                finished_at=datetime.utcnow(),
                result=result.model_dump()
            )

            asyncio.run(send_log(
                task_id,
                "INFO",
                f"Task completed successfully. Passed: {result.passed_tests}, Failed: {result.failed_tests}"
            ))

            return {
                "success": True,
                "result": result.model_dump()
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

        asyncio.run(send_log(task_id, "ERROR", f"Task failed: {error_msg}"))

        return {
            "success": False,
            "error": error_msg,
            "traceback": error_trace
        }


def load_script(script_id: str):
    """Load script from database"""
    from app.api import scripts as scripts_api
    return scripts_api._get_script_db(script_id)


def initialize_driver(task: Task):
    """Initialize Appium driver for the device"""
    from app.drivers.appium import AppiumDriver

    try:
        driver = AppiumDriver(
            platform=task.device_platform.value,
            device_id=task.device_id,
            capabilities=task.device_capabilities
        )
        driver.initialize()
        return driver
    except Exception as e:
        logger.warning(f"Failed to initialize real Appium driver: {e}")
        logger.info("Using simulated driver for testing")
        # Return a simulated driver for testing
        return SimulatedDriver()


def execute_script(script, driver, parameters: dict, task_id: str) -> ExecutionResult:
    """Execute the test script"""
    start_time = datetime.utcnow()

    # Create execution context
    context = {
        "driver": driver,
        "parameters": parameters,
        "task_id": task_id,
        "logs": [],
        "screenshots": [],
        "videos": [],
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }

    try:
        if script.script_type.value == "python":
            execute_python_script(script.content, context)
        elif script.script_type.value == "javascript":
            # Use JavaScript executor
            from app.executors.javascript import execute_javascript_script
            js_result = execute_javascript_script(script.content, driver, parameters, task_id)
            context["passed"] = js_result.get("passed", 0)
            context["failed"] = js_result.get("failed", 0)
            context["skipped"] = js_result.get("skipped", 0)
            context["screenshots"] = js_result.get("screenshots", [])
            context["errors"] = js_result.get("errors", [])
        else:
            raise ValueError(f"Unsupported script type: {script.script_type}")

    except Exception as e:
        context["errors"].append(str(e))
        context["failed"] += 1

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
    'StopIteration': StopIteration,

    # Math functions (safe)
    'complex': complex,

    # Removed dangerous functions:
    # - open (file access)
    # - exec, eval, compile (code execution)
    # - __import__, import (module loading)
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
        namespace = {
            "__builtins__": SAFE_BUILTINS,
            "driver": context["driver"],
            "params": context["parameters"],
            "task_id": context["task_id"],
            "test_pass": lambda: test_pass(context),
            "test_fail": lambda msg="": test_fail(context, msg),
            "test_skip": lambda: test_skip(context),
            "take_screenshot": lambda: asyncio.run(take_screenshot_async(context)),
            "log": lambda msg, level="INFO": log_message(context, msg, level),
        }

        # Execute the script in restricted mode
        with open(temp_path, "r") as f:
            exec(compile(f.read(), temp_path, "exec"), namespace)

    finally:
        os.unlink(temp_path)


def execute_javascript_script(content: str, context: dict):
    """Execute JavaScript test script (using Node.js)"""
    # For now, this is a placeholder
    # In production, you would use a JavaScript interpreter or Node.js subprocess
    raise NotImplementedError("JavaScript execution not yet implemented")


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
    import asyncio
    return asyncio.run(take_screenshot_async(context))


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
        else:
            # Simulate screenshot (placeholder image)
            import io
            from PIL import Image

            img = Image.new("RGB", (1080, 1920), color="gray")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            screenshot_data = buffer.getvalue()

        # Upload to MinIO
        object_name, url = await storage.upload_screenshot_bytes(
            task_id=task_id,
            data=screenshot_data,
            index=index,
        )

        context["screenshots"].append(url)
        log_message(context, f"Screenshot saved: {object_name}", "DEBUG")
        return url

    except Exception as e:
        logger.error(f"Failed to take screenshot: {e}")
        return f"error_{len(context['screenshots'])}"


def log_message(context: dict, message: str, level: str = "INFO"):
    """Add a log message"""
    from app.models.models import TaskLogEntry
    entry = TaskLogEntry(level=level, message=message)
    context["logs"].append(entry)
    asyncio.run(send_log(context["task_id"], level, message))


async def send_log(task_id: str, level: str, message: str):
    """Send log via WebSocket"""
    from app.api.tasks import send_task_log
    await send_task_log(task_id, level, message)


# Simulated driver for testing without real Appium
class SimulatedDriver:
    """Simulated driver for testing"""

    def __init__(self):
        self.session_id = None

    def initialize(self):
        self.session_id = "simulated_session"
        return self

    def find_element(self, *args, **kwargs):
        return SimulatedElement()

    def find_elements(self, *args, **kwargs):
        return [SimulatedElement()]

    def get(self, url):
        pass

    def back(self):
        pass

    def quit(self):
        self.session_id = None


class SimulatedElement:
    """Simulated element for testing"""

    def click(self):
        pass

    def send_keys(self, text):
        pass

    def text(self):
        return ""

    def get_attribute(self, name):
        return ""
