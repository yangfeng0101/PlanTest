"""Regression tests for the script-sandbox whitelist single source of truth.

Background
----------
Before this module existed, two independent whitelists lived in:
  - app.api.scripts.ALLOWED_SCRIPT_IMPORTS (static validation)
  - app.tasks.executor.ALLOWED_IMPORTS      (runtime enforcement)

When a module (e.g. `requests`) was added to the runtime list but not the
static list, user scripts that imported the new module would pass at
execution time but fail validation in the UI with "不允许导入模块:requests".

These tests pin the two lists together and guard against a repeat.
"""

import os
import sys
import unittest
from pathlib import Path

os.environ["DEBUG"] = "false"

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT.parent))


class ScriptSandboxWhitelistTest(unittest.TestCase):
    def test_static_and_runtime_whitelists_stay_in_sync(self):
        """The two whitelists must never drift apart."""
        from app.tasks.script_sandbox import assert_consistent

        # Should not raise — both lists are aligned by construction.
        assert_consistent()

    def test_requests_is_allowed_in_static_validation(self):
        """Regression for the '不允许导入模块:requests' bug.

        Before the fix, scripts importing `requests` failed static
        validation even though the runtime allowed it.
        """
        from app.api.scripts import _validate_script_content

        script_with_requests = """
import requests

resp = requests.get("https://example.com")
app.log(f"status={resp.status_code}")
test_pass()
"""
        result = _validate_script_content(script_with_requests)
        import_errors = [e for e in result.errors if e.startswith("不允许导入模块")]
        self.assertEqual(
            import_errors,
            [],
            f"Static validation must accept `requests`, but got: {import_errors}",
        )
        self.assertTrue(result.valid, f"Script should validate, errors={result.errors}")

    def test_static_validation_still_rejects_unknown_modules(self):
        """Sanity check: the whitelist is not a free-for-all."""
        from app.api.scripts import _validate_script_content

        script_with_os = """
import os

os.path.exists("/tmp")
test_pass()
"""
        result = _validate_script_content(script_with_os)
        self.assertFalse(result.valid)
        self.assertTrue(
            any("不允许导入模块" in e and "os" in e for e in result.errors),
            f"Should reject `os`, got errors={result.errors}",
        )

    def test_runtime_safe_import_uses_the_same_whitelist(self):
        """The runtime safe_import must read from the same module the
        static validator reads, not its own private copy."""
        from app.tasks.executor import safe_import
        from app.tasks.script_sandbox import ALLOWED_SCRIPT_IMPORTS

        # If safe_import allowed a module that ALLOWED_SCRIPT_IMPORTS
        # does not, the lists would have drifted.
        for module_name in ALLOWED_SCRIPT_IMPORTS:
            try:
                safe_import(module_name)
            except ImportError as exc:
                self.fail(
                    f"safe_import rejects '{module_name}' which is in "
                    f"ALLOWED_SCRIPT_IMPORTS: {exc}"
                )

        # And the reverse: a module not in the whitelist must be rejected.
        with self.assertRaises(ImportError):
            safe_import("os")


if __name__ == "__main__":
    unittest.main()
