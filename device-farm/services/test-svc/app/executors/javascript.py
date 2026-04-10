# JavaScript Test Script Executor
import json
import logging
import os
import subprocess
import tempfile
from typing import Dict, Any, Optional, List

from app.config import settings

logger = logging.getLogger(__name__)


class JavaScriptExecutor:
    """Execute JavaScript test scripts using Node.js"""

    def __init__(self, task_id: str, driver=None):
        self.task_id = task_id
        self.driver = driver
        self.results: List[Dict[str, Any]] = []
        self.screenshots: List[str] = []
        self.logs: List[Dict[str, str]] = []

    def execute(self, content: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute JavaScript test script

        Args:
            content: JavaScript code to execute
            parameters: Test parameters

        Returns:
            Execution result dict
        """
        parameters = parameters or {}

        # Create wrapper script that provides test API
        wrapper_script = self._create_wrapper_script(content, parameters)

        # Write to temporary file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".js",
            delete=False,
        ) as f:
            f.write(wrapper_script)
            script_path = f.name

        try:
            # Execute with Node.js
            result = self._run_node_script(script_path)
            return result
        finally:
            # Clean up
            if os.path.exists(script_path):
                os.unlink(script_path)

    def _create_wrapper_script(self, test_code: str, parameters: Dict[str, Any]) -> str:
        """Create wrapper script with sandboxed test API"""
        # Convert parameters to JSON for injection
        params_json = json.dumps(parameters)

        # Use Node.js VM module to create a sandboxed environment
        # This prevents access to require(), process.env, and other dangerous APIs
        wrapper = f'''
const vm = require('vm');
const {{ performance }} = require('perf_hooks');

// Test context (safe data only)
const context = {{
    taskId: "{self.task_id}",
    parameters: {params_json},
    results: [],
    screenshots: [],
    logs: [],
    passed: 0,
    failed: 0,
    skipped: 0
}};

// Test API functions (sandboxed)
function testPass() {{
    context.passed++;
    console.log(JSON.stringify({{ type: 'pass', message: 'Test passed' }}));
}}

function testFail(message = '') {{
    context.failed++;
    context.results.push({{ status: 'failed', message: message }});
    console.log(JSON.stringify({{ type: 'fail', message: message || 'Test failed' }}));
}}

function testSkip() {{
    context.skipped++;
    console.log(JSON.stringify({{ type: 'skip', message: 'Test skipped' }}));
}}

function log(message, level = 'INFO') {{
    context.logs.push({{ level: level, message: message }});
    console.log(JSON.stringify({{ type: 'log', level: level, message: message }}));
}}

function takeScreenshot() {{
    const screenshotId = `screenshot_${{context.screenshots.length}}`;
    context.screenshots.push(screenshotId);
    console.log(JSON.stringify({{ type: 'screenshot', id: screenshotId }}));
    return screenshotId;
}}

function sleep(ms) {{
    return new Promise(resolve => setTimeout(resolve, ms));
}}

// Simulated driver (same as Python executor)
const driver = {{
    findElement: (selector) => ({{
        click: () => log(`Clicked element: ${{selector}}`),
        sendKeys: (text) => log(`Typed: ${{text}} into ${{selector}}`),
        getText: () => '',
        getAttribute: (name) => ''
    }}),
    findElements: (selector) => [driver.findElement(selector)],
    get: (url) => log(`Navigated to: ${{url}}`),
    back: () => log('Navigated back'),
    quit: () => log('Driver quit')
}};

// Create sandboxed context with limited globals
// This prevents access to require, process, and other Node.js APIs
const sandbox = {{
    // Safe built-in objects
    console: console,
    JSON: JSON,
    Object: Object,
    Array: Array,
    String: String,
    Number: Number,
    Boolean: Boolean,
    Date: Date,
    Math: Math,
    RegExp: RegExp,
    Error: Error,
    TypeError: TypeError,
    ReferenceError: ReferenceError,
    SyntaxError: SyntaxError,
    RangeError: RangeError,
    Promise: Promise,
    Symbol: Symbol,
    Map: Map,
    Set: Set,
    WeakMap: WeakMap,
    WeakSet: WeakSet,
    Proxy: Proxy,
    Reflect: Reflect,

    // Timer functions (safe)
    setTimeout: setTimeout,
    setInterval: setInterval,
    clearTimeout: clearTimeout,
    clearInterval: clearInterval,

    // Test API
    testPass: testPass,
    testFail: testFail,
    testSkip: testSkip,
    log: log,
    takeScreenshot: takeScreenshot,
    sleep: sleep,
    driver: driver,
    params: context.parameters,
    taskId: context.taskId,

    // Constants
    undefined: undefined,
    NaN: NaN,
    Infinity: Infinity,

    // NOT included (dangerous):
    // - require (module loading)
    // - process (system access)
    // - global (global scope)
    // - module, exports (module system)
    // - __dirname, __filename (file system paths)
    // - Buffer (memory access)
}};

// Run test in sandboxed context
async function runTest() {{
    const startTime = performance.now();

    try {{
        // Create sandboxed context
        vm.createContext(sandbox);

        // Execute user code in sandbox
        // NOTE: This uses vm.runInContext which provides isolation from Node.js internals
        // User code cannot access require(), process, or other dangerous APIs
        const wrappedCode = `(async () => {{
            {test_code}
        }})()`;

        await vm.runInContext(wrappedCode, sandbox, {{
            timeout: {settings.APPIUM_TIMEOUT * 1000},  // Convert to milliseconds
            displayErrors: true
        }});

        const duration = (performance.now() - startTime) / 1000;

        // Output final result
        const finalResult = {{
            success: context.failed === 0,
            duration: duration,
            total: context.passed + context.failed + context.skipped,
            passed: context.passed,
            failed: context.failed,
            skipped: context.skipped,
            screenshots: context.screenshots,
            logs: context.logs
        }};

        console.log(JSON.stringify({{ type: 'result', data: finalResult }}));

    }} catch (error) {{
        console.log(JSON.stringify({{
            type: 'error',
            message: error.message,
            stack: error.stack
        }}));
        process.exit(1);
    }}
}}

runTest();
'''
        return wrapper

    def _run_node_script(self, script_path: str) -> Dict[str, Any]:
        """Run Node.js script and parse results"""
        try:
            # Execute Node.js
            result = subprocess.run(
                ["node", script_path],
                capture_output=True,
                text=True,
                timeout=settings.APPIUM_TIMEOUT,
                cwd=tempfile.gettempdir(),
            )

            # Parse output
            output_lines = result.stdout.strip().split("\n") if result.stdout else []

            execution_result = {
                "success": True,
                "duration": 0,
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "screenshots": [],
                "logs": [],
                "errors": [],
            }

            for line in output_lines:
                try:
                    data = json.loads(line)

                    if data.get("type") == "log":
                        execution_result["logs"].append({
                            "level": data.get("level", "INFO"),
                            "message": data.get("message", ""),
                        })

                    elif data.get("type") == "screenshot":
                        execution_result["screenshots"].append(data.get("id"))

                    elif data.get("type") == "result":
                        execution_result.update(data.get("data", {}))

                    elif data.get("type") == "error":
                        execution_result["success"] = False
                        execution_result["errors"].append(data.get("message"))
                except json.JSONDecodeError:
                    # Non-JSON output, add as log
                    execution_result["logs"].append({
                        "level": "INFO",
                        "message": line,
                    })

            # Check for errors
            if result.returncode != 0:
                execution_result["success"] = False
                if result.stderr:
                    execution_result["errors"].append(result.stderr)

            return execution_result

        except subprocess.TimeoutExpired:
            logger.error(f"JavaScript execution timed out for task {self.task_id}")
            return {
                "success": False,
                "error": "Execution timed out",
            }

        except FileNotFoundError:
            logger.error("Node.js not found. Please install Node.js to run JavaScript tests.")
            return {
                "success": False,
                "error": "Node.js not installed",
            }

        except Exception as e:
            logger.error(f"JavaScript execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }


def execute_javascript_script(
    content: str,
    driver,
    parameters: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """
    Execute JavaScript test script

    Args:
        content: JavaScript code
        driver: Appium driver (or simulated)
        parameters: Test parameters
        task_id: Task ID

    Returns:
        Execution result dict
    """
    executor = JavaScriptExecutor(task_id, driver)
    return executor.execute(content, parameters)
